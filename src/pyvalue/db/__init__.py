"""The pyvalue database: connections and schema migrations.

This package is the only place in pyvalue that imports ``sqlite3`` or contains
SQL (see ``docs/architecture.md``). Other packages call the functions exported
here.

Author: Emre Tezel
"""

from pyvalue.db.connection import DEFAULT_DATABASE_PATH, DatabaseError, connect
from pyvalue.db.migrate import (
    Migration,
    MigrationError,
    MigrationReport,
    load_migrations,
    migrate,
    packaged_migrations,
)

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "DatabaseError",
    "Migration",
    "MigrationError",
    "MigrationReport",
    "connect",
    "load_migrations",
    "migrate",
    "packaged_migrations",
]
