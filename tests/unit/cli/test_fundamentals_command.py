"""Tests for ``pyvalue fundamentals download``.

The command reads and writes under the folder it is run from, so every test
runs it in a temporary folder. No test touches the network: the command is
run against a stand-in for urllib's opener, which answers the account
request and serves the made-up sample payloads of
``tests/fixtures/eodhd_fundamentals``, and records what would have been sent.

Author: Emre Tezel
"""

import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest

from pyvalue.cli import main
from pyvalue.db import Database, Exchange, Provider, ProviderExchange, ProviderListing

# Stands in for a real key in the settings file of a test.
_KEY: str = "sample-api-key-0123456789"

# The account holder of the stand-in. The command must never print it.
_HOLDER: str = "Ada Example"

# Three listings: our exchange, EODHD's code for it, EODHD's symbol, the ISIN
# and the company. The sample payloads have none for the third.
_LISTINGS: tuple[tuple[str, str, str, str, str], ...] = (
    ("XNYS", "US", "ALPH", "US00000A0014", "Alpha Corp"),
    ("XLON", "LSE", "DLT", "GB00000D0016", "Delta PLC"),
    ("XASX", "AU", "MUP", "AU00000M0018", "Mu Property Trust"),
)


class _Response:
    """What urllib hands back for one request: a body and its headers."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = Message()

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


class _Eodhd:
    """Stands in for urllib's opener and for EODHD behind it.

    It answers the account request from a daily count it keeps, serves a
    sample payload by the symbol and code of the request, answers "not
    found" for every other symbol, and records each request.
    """

    def __init__(self, samples: Path, used: int = 0, refuse_with: int | None = None) -> None:
        """Prepare the answers; ``refuse_with`` makes every request fail with a status."""
        self._samples = samples
        self._refuse_with = refuse_with
        self.used = used
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        """Record the request and answer it."""
        self.requests.append(request)
        address = urllib.parse.urlsplit(request.full_url)
        assert address.scheme == "https"
        assert address.hostname == "eodhd.com"
        if self._refuse_with is not None:
            raise urllib.error.HTTPError(
                request.full_url, self._refuse_with, "Unauthorized", Message(), io.BytesIO(b"")
            )
        if address.path == "/api/user":
            # The command reads the real clock. A count dated ahead of it
            # counts as today's, whatever day the test runs on.
            account = {
                "name": _HOLDER,
                "email": "ada@example.invalid",
                "apiRequests": self.used,
                "apiRequestsDate": "2999-12-31",
                "dailyRateLimit": 100000,
                "extraLimit": 74094,
            }
            return _Response(json.dumps(account).encode())
        self.used += 10
        symbol, code = urllib.parse.unquote(address.path.rsplit("/", 1)[-1]).rsplit(".", 1)
        sample = self._samples / f"{code}_{symbol}.json"
        if not sample.is_file():
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", Message(), io.BytesIO(b"")
            )
        return _Response(sample.read_bytes())

    @property
    def asked(self) -> list[str]:
        """The paths that were requested, in order, without the common start."""
        return [
            urllib.parse.urlsplit(request.full_url).path.removeprefix("/api/")
            for request in self.requests
        ]


class _Screen(io.StringIO):
    """Stands in for a terminal on the error stream."""

    def isatty(self) -> bool:
        """Answer as a terminal does."""
        return True


def _install(monkeypatch: pytest.MonkeyPatch, eodhd: _Eodhd) -> None:
    """Make every request of the command go to the stand-in."""

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Eodhd:
        return eodhd

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)


@pytest.fixture
def eodhd(monkeypatch: pytest.MonkeyPatch, fundamentals_samples: Path) -> _Eodhd:
    """Return a stand-in for EODHD that every request of the test goes to."""
    stand_in = _Eodhd(fundamentals_samples)
    _install(monkeypatch, stand_in)
    return stand_in


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a temporary working folder with three listings and a key in its settings.

    It mirrors a checkout after the listing fill: ``data/pyvalue.db`` holds
    the listings and EODHD's symbol for each, and no payload is saved yet.
    """
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    with Database(tmp_path / "data" / "pyvalue.db").unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, code, symbol, isin, name in _LISTINGS:
            work.exchanges.save(Exchange(mic=mic, name=f"Exchange {mic}", country=isin[:2]))
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )
            security = work.instruments.add(work.companies.add(name, None).company_id, isin)
            listing = work.listings.add(security.instrument_id, mic, symbol, "USD")
            work.provider_listings.add(
                ProviderListing(
                    provider_code="eodhd", listing_id=listing.listing_id, provider_symbol=symbol
                )
            )
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.toml").write_text(f'[eodhd]\napi_key = "{_KEY}"\n', encoding="utf-8")
    return tmp_path


def test_download_keeps_the_payloads_and_says_what_it_did(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two of the three listings have a sample payload; EODHD has nothing for the third."""
    capsys.readouterr()

    status = main(["fundamentals", "download"])

    output = capsys.readouterr()
    assert status == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Database: {Path('data') / 'pyvalue.db'}",
        f"Payloads folder: {Path('data') / 'eodhd' / 'fundamentals'}",
        "Listings at EODHD: 3, on 3 of its lines",
        "Already saved: 0",
        "Requested: 3 (30 of the daily allowance)",
        "  Saved: 2",
        "  EODHD has nothing for the symbol: 1",
        "  The answer is not a payload for the symbol: 0",
        "  The request failed: 0",
        "Left for another day: 0",
        "Not reached: 0",
        "Left of today's allowance: 99,970 of 100,000",
        "Listings without a payload are listed in "
        f"{Path('data') / 'fundamentals' / 'not_downloaded.csv'}",
    ]
    payloads = workspace / "data" / "eodhd" / "fundamentals"
    assert sorted(str(path.relative_to(payloads)) for path in payloads.rglob("*.gz")) == [
        "LSE/DLT.json.gz",
        "US/ALPH.json.gz",
    ]
    report = workspace / "data" / "fundamentals" / "not_downloaded.csv"
    assert report.read_text(encoding="utf-8").splitlines()[1:] == [
        "eodhd,AU,MUP,AU00000M0018,Mu Property Trust,not_found,"
    ]


def test_the_account_is_asked_before_the_payloads_and_once_after(
    workspace: Path, eodhd: _Eodhd
) -> None:
    """Between the two, the three lines, which eight threads send in no fixed order."""
    assert main(["fundamentals", "download"]) == 0

    assert (eodhd.asked[0], eodhd.asked[-1]) == ("user", "user")
    assert sorted(eodhd.asked[1:-1]) == [
        "fundamentals/ALPH.US",
        "fundamentals/DLT.LSE",
        "fundamentals/MUP.AU",
    ]


def test_a_second_run_asks_only_for_what_has_no_payload(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """A saved payload is never asked for again."""
    assert main(["fundamentals", "download"]) == 0
    eodhd.requests.clear()
    capsys.readouterr()

    assert main(["fundamentals", "download"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert eodhd.asked == ["user", "fundamentals/MUP.AU", "user"]
    assert lines[3:7] == [
        "Already saved: 2",
        "Requested: 1 (10 of the daily allowance)",
        "  Saved: 0",
        "  EODHD has nothing for the symbol: 1",
    ]


def test_a_run_with_nothing_to_download_needs_no_key_and_makes_no_request(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every listing has its payload: the settings file is not even read."""
    payloads = workspace / "data" / "eodhd" / "fundamentals"
    for _, code, symbol, _, _ in _LISTINGS:
        (payloads / code).mkdir(parents=True, exist_ok=True)
        (payloads / code / f"{symbol}.json.gz").write_bytes(b"what an earlier run kept")
    (workspace / "private" / "config.toml").unlink()
    capsys.readouterr()

    status = main(["fundamentals", "download"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert eodhd.requests == []
    assert lines[3:5] == ["Already saved: 3", "Requested: 0 (0 of the daily allowance)"]
    # The account was not asked, so there is no allowance to state.
    assert not any(line.startswith("Left of today's allowance") for line in lines)


def test_the_key_goes_to_eodhd_and_is_never_printed(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """It travels in the address of each request, and nowhere else."""
    assert main(["fundamentals", "download"]) == 0

    output = capsys.readouterr()
    assert all(f"api_token={_KEY}" in request.full_url for request in eodhd.requests)
    for secret in (_KEY, _HOLDER):
        assert secret not in output.out
        assert secret not in output.err
        for path in (workspace / "data").rglob("*"):
            assert secret not in str(path)
            if path.is_file() and path.suffix == ".csv":
                assert secret not in path.read_text(encoding="utf-8")


def test_an_allowance_that_is_used_up_is_said_and_is_not_an_error(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """The account is 5,000 short of its limit: nothing is requested, and status is 0."""
    eodhd.used = 95_000
    capsys.readouterr()

    status = main(["fundamentals", "download"])

    output = capsys.readouterr()
    lines = output.out.splitlines()
    assert status == 0
    assert output.err == ""
    assert eodhd.asked == ["user"]
    assert "Requested: 0 (0 of the daily allowance)" in lines
    assert "Left for another day: 3" in lines
    assert "Left of today's allowance: 5,000 of 100,000" in lines
    assert lines[-1] == (
        "The day's allowance is used up. Run the command again on a later day; "
        "EODHD's day starts at midnight GMT"
    )


def test_a_key_that_is_not_accepted_stops_the_run_with_one_line_and_status_1(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    fundamentals_samples: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The account request shows it, so no payload is asked for."""
    refusing = _Eodhd(fundamentals_samples, refuse_with=401)
    _install(monkeypatch, refusing)
    capsys.readouterr()

    status = main(["fundamentals", "download"])

    output = capsys.readouterr()
    assert status == 1
    assert refusing.asked == ["user"]
    assert "Not reached: 3" in output.out.splitlines()
    assert output.err == (
        "pyvalue: error: the run stopped: the account request failed: cannot download "
        "https://eodhd.com/api/user?fmt=json: HTTP Error 401: Unauthorized\n"
    )
    assert _KEY not in output.err


def test_download_without_a_key_says_what_to_add(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line, no traceback, status 1, and no request."""
    (workspace / "private" / "config.toml").unlink()
    capsys.readouterr()

    status = main(["fundamentals", "download"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: ")
    assert "api_key" in output.err
    assert eodhd.requests == []


def test_download_without_a_database_says_how_to_create_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line, no traceback, and status 1."""
    monkeypatch.chdir(tmp_path)

    status = main(["fundamentals", "download"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: there is no database at")
    assert "pyvalue db migrate" in output.err


def test_download_takes_another_database_path(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--db`` points the command at another file, as for every database command."""
    other = workspace / "other.db"
    assert main(["db", "migrate", "--db", str(other)]) == 0
    capsys.readouterr()

    assert main(["fundamentals", "download", "--db", str(other)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"Database: {other}"
    assert lines[2] == "Listings at EODHD: 0, on 0 of its lines"
    assert eodhd.requests == []


def test_on_a_terminal_one_bar_is_redrawn_in_place_and_its_line_ended_once(
    workspace: Path,
    eodhd: _Eodhd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing scrolls while the run goes on, and the counts start on a line of their own."""
    screen = _Screen()
    monkeypatch.setattr(sys, "stderr", screen)
    capsys.readouterr()

    assert main(["fundamentals", "download"]) == 0

    drawn = screen.getvalue()
    assert drawn.count("\r") == 3
    assert drawn.count("\n") == 1
    assert drawn.endswith("\n")
    # The last line is padded so that it covers the longer one before it.
    assert drawn.rstrip().endswith("3 of 3  100%")
    assert capsys.readouterr().out.startswith("Database: ")
