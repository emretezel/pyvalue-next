"""Write the securities a run could not fill to a file an agent can read.

The file is generated, lives under ``data/`` and is never committed. It
describes the latest run only: each run overwrites it, and the same database
and decisions give the same bytes (ADR 0026).

Author: Emre Tezel
"""

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from pyvalue.csv_file import write_csv
from pyvalue.listings.errors import ListingsError
from pyvalue.listings.rule import Case

# Relative on purpose, like the database path: the report belongs to the
# folder pyvalue is run from, and `data/` is never committed.
DEFAULT_REPORT_DIR: Path = Path("data") / "listings"

CASES_FOR_AGENT_FILE: str = "cases_for_agent.csv"

# What separates several values in one cell. A ticker can hold a space, a
# dot or a slash, but not this.
_BETWEEN: str = "|"

# The columns, in order (ADR 0026). The three that name a line are the ones a
# decision is written with.
_HEADER: tuple[str, ...] = (
    "isin",
    "company",
    "reason",
    "detail",
    "trading_countries",
    "fund_tickers",
    "fund_currencies",
    "matched_by",
    "provider_code",
    "provider_exchange_code",
    "provider_symbol",
    "mic",
    "provider_name",
    "provider_currency",
    "provider_isin",
)


def _rows(case: Case) -> Iterator[tuple[str, ...]]:
    """Return the rows of one case: one per line it could be, or one without a line."""
    security = case.security
    about = (
        security.isin,
        security.company,
        case.reason.value,
        case.detail,
        _BETWEEN.join(sorted(security.home_countries)),
        _BETWEEN.join(security.tickers),
        _BETWEEN.join(sorted(security.currencies)),
    )
    if not case.lines:
        # A security nothing was found for still has its row: the agent
        # decides `none`, or finds out why the provider does not list it.
        yield (*about, "", "", "", "", "", "", "", "")
    for shown in case.lines:
        stored = shown.line.stored
        yield (
            *about,
            shown.matched_by.value,
            stored.provider_code,
            stored.provider_exchange_code,
            stored.provider_symbol,
            stored.mic,
            stored.provider_name or "",
            stored.provider_currency,
            stored.isin or "",
        )


def case_rows(cases: Iterable[Case]) -> Sequence[tuple[str, ...]]:
    """Return the rows of the report, in the order of the cases and their lines.

    Args:
        cases: The securities for the report.
    """
    return [row for case in cases for row in _rows(case)]


def write_cases(cases: Iterable[Case], folder: Path) -> Path:
    """Write the report of a run, replacing the one that was there.

    Args:
        cases: The securities for the report, in the order to write them.
        folder: Where to write; created when missing.

    Returns:
        The path of the file.

    Raises:
        ListingsError: If the file cannot be written.
    """
    path = folder / CASES_FOR_AGENT_FILE
    write_csv(path, _HEADER, case_rows(cases), ListingsError)
    return path
