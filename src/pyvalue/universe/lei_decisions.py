"""Decisions on which legal entity issued a security (ADR 0010).

The funds sometimes file different legal-entity identifiers for the same
security. Where that was looked into, the answer is one row of a committed
file, ``pyvalue/universe/decisions/lei.csv``, and the load applies it. A row
names only an identifier a fund filed (ADR 0011). The file is shipped inside
the package, so an installed copy builds the same universe.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.universe.decision_file import read_decisions, read_packaged, valid_day, valid_isin
from pyvalue.universe.errors import UniverseError
from pyvalue.universe.identifiers import is_valid_lei

# The columns of the file, in order.
_HEADER: tuple[str, ...] = ("isin", "lei", "company", "decided_on", "evidence")


@dataclass(frozen=True, slots=True)
class LeiDecision:
    """One decision: the company that issued this security has this identifier.

    Attributes:
        isin: The security the decision is about.
        lei: The legal-entity identifier of the company that issued it.
        company: The company's name, for the reader of the file. The load
            does not use it.
        decided_on: The day the decision was taken.
        evidence: Why: what the register or another source says.
    """

    isin: str
    lei: str
    company: str
    decided_on: date
    evidence: str


def _decision(row: list[str], where: str) -> LeiDecision:
    """Turn one row of the file into a decision, or say what is wrong with it."""
    isin, lei, company, decided_on, evidence = row
    valid_isin(isin, where)
    if not is_valid_lei(lei):
        raise UniverseError(f"{where}: '{lei}' is not a valid legal-entity identifier")
    # A decision nobody can retrace is worth little, so the two columns that
    # only people read are required as well.
    if not company.strip() or not evidence.strip():
        raise UniverseError(f"{where}: the company and the evidence must both be filled in")
    return LeiDecision(
        isin=isin,
        lei=lei,
        company=company,
        decided_on=valid_day(decided_on, where),
        evidence=evidence,
    )


def read_lei_decisions(path: Path) -> tuple[LeiDecision, ...]:
    """Read a file of decisions on legal-entity identifiers.

    Args:
        path: A comma-separated file with the header
            ``isin,lei,company,decided_on,evidence``.

    Returns:
        The decisions, in the order of the file.

    Raises:
        UniverseError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same security. The message
            names the row, counting the header as row 1.
    """
    return read_decisions(path, _HEADER, _decision)


def packaged_lei_decisions() -> tuple[LeiDecision, ...]:
    """Read the decisions shipped inside the installed package."""
    return read_packaged("lei.csv", read_lei_decisions)
