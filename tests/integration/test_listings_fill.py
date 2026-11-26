"""End to end: from the sample filings and the sample symbol lists to listings.

The four commands run one after the other in a temporary folder, as on a
rebuild (ADR 0026): ``db migrate``, ``universe load``, ``symbols load`` and
``listings fill``. The filings are the made-up ones of ``tests/fixtures/nport``
and the lists the ones of ``tests/fixtures/listings``, whose README says what
each security is there for. No request is made: every file is already there.

Author: Emre Tezel
"""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.db import Database
from pyvalue.listings import ListingsError, fill_listings
from pyvalue.listings.decisions import read_listing_decisions
from pyvalue.universe import FUNDS

pytestmark = pytest.mark.integration

# What the six filled securities get: ISIN, exchange, ticker, currency, and
# the provider's symbol.
_FILLED: list[tuple[str, str, str, str, str]] = [
    ("AU00000M0018", "XASX", "MUP", "AUD", "MUP"),
    ("DE00000T0019", "XETR", "THT", "EUR", "THT"),
    ("GB00000D0016", "XLON", "DLT", "GBP", "DLT"),
    ("US00000A0014", "XNYS", "ALPH", "USD", "ALPH"),
    ("US00000A0022", "XNYS", "ALPH.PA", "USD", "ALPH-PA"),
    ("US00000B0013", "XNAS", "BETA", "USD", "BETA"),
]


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    nport_samples: Path,
    vanguard_samples: Path,
    listings_samples: Path,
) -> Path:
    """Return a temporary working folder as it is before the listing fill of a rebuild.

    The filings, Vanguard's files and the symbol lists are where the commands
    look for them, and the first three commands have run.
    """
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    for folder in ("sec", "vanguard", "eodhd"):
        (data / folder).mkdir(parents=True)
    for fund in FUNDS:
        shutil.copyfile(nport_samples / f"{fund.code}.xml", data / "sec" / fund.filing_file_name)
        shutil.copyfile(
            vanguard_samples / f"{fund.code}.json", data / "vanguard" / f"{fund.code}.json"
        )
    for sample in sorted(listings_samples.glob("symbols_*.json")):
        shutil.copyfile(sample, data / "eodhd" / sample.name)
    assert main(["db", "migrate"]) == 0
    assert main(["universe", "load"]) == 0
    assert main(["symbols", "load"]) == 0
    return tmp_path


def _listings(database: Database) -> list[tuple[str, str, str, str, str]]:
    """Return every listing with its security's ISIN and the provider's symbol, by ISIN."""
    with database.unit_of_work() as work:
        isin_of = {each.instrument_id: each.isin for each in work.instruments.all()}
        symbol_of = {
            each.listing_id: each.provider_symbol
            for each in work.provider_listings.of_provider("eodhd")
        }
        return sorted(
            (
                isin_of[each.instrument_id],
                each.mic,
                each.ticker,
                each.currency,
                symbol_of[each.listing_id],
            )
            for each in work.listings.all()
        )


def test_the_sample_securities_get_exactly_the_expected_listings(
    workspace: Path, listings_samples: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Six are filled, and the report is the expected file, byte for byte."""
    capsys.readouterr()

    assert main(["listings", "fill"]) == 0

    assert _listings(Database(workspace / "data" / "pyvalue.db")) == _FILLED
    report = workspace / "data" / "listings" / "cases_for_agent.csv"
    assert (
        report.read_bytes() == (listings_samples / "expected" / "cases_for_agent.csv").read_bytes()
    )
    printed = capsys.readouterr().out
    assert "Securities: 16\n" in printed
    assert (
        "Filled by the rule: 6 (3 with ISIN and ticker agreeing, 3 by ISIN with no fund ticker)\n"
        in printed
    )
    assert "Market not served: 2 (HK 1, JP 1)\n" in printed
    assert "Waiting for a symbol list: 1 (TW 1)\n" in printed
    assert "  Exchange codes without a stored list: TWO\n" in printed
    assert "For the agent: 7, listed in data/listings/cases_for_agent.csv\n" in printed


def test_a_second_fill_changes_nothing_and_writes_the_same_report(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproducible: the same database and decisions give the same listings and bytes."""
    database = Database(workspace / "data" / "pyvalue.db")
    report = workspace / "data" / "listings" / "cases_for_agent.csv"
    assert main(["listings", "fill"]) == 0
    listings, first = _listings(database), report.read_bytes()
    capsys.readouterr()

    assert main(["listings", "fill"]) == 0

    assert _listings(database) == listings
    assert report.read_bytes() == first
    printed = capsys.readouterr().out
    assert "Already had a listing: 6\n" in printed
    assert "Filled by the rule: 0 (" in printed
    assert "For the agent: 7, " in printed


def test_the_listing_fill_changes_no_other_table(workspace: Path) -> None:
    """The universe and the symbol lists are read, never written."""
    database = Database(workspace / "data" / "pyvalue.db")

    def others() -> tuple[int, ...]:
        with database.unit_of_work() as work:
            return (
                len(work.companies.all()),
                len(work.instruments.all()),
                len(work.holdings.all()),
                len(work.exchanges.all()),
                len(work.provider_symbols.of_provider("eodhd")),
            )

    before = others()

    assert main(["listings", "fill"]) == 0

    assert others() == before == (14, 16, 20, 61, 18)


def test_the_sample_decisions_fill_one_security_and_settle_another(
    workspace: Path, listings_samples: Path
) -> None:
    """Lambda gets the line the decision names; Epsilon's B share gets none."""
    database = Database(workspace / "data" / "pyvalue.db")
    decisions = read_listing_decisions(listings_samples / "decisions" / "listing.csv")

    outcome = fill_listings(database, decisions, workspace / "data" / "listings")

    assert _listings(database) == sorted(
        [*_FILLED, ("MYL0000L0012", "XKLS", "5555", "MYR", "5555")]
    )
    assert [fill.security.isin for fill in outcome.plan.filled_by_decision] == ["MYL0000L0012"]
    assert [each.isin for each in outcome.plan.decided_none] == ["FR00000E0021"]
    assert sorted(case.security.isin for case in outcome.plan.cases) == [
        "FR00000E0013",
        "KR70000K0000",
        "US00000B0021",
        "US00000H0017",
        "US00000O0018",
    ]


def test_a_decision_that_arrives_after_the_listing_stops_the_fill(
    workspace: Path, listings_samples: Path
) -> None:
    """Alpha was filled by the rule; a later decision of none needs a rebuild (ADR 0026)."""
    database = Database(workspace / "data" / "pyvalue.db")
    assert main(["listings", "fill"]) == 0
    _, none = read_listing_decisions(listings_samples / "decisions" / "listing.csv")

    with pytest.raises(ListingsError, match="US00000A0014.*has to be rebuilt"):
        fill_listings(
            database, [replace(none, isin="US00000A0014")], workspace / "data" / "listings"
        )

    assert _listings(database) == _FILLED
