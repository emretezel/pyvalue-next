"""Apply schema migrations to the pyvalue database.

A migration is one numbered SQL file under ``pyvalue/db/migrations/``. The
database records each migration it has received in the ``schema_migration``
table. The rules this module enforces are set out in ADR 0007
(``docs/adr/0007-schema-migrations.md``).

Author: Emre Tezel
"""

import hashlib
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from pyvalue.db.connection import connect
from pyvalue.db.errors import DatabaseError

# The one piece of schema that is not in a migration file: it has to exist
# before migration 1 can be recorded. Keep it identical to the appendix of
# ADR 0007 and to docs/database/schema_migration.md.
_HISTORY_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version    INTEGER NOT NULL PRIMARY KEY CHECK (version > 0),
    name       TEXT NOT NULL UNIQUE CHECK (name <> '' AND name NOT GLOB '*[^a-z0-9_]*'),
    checksum   TEXT NOT NULL CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    applied_at TEXT NOT NULL CHECK (
      applied_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'
    )
)
"""

# NNNN_lower_snake_name.sql
_FILE_NAME: re.Pattern[str] = re.compile(r"(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql")

# Statements a migration file may not contain: the run owns the transaction and
# the foreign-key switch, and a file that touched either could commit half a
# migration or hide a broken reference from the check.
_FORBIDDEN_STATEMENT: re.Pattern[str] = re.compile(
    r"(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE|PRAGMA\s+foreign_keys)\b", re.IGNORECASE
)

# The whitespace, `-- line` comments and `/* block */` comments a text opens with.
_LEADING_COMMENTS: re.Pattern[str] = re.compile(r"\A(?:\s+|--[^\n]*|/\*.*?\*/)*", re.DOTALL)


class MigrationError(DatabaseError):
    """A migration could not be loaded, verified or applied."""


@dataclass(frozen=True)
class Migration:
    """One migration file.

    Attributes:
        version: The number in the file name; also its place in the sequence.
        name: The name part of the file name, without number or extension.
        statements: The SQL statements of the file, in order.
        checksum: SHA-256 of the file's bytes, as lower-case hexadecimal.
    """

    version: int
    name: str
    statements: tuple[str, ...]
    checksum: str

    @property
    def label(self) -> str:
        """The migration as a person would name it, e.g. ``0001_reference_schema``."""
        return f"{self.version:04d}_{self.name}"


@dataclass(frozen=True)
class MigrationReport:
    """What one migration run did.

    Attributes:
        path: The database that was migrated.
        applied: The migrations applied by this run, in order. Empty when the
            database was already up to date.
        version: The schema version after the run; 0 for a database that has
            received no migration.
    """

    path: Path
    applied: tuple[Migration, ...]
    version: int


def _without_leading_comments(text: str) -> str:
    """Drop the whitespace and SQL comments ``text`` opens with."""
    return _LEADING_COMMENTS.sub("", text, count=1)


def _split_statements(sql: str, source: str) -> tuple[str, ...]:
    """Split the text of a migration file into its statements.

    SQLite itself decides where a statement ends, so a semicolon inside a
    string literal, a comment or a trigger body does not split one.

    Raises:
        MigrationError: If text is left over after the last semicolon, a
            statement is one the run reserves for itself, or there is no
            statement at all.
    """
    *terminated, tail = sql.split(";")
    statements: list[str] = []
    buffer = ""
    for piece in terminated:
        buffer += piece + ";"
        if not sqlite3.complete_statement(buffer):
            continue
        body = _without_leading_comments(buffer)
        buffer = ""
        if body == ";":
            # A stray second semicolon: an empty statement, nothing to run.
            continue
        forbidden = _FORBIDDEN_STATEMENT.match(body)
        if forbidden:
            raise MigrationError(
                f"{source}: a migration may not contain '{forbidden.group(1).upper()}'; "
                "the migration run owns the transaction and the foreign-key switch"
            )
        statements.append(body)
    # Whatever was not closed by a semicolon. Only comments may remain.
    if _without_leading_comments(buffer + tail):
        raise MigrationError(f"{source}: the last statement does not end with a semicolon")
    if not statements:
        raise MigrationError(f"{source}: the file contains no statement")
    return tuple(statements)


def load_migrations(directory: Path) -> tuple[Migration, ...]:
    """Read the migration files of ``directory``.

    Files that do not end in ``.sql`` are ignored.

    Args:
        directory: A folder of ``NNNN_lower_snake_name.sql`` files.

    Returns:
        The migrations in version order.

    Raises:
        MigrationError: If the folder cannot be read, a ``.sql`` file is
            misnamed, the numbers do not run from 1 without gaps or repeats,
            or a file breaks the rules for migration content.
    """
    migrations: list[Migration] = []
    try:
        files = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError as error:
        raise MigrationError(f"cannot read migrations from {directory}: {error}") from error
    for file in files:
        if file.suffix != ".sql":
            continue
        matched = _FILE_NAME.fullmatch(file.name)
        if matched is None:
            raise MigrationError(
                f"{file.name}: a migration file is named NNNN_lower_snake_name.sql"
            )
        content = file.read_bytes()
        migrations.append(
            Migration(
                version=int(matched["version"]),
                name=matched["name"],
                statements=_split_statements(content.decode("utf-8"), file.name),
                checksum=hashlib.sha256(content).hexdigest(),
            )
        )
    # A gap would let a late-arriving file slip in below the database's version
    # and never run; a repeat would make the order ambiguous.
    for expected, migration in enumerate(migrations, start=1):
        if migration.version != expected:
            raise MigrationError(
                "migration numbers must run from 0001 without gaps or repeats: "
                f"found {migration.label} where number {expected:04d} was expected"
            )
    return tuple(migrations)


def packaged_migrations() -> tuple[Migration, ...]:
    """Read the migrations shipped inside the installed package."""
    packaged = resources.files("pyvalue.db").joinpath("migrations")
    # as_file gives a real folder even if the package were installed zipped.
    with resources.as_file(packaged) as directory:
        return load_migrations(directory)


def _recorded(connection: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Return (version, name, checksum) of every recorded migration, in order."""
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migration ORDER BY version"
    ).fetchall()
    return [(int(version), str(name), str(checksum)) for version, name, checksum in rows]


def _has_history(connection: sqlite3.Connection) -> bool:
    """Say whether the database has the migration history table."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'schema_migration'"
    ).fetchone()
    return row is not None


def _refuse_foreign_database(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a database that has content but no migration history.

    Such a file was not built by pyvalue, for example the legacy project's
    database reached through a mistyped path. Creating the history table in it
    would already be a change to somebody else's data.
    """
    if _has_history(connection):
        return
    has_content = connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
    if has_content is not None:
        raise MigrationError(
            f"{path} already holds tables but has no migration history, so it was not created "
            "by pyvalue; refusing to change it"
        )


def _verify_history(recorded: list[tuple[int, str, str]], migrations: Sequence[Migration]) -> None:
    """Refuse a database whose history does not match the migration files."""
    for position, (version, name, checksum) in enumerate(recorded, start=1):
        if version != position:
            raise MigrationError(
                "the database's migration history is not continuous: found version "
                f"{version} where {position} was expected"
            )
        if position > len(migrations):
            raise MigrationError(
                f"the database is at schema version {recorded[-1][0]}, but this copy of pyvalue "
                f"only knows migrations up to {len(migrations)}; use a newer pyvalue"
            )
        migration = migrations[position - 1]
        if name != migration.name:
            raise MigrationError(
                f"migration {version:04d} was applied as '{name}' but its file is now named "
                f"'{migration.name}'; an applied migration is never renamed"
            )
        if checksum != migration.checksum:
            raise MigrationError(
                f"migration {migration.label} has changed since it was applied; an applied "
                "migration is never edited, so restore the file and add a new migration"
            )


def _tables_with_broken_references(connection: sqlite3.Connection) -> list[str]:
    """Return the tables that hold a row pointing at a missing parent."""
    return sorted({str(row[0]) for row in connection.execute("PRAGMA foreign_key_check")})


def _apply(connection: sqlite3.Connection, migration: Migration) -> None:
    """Apply one migration and record it, as a single transaction."""
    # IMMEDIATE takes the write lock up front, so a second process cannot start
    # the same migration in between.
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in migration.statements:
            connection.execute(statement)
        broken = _tables_with_broken_references(connection)
        if broken:
            raise MigrationError(
                f"migration {migration.label} leaves rows that point at missing parents in "
                f"{', '.join(broken)}; it was rolled back"
            )
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) "
            "VALUES (?, ?, ?, ?)",
            (
                migration.version,
                migration.name,
                migration.checksum,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        connection.execute("COMMIT")
    except BaseException:
        # Schema statements are transactional in SQLite, so this undoes the
        # whole migration and leaves the database as it was before it.
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _apply_pending(connection: sqlite3.Connection, pending: Sequence[Migration]) -> None:
    """Apply the pending migrations in order, stopping at the first failure."""
    # Checked before anything runs, so a fault that was already in the database
    # is not blamed on the first pending migration.
    broken = _tables_with_broken_references(connection)
    if broken:
        raise MigrationError(
            "the database already holds rows that point at missing parents in "
            f"{', '.join(broken)}; repair it before migrating"
        )
    # SQLite cannot rebuild a table that others reference while enforcement is
    # on, and the pragma is ignored inside a transaction. So enforcement is off
    # for the run and each migration is checked as a whole before it commits.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        for migration in pending:
            try:
                _apply(connection, migration)
            except sqlite3.Error as error:
                raise MigrationError(
                    f"migration {migration.label} failed and was rolled back: {error}"
                ) from error
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def migrate(path: Path, migrations: Sequence[Migration] | None = None) -> MigrationReport:
    """Bring the database at ``path`` to the latest schema version.

    The database is created when it does not exist. Each pending migration is
    applied in its own transaction; a failure rolls that migration back and
    stops the run, leaving earlier migrations of the same run in place.

    Args:
        path: Location of the SQLite file.
        migrations: The migrations to apply, in order. Defaults to the ones
            shipped with the package; tests pass their own.

    Returns:
        What the run applied and the resulting schema version.

    Raises:
        MigrationError: If the file is not a pyvalue database, its history
            does not match the migration files, it already holds broken
            references, or a migration fails.
        DatabaseError: If the database cannot be opened.
    """
    known = packaged_migrations() if migrations is None else tuple(migrations)
    connection = connect(path)
    try:
        _refuse_foreign_database(connection, path)
        connection.execute(_HISTORY_TABLE_SQL)
        recorded = _recorded(connection)
        _verify_history(recorded, known)
        pending = known[len(recorded) :]
        if pending:
            _apply_pending(connection, pending)
        return MigrationReport(path=path, applied=pending, version=len(recorded) + len(pending))
    except sqlite3.Error as error:
        raise MigrationError(f"cannot migrate {path}: {error}") from error
    finally:
        connection.close()


def require_current_schema(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a database that is not at the schema version this pyvalue needs.

    The unit of work calls this before it hands out repositories: their SQL is
    written for the latest schema, so on an older database it would fail in the
    middle of a component's work, or worse, half succeed.

    Args:
        connection: An open connection to the database.
        path: Where the database is, for the message.

    Raises:
        MigrationError: If the database is newer than this copy of pyvalue, or
            one of its applied migrations no longer matches its file.
        DatabaseError: If the database is behind, or was never migrated.
    """
    known = packaged_migrations()
    try:
        recorded = _recorded(connection) if _has_history(connection) else []
    except sqlite3.Error as error:
        raise DatabaseError(f"cannot read the schema version of {path}: {error}") from error
    _verify_history(recorded, known)
    if len(recorded) < len(known):
        raise DatabaseError(
            f"{path} is at schema version {len(recorded)}, but this pyvalue needs version "
            f"{len(known)}; run `pyvalue db migrate`"
        )
