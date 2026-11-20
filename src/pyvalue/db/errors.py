"""The errors of the database package.

Other packages never see a ``sqlite3`` exception: whatever SQLite raises is
turned into one of these before it leaves ``pyvalue.db`` (ADR 0008).

Author: Emre Tezel
"""

from pyvalue.errors import PyvalueError


class DatabaseError(PyvalueError):
    """The database could not be opened or used as pyvalue requires."""


class ConstraintError(DatabaseError):
    """The schema refused a row.

    A value of the wrong shape, a repeat of something that must be unique, or
    a reference to a row that does not exist. The schema's constraints are the
    last line of defence: a component that sees this error handed the database
    something its own rules should have stopped.
    """
