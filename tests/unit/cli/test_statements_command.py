"""Tests for ``pyvalue fundamentals load``.

The command reads and writes under the folder it is run from, so every test
runs it in a temporary folder with two listings and the sample payloads of
``tests/fixtures/eodhd_fundamentals`` saved where the download keeps them.
The rows and findings themselves are tested with the load; these tests are
about what the command prints and how it fails.

Author: Emre Tezel
"""

import io
import sys
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.db import Database, Exchange, Provider, ProviderExchange, ProviderListing
from pyvalue.fundamentals.saved_payloads import pack, payload_file

# Two listings: our exchange, EODHD's code for it, EODHD's symbol, the ISIN
# and the company. The sample payloads have one for each.
_LISTINGS: tuple[tuple[str, str, str, str, str], ...] = (
    ("XNYS", "US", "BETA", "US00000B0013", "Beta Inc"),
    ("XLON", "LSE", "DLT", "GB00000D0016", "Delta PLC"),
)


class _Screen(io.StringIO):
    """Stands in for a terminal on the error stream."""

    def isatty(self) -> bool:
        """Answer as a terminal does."""
        return True


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fundamentals_samples: Path) -> Path:
    """Return a temporary working folder after the listing fill and the download."""
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    with Database(tmp_path / "data" / "pyvalue.db").unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, code, symbol, isin, name in _LISTINGS:
            work.exchanges.save(Exchange(mic=mic, name=f"Exchange {mic}", country=isin[:2]))
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )
            security = work.instruments.add(work.companies.add(name, None).company_id, isin)
            listing = work.listings.add(security.instrument_id, mic, symbol, "USD")
            work.provider_listings.add(
                ProviderListing(
                    provider_code="eodhd", listing_id=listing.listing_id, provider_symbol=symbol
                )
            )
            saved = tmp_path / "data" / "eodhd" / "fundamentals" / payload_file(code, symbol)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(pack((fundamentals_samples / f"{code}_{symbol}.json").read_bytes()))
    return tmp_path


def test_load_says_what_it_stored_and_found_by_outcome(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The counts are printed once, at the end, and the report is named."""
    capsys.readouterr()

    assert main(["fundamentals", "load"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        f"Database: {Path('data') / 'pyvalue.db'}",
        f"Payloads folder: {Path('data') / 'eodhd' / 'fundamentals'}",
        "Companies with a listing at EODHD: 2",
        "  With statements stored: 2",
        "Reporting periods: 7",
        "  Income statements: 5",
        "  Cash-flow statements: 5",
        "  Balance sheets: 6",
        "Findings: 9",
        "  Left out: 6",
        "    off_chain: 1",
        "    length_not_proven: 4",
        "    scale_outlier: 1",
        "  A figure left empty: 1",
        "    impossible_negative: 1",
        "  Stored with a warning: 2",
        "    gross_profit_mismatch: 1",
        "    sub_unit_label: 1",
        f"The findings are listed in {Path('data') / 'fundamentals' / 'findings.csv'}",
    ]
    assert (workspace / "data" / "fundamentals" / "findings.csv").is_file()


def test_a_load_from_a_folder_set_aside_stops_with_one_line_and_status_1(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the payload folder moved away, the tables are left as they were."""
    payloads = workspace / "data" / "eodhd" / "fundamentals"
    payloads.rename(workspace / "data" / "eodhd" / "fundamentals-set-aside")
    capsys.readouterr()

    status = main(["fundamentals", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: only 0 of 2 listings have a saved payload")
    assert output.err.count("\n") == 1


def test_load_without_a_database_says_how_to_create_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line, no traceback, and status 1."""
    monkeypatch.chdir(tmp_path)

    status = main(["fundamentals", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.err.startswith("pyvalue: error: there is no database at")
    assert "pyvalue db migrate" in output.err


def test_load_takes_another_database_path(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--db`` points the command at another file, as for every database command."""
    other = workspace / "other.db"
    assert main(["db", "migrate", "--db", str(other)]) == 0
    capsys.readouterr()

    assert main(["fundamentals", "load", "--db", str(other)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"Database: {other}"
    assert lines[2] == "Companies with a listing at EODHD: 0"


def test_on_a_terminal_one_bar_is_redrawn_in_place_and_its_line_ended_once(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing scrolls while the load goes on, and the counts start on a line of their own."""
    screen = _Screen()
    monkeypatch.setattr(sys, "stderr", screen)
    capsys.readouterr()

    assert main(["fundamentals", "load"]) == 0

    drawn = screen.getvalue()
    assert drawn.count("\r") == 2
    assert drawn.count("\n") == 1
    assert drawn.rstrip().endswith("2 of 2  100%")
    assert capsys.readouterr().out.startswith("Database: ")


def test_off_a_terminal_no_bar_is_drawn(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bar redrawn into a file would be noise."""
    capsys.readouterr()

    assert main(["fundamentals", "load"]) == 0

    assert capsys.readouterr().err == ""
