"""Decisions on which legal entity issued a security (ADR 0010).

The holdings filings are sometimes wrong about a company's legal-entity
identifier: an outdated one, a subsidiary's, or another company's altogether.
Where that was found and checked, the answer is one row of a committed file,
``pyvalue/universe/decisions/lei.csv``, and the load applies it. The file is
shipped inside the package, so an installed copy builds the same universe.

A file has no constraints of its own, so this module checks every row.

Author: Emre Tezel
"""

import csv
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from pyvalue.universe.errors import UniverseError
from pyvalue.universe.identifiers import is_valid_isin, is_valid_lei

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
    if len(row) != len(_HEADER):
        raise UniverseError(f"{where} has {len(row)} cells where {len(_HEADER)} are expected")
    isin, lei, company, decided_on, evidence = row
    if not is_valid_isin(isin):
        raise UniverseError(f"{where}: '{isin}' is not a valid ISIN")
    if not is_valid_lei(lei):
        raise UniverseError(f"{where}: '{lei}' is not a valid legal-entity identifier")
    # A decision nobody can retrace is worth little, so the two columns that
    # only people read are required as well.
    if not company.strip() or not evidence.strip():
        raise UniverseError(f"{where}: the company and the evidence must both be filled in")
    try:
        day = date.fromisoformat(decided_on)
    except ValueError as error:
        raise UniverseError(f"{where}: '{decided_on}' is not a date (YYYY-MM-DD)") from error
    return LeiDecision(isin=isin, lei=lei, company=company, decided_on=day, evidence=evidence)


def read_lei_decisions(path: Path) -> tuple[LeiDecision, ...]:
    """Read a decisions file.

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
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise UniverseError(f"cannot read the decisions file {path}: {error}") from error
    if not rows or tuple(rows[0]) != _HEADER:
        raise UniverseError(f"{path}: the first row must be {','.join(_HEADER)}")

    decisions: list[LeiDecision] = []
    seen: dict[str, int] = {}
    for number, row in enumerate(rows[1:], start=2):
        decision = _decision(row, f"{path} row {number}")
        if decision.isin in seen:
            # Two answers for one security: the file must say which one holds.
            raise UniverseError(
                f"{path} row {number}: {decision.isin} was already decided in row "
                f"{seen[decision.isin]}"
            )
        seen[decision.isin] = number
        decisions.append(decision)
    return tuple(decisions)


def packaged_lei_decisions() -> tuple[LeiDecision, ...]:
    """Read the decisions shipped inside the installed package."""
    packaged = resources.files("pyvalue.universe").joinpath("decisions", "lei.csv")
    # as_file gives a real file even if the package were installed zipped.
    with resources.as_file(packaged) as path:
        return read_lei_decisions(path)
