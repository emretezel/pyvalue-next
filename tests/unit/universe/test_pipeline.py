"""Tests for ``pyvalue.universe.pipeline``: obtaining the filings around a load.

What the load does with the lines is tested in ``test_load.py`` and, end to
end, in ``tests/integration/test_universe_load.py``. These tests are about the
files: which are downloaded, which are reused, and what is asked of the SEC.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.db import Database
from pyvalue.universe import PINNED_FILINGS, FilingError, load_universe

_CONTACT: str = "Sample Person sample@example.org"


def _never_asked() -> str:
    """Stand in for the settings; fails the test if the contact string is requested."""
    pytest.fail("the contact string was requested although nothing had to be downloaded")


def _never_fetched(url: str, user_agent: str) -> bytes:
    """Stand in for the network; fails the test if anything is fetched."""
    pytest.fail(f"{url} was fetched although the filing was already there")


def test_filings_that_are_there_are_used_without_asking_for_anything(
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """ADR 0009: a later run needs neither the network nor the contact line."""
    outcome = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
    )

    assert outcome.downloaded == ()
    assert outcome.result.lines_read == 31
    assert outcome.output.lines_not_loaded == tmp_path / "universe" / "lines_not_loaded.csv"
    assert outcome.output.cases_for_agent.is_file()


def test_missing_filings_are_downloaded_once_and_kept(
    database: Database, nport_samples: Path, tmp_path: Path
) -> None:
    """Each pinned filing is fetched at its own address, with the contact string."""
    filings_dir = tmp_path / "sec"
    by_url = {pinned.url: nport_samples / f"{pinned.ticker}.xml" for pinned in PINNED_FILINGS}
    calls: list[tuple[str, str]] = []

    def fetch(url: str, user_agent: str) -> bytes:
        calls.append((url, user_agent))
        return by_url[url].read_bytes()

    outcome = load_universe(database, filings_dir, tmp_path / "universe", lambda: _CONTACT, fetch)

    assert outcome.downloaded == PINNED_FILINGS
    assert calls == [(pinned.url, _CONTACT) for pinned in PINNED_FILINGS]
    assert sorted(path.name for path in filings_dir.iterdir()) == sorted(
        pinned.file_name for pinned in PINNED_FILINGS
    )

    # The second run finds all three and fetches nothing.
    again = load_universe(
        database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched
    )

    assert again.downloaded == ()
    assert again.result.instruments_added == 0


def test_only_the_missing_filing_is_downloaded(
    database: Database, filings_dir: Path, nport_samples: Path, tmp_path: Path
) -> None:
    """A folder that holds two of the three costs one request."""
    missing = PINNED_FILINGS[1]
    (filings_dir / missing.file_name).unlink()
    calls: list[str] = []

    def fetch(url: str, user_agent: str) -> bytes:
        calls.append(url)
        return (nport_samples / "VXUS.xml").read_bytes()

    outcome = load_universe(database, filings_dir, tmp_path / "universe", lambda: _CONTACT, fetch)

    assert outcome.downloaded == (missing,)
    assert calls == [missing.url]


def test_a_failed_download_stops_the_run_before_the_database_is_touched(
    database: Database, tmp_path: Path
) -> None:
    """No filing, no load: the tables stay empty and no output is written."""

    def fetch(url: str, user_agent: str) -> bytes:
        raise FilingError(f"cannot download {url}: no network")

    with pytest.raises(FilingError, match="no network"):
        load_universe(database, tmp_path / "sec", tmp_path / "universe", lambda: _CONTACT, fetch)

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
    assert not (tmp_path / "universe").exists()


def test_a_wrong_file_under_a_pinned_name_stops_the_run(
    database: Database, filings_dir: Path, tmp_path: Path
) -> None:
    """A file that is there is trusted only as far as its own content confirms the pin."""
    vti, vxus, _ = PINNED_FILINGS
    (filings_dir / vti.file_name).write_bytes((filings_dir / vxus.file_name).read_bytes())

    with pytest.raises(FilingError, match="is not the pinned VTI filing"):
        load_universe(database, filings_dir, tmp_path / "universe", _never_asked, _never_fetched)

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
