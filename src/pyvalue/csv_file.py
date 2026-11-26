"""Read a committed comma-separated file with a fixed header.

pyvalue keeps what people decide and maintain in small comma-separated files
under version control: the decisions that correct the universe load, our list
of exchanges, a provider's exchange codes. They share one shape, a header row
and then rows with as many cells as the header has. A file has no constraints
of its own, so every reader starts with the two checks made here; what a row
means is for the reader of its kind to check.

The module lives outside every component, like ``pyvalue.errors``, so that
each component can read its files without depending on another.

Author: Emre Tezel
"""

import csv
from pathlib import Path

from pyvalue.errors import PyvalueError


def read_csv(
    path: Path, header: tuple[str, ...], error: type[PyvalueError], what: str
) -> tuple[tuple[str, list[str]], ...]:
    """Read the rows of a comma-separated file whose header is known.

    Args:
        path: The file.
        header: The columns the file must have, in order.
        error: The error to raise. Each component has its own.
        what: What to call the file in a message, such as "the decisions
            file".

    Returns:
        One pair per row after the header: the words that locate the row in
        a message (the file and the row number, counting the header as row
        1), and the row's cells, already known to be as many as the header
        has.

    Raises:
        PyvalueError: Of the class given as ``error``, if the file cannot be
            read, its first row is not the header, or a row has another
            number of cells.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as failure:
        raise error(f"cannot read {what} {path}: {failure}") from failure
    if not rows or tuple(rows[0]) != header:
        raise error(f"{path}: the first row must be {','.join(header)}")

    located: list[tuple[str, list[str]]] = []
    for number, row in enumerate(rows[1:], start=2):
        where = f"{path} row {number}"
        if len(row) != len(header):
            raise error(f"{where} has {len(row)} cells where {len(header)} are expected")
        located.append((where, row))
    return tuple(located)
