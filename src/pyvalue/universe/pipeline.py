"""The universe load from start to finish: obtain the documents, load, write the output.

This is the one function the command line calls (ADR 0009).

Author: Emre Tezel
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyvalue.db import Database
from pyvalue.universe.errors import UniverseError
from pyvalue.universe.exclusions import Exclusion, packaged_exclusions
from pyvalue.universe.funds import FUNDS, FundDefinition, Sponsor, read_pinned_filing
from pyvalue.universe.holdings import FundHoldings, SponsorAdapter
from pyvalue.universe.lei_decisions import LeiDecision, packaged_lei_decisions
from pyvalue.universe.load import LoadResult, load_holdings
from pyvalue.universe.name_decisions import NameDecision, packaged_name_decisions
from pyvalue.universe.ordinary_shares import OrdinaryShare, packaged_ordinary_shares
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
        downloaded: The funds whose filing this run fetched from the SEC. A
            fund whose filing was already in the folder is not listed.
        sponsor_files_downloaded: The funds whose sponsor's own documents
            this run fetched. A fund whose documents were already there is
            not listed.
        result: What the load did to the database.
        output: Where the load output was written.
    """

    downloaded: tuple[FundDefinition, ...]
    sponsor_files_downloaded: tuple[FundDefinition, ...]
    result: LoadResult
    output: OutputFiles


def load_universe(
    database: Database,
    filings_dir: Path,
    output_dir: Path,
    user_agent: Callable[[], str],
    fetch: Fetch = fetch_from_sec,
    lei_decisions: Sequence[LeiDecision] | None = None,
    name_decisions: Sequence[NameDecision] | None = None,
    exclusions: Sequence[Exclusion] | None = None,
    ordinary_shares: Sequence[OrdinaryShare] | None = None,
    *,
    adapters: Mapping[Sponsor, SponsorAdapter],
) -> UniverseLoad:
    """Load the pinned filings of the funds into the database.

    Args:
        database: The database to load into.
        filings_dir: Where the filings are kept. A filing that is missing
            there is downloaded into it.
        output_dir: Where the two output files are written.
        user_agent: Returns the contact string the SEC asks for. It is called
            only if a filing has to be downloaded, so a run on files that are
            already there needs no setting. It is handed to the SEC download
            and to nothing else.
        fetch: What performs a download from the SEC. Tests pass their own.
        lei_decisions: The decisions on legal-entity identifiers to apply.
            Defaults to the ones shipped with the package (ADR 0010); tests
            pass their own.
        name_decisions: The decisions on company names to apply. Defaults
            to the ones shipped with the package (ADR 0012); tests pass
            their own.
        exclusions: The securities to keep out of the universe. Defaults
            to the ones shipped with the package (ADR 0013); tests pass
            their own.
        ordinary_shares: The receipts to read as their ordinary share.
            Defaults to the ones shipped with the package (ADR 0015);
            tests pass their own.
        adapters: The adapter of each fund sponsor, given by name. An adapter obtains the
            sponsor's own documents and turns a filing's lines into common
            holding lines (ADR 0016).

    Returns:
        What was downloaded, what the load did and where its output is.

    Raises:
        FilingError: If a filing cannot be downloaded or is not the pinned one.
        SponsorFileError: If a sponsor's own document cannot be obtained or
            read.
        UniverseError: If a decisions file is invalid, a fund's sponsor has
            no adapter, the load cannot handle a line, or the output cannot be
            written.
        DatabaseError: If the database is not ready or refuses a row.
    """
    # Read before anything is fetched: a broken decisions file should stop the
    # run at once, not after the downloads.
    if lei_decisions is None:
        lei_decisions = packaged_lei_decisions()
    if name_decisions is None:
        name_decisions = packaged_name_decisions()
    if exclusions is None:
        exclusions = packaged_exclusions()
    if ordinary_shares is None:
        ordinary_shares = packaged_ordinary_shares()
    # Asked before anything is fetched, for the same reason.
    for fund in FUNDS:
        if fund.sponsor not in adapters:
            raise UniverseError(f"there is no adapter for the sponsor of {fund.code}")

    downloaded: list[FundDefinition] = []
    sponsor_files_downloaded: list[FundDefinition] = []
    funds: list[FundHoldings] = []
    for fund in FUNDS:
        adapter = adapters[fund.sponsor]
        path = filings_dir / fund.filing_file_name
        if not path.is_file():
            download_filing(fund, path, user_agent(), fetch)
            downloaded.append(fund)
        if adapter.obtain(fund):
            sponsor_files_downloaded.append(fund)
        funds.append(adapter.holdings(fund, read_pinned_filing(path, fund)))

    result = load_holdings(
        database, funds, lei_decisions, name_decisions, exclusions, ordinary_shares
    )
    # Written only after the load is saved, so the files never describe a load
    # that was rolled back.
    output = write_output(result, output_dir)
    return UniverseLoad(
        downloaded=tuple(downloaded),
        sponsor_files_downloaded=tuple(sponsor_files_downloaded),
        result=result,
        output=output,
    )
