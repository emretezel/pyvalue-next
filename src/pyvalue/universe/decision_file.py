"""Reading a decisions file: what every kind of decision shares.

The load is corrected by committed files, one kind of decision per file
(ADR 0010 for legal-entity identifiers, ADR 0012 for company names). They have
the same shape: a comma-separated file with a header, one row per security,
keyed by its ISIN, with the date of the decision and its evidence. This module
reads that shape and checks what is common to all of them. What a row says
beyond that is for the module of its kind to check.

A file has no constraints of its own, so every row is checked here.

Author: Emre Tezel
"""

import csv
from collections.abc import Callable
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Protocol

from pyvalue.universe.errors import UniverseError
from pyvalue.universe.identifiers import is_valid_isin


class Decision(Protocol):
    """What every decision has: the security it is about."""

    @property
    def isin(self) -> str:
        """The ISIN of the security the decision is about."""
        ...


def valid_isin(text: str, where: str) -> str:
    """Return the ISIN of a row, or say that it is not one.

    Args:
        text: The cell as it stands in the file.
        where: The words that locate the row in a message.

    Raises:
        UniverseError: If the cell is not a valid ISIN.
    """
    if not is_valid_isin(text):
        raise UniverseError(f"{where}: '{text}' is not a valid ISIN")
    return text


def valid_day(text: str, where: str) -> date:
    """Return the date of a row, or say that it is not one.

    Args:
        text: The cell as it stands in the file.
        where: The words that locate the row in a message.

    Raises:
        UniverseError: If the cell is not a date written as YYYY-MM-DD.
    """
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise UniverseError(f"{where}: '{text}' is not a date (YYYY-MM-DD)") from error


def read_decisions[D: Decision](
    path: Path, header: tuple[str, ...], parse: Callable[[list[str], str], D]
) -> tuple[D, ...]:
    """Read a decisions file.

    Args:
        path: The comma-separated file.
        header: The columns the file must have, in order.
        parse: Turns the cells of one row into a decision, or raises
            ``UniverseError`` saying what is wrong with it. It is given the
            cells, already known to be as many as the header has, and the
            words that locate the row.

    Returns:
        The decisions, in the order of the file.

    Raises:
        UniverseError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same security. The message
            names the row, counting the header as row 1.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise UniverseError(f"cannot read the decisions file {path}: {error}") from error
    if not rows or tuple(rows[0]) != header:
        raise UniverseError(f"{path}: the first row must be {','.join(header)}")

    decisions: list[D] = []
    seen: dict[str, int] = {}
    for number, row in enumerate(rows[1:], start=2):
        where = f"{path} row {number}"
        if len(row) != len(header):
            raise UniverseError(f"{where} has {len(row)} cells where {len(header)} are expected")
        decision = parse(row, where)
        if decision.isin in seen:
            # Two answers for one security: the file must say which one holds.
            raise UniverseError(
                f"{where}: {decision.isin} was already decided in row {seen[decision.isin]}"
            )
        seen[decision.isin] = number
        decisions.append(decision)
    return tuple(decisions)


def read_packaged[D](file_name: str, read: Callable[[Path], tuple[D, ...]]) -> tuple[D, ...]:
    """Read a decisions file shipped inside the installed package.

    Args:
        file_name: The file's name in ``pyvalue/universe/decisions``.
        read: The reader of that kind of file.

    Returns:
        What the reader returns for the shipped file.
    """
    packaged = resources.files("pyvalue.universe").joinpath("decisions", file_name)
    # as_file gives a real file even if the package were installed zipped.
    with resources.as_file(packaged) as path:
        return read(path)
