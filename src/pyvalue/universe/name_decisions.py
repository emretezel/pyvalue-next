"""Decisions on what a company is called (ADR 0012).

A fund sometimes files a placeholder of its data vendor where the company's
name should be, such as "New Issuer: BB Company ID:68830100". The name such a
company gets is one row of a committed file,
``pyvalue/universe/decisions/name.csv``, and the load applies it. The file is
shipped inside the package, so an installed copy builds the same universe.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.universe.decision_file import read_decisions, read_packaged, valid_day, valid_isin
from pyvalue.universe.errors import UniverseError

# The columns of the file, in order.
_HEADER: tuple[str, ...] = ("isin", "name", "decided_on", "evidence")


@dataclass(frozen=True, slots=True)
class NameDecision:
    """One decision: the company that issued this security is called this.

    Attributes:
        isin: The security the decision is about.
        name: The name its company gets, in the form it is stored: not empty,
            no surrounding spaces, single spaces between words.
        decided_on: The day the decision was taken.
        evidence: Where the name comes from.
    """

    isin: str
    name: str
    decided_on: date
    evidence: str


def _decision(row: list[str], where: str) -> NameDecision:
    """Turn one row of the file into a decision, or say what is wrong with it."""
    isin, name, decided_on, evidence = row
    valid_isin(isin, where)
    # The load stores a filed name with its runs of spaces reduced to one. A
    # decided name is stored as it stands, so it has to be in that form
    # already; an empty one would be refused by the table.
    if not name or name != " ".join(name.split()):
        raise UniverseError(
            f"{where}: the name must not be empty and must not carry stray spaces, got '{name}'"
        )
    # A name nobody can retrace is a guess.
    if not evidence.strip():
        raise UniverseError(f"{where}: the evidence must be filled in")
    return NameDecision(
        isin=isin, name=name, decided_on=valid_day(decided_on, where), evidence=evidence
    )


def read_name_decisions(path: Path) -> tuple[NameDecision, ...]:
    """Read a file of decisions on company names.

    Args:
        path: A comma-separated file with the header
            ``isin,name,decided_on,evidence``.

    Returns:
        The decisions, in the order of the file.

    Raises:
        UniverseError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same security. The message
            names the row, counting the header as row 1.
    """
    return read_decisions(path, _HEADER, _decision)


def packaged_name_decisions() -> tuple[NameDecision, ...]:
    """Read the decisions shipped inside the installed package."""
    return read_packaged("name.csv", read_name_decisions)
