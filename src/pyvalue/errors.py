"""The base of every error pyvalue raises on purpose.

It lives in its own module, outside every component, so that each component can
derive its errors from it without depending on another component.

Author: Emre Tezel
"""


class PyvalueError(Exception):
    """A condition a person can act on, as opposed to a fault in pyvalue.

    A wrong path, a missing setting, a file that is not what it should be, a
    row the database refuses. The command line catches this one class and
    prints its message as a single line, so every message must stand on its
    own and say what to do where that is known.
    """
