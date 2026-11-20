"""Open connections to the pyvalue SQLite database.

Every connection pyvalue uses is opened here, so the two properties the schema
relies on are set in one place: foreign keys are enforced, and transactions are
explicit.

Author: Emre Tezel
"""

import sqlite3
from pathlib import Path

# Relative on purpose: the database belongs to the folder pyvalue is run from
# (the repository checkout), and `data/` is never committed. A command that
# needs another file takes an explicit path.
DEFAULT_DATABASE_PATH: Path = Path("data") / "pyvalue.db"


class DatabaseError(Exception):
    """The database could not be opened or used as pyvalue requires."""


def connect(path: Path) -> sqlite3.Connection:
    """Open the database at ``path`` with foreign keys enforced.

    The file and its parent folder are created when they do not exist, because
    the first caller is the migration run that builds a new database.

    Args:
        path: Location of the SQLite file.

    Returns:
        A connection in autocommit mode: no transaction is open until the
        caller begins one, and a statement run outside a transaction is
        committed at once.

    Raises:
        DatabaseError: If the file cannot be opened as a SQLite database, or
            if this SQLite build cannot enforce foreign keys.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # autocommit=True switches off Python's implicit transactions. Callers
        # begin and commit their own, which is what lets the migration run wrap
        # a whole migration, schema statements included, in one transaction.
        connection = sqlite3.connect(path, autocommit=True)
    except (OSError, sqlite3.Error) as error:
        raise DatabaseError(f"cannot open database {path}: {error}") from error

    try:
        # sqlite3.connect() does not read the file. Reading the schema does, so
        # a file that is not a SQLite database is refused here, with the path,
        # and not later by whichever statement happens to touch it first.
        connection.execute("SELECT count(*) FROM sqlite_schema").fetchone()
        # SQLite enforces foreign keys per connection and defaults to off, so
        # the constraints the schema declares mean nothing without this.
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute("PRAGMA foreign_keys").fetchone()
    except sqlite3.Error as error:
        connection.close()
        raise DatabaseError(f"cannot open database {path}: {error}") from error

    # A SQLite build compiled without foreign-key support accepts the pragma
    # and silently ignores it. Reading it back is the only way to know.
    if row is None or row[0] != 1:
        connection.close()
        raise DatabaseError(f"this SQLite build cannot enforce foreign keys ({path})")
    return connection
