"""The universe load end to end, on the checked-in sample filings.

Three small made-up filings (``tests/fixtures/nport``, described line by line
in its README) go through everything the command does except the download:
reading, sorting, placing, and writing the output. The expected rows and the
expected output files were worked out by hand from the rules of ADR 0006.

Author: Emre Tezel
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

from pyvalue.db import Company, Database, Instrument, migrate
from pyvalue.universe import Sponsor, SponsorAdapter, UniverseError, load_universe
from pyvalue.universe.exclusions import read_exclusions
from pyvalue.universe.lei_decisions import read_lei_decisions
from pyvalue.universe.name_decisions import read_name_decisions
from pyvalue.universe.ordinary_shares import read_ordinary_shares

pytestmark = pytest.mark.integration

_ALPHA: str = "549300ALPHA000000003"
_DELTA: str = "549300DELTA000000010"
_EPSILON: str = "549300EPSLN000000037"
_ZETA: str = "549300ZETA0000000008"
_THETA: str = "549300THETA000000051"
_KAPPA: str = "549300KAPPA000000078"
_NU: str = "549300NU000000000098"
_THETA_DECIDED: str = "549300THET2000000069"
_IOTA_DECIDED: str = "549300SIGMA000000049"

_EXPECTED_COMPANIES: tuple[Company, ...] = (
    Company(1, "ALPHA CORP", _ALPHA),
    Company(2, "BETA INC", None),
    Company(3, "DELTA PLC", _DELTA),
    # Loaded without an identifier from VXUS line 2; line 12 filled it in.
    Company(4, "EPSILON SA", _EPSILON),
    Company(5, "ZETA LTD", _ZETA),
    # VXUS line 14 names another identifier for the same ISIN: the first answer stays.
    Company(6, "THETA AG", _THETA),
    # VXUS line 15 supplies an identifier company 3 already has: it is not filled in.
    Company(7, "IOTA KK", None),
    Company(8, "LAMBDA BHD", None),
    # The same name as company 4, which by then is found by identifier only.
    Company(9, "Epsilon SA", None),
    Company(10, "Kappa Co Ltd", _KAPPA),
    Company(11, "Mu Property Trust", None),
    Company(12, "Nu Corp", _NU),
    # The two receipts whose company has no other line come after all ordinary lines.
    Company(13, "ETA HOLDINGS LTD", None),
    Company(14, "Omicron Ltd", None),
)

_EXPECTED_INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument(1, 1, "US00000A0014"),
    Instrument(2, 1, "US00000A0022"),
    Instrument(3, 2, "US00000B0013"),
    Instrument(4, 2, "US00000B0021"),
    Instrument(5, 3, "GB00000D0016"),
    Instrument(6, 4, "FR00000E0013"),
    Instrument(7, 5, "KYG0000Z0015"),
    Instrument(8, 6, "DE00000T0019"),
    Instrument(9, 7, "JP300000I006"),
    Instrument(10, 8, "MYL0000L0012"),
    Instrument(11, 9, "FR00000E0021"),
    Instrument(12, 10, "KR70000K0000"),
    Instrument(13, 11, "AU00000M0018"),
    Instrument(14, 12, "TW00000N0013"),
    Instrument(15, 13, "US00000H0017"),
    Instrument(16, 14, "US00000O0018"),
)


def _never_asked() -> str:
    """Fail the test if the contact string is requested: every filing is already there."""
    pytest.fail("the contact string was requested")


def _never_fetched(url: str, user_agent: str) -> bytes:
    """Fail the test if anything is fetched: every filing is already there."""
    pytest.fail(f"{url} was fetched")


def _tables(database: Database) -> tuple[tuple[Company, ...], tuple[Instrument, ...]]:
    """Read both tables in one unit of work."""
    with database.unit_of_work() as work:
        return work.companies.all(), work.instruments.all()


def test_the_sample_filings_give_exactly_the_expected_universe(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Every company and instrument, with the ids the order of loading gives them."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES, _EXPECTED_INSTRUMENTS)
    result = outcome.result
    assert result.lines_read == 31
    assert result.securities == 19
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        5,
        2,
        3,
    )
    assert (result.companies_added, result.instruments_added) == (14, 16)
    assert (result.joined_by_lei, result.joined_by_name, result.leis_filled) == (1, 1, 1)
    assert (result.companies, result.instruments) == (14, 16)
    assert (len(result.not_loaded), len(result.agent_cases)) == (11, 2)


def test_the_output_files_are_byte_identical_to_the_expected_ones(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Reproducibility: fixed filings give fixed files, down to the last byte."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    expected = nport_samples / "expected"
    assert (
        outcome.output.lines_not_loaded.read_bytes()
        == (expected / "lines_not_loaded.csv").read_bytes()
    )
    assert (
        outcome.output.cases_for_agent.read_bytes()
        == (expected / "cases_for_agent.csv").read_bytes()
    )


def test_every_line_of_the_filings_is_loaded_or_listed(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Nothing is left behind: 31 lines are 11 listed ones plus 20 that reached an instrument."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    result = outcome.result
    # 16 lines added an instrument; 4 met an ISIN that was already one (VXUS lines 11, 12, 14, 15).
    assert result.lines_read - len(result.not_loaded) == result.instruments_added + 4


def test_a_second_run_changes_nothing_and_writes_the_same_files(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """ADR 0009: running the load again is harmless, and its output is the same."""
    first = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )
    first_files = (
        first.output.lines_not_loaded.read_bytes(),
        first.output.cases_for_agent.read_bytes(),
    )

    second = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES, _EXPECTED_INSTRUMENTS)
    assert (second.result.companies_added, second.result.instruments_added) == (0, 0)
    assert second.result.leis_filled == 0
    assert (
        second.output.lines_not_loaded.read_bytes(),
        second.output.cases_for_agent.read_bytes(),
    ) == first_files


# --- With the sample decisions (ADR 0010) ------------------------------------------------

# What the two sample decisions change: Theta carries the identifier VXUS line 14 files,
# and Iota, which had none, carries its own.
_EXPECTED_COMPANIES_AFTER_DECISIONS: tuple[Company, ...] = tuple(
    {6: Company(6, "THETA AG", _THETA_DECIDED), 7: Company(7, "IOTA KK", _IOTA_DECIDED)}.get(
        company.company_id, company
    )
    for company in _EXPECTED_COMPANIES
)

_CASES_HEADER: bytes = (
    b"fund,line,reason,isin,issuer_name,line_lei,company_id,company_name,company_lei,"
    b"lei_owner_company_id,lei_owner_company_name\n"
)


def test_the_shipped_decisions_concern_none_of_the_sample_securities(
    database: Database,
    filings_dir: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """By default the load applies the package's own file, which is about real securities."""
    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        adapters=adapters,
    )

    assert outcome.result.lei_decisions_used == 0
    assert outcome.result.name_decisions_used == 0
    assert outcome.result.exclusions_used == 0
    assert outcome.result.ordinary_shares_used == 0
    assert len(outcome.result.agent_cases) == 2


def test_the_sample_decisions_settle_both_cases(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """A database built with the decisions has the decided identifiers and no open case."""
    decisions = read_lei_decisions(nport_samples / "decisions" / "lei.csv")

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        decisions,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES_AFTER_DECISIONS, _EXPECTED_INSTRUMENTS)
    result = outcome.result
    assert (result.lei_decisions_used, result.leis_corrected) == (2, 0)
    assert result.agent_cases == ()
    assert outcome.output.cases_for_agent.read_bytes() == _CASES_HEADER
    # The lines that are not loaded have nothing to do with the decisions.
    assert (
        outcome.output.lines_not_loaded.read_bytes()
        == (nport_samples / "expected" / "lines_not_loaded.csv").read_bytes()
    )


def test_decisions_applied_later_give_the_database_a_rebuild_would_give(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Corrected in place or built from scratch, the rows are the same."""
    decisions = read_lei_decisions(nport_samples / "decisions" / "lei.csv")
    # In place: loaded before the decisions existed, as the real database was.
    load_universe(
        database,
        filings_dir,
        tmp_path / "first",
        _never_asked,
        _never_fetched,
        (),
        adapters=adapters,
    )
    corrected = load_universe(
        database,
        filings_dir,
        tmp_path / "second",
        _never_asked,
        _never_fetched,
        decisions,
        adapters=adapters,
    )
    # From scratch: a second database that sees the decisions from the start.
    migrate(tmp_path / "scratch.db")
    scratch = Database(tmp_path / "scratch.db")
    load_universe(
        scratch,
        filings_dir,
        tmp_path / "third",
        _never_asked,
        _never_fetched,
        decisions,
        adapters=adapters,
    )

    assert _tables(database) == _tables(scratch)
    assert _tables(database) == (_EXPECTED_COMPANIES_AFTER_DECISIONS, _EXPECTED_INSTRUMENTS)
    # One identifier was replaced (Theta) and one given for the first time (Iota).
    assert (corrected.result.leis_corrected, corrected.result.leis_filled) == (1, 1)
    assert corrected.result.agent_cases == ()
    assert corrected.output.cases_for_agent.read_bytes() == _CASES_HEADER


# --- With the sample name decision (ADR 0012) --------------------------------------------

# What the sample name decision changes: Iota is called as VXUS line 15 spells it.
_EXPECTED_COMPANIES_AFTER_NAMING: tuple[Company, ...] = tuple(
    Company(7, "Iota KK", None) if company.company_id == 7 else company
    for company in _EXPECTED_COMPANIES
)


def test_the_sample_name_decision_names_the_company(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """A database built with the decision stores the decided name from the start."""
    names = read_name_decisions(nport_samples / "decisions" / "name.csv")

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        (),
        names,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES_AFTER_NAMING, _EXPECTED_INSTRUMENTS)
    # The company was added under the decided name, so nothing had to be renamed.
    assert (outcome.result.name_decisions_used, outcome.result.companies_renamed) == (1, 0)
    # A name decides nothing about identifiers: both cases are still open.
    assert len(outcome.result.agent_cases) == 2
    assert (
        outcome.output.lines_not_loaded.read_bytes()
        == (nport_samples / "expected" / "lines_not_loaded.csv").read_bytes()
    )


def test_a_name_decided_later_gives_the_database_a_rebuild_would_give(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """Renamed in place or built from scratch, with both kinds of decision, the rows agree."""
    leis = read_lei_decisions(nport_samples / "decisions" / "lei.csv")
    names = read_name_decisions(nport_samples / "decisions" / "name.csv")
    # In place: loaded before any decision existed.
    load_universe(
        database,
        filings_dir,
        tmp_path / "first",
        _never_asked,
        _never_fetched,
        (),
        (),
        adapters=adapters,
    )
    renamed = load_universe(
        database,
        filings_dir,
        tmp_path / "second",
        _never_asked,
        _never_fetched,
        leis,
        names,
        adapters=adapters,
    )
    again = load_universe(
        database,
        filings_dir,
        tmp_path / "third",
        _never_asked,
        _never_fetched,
        leis,
        names,
        adapters=adapters,
    )
    # From scratch: a second database that sees the decisions from the start.
    migrate(tmp_path / "scratch.db")
    scratch = Database(tmp_path / "scratch.db")
    load_universe(
        scratch,
        filings_dir,
        tmp_path / "fourth",
        _never_asked,
        _never_fetched,
        leis,
        names,
        adapters=adapters,
    )

    expected = tuple(
        Company(7, "Iota KK", _IOTA_DECIDED) if company.company_id == 7 else company
        for company in _EXPECTED_COMPANIES_AFTER_DECISIONS
    )
    assert _tables(database) == _tables(scratch) == (expected, _EXPECTED_INSTRUMENTS)
    assert (renamed.result.name_decisions_used, renamed.result.companies_renamed) == (1, 1)
    # The second run finds the name already there.
    assert (again.result.name_decisions_used, again.result.companies_renamed) == (1, 0)


# --- With the sample exclusion (ADR 0013) ------------------------------------------------

# What the sample exclusion changes: Eta Holdings, whose only line is the excluded
# receipt, is not loaded, so Omicron takes the next free ids.
_EXPECTED_COMPANIES_WITHOUT_ETA: tuple[Company, ...] = (
    *_EXPECTED_COMPANIES[:12],
    Company(13, "Omicron Ltd", None),
)
_EXPECTED_INSTRUMENTS_WITHOUT_ETA: tuple[Instrument, ...] = (
    *_EXPECTED_INSTRUMENTS[:14],
    Instrument(15, 13, "US00000O0018"),
)
_EXCLUDED_LINE: str = (
    "VXUS,5,excluded_by_decision,ETA HOLDINGS LTD,ETA HOLDINGS LTD SPONSORED ADR,US00000H0017,,EC,"
)


def test_the_sample_exclusion_keeps_the_security_out(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """A database built with the exclusion never holds the security or its company."""
    exclusions = read_exclusions(nport_samples / "decisions" / "excluded.csv")

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        (),
        (),
        exclusions,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES_WITHOUT_ETA, _EXPECTED_INSTRUMENTS_WITHOUT_ETA)
    result = outcome.result
    assert (result.exclusions_used, result.securities) == (1, 18)
    # One receipt fewer is recognised, and one fewer is kept as a company's only line.
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        4,
        1,
        3,
    )
    # The file of lines not loaded has the excluded line, in the order of the
    # filings, and is otherwise as without the exclusion.
    expected = (
        (nport_samples / "expected" / "lines_not_loaded.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    written = outcome.output.lines_not_loaded.read_text(encoding="utf-8").splitlines()
    assert _EXCLUDED_LINE in written
    assert [line for line in written if line != _EXCLUDED_LINE] == expected
    assert written.index(_EXCLUDED_LINE) == written.index(expected[4]) + 1


def test_an_exclusion_added_later_is_refused_until_the_database_is_rebuilt(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """The load never deletes: the old database is left as it is, a new one is right."""
    exclusions = read_exclusions(nport_samples / "decisions" / "excluded.csv")
    load_universe(
        database,
        filings_dir,
        tmp_path / "first",
        _never_asked,
        _never_fetched,
        (),
        (),
        adapters=adapters,
    )

    with pytest.raises(UniverseError, match="US00000H0017"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "second",
            _never_asked,
            _never_fetched,
            (),
            (),
            exclusions,
            adapters=adapters,
        )

    assert _tables(database) == (_EXPECTED_COMPANIES, _EXPECTED_INSTRUMENTS)
    # The rebuild: a new database that sees the exclusion from the start.
    migrate(tmp_path / "rebuilt.db")
    rebuilt = Database(tmp_path / "rebuilt.db")
    load_universe(
        rebuilt,
        filings_dir,
        tmp_path / "third",
        _never_asked,
        _never_fetched,
        (),
        (),
        exclusions,
        adapters=adapters,
    )
    assert _tables(rebuilt) == (_EXPECTED_COMPANIES_WITHOUT_ETA, _EXPECTED_INSTRUMENTS_WITHOUT_ETA)


# --- With the sample swap (ADR 0015) -----------------------------------------------------

# What the sample swap changes: Omicron's receipt line is read as its ordinary
# share. As an ordinary line it is placed in step 4, before the receipts, so
# Omicron comes before Eta Holdings, whose only line is still a receipt.
_EXPECTED_COMPANIES_WITH_SWAP: tuple[Company, ...] = (
    *_EXPECTED_COMPANIES[:12],
    Company(13, "Omicron Ltd", None),
    Company(14, "ETA HOLDINGS LTD", None),
)
_EXPECTED_INSTRUMENTS_WITH_SWAP: tuple[Instrument, ...] = (
    *_EXPECTED_INSTRUMENTS[:14],
    Instrument(15, 13, "SG00000O0017"),
    Instrument(16, 14, "US00000H0017"),
)


def test_the_sample_swap_loads_the_receipt_as_its_ordinary_share(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """The company is the one the filing names; its instrument is the ordinary share."""
    swaps = read_ordinary_shares(nport_samples / "decisions" / "ordinary_share.csv")

    outcome = load_universe(
        database,
        filings_dir,
        tmp_path / "universe",
        _never_asked,
        _never_fetched,
        (),
        (),
        (),
        swaps,
        adapters=adapters,
    )

    assert _tables(database) == (_EXPECTED_COMPANIES_WITH_SWAP, _EXPECTED_INSTRUMENTS_WITH_SWAP)
    result = outcome.result
    assert (result.ordinary_shares_used, result.securities) == (1, 19)
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        4,
        1,
        3,
    )
    # The swapped line is loaded, so the file of lines not loaded is unchanged.
    assert (
        outcome.output.lines_not_loaded.read_bytes()
        == (nport_samples / "expected" / "lines_not_loaded.csv").read_bytes()
    )


def test_a_swap_added_later_is_refused_until_the_database_is_rebuilt(
    database: Database,
    filings_dir: Path,
    nport_samples: Path,
    tmp_path: Path,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> None:
    """The load never deletes the receipt it loaded before: the old database is left as it is."""
    swaps = read_ordinary_shares(nport_samples / "decisions" / "ordinary_share.csv")
    load_universe(
        database,
        filings_dir,
        tmp_path / "first",
        _never_asked,
        _never_fetched,
        (),
        (),
        adapters=adapters,
    )

    with pytest.raises(UniverseError, match="US00000O0018"):
        load_universe(
            database,
            filings_dir,
            tmp_path / "second",
            _never_asked,
            _never_fetched,
            (),
            (),
            (),
            swaps,
            adapters=adapters,
        )

    assert _tables(database) == (_EXPECTED_COMPANIES, _EXPECTED_INSTRUMENTS)
