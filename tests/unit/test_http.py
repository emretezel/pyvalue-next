"""Tests for the requests pyvalue sends: ``pyvalue.http`` and the fetches built on it.

No test here touches the network. A request is tested against a stand-in for
urllib's opener, which records what would have been sent.

Author: Emre Tezel
"""

import gzip
import http.client
import io
import urllib.error
import urllib.request
from email.message import Message
from types import TracebackType
from typing import Self

import pytest

from pyvalue.errors import PyvalueError
from pyvalue.http import _NoRedirect, fetch_https
from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import (
    EODHD_HOST,
    ListNotFoundError,
    exchange_list_url,
    fetch_from_eodhd,
    symbol_list_url,
)
from pyvalue.universe import FilingError, SponsorFileError, UniverseError
from pyvalue.universe.sec import SEC_HOST, fetch_from_sec
from pyvalue.universe.vanguard_file import VANGUARD_HOST, fetch_from_vanguard

_CONTACT: str = "Sample Person sample@example.org"
_HOST: str = "data.example.org"
# Stands in for an API key. The space and the ampersand are there on purpose: a
# key must not be able to break out of its place in the address.
_KEY: str = "sample key&0123456789"
_KEY_SENT: str = "sample+key%260123456789"
_URL: str = "https://data.example.org/files/one.json"
_SEC_URL: str = "https://www.sec.gov/Archives/edgar/data/1/2/primary_doc.xml"
_VANGUARD_URL: str = (
    "https://investor.vanguard.com/vmf/api/0970/portfolio-holding/stock.json?start=1&count=500"
)


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
    """Make every fetch talk to a stand-in opener and return it."""
    opener = _Opener(answer)

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Opener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    return opener


# --- The shared fetch ------------------------------------------------------------------------


def test_the_headers_are_sent_and_a_compressed_answer_is_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller's headers go out as given, plus the request for compression."""
    opener = _install(monkeypatch, _Response(b"{}", None))

    body = fetch_https(_URL, _HOST, {"User-Agent": "someone", "Accept": "text/x"}, UniverseError)

    (request,) = opener.requests
    assert body == b"{}"
    assert request.full_url == _URL
    assert dict(request.header_items()) == {
        "User-agent": "someone",
        "Accept": "text/x",
        "Accept-encoding": "gzip",
    }


def test_a_compressed_answer_is_unpacked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The filings are several megabytes, so they are asked for compressed."""
    _install(monkeypatch, _Response(gzip.compress(b"<filing/>"), "gzip"))

    assert fetch_https(_URL, _HOST, {}, UniverseError) == b"<filing/>"


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
def test_a_failed_download_is_reported_with_the_address_and_never_a_header(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """The message names the address and the cause, and nothing that was sent."""
    _install(monkeypatch, failure)

    with pytest.raises(UniverseError, match="cannot download https://data.example.org/") as raised:
        fetch_https(_URL, _HOST, {"User-Agent": _CONTACT}, UniverseError)

    assert _CONTACT not in str(raised.value)
    assert "sample@example.org" not in str(raised.value)


def test_a_damaged_compressed_answer_is_a_failed_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body that claims to be compressed and is not must not escape as a raw error."""
    _install(monkeypatch, _Response(b"not gzip at all", "gzip"))

    with pytest.raises(UniverseError, match="cannot download"):
        fetch_https(_URL, _HOST, {}, UniverseError)


@pytest.mark.parametrize(
    "error", [FilingError, SponsorFileError], ids=["a filing", "a sponsor file"]
)
def test_the_error_is_the_callers_own(
    monkeypatch: pytest.MonkeyPatch, error: type[UniverseError]
) -> None:
    """A failed filing download and a failed sponsor file read as what they are."""
    _install(monkeypatch, urllib.error.URLError("no route to host"))

    with pytest.raises(error, match="cannot download"):
        fetch_https(_URL, _HOST, {}, error)
    with pytest.raises(error, match="refusing to fetch"):
        fetch_https("https://elsewhere.example.org/x", _HOST, {}, error)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://example.org/files/one.json", id="other host"),
        pytest.param("http://data.example.org/files/one.json", id="no https"),
        pytest.param("https://data.example.org.evil.example/one.json", id="look-alike host"),
        pytest.param("https://data.example.org@evil.example/one.json", id="host hidden as a user"),
        pytest.param("file:///etc/hosts", id="a local file"),
    ],
)
def test_no_other_address_is_ever_fetched(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """A request goes to the named host over HTTPS and nowhere else."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(UniverseError, match="refusing to fetch .* only https://data.example.org/"):
        fetch_https(url, _HOST, {"User-Agent": _CONTACT}, UniverseError)

    assert opener.requests == []


def test_a_redirect_is_never_followed() -> None:
    """urllib would repeat the request, headers included, at the new address."""
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
    opener = _Opener(_Response(b"{}", None))

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Opener:
        built.append(handlers)
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    fetch_https(_URL, _HOST, {}, UniverseError)
    fetch_from_sec(_SEC_URL, _CONTACT)
    fetch_from_vanguard(_VANGUARD_URL)
    fetch_from_eodhd(symbol_list_url("KO"), _KEY)

    assert built == [(_NoRedirect,)] * 4


# --- Secret parts of an address --------------------------------------------------------------


class _RequestError(PyvalueError):
    """Stands in for a caller's own error."""


class _NothingThereError(_RequestError):
    """Stands in for a caller's error for a document the host does not have."""


def test_a_secret_part_is_added_to_the_address_that_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider takes its key as part of the address, so that is where it goes."""
    opener = _install(monkeypatch, _Response(b"[]", None))

    fetch_https(_URL, _HOST, {}, _RequestError, secret_query={"api_token": _KEY})

    (request,) = opener.requests
    assert request.full_url == f"{_URL}?api_token={_KEY_SENT}"


def test_a_secret_part_joins_the_parts_the_address_already_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An address with a query keeps it."""
    opener = _install(monkeypatch, _Response(b"[]", None))

    fetch_https(f"{_URL}?fmt=json", _HOST, {}, _RequestError, secret_query={"api_token": _KEY})

    (request,) = opener.requests
    assert request.full_url == f"{_URL}?fmt=json&api_token={_KEY_SENT}"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(urllib.error.URLError("no route to host"), id="network"),
        pytest.param(
            urllib.error.HTTPError(
                f"{_URL}?api_token={_KEY_SENT}", 401, "Unauthorized", Message(), io.BytesIO(b"")
            ),
            id="refused",
        ),
        pytest.param(TimeoutError("timed out"), id="timeout"),
        pytest.param(
            # What the standard library raises for an address it will not send:
            # its text quotes the address, secret included.
            http.client.InvalidURL(
                f"URL can't contain control characters. '/files/one.json?api_token={_KEY}'"
            ),
            id="an address the library refuses, quoted plainly",
        ),
        pytest.param(
            http.client.InvalidURL(f"nonnumeric port in '/one.json?api_token={_KEY_SENT}'"),
            id="an address the library refuses, quoted as sent",
        ),
    ],
)
def test_a_secret_part_is_in_no_message_whatever_fails(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """The message names the address without its secret parts, and a cleaned cause."""
    _install(monkeypatch, failure)

    with pytest.raises(_RequestError, match="cannot download https://data.example.org/") as raised:
        fetch_https(_URL, _HOST, {}, _RequestError, secret_query={"api_token": _KEY})

    message = str(raised.value)
    assert _KEY not in message
    assert _KEY_SENT not in message
    # The cause may quote the address that was requested, and a traceback
    # would print it, so it is not kept.
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_a_refused_address_is_reported_without_the_secret_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host check runs on the address before the secret is added."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(_RequestError, match="refusing to fetch") as raised:
        fetch_https(
            "https://elsewhere.example.org/x",
            _HOST,
            {},
            _RequestError,
            secret_query={"api_token": _KEY},
        )

    assert opener.requests == []
    assert _KEY not in str(raised.value)
    assert _KEY_SENT not in str(raised.value)


def test_a_failure_without_a_secret_keeps_its_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing secret was sent, so the cause stays for whoever reads a traceback."""
    failure = urllib.error.URLError("no route to host")
    _install(monkeypatch, failure)

    with pytest.raises(_RequestError) as raised:
        fetch_https(_URL, _HOST, {}, _RequestError)

    assert raised.value.__cause__ is failure


def test_an_address_the_library_refuses_is_a_failed_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It must not escape as a raw error: the command line prints only pyvalue's own."""
    _install(monkeypatch, http.client.InvalidURL("URL can't contain control characters."))

    with pytest.raises(_RequestError, match="cannot download"):
        fetch_https(_URL, _HOST, {}, _RequestError)


# --- A document the host does not have -------------------------------------------------------


def _answered(status: int) -> urllib.error.HTTPError:
    """Return the error urllib raises when a host answers with a failure status."""
    return urllib.error.HTTPError(_URL, status, "No", Message(), io.BytesIO(b""))


def test_not_found_is_told_apart_when_the_caller_asks_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider answers so for a list that is not in the subscription."""
    _install(monkeypatch, _answered(404))

    with pytest.raises(_NothingThereError, match="cannot download"):
        fetch_https(_URL, _HOST, {}, _RequestError, not_found=_NothingThereError)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_every_other_answer_is_the_ordinary_failure(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """Only "not found" has a meaning of its own."""
    _install(monkeypatch, _answered(status))

    with pytest.raises(_RequestError) as raised:
        fetch_https(_URL, _HOST, {}, _RequestError, not_found=_NothingThereError)

    assert not isinstance(raised.value, _NothingThereError)


def test_not_found_is_an_ordinary_failure_for_a_caller_that_does_not_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A filing that is not there is a failed download like any other."""
    _install(monkeypatch, _answered(404))

    with pytest.raises(UniverseError, match="cannot download"):
        fetch_https(_URL, _HOST, {}, UniverseError)


# --- The SEC ---------------------------------------------------------------------------------


def test_the_contact_string_is_sent_to_the_sec_as_the_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SEC asks for it in exactly this header."""
    opener = _install(monkeypatch, _Response(b"<filing/>", None))

    body = fetch_from_sec(_SEC_URL, _CONTACT)

    (request,) = opener.requests
    assert body == b"<filing/>"
    assert request.full_url == _SEC_URL
    assert request.get_header("User-agent") == _CONTACT
    assert request.get_header("Accept-encoding") == "gzip"


def test_the_only_host_of_the_contact_string_is_the_sec() -> None:
    """A change of this constant is a change of where personal data may go."""
    assert SEC_HOST == "www.sec.gov"


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(_VANGUARD_URL, id="the sponsor's host"),
        pytest.param("https://example.org/Archives/primary_doc.xml", id="other host"),
        pytest.param("http://www.sec.gov/Archives/primary_doc.xml", id="no https"),
        pytest.param("https://www.sec.gov.example.org/primary_doc.xml", id="look-alike host"),
        pytest.param("https://sec.gov@example.org/primary_doc.xml", id="host hidden as a user"),
    ],
)
def test_the_contact_string_goes_nowhere_but_the_sec(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """Not even to the sponsor whose file the same load downloads."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(FilingError, match="refusing to fetch"):
        fetch_from_sec(url, _CONTACT)

    assert opener.requests == []


def test_a_failed_sec_download_is_a_filing_error_without_the_contact_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the command line prints names the address, not the person."""
    _install(monkeypatch, urllib.error.URLError("no route to host"))

    with pytest.raises(FilingError, match="cannot download https://www.sec.gov/") as raised:
        fetch_from_sec(_SEC_URL, _CONTACT)

    assert _CONTACT not in str(raised.value)


# --- Vanguard --------------------------------------------------------------------------------


def test_vanguard_is_sent_a_plain_client_name_and_nothing_personal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fetch takes an address only, so no contact string can travel with it."""
    opener = _install(monkeypatch, _Response(b'{"size": 0}', None))

    body = fetch_from_vanguard(_VANGUARD_URL)

    (request,) = opener.requests
    assert body == b'{"size": 0}'
    assert request.full_url == _VANGUARD_URL
    assert dict(request.header_items()) == {
        "User-agent": "pyvalue",
        "Accept": "application/json",
        "Accept-encoding": "gzip",
    }


def test_the_only_host_of_the_sponsor_file_is_vanguards() -> None:
    """The file is fetched from the site that serves Vanguard's fund pages."""
    assert VANGUARD_HOST == "investor.vanguard.com"


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(_SEC_URL, id="the SEC"),
        pytest.param("http://investor.vanguard.com/vmf/api/0970/x.json", id="no https"),
        pytest.param("https://api.vanguard.com/rs/ire/01/ind/fund/0970/x", id="another host"),
        pytest.param("https://investor.vanguard.com.example.org/x.json", id="look-alike host"),
    ],
)
def test_vanguards_file_is_fetched_from_its_own_host_only(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """The file itself names another host for its next page; that address is never used."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(SponsorFileError, match="refusing to fetch"):
        fetch_from_vanguard(url)

    assert opener.requests == []


def test_a_failed_vanguard_download_is_a_sponsor_file_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run stops with one line that names the address and the cause."""
    _install(monkeypatch, urllib.error.URLError("no route to host"))

    with pytest.raises(SponsorFileError, match="cannot download https://investor.vanguard.com/"):
        fetch_from_vanguard(_VANGUARD_URL)


# --- EODHD -----------------------------------------------------------------------------------


def test_the_two_list_addresses_carry_no_key() -> None:
    """An address is safe to print: the key is added only when the request is made."""
    assert exchange_list_url() == "https://eodhd.com/api/exchanges-list/?fmt=json"
    assert symbol_list_url("US") == "https://eodhd.com/api/exchange-symbol-list/US?fmt=json"


def test_an_exchange_code_cannot_change_the_address() -> None:
    """A code comes from a committed file, and is escaped all the same."""
    assert (
        symbol_list_url("US/../x?y=1")
        == "https://eodhd.com/api/exchange-symbol-list/US%2F..%2Fx%3Fy%3D1?fmt=json"
    )


def test_the_key_is_sent_to_eodhd_in_the_address_with_a_plain_client_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EODHD takes the key as a part of the address, and nothing personal goes with it."""
    opener = _install(monkeypatch, _Response(b"[]", None))

    body = fetch_from_eodhd(symbol_list_url("KO"), _KEY)

    (request,) = opener.requests
    assert body == b"[]"
    assert request.full_url == (
        f"https://eodhd.com/api/exchange-symbol-list/KO?fmt=json&api_token={_KEY_SENT}"
    )
    assert dict(request.header_items()) == {
        "User-agent": "pyvalue",
        "Accept": "application/json",
        "Accept-encoding": "gzip",
    }


def test_the_only_host_of_the_key_is_eodhds() -> None:
    """A change of this constant is a change of where a credential may go."""
    assert EODHD_HOST == "eodhd.com"


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(_SEC_URL, id="the SEC"),
        pytest.param(_VANGUARD_URL, id="the sponsor's host"),
        pytest.param("http://eodhd.com/api/exchanges-list/?fmt=json", id="no https"),
        pytest.param("https://eodhd.com.example.org/api/exchanges-list/", id="look-alike host"),
        pytest.param(
            "https://eodhd.com@example.org/api/exchanges-list/", id="host hidden as a user"
        ),
        pytest.param(
            "https://api.eodhd.com/api/exchanges-list/", id="another host of the provider"
        ),
    ],
)
def test_the_key_goes_nowhere_but_eodhd(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """Whatever address is passed, a request with the key is made to one host only."""
    opener = _install(monkeypatch, _Response(b"", None))

    with pytest.raises(ProviderError, match="refusing to fetch") as raised:
        fetch_from_eodhd(url, _KEY)

    assert opener.requests == []
    assert _KEY not in str(raised.value)


def test_a_list_that_is_not_there_has_an_error_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EODHD answers "not found" for an exchange that is not in the subscription."""
    _install(monkeypatch, _answered(404))

    with pytest.raises(ListNotFoundError, match="cannot download https://eodhd.com/") as raised:
        fetch_from_eodhd(symbol_list_url("KO"), _KEY)

    assert _KEY not in str(raised.value)
    assert _KEY_SENT not in str(raised.value)


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_a_refused_request_is_a_provider_error_without_the_key(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """A key that is not accepted, or a limit that is reached, is not "not found"."""
    _install(monkeypatch, _answered(status))

    with pytest.raises(ProviderError, match="cannot download https://eodhd.com/") as raised:
        fetch_from_eodhd(symbol_list_url("KO"), _KEY)

    assert not isinstance(raised.value, ListNotFoundError)
    assert _KEY not in str(raised.value)
    assert _KEY_SENT not in str(raised.value)
    assert raised.value.__cause__ is None
