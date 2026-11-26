"""The errors of the listings component.

Author: Emre Tezel
"""

from pyvalue.errors import PyvalueError


class ListingsError(PyvalueError):
    """The exchanges or a provider's symbol lists could not be read or stored."""
