"""Fixtures shared by the whole pyvalue test suite.

No test touches the real database (``data/pyvalue.db``): every database a test
uses is built here, in pytest's temporary folder. And no test reaches the
network: a fixture that applies to every test makes any real request fail.

Author: Emre Tezel
"""

import shutil
import sqlite3
import urllib.request
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from pyvalue.db import Database, Exchange, migrate
from pyvalue.db.connection import connect
from pyvalue.listings import read_exchanges
from pyvalue.providers import ExchangeCodes, read_exchange_codes
from pyvalue.universe import FUNDS, Sponsor, SponsorAdapter, VanguardAdapter

# The checked-in sample data: tests/fixtures.
_FIXTURES: Path = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every real request fail, in every test.

    Every download of pyvalue goes through one opener built by urllib. A test
    of a download installs its own stand-in over this one; any other test
    that would reach the network fails here instead of quietly fetching.
    """

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> urllib.request.OpenerDirector:
        pytest.fail("a test tried to reach the network")

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)


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


@pytest.fixture
def eodhd_samples() -> Path:
    """Return the folder of the sample EODHD lists, ``tests/fixtures/eodhd``.

    The files are made up in the provider's shape and described in the
    folder's README.
    """
    return _FIXTURES / "eodhd"


@pytest.fixture
def eodhd_lists_dir(tmp_path: Path, eodhd_samples: Path) -> Path:
    """Return a temporary folder holding the sample EODHD lists as the load expects them.

    It stands in for ``data/eodhd`` after a download: the exchange list and
    the symbol lists of three codes.
    """
    folder = tmp_path / "eodhd"
    folder.mkdir()
    for sample in sorted(eodhd_samples.glob("*.json")):
        shutil.copyfile(sample, folder / sample.name)
    return folder


@pytest.fixture
def sample_exchanges(eodhd_samples: Path) -> tuple[Exchange, ...]:
    """Return the five exchanges that go with the sample EODHD lists."""
    return read_exchanges(eodhd_samples / "exchange.csv")


@pytest.fixture
def sample_codes(eodhd_samples: Path) -> ExchangeCodes:
    """Return the provider's exchange file that goes with the sample EODHD lists."""
    return read_exchange_codes(eodhd_samples / "eodhd_exchange.csv")


@pytest.fixture
def listings_samples() -> Path:
    """Return the folder of the sample lists for the listing fill, ``tests/fixtures/listings``.

    The lists go with the sample holdings filings and are described in the
    folder's README.
    """
    return _FIXTURES / "listings"


@pytest.fixture
def vanguard_samples() -> Path:
    """Return the folder of the sample Vanguard holdings files, ``tests/fixtures/vanguard``.

    The files are named by fund code and described in the folder's README.
    """
    return _FIXTURES / "vanguard"


@pytest.fixture
def vanguard_dir(tmp_path: Path, vanguard_samples: Path) -> Path:
    """Return a temporary folder holding the sample Vanguard files as the load expects them.

    So a load that reads this folder downloads nothing from Vanguard.
    """
    folder = tmp_path / "vanguard"
    folder.mkdir()
    for fund in FUNDS:
        shutil.copyfile(vanguard_samples / f"{fund.code}.json", folder / f"{fund.code}.json")
    return folder


@pytest.fixture
def adapters(vanguard_dir: Path) -> Mapping[Sponsor, SponsorAdapter]:
    """Return the sponsor adapters of a load on the sample documents.

    The Vanguard adapter reads the sample files and fails the test if it is
    asked to fetch anything: every file is already there.
    """

    def never_fetched(url: str) -> bytes:
        pytest.fail(f"{url} was fetched")

    return {Sponsor.VANGUARD: VanguardAdapter(vanguard_dir, never_fetched)}
