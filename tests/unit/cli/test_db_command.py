"""Tests for ``pyvalue db migrate``.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

import pyvalue
from pyvalue.cli import main
from pyvalue.db import MigrationError, packaged_migrations


def test_migrate_creates_the_database_and_reports_it(
    database_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first run builds the database and names what it applied."""
    status = main(["db", "migrate", "--db", str(database_path)])

    output = capsys.readouterr()
    assert status == 0
    assert database_path.is_file()
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Database: {database_path}",
        *(f"Applied {migration.label}" for migration in packaged_migrations()),
        f"Schema version: {len(packaged_migrations())}",
    ]


def test_migrate_reports_up_to_date_on_the_second_run(
    database_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running the command again is harmless and says so."""
    main(["db", "migrate", "--db", str(database_path)])
    capsys.readouterr()

    status = main(["db", "migrate", "--db", str(database_path)])

    assert status == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Database: {database_path}",
        "Up to date",
        f"Schema version: {len(packaged_migrations())}",
    ]


def test_migrate_defaults_to_data_folder_of_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --db the database is data/pyvalue.db under the current folder."""
    monkeypatch.chdir(tmp_path)

    status = main(["db", "migrate"])

    assert status == 0
    assert (tmp_path / "data" / "pyvalue.db").is_file()
    assert capsys.readouterr().out.splitlines()[0] == f"Database: {Path('data') / 'pyvalue.db'}"


def test_file_that_is_not_a_database_gives_one_line_and_status_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A condition the user can fix is reported without a traceback."""
    path = tmp_path / "notes.db"
    path.write_text("this is not a SQLite database, just some text " * 20)

    status = main(["db", "migrate", "--db", str(path)])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: cannot open database")
    assert len(output.err.splitlines()) == 1


def test_failed_migration_gives_one_line_and_status_one(
    database_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A migration failure reaches the user as the migration run worded it."""

    def failing_migrate(path: Path) -> None:
        raise MigrationError("migration 0002_broken failed and was rolled back: boom")

    monkeypatch.setattr("pyvalue.cli.app.migrate", failing_migrate)

    status = main(["db", "migrate", "--db", str(database_path)])

    assert status == 1
    assert capsys.readouterr().err == (
        "pyvalue: error: migration 0002_broken failed and was rolled back: boom\n"
    )


def test_version_option_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    """--version identifies which pyvalue is installed (the legacy one is 0.1.0)."""
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert capsys.readouterr().out == f"pyvalue {pyvalue.__version__}\n"


@pytest.mark.parametrize("arguments", [[], ["db"], ["db", "nonsense"], ["nonsense"]])
def test_bad_usage_exits_with_status_two(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """argparse reports a missing or unknown command and exits with 2."""
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2
    assert "usage: pyvalue" in capsys.readouterr().err
