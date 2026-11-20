"""The errors of the universe component.

Author: Emre Tezel
"""

from pyvalue.errors import PyvalueError


class UniverseError(PyvalueError):
    """The universe load could not run or could not finish."""


class FilingError(UniverseError):
    """A holdings filing could not be obtained, or is not what was expected."""
