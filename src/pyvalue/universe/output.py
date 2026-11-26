"""Write what a load left undone to two files a person or an agent can read.

The files are generated, live under ``data/`` and are never committed. They
describe the latest load only: each run overwrites them, and the same load
writes the same bytes (ADR 0009).

Author: Emre Tezel
"""

from dataclasses import dataclass
from pathlib import Path

from pyvalue.csv_file import write_csv
from pyvalue.universe.errors import UniverseError
from pyvalue.universe.load import AgentCase, LoadResult, NotLoadedLine

LINES_NOT_LOADED_FILE: str = "lines_not_loaded.csv"
CASES_FOR_AGENT_FILE: str = "cases_for_agent.csv"

_LINES_NOT_LOADED_HEADER: tuple[str, ...] = (
    "fund",
    "line",
    "reason",
    "issuer_name",
    "title",
    "isin",
    "lei",
    "category",
    "category_label",
)

_CASES_FOR_AGENT_HEADER: tuple[str, ...] = (
    "fund",
    "line",
    "reason",
    "isin",
    "issuer_name",
    "line_lei",
    "company_id",
    "company_name",
    "company_lei",
    "lei_owner_company_id",
    "lei_owner_company_name",
)


@dataclass(frozen=True, slots=True)
class OutputFiles:
    """Where the output of a load was written.

    Attributes:
        lines_not_loaded: The file listing every line that was not loaded.
        cases_for_agent: The file listing every case for the agent.
    """

    lines_not_loaded: Path
    cases_for_agent: Path


def _not_loaded_row(entry: NotLoadedLine) -> tuple[str, ...]:
    """Return one row of the lines-not-loaded file. An absent value is an empty cell."""
    line = entry.line
    return (
        entry.fund,
        str(line.number),
        entry.reason.value,
        line.issuer_name,
        line.title,
        line.isin or "",
        line.lei or "",
        line.category,
        line.category_label or "",
    )


def _agent_case_row(case: AgentCase) -> tuple[str, ...]:
    """Return one row of the cases-for-agent file. An absent value is an empty cell."""
    owner = case.lei_owner
    return (
        case.fund,
        str(case.line.number),
        case.reason.value,
        case.line.isin or "",
        case.line.issuer_name,
        case.line.lei or "",
        str(case.company.company_id),
        case.company.name,
        case.company.lei or "",
        "" if owner is None else str(owner.company_id),
        "" if owner is None else owner.name,
    )


def write_output(result: LoadResult, folder: Path) -> OutputFiles:
    """Write the two output files of a load.

    Args:
        result: What the load did.
        folder: Where to write; created when missing.

    Returns:
        The paths of the two files.

    Raises:
        UniverseError: If a file cannot be written.
    """
    files = OutputFiles(
        lines_not_loaded=folder / LINES_NOT_LOADED_FILE,
        cases_for_agent=folder / CASES_FOR_AGENT_FILE,
    )
    write_csv(
        files.lines_not_loaded,
        _LINES_NOT_LOADED_HEADER,
        (_not_loaded_row(entry) for entry in result.not_loaded),
        UniverseError,
    )
    write_csv(
        files.cases_for_agent,
        _CASES_FOR_AGENT_HEADER,
        (_agent_case_row(case) for case in result.agent_cases),
        UniverseError,
    )
    return files
