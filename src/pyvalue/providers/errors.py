"""The errors of the provider clients.

Author: Emre Tezel
"""

from pyvalue.errors import PyvalueError


class ProviderError(PyvalueError):
    """A provider's file or answer could not be obtained, or is not what was expected."""
