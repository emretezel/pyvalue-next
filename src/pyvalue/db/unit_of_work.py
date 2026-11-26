"""The way into the database for every other package.

A component gets a ``Database``, asks it for a unit of work, and reaches the
repositories through that. The unit of work owns the connection and the
transaction: what a component does inside it is saved together when the block
ends, or undone together when an exception leaves it (ADR 0008).

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from pyvalue.db.company import CompanyRepository
from pyvalue.db.connection import connect
from pyvalue.db.errors import DatabaseError
from pyvalue.db.fund import FundRepository
from pyvalue.db.holding import HoldingRepository
from pyvalue.db.instrument import InstrumentRepository
from pyvalue.db.migrate import require_current_schema


class UnitOfWork:
    """The repositories of one transaction.

    All of them share one connection, so their writes are saved or undone as
    one. A unit of work is created by ``Database.unit_of_work`` and is of no
    use after its block has ended.

    Attributes:
        companies: The repository of the ``company`` table.
        instruments: The repository of the ``instrument`` table.
        funds: The repository of the ``fund`` table.
        holdings: The repository of the ``holding`` table.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create the repositories on the connection of this unit of work."""
        self.companies: Final[CompanyRepository] = CompanyRepository(connection)
        self.instruments: Final[InstrumentRepository] = InstrumentRepository(connection)
        self.funds: Final[FundRepository] = FundRepository(connection)
        self.holdings: Final[HoldingRepository] = HoldingRepository(connection)


class Database:
    """One pyvalue database file.

    Creating a ``Database`` opens nothing. Each unit of work opens its own
    connection and closes it when it ends.
    """

    def __init__(self, path: Path) -> None:
        """Name the database file.

        Args:
            path: Location of the SQLite file. It must already have been
                created by ``pyvalue db migrate``.
        """
        self._path: Final[Path] = path

    @property
    def path(self) -> Path:
        """Where the database file is."""
        return self._path

    @contextmanager
    def unit_of_work(self) -> Iterator[UnitOfWork]:
        """Open a unit of work: one transaction over all repositories.

        Use it as ``with database.unit_of_work() as work:``. Leaving the block
        normally saves everything done inside it. Leaving it through an
        exception undoes everything and lets the exception pass.

        Yields:
            The repositories, bound to one connection and one transaction.

        Raises:
            DatabaseError: If there is no database at the path, it is not at
                the latest schema version, or the transaction cannot be begun
                or saved.
        """
        connection = self._open()
        try:
            # A plain BEGIN takes no lock until the first statement, and the
            # write lock only at the first write, so a unit of work that only
            # reads never blocks another one.
            connection.execute("BEGIN")
            try:
                yield UnitOfWork(connection)
                connection.execute("COMMIT")
            except BaseException:
                # BaseException on purpose: a Ctrl-C in the middle of a load
                # must not leave half of it behind either.
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        except sqlite3.Error as error:
            raise DatabaseError(
                f"cannot complete the unit of work on {self._path}: {error}"
            ) from error
        finally:
            connection.close()

    def _open(self) -> sqlite3.Connection:
        """Open a connection, refusing a database that is not ready for use."""
        # connect() creates a missing file, which is right for the migration
        # run and wrong here: a component that met a mistyped path would
        # otherwise leave an empty database behind and report a schema problem.
        if not self._path.is_file():
            raise DatabaseError(
                f"there is no database at {self._path}; run `pyvalue db migrate` to create it"
            )
        connection = connect(self._path)
        try:
            require_current_schema(connection, self._path)
        except BaseException:
            connection.close()
            raise
        return connection
