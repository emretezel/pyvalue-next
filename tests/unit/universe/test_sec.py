"""Tests for ``pyvalue.universe.sec``: downloading a pinned filing.

No test here touches the network. The request itself is tested against a
stand-in for urllib's opener, and the download against a stand-in fetch.

Author: Emre Tezel
"""

import gzip
import io
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest

from pyvalue.universe import FUNDS, FilingError
from pyvalue.universe.sec import SEC_HOST, _NoRedirect, download_filing, fetch_from_sec

_CONTACT: str = "Sample Person sample@example.org"
_URL: str = "https://www.sec.gov/Archives/edgar/data/1/2/primary_doc.xml"


class _Response:
    """What urllib hands back for one request: a body and its headers."""

    def __init__(self, body: bytes, encoding: str | None) -> None:
        self._body = body
        self.headers = Message()
        if encoding is not None:
            self.headers["Content-Encoding"] = encoding

    def read(self) -> bytes:
        """Return the body."""
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None


class _Opener:
    """Stands in for urllib's opener: records the request, answers or fails."""

    def __init__(self, answer: _Response | Exception) -> None:
        self._answer = answer
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        """Record the request and give the prepared answer."""
        assert timeout > 0
        self.requests.append(request)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _install(monkeypatch: pytest.MonkeyPatch, answer: _Response | Exception) -> _Opener:
    """Make ``fetch_from_sec`` talk to a stand-in opener and return it."""
    opener = _Opener(answer)

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Opener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    return opener


def test_the_contact_string_is_sent_as_the_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SEC asks for it in exactly this header."""
    opener = _install(monkeypatch, _Response(b"<filing/>", None))

    body = fetch_from_sec(_URL, _CONTACT)

    (request,) = opener.requests
    assert body == b"<filing/>"
    assert request.full_url == _URL
    assert request.get_header("User-agent") == _CONTACT
    assert request.get_header("Accept-encoding") == "gzip"


def test_a_compressed_answer_is_unpacked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The filings are several megabytes, so they are asked for compressed."""
    _install(monkeypatch, _Response(gzip.compress(b"<filing/>"), "gzip"))

    assert fetch_from_sec(_URL, _CONTACT) == b"<filing/>"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(urllib.error.URLError("no route to host"), id="network"),
        pytest.param(
            urllib.error.HTTPError(_URL, 403, "Forbidden", Message(), io.BytesIO(b"")), id="http"
        ),
        pytest.param(TimeoutError("timed out"), id="timeout"),
    ],
)
def test_a_failed_download_is_reported_without_the_contact_string(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """The message names the address and the cause, and nothing personal."""
    _install(monkeypatch, failure)

    with pytest.raises(FilingError, match="cannot download https://www.sec.gov/") as raised:
        fetch_from_sec(_URL, _CONTACT)

    assert _CONTACT not in str(raised.value)
    assert "sample@example.org" not in str(raised.value)


def test_a_damaged_compressed_answer_is_a_failed_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body that claims to be compressed and is not must not escape as a raw error."""
    _install(monkeypatch, _Response(b"not gzip at all", "gzip"))

    with pytest.raises(FilingError, match="cannot download"):
        fetch_from_sec(_URL, _CONTACT)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(
            "https://example.org/Archives/edgar/data/1/2/primary_doc.xml", id="other host"
        ),
        pytest.param("http://www.sec.gov/Archives/edgar/data/1/2/primary_doc.xml", id="no https"),
        pytest.param("https://www.sec.gov.example.org/primary_doc.xml", id="look-alike host"),
        pytest.param("https://sec.gov@example.org/primary_doc.xml", id="host hidden as a user"),
        pytest.param("file:///etc/hosts", id="a local file"),
    ],
)
def test_no_other_address_is_ever_fetched(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """The contact string goes to www.sec.gov over HTTPS and nowhere else."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(FilingError, match="refusing to fetch"):
        fetch_from_sec(url, _CONTACT)

    assert opener.requests == []


def test_a_redirect_is_never_followed() -> None:
    """urllib would repeat the request, contact string included, at the new address."""
    follow_up = _NoRedirect().redirect_request(
        urllib.request.Request(_URL),
        io.BytesIO(b""),
        302,
        "Found",
        Message(),
        "https://example.org/elsewhere",
    )

    assert follow_up is None


def test_every_request_is_made_with_the_redirect_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard only works if it is in the opener that sends the request."""
    built: list[tuple[type[urllib.request.BaseHandler], ...]] = []
    opener = _Opener(_Response(b"<filing/>", None))

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Opener:
        built.append(handlers)
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    fetch_from_sec(_URL, _CONTACT)

    assert built == [(_NoRedirect,)]


def test_the_only_host_is_the_sec() -> None:
    """A change of this constant is a change of where personal data may go."""
    assert SEC_HOST == "www.sec.gov"


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
