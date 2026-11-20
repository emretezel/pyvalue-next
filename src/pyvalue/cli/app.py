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
from pyvalue.db import DEFAULT_DATABASE_PATH, DatabaseError, migrate


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
    db_migrate.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        metavar="PATH",
        help=f"the database file (default: {DEFAULT_DATABASE_PATH} in the current folder)",
    )
    db_migrate.set_defaults(run=_db_migrate)
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
    except DatabaseError as error:
        # One line, no traceback: these are conditions a person fixes (a wrong
        # path, an edited migration), not faults in pyvalue.
        print(f"pyvalue: error: {error}", file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
