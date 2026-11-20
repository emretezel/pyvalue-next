"""The universe load from start to finish: obtain the filings, load, write the output.

This is the one function the command line calls (ADR 0009).

Author: Emre Tezel
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pyvalue.db import Database
from pyvalue.universe.filings import PINNED_FILINGS, PinnedFiling, read_pinned_filing
from pyvalue.universe.load import FundHoldings, LoadResult, load_holdings
from pyvalue.universe.output import OutputFiles, write_output
from pyvalue.universe.sec import Fetch, download_filing, fetch_from_sec

# Relative on purpose, like the database path: both folders belong to the
# folder pyvalue is run from, under `data/`, which is never committed.
DEFAULT_FILINGS_DIR: Path = Path("data") / "sec"
DEFAULT_OUTPUT_DIR: Path = Path("data") / "universe"


@dataclass(frozen=True, slots=True)
class UniverseLoad:
    """What one run of the universe load did.

    Attributes:
        downloaded: The filings this run fetched from the SEC. Filings that
            were already in the folder are not listed.
        result: What the load did to the database.
        output: Where the load output was written.
    """

    downloaded: tuple[PinnedFiling, ...]
    result: LoadResult
    output: OutputFiles


def load_universe(
    database: Database,
    filings_dir: Path,
    output_dir: Path,
    user_agent: Callable[[], str],
    fetch: Fetch = fetch_from_sec,
) -> UniverseLoad:
    """Load the pinned filings into the database.

    Args:
        database: The database to load into.
        filings_dir: Where the filings are kept. A filing that is missing
            there is downloaded into it.
        output_dir: Where the two output files are written.
        user_agent: Returns the contact string the SEC asks for. It is called
            only if a filing has to be downloaded, so a run on files that are
            already there needs no setting.
        fetch: What performs a download. Tests pass their own.

    Returns:
        What was downloaded, what the load did and where its output is.

    Raises:
        FilingError: If a filing cannot be downloaded or is not the pinned one.
        UniverseError: If the load cannot handle a line, or the output cannot
            be written.
        DatabaseError: If the database is not ready or refuses a row.
    """
    downloaded: list[PinnedFiling] = []
    funds: list[FundHoldings] = []
    for pinned in PINNED_FILINGS:
        path = filings_dir / pinned.file_name
        if not path.is_file():
            download_filing(pinned, path, user_agent(), fetch)
            downloaded.append(pinned)
        funds.append(FundHoldings(ticker=pinned.ticker, lines=read_pinned_filing(path, pinned)))

    result = load_holdings(database, funds)
    # Written only after the load is saved, so the files never describe a load
    # that was rolled back.
    output = write_output(result, output_dir)
    return UniverseLoad(downloaded=tuple(downloaded), result=result, output=output)
