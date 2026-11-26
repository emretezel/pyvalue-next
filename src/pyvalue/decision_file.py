"""Reading a decisions file: what every kind of decision shares.

What pyvalue works out by rule is corrected by committed files, one kind of
decision per file: which legal-entity identifier a company gets (ADR 0010),
a company's name (ADR 0012), a security that is kept out (ADR 0013), a
receipt read as its ordinary share (ADR 0015), a security's listing
(ADR 0019). They have the same shape: a comma-separated file with a header,
one row per security, keyed by its ISIN, with the date of the decision and
its evidence. This module reads that shape and checks what is common to all
of them. What a row says beyond that is for the module of its kind to check.

A file has no constraints of its own, so every row is checked here.

The module lives outside every component, like ``pyvalue.csv_file``, so that
each component reads its own decisions without depending on another. That is
also why every function is told which error to raise.

Author: Emre Tezel
"""

from collections.abc import Callable
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Protocol

from pyvalue.csv_file import read_csv
from pyvalue.errors import PyvalueError
from pyvalue.identifiers import is_valid_isin


class Decision(Protocol):
    """What every decision has: the security it is about."""

    @property
    def isin(self) -> str:
        """The ISIN of the security the decision is about."""
        ...


def valid_isin(text: str, where: str, error: type[PyvalueError]) -> str:
    """Return the ISIN of a row, or say that it is not one.

    Args:
        text: The cell as it stands in the file.
        where: The words that locate the row in a message.
        error: The error to raise. Each component has its own.

    Raises:
        PyvalueError: Of the class given as ``error``, if the cell is not a
            valid ISIN.
    """
    if not is_valid_isin(text):
        raise error(f"{where}: '{text}' is not a valid ISIN")
    return text


def valid_day(text: str, where: str, error: type[PyvalueError]) -> date:
    """Return the date of a row, or say that it is not one.

    Args:
        text: The cell as it stands in the file.
        where: The words that locate the row in a message.
        error: The error to raise. Each component has its own.

    Raises:
        PyvalueError: Of the class given as ``error``, if the cell is not a
            date written as YYYY-MM-DD.
    """
    try:
        return date.fromisoformat(text)
    except ValueError as failure:
        raise error(f"{where}: '{text}' is not a date (YYYY-MM-DD)") from failure


def read_decisions[D: Decision](
    path: Path,
    header: tuple[str, ...],
    parse: Callable[[list[str], str], D],
    error: type[PyvalueError],
) -> tuple[D, ...]:
    """Read a decisions file.

    Args:
        path: The comma-separated file.
        header: The columns the file must have, in order.
        parse: Turns the cells of one row into a decision, or raises an error
            saying what is wrong with it. It is given the cells, already
            known to be as many as the header has, and the words that locate
            the row.
        error: The error to raise. Each component has its own.

    Returns:
        The decisions, in the order of the file.

    Raises:
        PyvalueError: Of the class given as ``error``, if the file cannot be
            read, its header is wrong, a row is invalid, or two rows are
            about the same security. The message names the row, counting the
            header as row 1.
    """
    decisions: list[D] = []
    seen: dict[str, int] = {}
    for number, (where, row) in enumerate(
        read_csv(path, header, error, "the decisions file"), start=2
    ):
        decision = parse(row, where)
        if decision.isin in seen:
            # Two answers for one security: the file must say which one holds.
            raise error(
                f"{where}: {decision.isin} was already decided in row {seen[decision.isin]}"
            )
        seen[decision.isin] = number
        decisions.append(decision)
    return tuple(decisions)


def read_packaged[D](
    package: str, file_name: str, read: Callable[[Path], tuple[D, ...]]
) -> tuple[D, ...]:
    """Read a decisions file shipped inside the installed package.

    Args:
        package: The component the file belongs to, such as
            ``pyvalue.universe``. Its decisions are in its ``decisions``
            folder.
        file_name: The file's name in that folder.
        read: The reader of that kind of file.

    Returns:
        What the reader returns for the shipped file.
    """
    packaged = resources.files(package).joinpath("decisions", file_name)
    # as_file gives a real file even if the package were installed zipped.
    with resources.as_file(packaged) as path:
        return read(path)
