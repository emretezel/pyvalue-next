"""Decisions that a security is not part of the universe (ADR 0013).

The funds hold some securities that pyvalue does not want to analyse, such as
a depositary receipt of a company whose ordinary share is listed on its home
exchange. Each such security is one row of a committed file,
``pyvalue/universe/decisions/excluded.csv``, and the load leaves its lines
out. The file is shipped inside the package, so an installed copy builds the
same universe.

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
_HEADER: tuple[str, ...] = ("isin", "company", "decided_on", "evidence")


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One decision: this security is not part of the universe.

    Attributes:
        isin: The security that is kept out.
        company: The company's name, for the reader of the file. The load
            does not use it.
        decided_on: The day the decision was taken.
        evidence: Why the security is kept out.
    """

    isin: str
    company: str
    decided_on: date
    evidence: str


def _exclusion(row: list[str], where: str) -> Exclusion:
    """Turn one row of the file into an exclusion, or say what is wrong with it."""
    isin, company, decided_on, evidence = row
    valid_isin(isin, where, UniverseError)
    # Keeping a security out is a decision someone must be able to retrace,
    # so the two columns that only people read are required as well.
    if not company.strip() or not evidence.strip():
        raise UniverseError(f"{where}: the company and the evidence must both be filled in")
    return Exclusion(
        isin=isin,
        company=company,
        decided_on=valid_day(decided_on, where, UniverseError),
        evidence=evidence,
    )


def read_exclusions(path: Path) -> tuple[Exclusion, ...]:
    """Read a file of securities that are kept out of the universe.

    Args:
        path: A comma-separated file with the header
            ``isin,company,decided_on,evidence``.

    Returns:
        The exclusions, in the order of the file.

    Raises:
        UniverseError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same security. The message
            names the row, counting the header as row 1.
    """
    return read_decisions(path, _HEADER, _exclusion, UniverseError)


def packaged_exclusions() -> tuple[Exclusion, ...]:
    """Read the exclusions shipped inside the installed package."""
    return read_packaged(_PACKAGE, "excluded.csv", read_exclusions)
