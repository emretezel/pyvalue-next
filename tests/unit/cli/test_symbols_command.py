"""Tests for ``pyvalue symbols load``.

The command reads and writes under the folder it is run from, so every test
runs it in a temporary folder. It uses the exchange files shipped with
pyvalue and the made-up sample lists of ``tests/fixtures/eodhd``. No test
touches the network, and the command could not: it only reads files.

Author: Emre Tezel
"""

import shutil
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.providers import packaged_exchange_codes
from pyvalue.providers.eodhd import EXCHANGE_FILE

# Stands in for a real key in the settings file of a test.
_KEY: str = "sample-api-key-0123456789"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eodhd_samples: Path) -> Path:
    """Return a temporary working folder with a migrated database and three saved lists.

    It mirrors a checkout after ``pyvalue db migrate`` and a download of the
    lists of ``KO``, ``LSE`` and ``US``: ``data/pyvalue.db`` and
    ``data/eodhd/``. The settings file holds a key, which the load must
    never read.
    """
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    lists = tmp_path / "data" / "eodhd"
    lists.mkdir()
    for sample in sorted(eodhd_samples.glob("*.json")):
        shutil.copyfile(sample, lists / sample.name)
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.toml").write_text(f'[eodhd]\napi_key = "{_KEY}"\n', encoding="utf-8")
    return tmp_path


def _without_a_list() -> list[str]:
    """Return the codes of the shipped file for which the workspace has no saved list."""
    codes = packaged_exchange_codes(EXCHANGE_FILE).codes_with_a_market()
    return [code for code in codes if code not in ("KO", "LSE", "US")]


def test_load_fills_the_tables_and_says_what_it_did(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The numbers of the sample lists (tests/fixtures/eodhd/README.md)."""
    capsys.readouterr()

    status = main(["symbols", "load"])

    output = capsys.readouterr()
    missing = _without_a_list()
    assert status == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Database: {Path('data') / 'pyvalue.db'}",
        "Exchanges: 61 (61 added, 0 corrected)",
        "EODHD exchange codes: 61 (61 added)",
        "Lists stored: 3 of 59, 12 lines",
        "  KO: 4 lines",
        "  LSE: 4 lines",
        "  US: 4 lines",
        "Lines not stored: 3 not a share (ETF 2, FUND 1), 1 without a symbol, "
        "1 without a currency, 1 under a venue label that is left out",
        "Lines stored without an ISIN: 4, of which 1 carried one that is not valid",
        f"Codes without a saved list: 56 ({', '.join(missing)})",
        "Lists not stored: 0",
    ]


def test_a_second_load_adds_nothing_and_stores_the_same(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running it again changes nothing."""
    assert main(["symbols", "load"]) == 0
    first = capsys.readouterr().out.splitlines()

    assert main(["symbols", "load"]) == 0

    second = capsys.readouterr().out.splitlines()
    assert second[1:3] == [
        "Exchanges: 61 (0 added, 0 corrected)",
        "EODHD exchange codes: 61 (0 added)",
    ]
    assert second[3:] == first[3:]


def test_a_list_that_cannot_be_stored_is_named_with_what_to_act_on(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command still succeeds: the other lists are stored, and this one is reported."""
    (workspace / "data" / "eodhd" / "symbols_KO.json").write_text("Unauthorized", encoding="utf-8")
    capsys.readouterr()

    status = main(["symbols", "load"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert "Lists stored: 2 of 59, 8 lines" in lines
    assert lines[-2] == "Lists not stored: 1"
    assert lines[-1].startswith("  KO: the saved file is not a symbol list (")
    assert "symbols_KO.json is not an EODHD symbol list" in lines[-1]


def test_load_works_before_any_list_was_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A new checkout: the exchange tables are filled, and every code lacks its list."""
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    capsys.readouterr()

    status = main(["symbols", "load"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert lines[1:4] == [
        "Exchanges: 61 (61 added, 0 corrected)",
        "EODHD exchange codes: 61 (61 added)",
        "Lists stored: 0 of 59, 0 lines",
    ]
    assert lines[-2].startswith("Codes without a saved list: 59 (AS, AT, AU, ")
    assert lines[-1] == "Lists not stored: 0"


def test_load_never_reads_the_key_and_never_prints_it(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The settings file holds a key; the load has no use for it."""
    assert main(["symbols", "load"]) == 0

    output = capsys.readouterr()
    assert _KEY not in output.out
    assert _KEY not in output.err


def test_load_without_a_database_says_how_to_create_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line, no traceback, and status 1."""
    monkeypatch.chdir(tmp_path)

    status = main(["symbols", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: there is no database at")
    assert "pyvalue db migrate" in output.err


def test_load_takes_another_database_path(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--db`` points the command at another file, as for every database command."""
    other = workspace / "other.db"
    assert main(["db", "migrate", "--db", str(other)]) == 0
    capsys.readouterr()

    assert main(["symbols", "load", "--db", str(other)]) == 0

    assert capsys.readouterr().out.splitlines()[0] == f"Database: {other}"
