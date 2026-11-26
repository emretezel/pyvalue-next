"""Fixtures shared by the whole pyvalue test suite.

No test touches the real database (``data/pyvalue.db``): every database a test
uses is built here, in pytest's temporary folder.

Author: Emre Tezel
"""

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyvalue.db import Database, migrate
from pyvalue.db.connection import connect
from pyvalue.universe import FUNDS

# The checked-in sample data: tests/fixtures.
_FIXTURES: Path = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Return a path for a temporary database that does not exist yet."""
    return tmp_path / "pyvalue.db"


@pytest.fixture
def migrated_path(database_path: Path) -> Path:
    """Return the path of a temporary database at the latest schema version."""
    migrate(database_path)
    return database_path


@pytest.fixture
def database(migrated_path: Path) -> Database:
    """Return a ``Database`` on a temporary file at the latest schema version.

    This is the door every component uses, so it is the door the tests of the
    components use too (ADR 0008).
    """
    return Database(migrated_path)


@pytest.fixture
def migrated_db(migrated_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection to a temporary database at the latest schema version.

    Only for the tests of ``pyvalue.db`` itself and of the schema. The
    connection is opened the way pyvalue opens every connection: foreign keys
    enforced, no implicit transactions.
    """
    connection = connect(migrated_path)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def nport_samples() -> Path:
    """Return the folder of the sample holdings filings, ``tests/fixtures/nport``.

    The files are named by ticker and described in the folder's README.
    """
    return _FIXTURES / "nport"


@pytest.fixture
def filings_dir(tmp_path: Path, nport_samples: Path) -> Path:
    """Return a temporary folder holding the sample filings as the load expects them.

    Each sample is copied under the file name of the pinned filing it stands
    in for, so a load that reads this folder downloads nothing.
    """
    folder = tmp_path / "sec"
    folder.mkdir()
    for fund in FUNDS:
        shutil.copyfile(nport_samples / f"{fund.code}.xml", folder / fund.filing_file_name)
    return folder
