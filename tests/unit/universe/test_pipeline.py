"""Tests for ``pyvalue.universe.pipeline``: obtaining the filings around a load.

What the load does with the lines is tested in ``test_load.py`` and, end to
end, in ``tests/integration/test_universe_load.py``. These tests are about the
files: which are downloaded, which are reused, and what is asked of the SEC.

Author: Emre Tezel
"""

from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from pyvalue.db import Database
from pyvalue.universe import (
    FUNDS,
    Exclusion,
    FilingError,
    NameDecision,
    OrdinaryShare,
    Sponsor,
    SponsorAdapter,
    SponsorFileError,
    UniverseError,
    VanguardAdapter,
    load_universe,
)

_CONTACT: str = "Sample Person sample@example.org"


def _never_asked() -> str:
    """Stand in for the settings; fails the test if the contact string is requested."""
    pytest.fail("the contact string was requested although nothing had to be downloaded")


def _never_fetched(url: str, user_agent: str) -> bytes:
    """Stand in for the network; fails the test if anything is fetched."""
    pytest.fail(f"{url} was fetched although the filing was already there")


def test_filings_that_are_there_are_used_without_asking_for_anything(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """ADR 0009: a later run needs neither the network nor the contact line."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert outcome.downloaded == ()
    assert outcome.result.lines_read == 31
    assert outcome.output.lines_not_loaded == tmp_path / "universe" / "lines_not_loaded.csv"
    assert outcome.output.cases_for_agent.is_file()


def test_the_decisions_shipped_with_the_package_are_applied_by_default(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """ADR 0010, 0012, 0013 and 0015: a caller that passes none gets the package's own.

    The shipped files are about real securities, so on the sample filings they
    are read and match nothing. A caller's own decisions replace them.
    """
    shipped = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )
    named = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        name_decisions=[
            NameDecision(
                isin="JP300000I006",
                name="Iota KK",
                decided_on=date(2026, 11, 21),
                evidence="Made up for a test",
            )
        ],
        adapters=adapters,
    )

    assert (shipped.result.lei_decisions_used, shipped.result.name_decisions_used) == (0, 0)
    assert (shipped.result.exclusions_used, shipped.result.ordinary_shares_used) == (0, 0)
    assert (named.result.name_decisions_used, named.result.companies_renamed) == (1, 1)


def test_a_callers_exclusions_keep_a_security_out(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """ADR 0013: the exclusions reach the load, and an existing database is refused."""
    exclusions = [
        Exclusion(
            isin="US00000H0017",
            company="Eta Holdings Ltd",
            decided_on=date(2026, 11, 21),
            evidence="Made up for a test",
        )
    ]

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        exclusions=exclusions,
        adapters=adapters,
    )

    assert (outcome.result.exclusions_used, outcome.result.companies) == (1, 13)
    # The line is reported in the file of lines that were not loaded.
    assert "VXUS,5,excluded_by_decision," in outcome.output.lines_not_loaded.read_text(
        encoding="utf-8"
    )


def test_an_exclusion_stops_the_run_on_a_database_that_holds_the_security(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Nothing is written, and the output files of the earlier run are left as they were."""
    first = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )
    before = first.output.lines_not_loaded.read_bytes()
    exclusions = [
        Exclusion(
            isin="US00000H0017",
            company="Eta Holdings Ltd",
            decided_on=date(2026, 11, 21),
            evidence="Made up for a test",
        )
    ]

    with pytest.raises(UniverseError, match="has to be rebuilt"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "universe",
            _never_asked,
            _never_fetched,
            exclusions=exclusions,
            adapters=adapters,
        )

    assert first.output.lines_not_loaded.read_bytes() == before


def test_a_callers_swap_reads_a_receipt_as_its_ordinary_share(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """ADR 0015: the swaps reach the load, and the receipt's lines are loaded under the share."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        ordinary_shares=[
            OrdinaryShare(
                isin="US00000O0018",
                ordinary_isin="SG00000O0017",
                company="Omicron Ltd",
                decided_on=date(2026, 11, 21),
                evidence="Made up for a test",
            )
        ],
        adapters=adapters,
    )

    result = outcome.result
    assert (result.ordinary_shares_used, result.companies, result.instruments) == (1, 14, 16)
    # One receipt fewer: the swapped line is an ordinary line.
    assert (result.receipts_recognised, result.receipts_kept) == (4, 1)


def test_missing_filings_are_downloaded_once_and_kept(
    database: Database,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Each pinned filing is fetched at its own address, with the contact string."""
    filings_dir = tmp_path / "sec"
    by_url = {fund.filing_url: nport_samples / f"{fund.code}.xml" for fund in FUNDS}
    calls: list[tuple[str, str]] = []

    def fetch(url: str, user_agent: str) -> bytes:
        calls.append((url, user_agent))
        return by_url[url].read_bytes()

    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", lambda: _CONTACT, fetch, adapters=adapters
    )

    assert outcome.downloaded == FUNDS
    assert calls == [(fund.filing_url, _CONTACT) for fund in FUNDS]
    assert sorted(path.name for path in filings_dir.iterdir()) == sorted(
        fund.filing_file_name for fund in FUNDS
    )

    # The second run finds both and fetches nothing.
    again = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert again.downloaded == ()
    assert again.result.instruments_added == 0


def test_only_the_missing_filing_is_downloaded(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """A folder that holds one of the two costs one request."""
    missing = FUNDS[1]
    (filings_dir / missing.filing_file_name).unlink()
    calls: list[str] = []

    def fetch(url: str, user_agent: str) -> bytes:
        calls.append(url)
        return (nport_samples / "VXUS.xml").read_bytes()

    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", lambda: _CONTACT, fetch, adapters=adapters
    )

    assert outcome.downloaded == (missing,)
    assert calls == [missing.filing_url]


def test_a_failed_download_stops_the_run_before_the_database_is_touched(
    database: Database, tmp_path: Path, adapters: Mapping[Sponsor, SponsorAdapter]
) -> None:
    """No filing, no load: the tables stay empty and no output is written."""

    def fetch(url: str, user_agent: str) -> bytes:
        raise FilingError(f"cannot download {url}: no network")

    with pytest.raises(FilingError, match="no network"):
        load_universe(
            database,
            tmp_path / "sec",
            tmp_path / "universe",
            lambda: _CONTACT,
            fetch,
            adapters=adapters,
        )

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
    assert not (tmp_path / "universe").exists()


def test_a_wrong_file_under_a_pinned_name_stops_the_run(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """A file that is there is trusted only as far as its own content confirms the pin."""
    vti, vxus = FUNDS
    (filings_dir / vti.filing_file_name).write_bytes(
        (filings_dir / vxus.filing_file_name).read_bytes()
    )

    with pytest.raises(FilingError, match="is not the pinned VTI filing"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "universe",
            _never_asked,
            _never_fetched,
            adapters=adapters,
        )

    with database.unit_of_work() as work:
        assert work.companies.all() == ()


# --- The sponsor's own documents (ADR 0016) ----------------------------------------------------


def test_missing_sponsor_files_are_downloaded_once_and_kept(
    database: Database, filings_dir: Path, vanguard_samples: Path, tmp_path: Path
) -> None:
    """Each fund's file is fetched from Vanguard under its own id, and found the next time."""
    folder = tmp_path / "vanguard"
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        code = "VTI" if "/0970/" in url else "VXUS"
        return (vanguard_samples / f"{code}.json").read_bytes()

    adapters = {Sponsor.VANGUARD: VanguardAdapter(folder, fetch)}

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert outcome.sponsor_files_downloaded == FUNDS
    assert outcome.downloaded == ()
    assert [url.split("/vmf/api/")[1].split("/")[0] for url in requests] == ["0970", "3369"]
    assert sorted(path.name for path in folder.iterdir()) == ["VTI.json", "VXUS.json"]

    # The second run finds both and fetches nothing.
    again = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert again.sponsor_files_downloaded == ()
    assert len(requests) == 2


def test_the_contact_string_goes_to_the_sec_and_never_to_the_sponsor(
    database: Database, nport_samples: Path, vanguard_samples: Path, tmp_path: Path
) -> None:
    """A run that downloads everything: the contact travels with the filings only."""
    sec_calls: list[tuple[str, str]] = []
    sponsor_calls: list[str] = []

    def fetch_filing(url: str, user_agent: str) -> bytes:
        sec_calls.append((url, user_agent))
        code = next(fund.code for fund in FUNDS if fund.filing_url == url)
        return (nport_samples / f"{code}.xml").read_bytes()

    def fetch_sponsor_file(url: str) -> bytes:
        sponsor_calls.append(url)
        code = "VTI" if "/0970/" in url else "VXUS"
        return (vanguard_samples / f"{code}.json").read_bytes()

    load_universe(
        database,
        tmp_path / "sec",
        tmp_path / "universe",
        lambda: _CONTACT,
        fetch_filing,
        adapters={Sponsor.VANGUARD: VanguardAdapter(tmp_path / "vanguard", fetch_sponsor_file)},
    )

    assert [(url.split("/")[2], user_agent) for url, user_agent in sec_calls] == [
        ("www.sec.gov", _CONTACT),
        ("www.sec.gov", _CONTACT),
    ]
    assert len(sponsor_calls) == 2
    assert all(url.startswith("https://investor.vanguard.com/") for url in sponsor_calls)
    assert all(_CONTACT not in url for url in sponsor_calls)


def test_a_failed_sponsor_download_stops_the_run_before_the_database_is_touched(
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """No sponsor file, no load: there is no fallback to lines without tickers."""

    def fetch(url: str) -> bytes:
        raise SponsorFileError(f"cannot download {url}: no network")

    adapters = {Sponsor.VANGUARD: VanguardAdapter(tmp_path / "vanguard", fetch)}

    with pytest.raises(SponsorFileError, match="no network"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "universe",
            _never_asked,
            _never_fetched,
            adapters=adapters,
        )

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
    assert not (tmp_path / "universe").exists()
    assert not (tmp_path / "vanguard").exists()


def test_a_sponsor_file_that_is_not_one_stops_the_run(
    database: Database, filings_dir: Path, vanguard_dir: Path, tmp_path: Path
) -> None:
    """A damaged file under the expected name is named, and nothing is loaded."""
    (vanguard_dir / "VXUS.json").write_text("<html></html>", encoding="utf-8")

    def never_fetched(url: str) -> bytes:
        pytest.fail(f"{url} was fetched")

    with pytest.raises(SponsorFileError, match="VXUS.json is not a Vanguard holdings file"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "universe",
            _never_asked,
            _never_fetched,
            adapters={Sponsor.VANGUARD: VanguardAdapter(vanguard_dir, never_fetched)},
        )

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
    assert not (tmp_path / "universe").exists()


def test_a_fund_whose_sponsor_has_no_adapter_stops_the_run_before_any_download(
    database: Database, tmp_path: Path
) -> None:
    """Asked first: a run that cannot finish should not start fetching."""
    with pytest.raises(UniverseError, match="there is no adapter for the sponsor of VTI"):
        load_universe(
            database,
            tmp_path / "sec",
            tmp_path / "universe",
            _never_asked,
            _never_fetched,
            adapters={},
        )

    assert not (tmp_path / "sec").exists()


def test_a_receipt_only_the_sponsors_file_names_is_recognised_from_file_to_database(
    database: Database, filings_dir: Path, vanguard_dir: Path, tmp_path: Path
) -> None:
    """ADR 0020, end to end: the name in Vanguard's file keeps a second security out."""
    # In the sample, VTI line 2 is another security of Alpha Corp, whose own
    # share is line 1. Calling it an ADR in Vanguard's file makes it a receipt.
    path = vanguard_dir / "VTI.json"
    text = path.read_text(encoding="utf-8")
    assert text.count("Alpha Corp. Preferred Series A") == 1
    path.write_text(
        text.replace("Alpha Corp. Preferred Series A", "Alpha Corp. ADR"), encoding="utf-8"
    )

    def never_fetched(url: str) -> bytes:
        pytest.fail(f"{url} was fetched")

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters={Sponsor.VANGUARD: VanguardAdapter(vanguard_dir, never_fetched)},
    )

    result = outcome.result
    # One instrument fewer than the 16 of the unchanged sample, and one receipt more.
    assert (result.companies, result.instruments) == (14, 15)
    assert (result.receipts_recognised, result.receipts_not_loaded) == (6, 4)
    with database.unit_of_work() as work:
        assert "US00000A0022" not in {instrument.isin for instrument in work.instruments.all()}
        (row,) = [row for row in work.holdings.all() if row.isin == "US00000A0022"]
    assert (row.instrument_id, row.not_loaded_reason) == (None, "receipt_company_already_loaded")
