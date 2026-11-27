"""Keep downloaded bytes as a file that is whole or absent.

A subscription is bought for a month at a time, so a saved answer may be the
only copy there is. A run that is interrupted while it writes must therefore
never leave half a file under a name that later code trusts. The one function
here writes under a temporary name and gives the file its final name in one
step.

The module lives outside every component, like ``pyvalue.csv_file``, so that
each download can use it and name its own error.

Author: Emre Tezel
"""

import contextlib
from pathlib import Path

from pyvalue.errors import PyvalueError


def save_whole(body: bytes, destination: Path, error: type[PyvalueError]) -> None:
    """Keep bytes under their final name, replacing what was there.

    The bytes are written under a temporary name beside the destination and
    renamed, so a file with the final name is always whole, even if the run
    is interrupted. The temporary name is made from the destination's, so two
    callers that write different files never share one.

    Args:
        body: What to keep.
        destination: The final name. Its folder is created when missing.
        error: The error to raise. Each component has its own.

    Raises:
        PyvalueError: Of the class given as ``error``, if the file cannot be
            written.
    """
    partial = destination.with_name(destination.name + ".part")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(body)
        partial.replace(destination)
    except OSError as failure:
        raise error(f"cannot save {destination}: {failure}") from failure
    finally:
        # The temporary file must not stay, whatever happened. If it cannot be
        # removed either, the error already on its way is the one to report.
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
