"""The base of every error pyvalue raises on purpose.

It lives in its own module, outside every component, so that each component can
derive its errors from it without depending on another component.

Author: Emre Tezel
"""

# How a database is rebuilt, for the messages that ask for it. No load deletes
# a row and no run changes a listing, so a database that no longer agrees with
# the committed files is built again from them (ADR 0013, ADR 0024, ADR 0026).
# The statements are read again from the saved payloads, last, because a
# rebuilt database gives the companies new ids (ADR 0029). Every such message
# gives the same steps, in the order they have to be run.
REBUILD_STEPS: str = (
    "set the file aside, run `pyvalue db migrate`, then `pyvalue universe load`, "
    "`pyvalue symbols load`, `pyvalue listings fill` and `pyvalue fundamentals load`"
)


class PyvalueError(Exception):
    """A condition a person can act on, as opposed to a fault in pyvalue.

    A wrong path, a missing setting, a file that is not what it should be, a
    row the database refuses. The command line catches this one class and
    prints its message as a single line, so every message must stand on its
    own and say what to do where that is known.
    """
