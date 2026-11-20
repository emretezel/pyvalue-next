"""The pyvalue database: the unit of work, the repositories and the migrations.

This package is the only place in pyvalue that imports ``sqlite3`` or contains
SQL (see ``docs/architecture.md`` and ADR 0008). Other packages import the
names exported here and nothing from the modules inside: they open a
``Database``, ask it for a unit of work, and reach the tables through the
repositories of that unit of work.

Author: Emre Tezel
"""

from pyvalue.db.company import Company, CompanyRepository
from pyvalue.db.connection import DEFAULT_DATABASE_PATH
from pyvalue.db.errors import ConstraintError, DatabaseError
from pyvalue.db.instrument import Instrument, InstrumentRepository
from pyvalue.db.migrate import (
    Migration,
    MigrationError,
    MigrationReport,
    load_migrations,
    migrate,
    packaged_migrations,
)
from pyvalue.db.unit_of_work import Database, UnitOfWork

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "Company",
    "CompanyRepository",
    "ConstraintError",
    "Database",
    "DatabaseError",
    "Instrument",
    "InstrumentRepository",
    "Migration",
    "MigrationError",
    "MigrationReport",
    "UnitOfWork",
    "load_migrations",
    "migrate",
    "packaged_migrations",
]
