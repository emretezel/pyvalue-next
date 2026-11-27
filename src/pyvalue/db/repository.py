"""The base class of the repositories.

A repository is the one class that reads and writes one table (ADR 0008). This
base gives every repository the two things they share: the connection of the
unit of work they belong to, and one place where ``sqlite3`` errors become
pyvalue's own.

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Sequence
from typing import ClassVar

from pyvalue.db.errors import ConstraintError, DatabaseError


class Repository:
    """Every statement that reads or changes one table.

    A subclass names its table in ``table`` and adds one method per thing a
    component wants from that table. A repository never begins, commits or
    rolls back: the unit of work that created it owns the transaction.

    Attributes:
        table: The table this repository owns. A test checks that every
            repository names an existing table and that no two share one.
    """

    table: ClassVar[str]

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Attach the repository to the connection of its unit of work.

        Args:
            connection: The connection the unit of work opened. All
                repositories of one unit of work share it, which is what puts
                their writes in one transaction.
        """
        self._connection = connection

    def _execute(self, sql: str, parameters: Sequence[str | int | None] = ()) -> sqlite3.Cursor:
        """Run one statement of this repository.

        Every statement goes through here so that no ``sqlite3`` exception
        reaches a component.

        Args:
            sql: The statement, with ``?`` for each value.
            parameters: The values, in order.

        Returns:
            The cursor of the statement.

        Raises:
            ConstraintError: If the schema refuses the row, or a whole number
                is too large for the database.
            DatabaseError: If the statement fails for any other reason, for
                example because the unit of work has already ended.
        """
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.IntegrityError as error:
            # SQLite has already undone this one statement. The transaction is
            # still open, so the component decides whether the whole unit of
            # work fails (by letting this error escape) or carries on.
            raise ConstraintError(f"the {self.table} table refused a row: {error}") from error
        except OverflowError as error:
            # A whole number beyond SQLite's 64-bit range never reaches the
            # database: Python's own driver refuses it. It is a value the
            # table cannot hold, so it is refused like one.
            raise ConstraintError(f"the {self.table} table refused a row: {error}") from error
        except sqlite3.Error as error:
            raise DatabaseError(f"cannot read or write {self.table}: {error}") from error
