"""Write the listings a run has no payload for to a file a person can read.

The file is generated, lives under ``data/`` and is never committed. It
describes the latest run only: each run overwrites it (ADR 0028).

Author: Emre Tezel
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pyvalue.csv_file import write_csv
from pyvalue.fundamentals.errors import FundamentalsError

# Relative on purpose, like the database path: the report belongs to the
# folder pyvalue is run from, and `data/` is never committed.
DEFAULT_REPORT_DIR: Path = Path("data") / "fundamentals"

NOT_DOWNLOADED_FILE: str = "not_downloaded.csv"

# The columns, in order. The first three name the provider's line; the next
# two say which security of ours is listed on it.
_HEADER: tuple[str, ...] = (
    "provider_code",
    "provider_exchange_code",
    "provider_symbol",
    "isin",
    "company",
    "reason",
    "detail",
)


@dataclass(frozen=True, slots=True)
class NotDownloaded:
    """One listing that has no saved payload after a run.

    Attributes:
        provider_code: The provider.
        provider_exchange_code: The provider's exchange code of the line.
        provider_symbol: The provider's symbol of the line.
        isin: The ISIN of the security that is listed on the line.
        company: The company's name.
        reason: Why there is no payload, as a code.
        detail: What the provider or the request said, or nothing.
    """

    provider_code: str
    provider_exchange_code: str
    provider_symbol: str
    isin: str
    company: str
    reason: str
    detail: str


def write_not_downloaded(rows: Iterable[NotDownloaded], folder: Path) -> Path:
    """Write the report of a run, replacing the one that was there.

    Args:
        rows: The listings without a payload, in the order to write them.
        folder: Where to write; created when missing.

    Returns:
        The path of the file.

    Raises:
        FundamentalsError: If the file cannot be written.
    """
    path = folder / NOT_DOWNLOADED_FILE
    write_csv(
        path,
        _HEADER,
        (
            (
                row.provider_code,
                row.provider_exchange_code,
                row.provider_symbol,
                row.isin,
                row.company,
                row.reason,
                row.detail,
            )
            for row in rows
        ),
        FundamentalsError,
    )
    return path
