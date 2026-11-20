"""Tests for ``pyvalue.db.unit_of_work``: the door of ADR 0008.

A unit of work is one transaction over all repositories. These tests pin the
promise that matters to every component: what is done inside the block is
saved together or undone together, and nothing gets in through a database that
is not ready.

Author: Emre Tezel
"""

import sqlite3
from pathlib import Path

import pytest

from pyvalue.db import (
    Company,
    ConstraintError,
    Database,
    DatabaseError,
    Instrument,
    MigrationError,
    migrate,
)

# Made-up identifiers with correct check digits.
_LEI: str = "549300ALPHA000000003"
_ISIN: str = "US00000A0014"


def _companies(database: Database) -> tuple[Company, ...]:
    """Read every company in a unit of work of its own."""
    with database.unit_of_work() as work:
        return work.companies.all()


def _instruments(database: Database) -> tuple[Instrument, ...]:
    """Read every instrument in a unit of work of its own."""
    with database.unit_of_work() as work:
        return work.instruments.all()


def test_leaving_the_block_saves_everything(database: Database) -> None:
    """Rows written through two repositories are both there afterwards."""
    with database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", _LEI)
        work.instruments.add(company.company_id, _ISIN)

    assert _companies(database) == (Company(company_id=1, name="Alpha Corp", lei=_LEI),)
    assert _instruments(database) == (Instrument(instrument_id=1, company_id=1, isin=_ISIN),)


def test_an_exception_undoes_everything(database: Database) -> None:
    """An exception that leaves the block takes every row of the block with it."""
    with pytest.raises(RuntimeError, match="stop"), database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", _LEI)
        work.instruments.add(company.company_id, _ISIN)
        raise RuntimeError("stop")

    assert _companies(database) == ()
    assert _instruments(database) == ()


def test_a_refused_row_undoes_the_rows_before_it(database: Database) -> None:
    """Both rows or neither: the company does not survive its refused instrument."""
    with pytest.raises(ConstraintError), database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", _LEI)
        work.instruments.add(company.company_id, "not an isin")

    assert _companies(database) == ()


def test_a_component_may_catch_a_refused_row_and_carry_on(database: Database) -> None:
    """A refused row undoes only itself; the unit of work stays usable."""
    with database.unit_of_work() as work:
        work.companies.add("Alpha Corp", _LEI)
        with pytest.raises(ConstraintError):
            work.companies.add("Beta Inc", _LEI)
        work.companies.add("Gamma Ltd", None)

    assert [company.name for company in _companies(database)] == ["Alpha Corp", "Gamma Ltd"]


def test_nothing_is_visible_to_others_before_the_block_ends(
    database: Database, migrated_path: Path
) -> None:
    """Another connection sees the rows only once the unit of work has ended."""
    observer = sqlite3.connect(migrated_path)
    try:
        with database.unit_of_work() as work:
            work.companies.add("Alpha Corp", _LEI)
            assert observer.execute("SELECT count(*) FROM company").fetchone() == (0,)

        assert observer.execute("SELECT count(*) FROM company").fetchone() == (1,)
    finally:
        observer.close()


def test_foreign_keys_are_enforced_inside_a_unit_of_work(database: Database) -> None:
    """An instrument of a company that does not exist is refused."""
    with (
        pytest.raises(ConstraintError, match="FOREIGN KEY constraint failed"),
        database.unit_of_work() as work,
    ):
        work.instruments.add(999, _ISIN)


def test_a_repository_is_of_no_use_after_its_unit_of_work(database: Database) -> None:
    """The connection is closed with the block, and says so in pyvalue's own words."""
    with database.unit_of_work() as work:
        kept = work.companies

    with pytest.raises(DatabaseError, match="cannot read or write company"):
        kept.all()


def test_a_missing_database_is_refused_and_not_created(database_path: Path) -> None:
    """A mistyped path must not leave an empty database behind."""
    with (
        pytest.raises(DatabaseError, match="there is no database at .*run `pyvalue db migrate`"),
        Database(database_path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")

    assert not database_path.exists()


def test_a_database_behind_the_schema_is_refused(database_path: Path) -> None:
    """Repositories are written for the latest schema and refuse an older one."""
    # A run with no migrations creates the history table and nothing else.
    migrate(database_path, migrations=())

    with (
        pytest.raises(DatabaseError, match="is at schema version 0.*run `pyvalue db migrate`"),
        Database(database_path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")


def test_a_file_that_was_never_migrated_is_refused(database_path: Path) -> None:
    """An empty file is a database at version 0."""
    database_path.touch()

    with (
        pytest.raises(DatabaseError, match="is at schema version 0"),
        Database(database_path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")


def test_a_history_table_pyvalue_did_not_make_is_refused(database_path: Path) -> None:
    """A foreign table of the same name cannot be read as a schema version."""
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE schema_migration (something TEXT)")
        connection.commit()
    finally:
        connection.close()

    with (
        pytest.raises(DatabaseError, match="cannot read the schema version"),
        Database(database_path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")


def test_a_database_newer_than_the_code_is_refused(migrated_path: Path) -> None:
    """A migration this copy of pyvalue does not know means its SQL may be wrong."""
    connection = sqlite3.connect(migrated_path)
    try:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) "
            "SELECT max(version) + 1, 'from_the_future', ?, '2026-11-20T00:00:00Z' "
            "FROM schema_migration",
            ("0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    with (
        pytest.raises(MigrationError, match="use a newer pyvalue"),
        Database(migrated_path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")


def test_a_file_that_is_not_a_database_is_refused(tmp_path: Path) -> None:
    """A wrong file is reported with its path."""
    path = tmp_path / "notes.db"
    path.write_text("this is not a SQLite database, just some text " * 20)

    with (
        pytest.raises(DatabaseError, match="cannot open database"),
        Database(path).unit_of_work(),
    ):
        pytest.fail("the unit of work must not open")


def test_the_database_knows_its_path(database: Database, migrated_path: Path) -> None:
    """Commands print the path, so the database hands it back."""
    assert database.path == migrated_path
