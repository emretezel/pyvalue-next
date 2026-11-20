"""Fixtures shared by the whole pyvalue test suite.

No test touches the real database (``data/pyvalue.db``): every database a test
uses is built here, in pytest's temporary folder.

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyvalue.db import connect, migrate


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Return a path for a temporary database that does not exist yet."""
    return tmp_path / "pyvalue.db"


@pytest.fixture
def migrated_db(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection to a temporary database at the latest schema version.

    The connection is opened the way pyvalue opens every connection: foreign
    keys enforced, no implicit transactions.
    """
    migrate(database_path)
    connection = connect(database_path)
    try:
        yield connection
    finally:
        connection.close()
