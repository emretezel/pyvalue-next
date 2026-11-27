"""Write what the statements load found to a file a person or an agent can read.

The file is generated, lives under ``data/`` and is never committed. It
describes the latest load only: each load overwrites it (ADR 0030). The same
findings always give the same bytes: the rows are sorted, and nothing in a
row depends on the order the companies were read in or on a company id,
which changes when the database is rebuilt.

Author: Emre Tezel
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pyvalue.csv_file import write_csv
from pyvalue.fundamentals.checks import Finding
from pyvalue.fundamentals.errors import FundamentalsError

FINDINGS_FILE: str = "findings.csv"

# The columns, in order. The first four say whose payload a finding is about,
# the next three where in it, the last three what was found.
_HEADER: tuple[str, ...] = (
    "isin",
    "company",
    "provider_exchange_code",
    "provider_symbol",
    "statement",
    "period_end",
    "check",
    "outcome",
    "figure",
    "detail",
)


@dataclass(frozen=True, slots=True)
class Security:
    """A security whose payload is read, as the report names it.

    Attributes:
        isin: Its ISIN.
        company: The company's name.
        provider_exchange_code: The provider's exchange code of its listing.
        provider_symbol: The provider's symbol of its listing.
    """

    isin: str
    company: str
    provider_exchange_code: str
    provider_symbol: str


def _row(finding: Finding, security: Security) -> tuple[str, ...]:
    """Return the cells of one finding."""
    return (
        security.isin,
        security.company,
        security.provider_exchange_code,
        security.provider_symbol,
        "" if finding.statement is None else finding.statement.value,
        "" if finding.period_end is None else finding.period_end.isoformat(),
        finding.check.value,
        finding.outcome.value,
        "" if finding.figure is None else finding.figure.value,
        finding.detail,
    )


def write_findings(
    findings: Iterable[Finding], securities: Mapping[str, Security], folder: Path
) -> Path:
    """Write the report of a load, replacing the one that was there.

    Args:
        findings: Everything the load found, in any order.
        securities: Every security a finding can be about, by ISIN.
        folder: Where to write; created when missing.

    Returns:
        The path of the file.

    Raises:
        FundamentalsError: If the file cannot be written.
    """
    rows = sorted(_row(finding, securities[finding.isin]) for finding in findings)
    path = folder / FINDINGS_FILE
    write_csv(path, _HEADER, rows, FundamentalsError)
    return path
