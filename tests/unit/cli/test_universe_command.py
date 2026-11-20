"""Tests for ``pyvalue universe load``.

The command reads and writes under the folder it is run from, so every test
runs it in a temporary folder. None touches the network: either the sample
filings are already in place, or the run stops before a download.

Author: Emre Tezel
"""

import shutil
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.universe import PINNED_FILINGS


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nport_samples: Path) -> Path:
    """Return a temporary working folder with a migrated database and the sample filings.

    It mirrors a checkout after ``pyvalue db migrate`` and one earlier download:
    ``data/pyvalue.db`` and ``data/sec/``. There is no ``private/config.toml``.
    """
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    folder = tmp_path / "data" / "sec"
    folder.mkdir()
    for pinned in PINNED_FILINGS:
        shutil.copyfile(nport_samples / f"{pinned.ticker}.xml", folder / pinned.file_name)
    return tmp_path


def test_load_fills_the_database_and_says_what_it_did(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The numbers of the sample filings (tests/fixtures/nport/README.md)."""
    capsys.readouterr()

    status = main(["universe", "load"])

    output = capsys.readouterr()
    assert status == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Database: {Path('data') / 'pyvalue.db'}",
        "Filing VTI 0000036405-26-000480: already there",
        "Filing VXUS 0000736054-26-000275: already there",
        "Filing DFAX 0001004726-26-009205: already there",
        "Lines read: 31",
        "Lines not loaded: 11 (3 debt or derivative, 4 without a valid ISIN, "
        "4 receipt of a company already loaded)",
        "Securities: 19, of which 5 receipts (2 kept as the company's only line, 3 not loaded)",
        "Added: 14 companies and 16 instruments",
        "Joined to an existing company: 1 by legal-entity identifier, 1 by name",
        "Legal-entity identifiers filled in: 1",
        "The database now holds 14 companies and 16 instruments",
        f"Lines not loaded are listed in {Path('data') / 'universe' / 'lines_not_loaded.csv'}",
        f"Cases for the agent: 2, listed in {Path('data') / 'universe' / 'cases_for_agent.csv'}",
    ]
    assert (workspace / "data" / "universe" / "lines_not_loaded.csv").is_file()
    assert (workspace / "data" / "universe" / "cases_for_agent.csv").is_file()


def test_a_second_load_adds_nothing(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Running the command again is harmless and says so."""
    main(["universe", "load"])
    capsys.readouterr()

    status = main(["universe", "load"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert "Added: 0 companies and 0 instruments" in lines
    assert "The database now holds 14 companies and 16 instruments" in lines
    assert lines[-1].startswith("Cases for the agent: 2, ")


def test_the_database_option_points_the_load_elsewhere(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--db works as it does for ``db migrate``; the filings stay under data/sec."""
    other = workspace / "elsewhere" / "other.db"
    assert main(["db", "migrate", "--db", str(other)]) == 0
    capsys.readouterr()

    status = main(["universe", "load", "--db", str(other)])

    assert status == 0
    assert capsys.readouterr().out.splitlines()[0] == f"Database: {other}"


def test_a_missing_database_gives_one_line_and_status_one(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The load does not create a database; it says which command does."""
    capsys.readouterr()

    status = main(["universe", "load", "--db", str(workspace / "absent.db")])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: there is no database at ")
    assert "run `pyvalue db migrate`" in output.err
    assert len(output.err.splitlines()) == 1
    assert not (workspace / "absent.db").exists()


def test_a_missing_filing_without_the_contact_line_stops_before_any_download(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0009: no contact line, no request; the message names the line to add."""
    (workspace / "data" / "sec" / PINNED_FILINGS[0].file_name).unlink()
    capsys.readouterr()

    status = main(["universe", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith(
        f"pyvalue: error: {Path('private') / 'config.toml'} does not exist; create it and add "
        "a section [sec]"
    )
    assert len(output.err.splitlines()) == 1
    # Nothing was fetched, and nothing was loaded from the two filings that were there.
    assert not (workspace / "data" / "sec" / PINNED_FILINGS[0].file_name).exists()
    assert not (workspace / "data" / "universe").exists()


def test_a_damaged_filing_gives_one_line_and_status_one(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that is not the pinned filing is named, and the database stays empty."""
    (workspace / "data" / "sec" / PINNED_FILINGS[2].file_name).write_text("<html></html>")
    capsys.readouterr()

    status = main(["universe", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.err.startswith("pyvalue: error: ")
    assert "is not an N-PORT filing" in output.err
    assert len(output.err.splitlines()) == 1


@pytest.mark.parametrize("arguments", [["universe"], ["universe", "nonsense"]])
def test_bad_usage_exits_with_status_two(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """argparse reports a missing or unknown action and exits with 2."""
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2
    assert "usage: pyvalue universe" in capsys.readouterr().err
