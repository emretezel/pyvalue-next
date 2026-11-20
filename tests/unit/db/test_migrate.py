"""Tests for ``pyvalue.db.migrate``: the rules of ADR 0007.

Most tests build their own small migrations in a temporary folder, so they pin
the behaviour of the migration run and not the content of the real schema.

Author: Emre Tezel
"""

import re
import sqlite3
from pathlib import Path

import pytest

from pyvalue.db import MigrationError, load_migrations, migrate, packaged_migrations
from pyvalue.db.connection import connect

# A parent table and a child that references it, with one valid row each.
_PARENT_AND_CHILD: str = """
CREATE TABLE parent (parent_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE child (
    child_id  INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES parent (parent_id)
);
INSERT INTO parent (parent_id, name) VALUES (1, 'first');
INSERT INTO child (child_id, parent_id) VALUES (10, 1);
"""


def _write(directory: Path, file_name: str, sql: str) -> None:
    """Write one migration file into ``directory``, creating the folder."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / file_name).write_text(sql, encoding="utf-8")


def _tables(path: Path) -> set[str]:
    """Return the names of the tables in the database at ``path``."""
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()
    finally:
        connection.close()
    return {str(name) for (name,) in rows}


def _history(path: Path) -> list[tuple[int, str]]:
    """Return (version, name) of each recorded migration, in order."""
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT version, name FROM schema_migration ORDER BY version"
        ).fetchall()
    finally:
        connection.close()
    return [(int(version), str(name)) for version, name in rows]


# --- the packaged migrations -------------------------------------------------


def test_packaged_migrations_are_found_and_well_formed() -> None:
    """The SQL files ship with the package and load through importlib.resources."""
    migrations = packaged_migrations()

    assert migrations, "the package ships no migration"
    assert migrations[0].label == "0001_reference_schema"
    assert [migration.version for migration in migrations] == list(range(1, len(migrations) + 1))
    for migration in migrations:
        assert re.fullmatch(r"[0-9a-f]{64}", migration.checksum)
        assert migration.statements


def test_fresh_database_reaches_the_latest_version(database_path: Path) -> None:
    """One run takes a database that does not exist to the latest schema."""
    migrations = packaged_migrations()

    report = migrate(database_path)

    assert report.path == database_path
    assert report.applied == migrations
    assert report.version == len(migrations)
    assert _history(database_path) == [(m.version, m.name) for m in migrations]


def test_second_run_changes_nothing(database_path: Path) -> None:
    """With nothing pending a run applies nothing and rewrites no history."""
    migrate(database_path)
    connection = sqlite3.connect(database_path)
    before = connection.execute("SELECT version, applied_at FROM schema_migration").fetchall()
    connection.close()

    report = migrate(database_path)

    connection = sqlite3.connect(database_path)
    after = connection.execute("SELECT version, applied_at FROM schema_migration").fetchall()
    connection.close()
    assert report.applied == ()
    assert report.version == len(packaged_migrations())
    assert after == before


# --- applying ----------------------------------------------------------------


def test_only_pending_migrations_are_applied(tmp_path: Path, database_path: Path) -> None:
    """A later run applies just the files the database has not received."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    _write(folder, "0002_second.sql", "CREATE TABLE second (second_id INTEGER PRIMARY KEY);")
    first_run = migrate(database_path, load_migrations(folder))

    _write(folder, "0003_third.sql", "CREATE TABLE third (third_id INTEGER PRIMARY KEY);")
    second_run = migrate(database_path, load_migrations(folder))

    assert [m.label for m in first_run.applied] == ["0001_first", "0002_second"]
    assert [m.label for m in second_run.applied] == ["0003_third"]
    assert second_run.version == 3
    assert {"first", "second", "third"} <= _tables(database_path)


def test_empty_migration_list_leaves_version_zero(database_path: Path) -> None:
    """A database that has received nothing is at version 0."""
    report = migrate(database_path, [])

    assert report.applied == ()
    assert report.version == 0


def test_applied_at_is_recorded_in_utc(tmp_path: Path, database_path: Path) -> None:
    """The history row carries the documented timestamp form."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    migrate(database_path, load_migrations(folder))

    connection = sqlite3.connect(database_path)
    (applied_at,) = connection.execute("SELECT applied_at FROM schema_migration").fetchone()
    connection.close()

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", applied_at)


def test_failed_migration_leaves_no_trace(tmp_path: Path, database_path: Path) -> None:
    """A migration that fails half way is rolled back as a whole.

    The first statement of the failing migration creates a table. If schema
    statements were committed one by one, that table would survive the failure.
    """
    folder = tmp_path / "migrations"
    _write(folder, "0001_good.sql", "CREATE TABLE good (good_id INTEGER PRIMARY KEY);")
    _write(
        folder,
        "0002_bad.sql",
        "CREATE TABLE half (half_id INTEGER PRIMARY KEY);\n"
        "INSERT INTO no_such_table (x) VALUES (1);",
    )

    with pytest.raises(MigrationError, match="0002_bad failed and was rolled back"):
        migrate(database_path, load_migrations(folder))

    # The earlier migration of the same run stays; the failed one left nothing.
    assert "good" in _tables(database_path)
    assert "half" not in _tables(database_path)
    assert _history(database_path) == [(1, "good")]


def test_migration_leaving_a_dangling_reference_is_rolled_back(
    tmp_path: Path, database_path: Path
) -> None:
    """Enforcement is off during a run, so the check before commit must catch this."""
    folder = tmp_path / "migrations"
    _write(
        folder,
        "0001_dangling.sql",
        _PARENT_AND_CHILD + "INSERT INTO child (child_id, parent_id) VALUES (11, 999);",
    )

    with pytest.raises(MigrationError, match="point at missing parents in child"):
        migrate(database_path, load_migrations(folder))

    assert not {"parent", "child"} & _tables(database_path)
    assert _history(database_path) == []


def test_referenced_table_can_be_rebuilt(tmp_path: Path, database_path: Path) -> None:
    """The reason enforcement is off during a run.

    Changing a column of a table that others reference means building a new
    table and dropping the old one. With enforcement on, the DROP is refused.
    """
    folder = tmp_path / "migrations"
    _write(folder, "0001_create.sql", _PARENT_AND_CHILD)
    _write(
        folder,
        "0002_rebuild_parent.sql",
        "CREATE TABLE parent_new (\n"
        "    parent_id INTEGER PRIMARY KEY,\n"
        "    name TEXT NOT NULL CHECK (name <> '')\n"
        ");\n"
        "INSERT INTO parent_new (parent_id, name) SELECT parent_id, name FROM parent;\n"
        "DROP TABLE parent;\n"
        "ALTER TABLE parent_new RENAME TO parent;",
    )

    report = migrate(database_path, load_migrations(folder))

    assert report.version == 2
    connection = connect(database_path)
    try:
        assert connection.execute("SELECT parent_id FROM child").fetchall() == [(1,)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        # The rebuilt table carries the new constraint, and enforcement is back.
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute("INSERT INTO parent (parent_id, name) VALUES (2, '')")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            connection.execute("INSERT INTO child (child_id, parent_id) VALUES (12, 999)")
    finally:
        connection.close()


# --- verifying the history ---------------------------------------------------


def test_edited_migration_is_detected(tmp_path: Path, database_path: Path) -> None:
    """Any change to an applied file stops the run, a comment included."""
    folder = tmp_path / "migrations"
    sql = "CREATE TABLE first (first_id INTEGER PRIMARY KEY);"
    _write(folder, "0001_first.sql", sql)
    migrate(database_path, load_migrations(folder))

    _write(folder, "0001_first.sql", sql + "\n-- a harmless-looking comment")

    with pytest.raises(MigrationError, match="0001_first has changed since it was applied"):
        migrate(database_path, load_migrations(folder))


def test_renamed_migration_is_detected(tmp_path: Path, database_path: Path) -> None:
    """The name is part of a migration's identity."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    migrate(database_path, load_migrations(folder))

    (folder / "0001_first.sql").rename(folder / "0001_renamed.sql")

    with pytest.raises(MigrationError, match="never renamed"):
        migrate(database_path, load_migrations(folder))


def test_database_newer_than_the_code_is_refused(tmp_path: Path, database_path: Path) -> None:
    """An older pyvalue must not touch a database a newer one has migrated."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    _write(folder, "0002_second.sql", "CREATE TABLE second (second_id INTEGER PRIMARY KEY);")
    newer = load_migrations(folder)
    migrate(database_path, newer)

    with pytest.raises(MigrationError, match="only knows migrations up to 1"):
        migrate(database_path, newer[:1])


def test_history_with_a_hole_is_refused(tmp_path: Path, database_path: Path) -> None:
    """A history that does not run 1, 2, 3 means somebody edited the table."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    _write(folder, "0002_second.sql", "CREATE TABLE second (second_id INTEGER PRIMARY KEY);")
    migrations = load_migrations(folder)
    migrate(database_path, migrations)
    connection = sqlite3.connect(database_path)
    connection.execute("DELETE FROM schema_migration WHERE version = 1")
    connection.commit()
    connection.close()

    with pytest.raises(MigrationError, match="not continuous"):
        migrate(database_path, migrations)


def test_database_not_created_by_pyvalue_is_refused(tmp_path: Path) -> None:
    """A mistyped path to another database must not be changed at all."""
    path = tmp_path / "somebody_elses.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE listing (listing_id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    with pytest.raises(MigrationError, match="not created by pyvalue"):
        migrate(path)

    # Not even the history table was added.
    assert _tables(path) == {"listing"}


def test_database_with_broken_references_is_refused(tmp_path: Path, database_path: Path) -> None:
    """A fault already in the database is reported as such, not blamed on a migration."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_create.sql", _PARENT_AND_CHILD)
    migrate(database_path, load_migrations(folder))
    # A plain sqlite3 connection has enforcement off, as another tool would.
    connection = sqlite3.connect(database_path)
    connection.execute("INSERT INTO child (child_id, parent_id) VALUES (11, 999)")
    connection.commit()
    connection.close()
    _write(folder, "0002_more.sql", "CREATE TABLE more (more_id INTEGER PRIMARY KEY);")

    with pytest.raises(MigrationError, match="already holds rows that point at missing parents"):
        migrate(database_path, load_migrations(folder))

    assert "more" not in _tables(database_path)


# --- loading migration files -------------------------------------------------


def test_files_that_are_not_sql_are_ignored(tmp_path: Path) -> None:
    """A README beside the migrations is not a migration."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    _write(folder, "README.md", "notes")

    assert [m.label for m in load_migrations(folder)] == ["0001_first"]


@pytest.mark.parametrize(
    "file_name",
    ["1_first.sql", "0001-first.sql", "0001_First.sql", "first.sql", "00001_first.sql"],
)
def test_misnamed_migration_file_is_rejected(tmp_path: Path, file_name: str) -> None:
    """A .sql file that does not follow the naming rule stops the load."""
    folder = tmp_path / "migrations"
    _write(folder, file_name, "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")

    with pytest.raises(MigrationError, match="NNNN_lower_snake_name.sql"):
        load_migrations(folder)


@pytest.mark.parametrize(
    ("file_names", "reason"),
    [
        (["0001_first.sql", "0003_third.sql"], "a gap"),
        (["0002_second.sql"], "does not start at 1"),
        (["0001_first.sql", "0001_again.sql"], "a repeat"),
    ],
)
def test_numbering_must_run_from_one_without_gaps_or_repeats(
    tmp_path: Path, file_names: list[str], reason: str
) -> None:
    """A gap would let a file slip in below the database's version and never run."""
    folder = tmp_path / "migrations"
    for file_name in file_names:
        _write(folder, file_name, "CREATE TABLE t (t_id INTEGER PRIMARY KEY);")

    with pytest.raises(MigrationError, match="without gaps or repeats"):
        load_migrations(folder)


def test_missing_migration_folder_is_reported(tmp_path: Path) -> None:
    """A folder that cannot be read fails with pyvalue's own error."""
    with pytest.raises(MigrationError, match="cannot read migrations"):
        load_migrations(tmp_path / "no_such_folder")


@pytest.mark.parametrize(
    "statement",
    [
        "BEGIN;",
        "begin transaction;",
        "COMMIT;",
        "END;",
        "ROLLBACK;",
        "SAVEPOINT s;",
        "RELEASE s;",
        "PRAGMA foreign_keys = OFF;",
        "-- a comment first\nCOMMIT;",
        "/* a block comment first */ pragma   foreign_keys=on;",
    ],
)
def test_transaction_control_in_a_file_is_rejected(tmp_path: Path, statement: str) -> None:
    """The run owns the transaction and the foreign-key switch."""
    folder = tmp_path / "migrations"
    _write(
        folder,
        "0001_first.sql",
        "CREATE TABLE first (first_id INTEGER PRIMARY KEY);\n" + statement,
    )

    with pytest.raises(MigrationError, match="may not contain"):
        load_migrations(folder)


def test_trigger_body_is_one_statement(tmp_path: Path, database_path: Path) -> None:
    """BEGIN and END inside a trigger are not transaction control."""
    folder = tmp_path / "migrations"
    _write(
        folder,
        "0001_trigger.sql",
        "CREATE TABLE audited (audited_id INTEGER PRIMARY KEY, note TEXT NOT NULL);\n"
        "CREATE TABLE audit_log (audit_log_id INTEGER PRIMARY KEY, note TEXT NOT NULL);\n"
        "CREATE TRIGGER audited_insert AFTER INSERT ON audited BEGIN\n"
        "    INSERT INTO audit_log (note) VALUES (new.note);\n"
        "    INSERT INTO audit_log (note) VALUES ('second; statement');\n"
        "END;",
    )

    migrations = load_migrations(folder)
    migrate(database_path, migrations)

    assert len(migrations[0].statements) == 3
    connection = connect(database_path)
    try:
        connection.execute("INSERT INTO audited (note) VALUES ('hello')")
        assert connection.execute(
            "SELECT note FROM audit_log ORDER BY audit_log_id"
        ).fetchall() == [
            ("hello",),
            ("second; statement",),
        ]
    finally:
        connection.close()


def test_semicolons_in_strings_and_comments_do_not_split(
    tmp_path: Path, database_path: Path
) -> None:
    """SQLite decides where a statement ends, not a naive split on semicolons."""
    folder = tmp_path / "migrations"
    _write(
        folder,
        "0001_semicolons.sql",
        "-- a comment; with a semicolon\n"
        "CREATE TABLE note (note_id INTEGER PRIMARY KEY, body TEXT NOT NULL); -- trailing; note\n"
        "/* a block; comment */\n"
        "INSERT INTO note (body) VALUES ('one; two');\n"
        ";\n"
        "-- the file may end with a comment; like this one\n",
    )

    migrations = load_migrations(folder)
    migrate(database_path, migrations)

    assert len(migrations[0].statements) == 2
    connection = connect(database_path)
    try:
        assert connection.execute("SELECT body FROM note").fetchall() == [("one; two",)]
    finally:
        connection.close()


def test_statement_without_final_semicolon_is_rejected(tmp_path: Path) -> None:
    """A truncated file must not be applied as far as it happens to parse."""
    folder = tmp_path / "migrations"
    _write(
        folder,
        "0001_first.sql",
        "CREATE TABLE first (first_id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE second (second_id INTEGER",
    )

    with pytest.raises(MigrationError, match="does not end with a semicolon"):
        load_migrations(folder)


@pytest.mark.parametrize("sql", ["", "   \n", "-- only a comment\n", ";"])
def test_file_without_a_statement_is_rejected(tmp_path: Path, sql: str) -> None:
    """An empty migration would be recorded as applied although it did nothing."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", sql)

    with pytest.raises(MigrationError, match="contains no statement"):
        load_migrations(folder)


# --- the history table itself ------------------------------------------------


@pytest.mark.parametrize(
    ("version", "name", "checksum", "applied_at", "constraint"),
    [
        (0, "zero", "a" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (-1, "negative", "a" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "", "a" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "Upper", "a" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "with space", "a" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "short_checksum", "a" * 63, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "upper_checksum", "A" * 64, "2026-11-20T18:30:00Z", "CHECK"),
        (2, "no_zone", "a" * 64, "2026-11-20T18:30:00", "CHECK"),
        (2, "space_not_t", "a" * 64, "2026-11-20 18:30:00Z", "CHECK"),
        (1, "repeat_version", "a" * 64, "2026-11-20T18:30:00Z", "UNIQUE"),
        (2, "first", "a" * 64, "2026-11-20T18:30:00Z", "UNIQUE"),
    ],
)
def test_history_table_rejects_malformed_rows(
    tmp_path: Path,
    database_path: Path,
    version: int,
    name: str,
    checksum: str,
    applied_at: str,
    constraint: str,
) -> None:
    """The history table declares its own invariants, like every other table."""
    folder = tmp_path / "migrations"
    _write(folder, "0001_first.sql", "CREATE TABLE first (first_id INTEGER PRIMARY KEY);")
    migrate(database_path, load_migrations(folder))
    connection = connect(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match=f"{constraint} constraint failed"):
            connection.execute(
                "INSERT INTO schema_migration (version, name, checksum, applied_at) "
                "VALUES (?, ?, ?, ?)",
                (version, name, checksum, applied_at),
            )
    finally:
        connection.close()
