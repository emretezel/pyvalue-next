"""Tests for ``pyvalue.universe.sec``: downloading a pinned filing.

No test here touches the network: the download is tested against a stand-in
fetch. The request itself is tested in ``test_http.py``.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.universe import FUNDS, FilingError
from pyvalue.universe.sec import download_filing

_CONTACT: str = "Sample Person sample@example.org"


def test_a_download_is_kept_under_its_final_name(tmp_path: Path, nport_samples: Path) -> None:
    """The filing is asked for at its pinned address, with the contact string."""
    fund = FUNDS[0]
    destination = tmp_path / "data" / "sec" / fund.filing_file_name
    calls: list[tuple[str, str]] = []

    def fetch(url: str, user_agent: str) -> bytes:
        calls.append((url, user_agent))
        return (nport_samples / "VTI.xml").read_bytes()

    download_filing(fund, destination, _CONTACT, fetch)

    assert calls == [(fund.filing_url, _CONTACT)]
    assert destination.read_bytes() == (nport_samples / "VTI.xml").read_bytes()
    assert sorted(path.name for path in destination.parent.iterdir()) == [fund.filing_file_name]


@pytest.mark.parametrize(
    "sample",
    [
        pytest.param("VXUS.xml", id="the filing of another fund"),
        pytest.param("README.md", id="something that is no filing"),
    ],
)
def test_an_answer_that_is_not_the_pinned_filing_is_not_kept(
    tmp_path: Path, nport_samples: Path, sample: str
) -> None:
    """An error page or a wrong document must never get the filing's name."""
    fund = FUNDS[0]
    destination = tmp_path / "sec" / fund.filing_file_name

    def fetch(url: str, user_agent: str) -> bytes:
        return (nport_samples / sample).read_bytes()

    with pytest.raises(FilingError, match="did not return the pinned VTI filing; nothing was kept"):
        download_filing(fund, destination, _CONTACT, fetch)

    assert list(destination.parent.iterdir()) == []


def test_a_failed_fetch_leaves_nothing_behind(tmp_path: Path) -> None:
    """The fetch's own error passes through, and no file or folder is made."""
    fund = FUNDS[0]
    destination = tmp_path / "sec" / fund.filing_file_name

    def fetch(url: str, user_agent: str) -> bytes:
        raise FilingError("cannot download: no network")

    with pytest.raises(FilingError, match="no network"):
        download_filing(fund, destination, _CONTACT, fetch)

    assert not destination.parent.exists()


def test_a_folder_that_cannot_be_made_is_reported(tmp_path: Path, nport_samples: Path) -> None:
    """A file where the folder should be is a condition to report, not a crash."""
    fund = FUNDS[0]
    blocker = tmp_path / "sec"
    blocker.write_text("a file where a folder is expected")

    def fetch(url: str, user_agent: str) -> bytes:
        return (nport_samples / "VTI.xml").read_bytes()

    with pytest.raises(FilingError, match="cannot save the VTI filing"):
        download_filing(fund, blocker / fund.filing_file_name, _CONTACT, fetch)
