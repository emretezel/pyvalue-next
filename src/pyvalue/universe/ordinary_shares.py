"""Decisions that a depositary receipt is read as its ordinary share (ADR 0015).

The funds hold some companies through a depositary receipt. What pyvalue
analyses is the ordinary share, and a listing is found by the ISIN of the
instrument. So where the ISIN of the ordinary share is known, the pair is one
row of a committed file, ``pyvalue/universe/decisions/ordinary_share.csv``,
and the load reads the lines of the receipt as lines of the ordinary share.
The file is shipped inside the package, so an installed copy builds the same
universe.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.decision_file import read_decisions, read_packaged, valid_day, valid_isin
from pyvalue.universe.errors import UniverseError

# The component whose `decisions` folder holds the file.
_PACKAGE: str = "pyvalue.universe"

# The columns of the file, in order.
_HEADER: tuple[str, ...] = ("isin", "ordinary_isin", "company", "decided_on", "evidence")


@dataclass(frozen=True, slots=True)
class OrdinaryShare:
    """One decision: this receipt stands for that ordinary share.

    Attributes:
        isin: The receipt, as the funds file it.
        ordinary_isin: The ordinary share its lines are read as.
        company: The company's name, for the reader of the file. The load
            does not use it.
        decided_on: The day the decision was taken.
        evidence: What shows that the first is a receipt and the second its
            ordinary share.
    """

    isin: str
    ordinary_isin: str
    company: str
    decided_on: date
    evidence: str


def _ordinary_share(row: list[str], where: str) -> OrdinaryShare:
    """Turn one row of the file into a decision, or say what is wrong with it."""
    isin, ordinary_isin, company, decided_on, evidence = row
    valid_isin(isin, where, UniverseError)
    valid_isin(ordinary_isin, where, UniverseError)
    if isin == ordinary_isin:
        raise UniverseError(f"{where}: {isin} is given as its own ordinary share")
    # A wrong pair would attach a company to another company's share, and the
    # load cannot notice. So the two columns that only people read, which say
    # who it is and how the pair was confirmed, are required as well.
    if not company.strip() or not evidence.strip():
        raise UniverseError(f"{where}: the company and the evidence must both be filled in")
    return OrdinaryShare(
        isin=isin,
        ordinary_isin=ordinary_isin,
        company=company,
        decided_on=valid_day(decided_on, where, UniverseError),
        evidence=evidence,
    )


def read_ordinary_shares(path: Path) -> tuple[OrdinaryShare, ...]:
    """Read a file of receipts and the ordinary shares they are read as.

    Args:
        path: A comma-separated file with the header
            ``isin,ordinary_isin,company,decided_on,evidence``.

    Returns:
        The decisions, in the order of the file.

    Raises:
        UniverseError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same receipt. The message
            names the row, counting the header as row 1.
    """
    return read_decisions(path, _HEADER, _ordinary_share, UniverseError)


def packaged_ordinary_shares() -> tuple[OrdinaryShare, ...]:
    """Read the decisions shipped inside the installed package."""
    return read_packaged(_PACKAGE, "ordinary_share.csv", read_ordinary_shares)
