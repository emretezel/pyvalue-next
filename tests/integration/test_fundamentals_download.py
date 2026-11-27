"""End to end: from the sample filings to a saved fundamentals payload per listing.

The five commands run one after the other in a temporary folder: ``db
migrate``, ``universe load``, ``symbols load``, ``listings fill`` and
``fundamentals download`` (ADR 0028). The filings and lists are the made-up
ones the listing fill is tested with, which give six listings, and the
payloads are the ones of ``tests/fixtures/eodhd_fundamentals``.

No request leaves the test: the download is run against a stand-in for
urllib's opener.

Author: Emre Tezel
"""

import gzip
import io
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest

from pyvalue.cli import main
from pyvalue.universe import FUNDS

pytestmark = pytest.mark.integration

# Stands in for a real key in the settings file.
_KEY: str = "sample-api-key-0123456789"

# The six listings of the sample data, as EODHD addresses them.
_LINES: list[str] = ["ALPH-PA.US", "ALPH.US", "BETA.US", "DLT.LSE", "MUP.AU", "THT.XETRA"]


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

    It answers the account request, serves a sample payload by the symbol
    and code of the request, and answers "not found" for a symbol that has
    no sample, as EODHD does for one it has no fundamentals for.
    """

    def __init__(self, samples: Path) -> None:
        """Prepare to serve the sample payloads."""
        self._samples = samples
        self.used = 0
        self.asked: list[str] = []

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        """Record the request and answer it."""
        address = urllib.parse.urlsplit(request.full_url)
        assert address.hostname == "eodhd.com"
        if address.path == "/api/user":
            self.asked.append("account")
            # The command reads the real clock. A count dated ahead of it
            # counts as today's, whatever day the test runs on.
            account = {
                "apiRequests": self.used,
                "apiRequestsDate": "2999-12-31",
                "dailyRateLimit": 100000,
            }
            return _Response(json.dumps(account).encode())
        line = urllib.parse.unquote(address.path.rsplit("/", 1)[-1])
        self.asked.append(line)
        self.used += 10
        symbol, code = line.rsplit(".", 1)
        sample = self._samples / f"{code}_{symbol}.json"
        if not sample.is_file():
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", Message(), io.BytesIO(b"")
            )
        return _Response(sample.read_bytes())


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    nport_samples: Path,
    vanguard_samples: Path,
    listings_samples: Path,
) -> Path:
    """Return a temporary working folder as it is before the first fundamentals download.

    The filings, Vanguard's files and the symbol lists are where the commands
    look for them, the four commands before the download have run, and the
    settings hold a key.
    """
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    for folder in ("sec", "vanguard", "eodhd"):
        (data / folder).mkdir(parents=True)
    for fund in FUNDS:
        shutil.copyfile(nport_samples / f"{fund.code}.xml", data / "sec" / fund.filing_file_name)
        shutil.copyfile(
            vanguard_samples / f"{fund.code}.json", data / "vanguard" / f"{fund.code}.json"
        )
    for sample in sorted(listings_samples.glob("symbols_*.json")):
        shutil.copyfile(sample, data / "eodhd" / sample.name)
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.toml").write_text(f'[eodhd]\napi_key = "{_KEY}"\n', encoding="utf-8")
    for command in (["db", "migrate"], ["universe", "load"], ["symbols", "load"]):
        assert main(command) == 0
    assert main(["listings", "fill"]) == 0
    return tmp_path


@pytest.fixture
def eodhd(monkeypatch: pytest.MonkeyPatch, fundamentals_samples: Path) -> _Eodhd:
    """Return a stand-in for EODHD that every request of the test goes to."""
    stand_in = _Eodhd(fundamentals_samples)

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Eodhd:
        return stand_in

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    return stand_in


def test_every_sample_listing_gets_its_payload_or_a_row_in_the_report(
    workspace: Path,
    eodhd: _Eodhd,
    fundamentals_samples: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Five payloads are kept as they arrived, and the sixth listing is reported."""
    capsys.readouterr()

    assert main(["fundamentals", "download"]) == 0

    payloads = workspace / "data" / "eodhd" / "fundamentals"
    kept = {
        str(path.relative_to(payloads)): gzip.decompress(path.read_bytes())
        for path in payloads.rglob("*.json.gz")
    }
    assert kept == {
        f"{code}/{symbol}.json.gz": (fundamentals_samples / f"{code}_{symbol}.json").read_bytes()
        for code, symbol in (
            ("LSE", "DLT"),
            ("US", "ALPH"),
            ("US", "ALPH-PA"),
            ("US", "BETA"),
            ("XETRA", "THT"),
        )
    }
    # The account before and after; between them the six lines, which eight
    # threads send in no fixed order.
    assert (eodhd.asked[0], eodhd.asked[-1]) == ("account", "account")
    assert sorted(eodhd.asked[1:-1]) == _LINES
    report = workspace / "data" / "fundamentals" / "not_downloaded.csv"
    assert report.read_text(encoding="utf-8").splitlines()[1:] == [
        "eodhd,AU,MUP,AU00000M0018,Mu Property Trust,not_found,"
    ]
    printed = capsys.readouterr().out
    assert "Listings at EODHD: 6, on 6 of its lines\n" in printed
    assert "Requested: 6 (60 of the daily allowance)\n" in printed
    assert "  Saved: 5\n" in printed
    assert "  EODHD has nothing for the symbol: 1\n" in printed


def test_a_second_download_asks_only_for_what_is_missing_and_writes_the_same_report(
    workspace: Path, eodhd: _Eodhd, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproducible: nothing saved is asked for again, and the report has the same bytes."""
    payloads = workspace / "data" / "eodhd" / "fundamentals"
    report = workspace / "data" / "fundamentals" / "not_downloaded.csv"
    assert main(["fundamentals", "download"]) == 0
    first = report.read_bytes()
    files = {path: path.read_bytes() for path in payloads.rglob("*.json.gz")}
    eodhd.asked.clear()
    capsys.readouterr()

    assert main(["fundamentals", "download"]) == 0

    assert eodhd.asked == ["account", "MUP.AU", "account"]
    assert report.read_bytes() == first
    assert {path: path.read_bytes() for path in payloads.rglob("*.json.gz")} == files
    printed = capsys.readouterr().out
    assert "Already saved: 5\n" in printed
    assert "Requested: 1 (10 of the daily allowance)\n" in printed


def test_the_download_never_writes_the_database(workspace: Path, eodhd: _Eodhd) -> None:
    """The listings are read. A saved file is the only record of a download."""
    database = workspace / "data" / "pyvalue.db"
    before = database.read_bytes()

    assert main(["fundamentals", "download"]) == 0

    assert database.read_bytes() == before
