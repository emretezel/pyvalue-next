"""The universe load end to end, on the checked-in sample filings.

Three small made-up filings (``tests/fixtures/nport``, described line by line
in its README) go through everything the command does except the download:
reading, sorting, placing, and writing the output. The expected rows and the
expected output files were worked out by hand from the rules of ADR 0006.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.db import Company, Database, Instrument
from pyvalue.universe import load_universe

pytestmark = pytest.mark.integration

_ALPHA: str = "549300ALPHA000000003"
_DELTA: str = "549300DELTA000000010"
_EPSILON: str = "549300EPSLN000000037"
_ZETA: str = "549300ZETA0000000008"
_THETA: str = "549300THETA000000051"
_KAPPA: str = "549300KAPPA000000078"
_NU: str = "549300NU000000000098"

_EXPECTED_COMPANIES: tuple[Company, ...] = (
    Company(1, "ALPHA CORP", _ALPHA),
    Company(2, "BETA INC", None),
    Company(3, "DELTA PLC", _DELTA),
    # Loaded without an identifier from VXUS; DFAX filled it in.
    Company(4, "EPSILON SA", _EPSILON),
    Company(5, "ZETA LTD", _ZETA),
    # DFAX names another identifier for the same ISIN: the first answer stays.
    Company(6, "THETA AG", _THETA),
    # DFAX supplies an identifier company 3 already has: it is not filled in.
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
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """Every company and instrument, with the ids the order of loading gives them."""
    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
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
    database: Database, filings_dir: Path, nport_samples: Path, tmp_path: Path
) -> None:
    """Reproducibility: fixed filings give fixed files, down to the last byte."""
    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
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
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """Nothing is left behind: 31 lines are 11 listed ones plus 20 that reached an instrument."""
    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
    )

    result = outcome.result
    # 16 lines added an instrument; 4 met an ISIN that was already one (DFAX lines 1, 2, 4, 5).
    assert result.lines_read - len(result.not_loaded) == result.instruments_added + 4


def test_a_second_run_changes_nothing_and_writes_the_same_files(
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """ADR 0009: running the load again is harmless, and its output is the same."""
    first = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
    )
    first_files = (
        first.output.lines_not_loaded.read_bytes(),
        first.output.cases_for_agent.read_bytes(),
    )

    second = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
    )

    assert _tables(database) == (_EXPECTED_COMPANIES, _EXPECTED_INSTRUMENTS)
    assert (second.result.companies_added, second.result.instruments_added) == (0, 0)
    assert second.result.leis_filled == 0
    assert (
        second.output.lines_not_loaded.read_bytes(),
        second.output.cases_for_agent.read_bytes(),
    ) == first_files
