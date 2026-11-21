"""The ``pyvalue`` command.

Commands here are thin: they read their arguments, call one function of a
component, and print the outcome. No command contains logic of its own.

Author: Emre Tezel
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pyvalue import __version__
from pyvalue.config import sec_user_agent
from pyvalue.db import DEFAULT_DATABASE_PATH, Database, migrate
from pyvalue.errors import PyvalueError
from pyvalue.universe import (
    DEFAULT_FILINGS_DIR,
    DEFAULT_OUTPUT_DIR,
    PINNED_FILINGS,
    NotLoadedReason,
    load_universe,
)


def _db_migrate(arguments: argparse.Namespace) -> int:
    """Create or upgrade the database and say what was done."""
    path: Path = arguments.db
    report = migrate(path)
    print(f"Database: {report.path}")
    if report.applied:
        for migration in report.applied:
            print(f"Applied {migration.label}")
    else:
        print("Up to date")
    print(f"Schema version: {report.version}")
    return 0


def _universe_load(arguments: argparse.Namespace) -> int:
    """Load the pinned holdings filings and say what was done."""
    database = Database(arguments.db)
    outcome = load_universe(
        database,
        filings_dir=DEFAULT_FILINGS_DIR,
        output_dir=DEFAULT_OUTPUT_DIR,
        # Passed as a function: the settings file is read only if a filing
        # actually has to be downloaded.
        user_agent=sec_user_agent,
    )
    result = outcome.result

    print(f"Database: {database.path}")
    for pinned in PINNED_FILINGS:
        action = "downloaded" if pinned in outcome.downloaded else "already there"
        print(f"Filing {pinned.ticker} {pinned.filing_number}: {action}")
    print(f"Lines read: {result.lines_read:,}")
    print(
        f"Lines not loaded: {len(result.not_loaded):,} "
        f"({result.not_loaded_for(NotLoadedReason.DEBT_OR_DERIVATIVE):,} debt or derivative, "
        f"{result.not_loaded_for(NotLoadedReason.NO_VALID_ISIN):,} without a valid ISIN, "
        f"{result.not_loaded_for(NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED):,} "
        "receipt of a company already loaded)"
    )
    print(
        f"Securities: {result.securities:,}, of which {result.receipts_recognised:,} receipts "
        f"({result.receipts_kept:,} kept as the company's only line, "
        f"{result.receipts_not_loaded:,} not loaded)"
    )
    print(
        f"Added: {result.companies_added:,} companies and {result.instruments_added:,} instruments"
    )
    print(
        f"Joined to an existing company: {result.joined_by_lei:,} by legal-entity identifier, "
        f"{result.joined_by_name:,} by name"
    )
    print(f"Legal-entity identifiers filled in: {result.leis_filled:,}")
    # "Companies corrected: 1" reads right for any count, which "corrected 1
    # companies" did not.
    print(
        f"Decisions on legal-entity identifiers used: {result.lei_decisions_used:,}; "
        f"companies corrected: {result.leis_corrected:,}"
    )
    print(
        f"Decisions on company names used: {result.name_decisions_used:,}; "
        f"companies renamed: {result.companies_renamed:,}"
    )
    print(
        f"The database now holds {result.companies:,} companies and "
        f"{result.instruments:,} instruments"
    )
    print(f"Lines not loaded are listed in {outcome.output.lines_not_loaded}")
    print(
        f"Cases for the agent: {len(result.agent_cases):,}, "
        f"listed in {outcome.output.cases_for_agent}"
    )
    return 0


def _add_database_option(command: argparse.ArgumentParser) -> None:
    """Give a command the ``--db`` option every database command shares."""
    command.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        metavar="PATH",
        help=f"the database file (default: {DEFAULT_DATABASE_PATH} in the current folder)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the ``pyvalue`` command and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="pyvalue",
        description="A value-investing toolkit: stock universe, data-quality checks, screening.",
    )
    parser.add_argument("--version", action="version", version=f"pyvalue {__version__}")
    groups = parser.add_subparsers(dest="group", required=True, metavar="COMMAND")

    db = groups.add_parser("db", help="create and upgrade the database")
    db_commands = db.add_subparsers(dest="command", required=True, metavar="ACTION")
    db_migrate = db_commands.add_parser(
        "migrate",
        help="create the database if it is missing and apply every pending migration",
    )
    _add_database_option(db_migrate)
    db_migrate.set_defaults(run=_db_migrate)

    universe = groups.add_parser("universe", help="build the stock universe")
    universe_commands = universe.add_subparsers(dest="command", required=True, metavar="ACTION")
    universe_load = universe_commands.add_parser(
        "load",
        help="load the companies and securities of the three fund holdings filings",
        description=(
            "Download the three pinned SEC holdings filings if they are not in "
            f"{DEFAULT_FILINGS_DIR} yet, and load their companies and securities into the "
            f"database. The lines that were not loaded and the cases left for an agent are "
            f"written to {DEFAULT_OUTPUT_DIR}. Running it again adds nothing."
        ),
    )
    _add_database_option(universe_load)
    universe_load.set_defaults(run=_universe_load)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``pyvalue`` command.

    Args:
        argv: The arguments after the program name. Defaults to the ones the
            process was started with.

    Returns:
        The process exit status: 0 on success, 1 when the command failed for a
        reason the user can act on. argparse itself exits with 2 on bad usage.
    """
    arguments = build_parser().parse_args(argv)
    try:
        status: int = arguments.run(arguments)
    except PyvalueError as error:
        # One line, no traceback: these are conditions a person fixes (a wrong
        # path, an edited migration, a missing setting), not faults in pyvalue.
        print(f"pyvalue: error: {error}", file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
