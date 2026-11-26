"""Tests for ``pyvalue symbols load`` and ``pyvalue symbols download``.

The commands read and write under the folder they are run from, so every test
runs them in a temporary folder. They use the exchange files shipped with
pyvalue and the made-up sample lists of ``tests/fixtures/eodhd``.

No test touches the network. The load could not: it only reads files. The
download is run against a stand-in for urllib's opener, which answers from
the sample lists and records what would have been sent.

Author: Emre Tezel
"""

import io
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
from pyvalue.providers import packaged_exchange_codes
from pyvalue.providers.eodhd import EXCHANGE_FILE

# Stands in for a real key in the settings file of a test.
_KEY: str = "sample-api-key-0123456789"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eodhd_samples: Path) -> Path:
    """Return a temporary working folder with a migrated database and three saved lists.

    It mirrors a checkout after ``pyvalue db migrate`` and a download of the
    lists of ``KO``, ``LSE`` and ``US``: ``data/pyvalue.db`` and
    ``data/eodhd/``. The settings file holds a key, which the load must
    never read.
    """
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    lists = tmp_path / "data" / "eodhd"
    lists.mkdir()
    for sample in sorted(eodhd_samples.glob("*.json")):
        shutil.copyfile(sample, lists / sample.name)
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.toml").write_text(f'[eodhd]\napi_key = "{_KEY}"\n', encoding="utf-8")
    return tmp_path


def _without_a_list() -> list[str]:
    """Return the codes of the shipped file for which the workspace has no saved list."""
    codes = packaged_exchange_codes(EXCHANGE_FILE).codes_with_a_market()
    return [code for code in codes if code not in ("KO", "LSE", "US")]


def test_load_fills_the_tables_and_says_what_it_did(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The numbers of the sample lists (tests/fixtures/eodhd/README.md)."""
    capsys.readouterr()

    status = main(["symbols", "load"])

    output = capsys.readouterr()
    missing = _without_a_list()
    assert status == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Database: {Path('data') / 'pyvalue.db'}",
        "Exchanges: 61 (61 added, 0 corrected)",
        "EODHD exchange codes: 61 (61 added)",
        "Lists stored: 3 of 59, 12 lines",
        "  KO: 4 lines",
        "  LSE: 4 lines",
        "  US: 4 lines",
        "Lines not stored: 3 not a share (ETF 2, FUND 1), 1 without a symbol, "
        "1 without a currency, 1 under a venue label that is left out",
        "Lines stored without an ISIN: 4, of which 1 carried one that is not valid",
        f"Codes without a saved list: 56 ({', '.join(missing)})",
        "Lists not stored: 0",
    ]


def test_a_second_load_adds_nothing_and_stores_the_same(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running it again changes nothing."""
    assert main(["symbols", "load"]) == 0
    first = capsys.readouterr().out.splitlines()

    assert main(["symbols", "load"]) == 0

    second = capsys.readouterr().out.splitlines()
    assert second[1:3] == [
        "Exchanges: 61 (0 added, 0 corrected)",
        "EODHD exchange codes: 61 (0 added)",
    ]
    assert second[3:] == first[3:]


def test_a_list_that_cannot_be_stored_is_named_with_what_to_act_on(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command still succeeds: the other lists are stored, and this one is reported."""
    (workspace / "data" / "eodhd" / "symbols_KO.json").write_text("Unauthorized", encoding="utf-8")
    capsys.readouterr()

    status = main(["symbols", "load"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert "Lists stored: 2 of 59, 8 lines" in lines
    assert lines[-2] == "Lists not stored: 1"
    assert lines[-1].startswith("  KO: the saved file is not a symbol list (")
    assert "symbols_KO.json is not an EODHD symbol list" in lines[-1]


def test_load_works_before_any_list_was_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A new checkout: the exchange tables are filled, and every code lacks its list."""
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    capsys.readouterr()

    status = main(["symbols", "load"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert lines[1:4] == [
        "Exchanges: 61 (61 added, 0 corrected)",
        "EODHD exchange codes: 61 (61 added)",
        "Lists stored: 0 of 59, 0 lines",
    ]
    assert lines[-2].startswith("Codes without a saved list: 59 (AS, AT, AU, ")
    assert lines[-1] == "Lists not stored: 0"


def test_load_never_reads_the_key_and_never_prints_it(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The settings file holds a key; the load has no use for it."""
    assert main(["symbols", "load"]) == 0

    output = capsys.readouterr()
    assert _KEY not in output.out
    assert _KEY not in output.err


def test_load_without_a_database_says_how_to_create_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line, no traceback, and status 1."""
    monkeypatch.chdir(tmp_path)

    status = main(["symbols", "load"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: there is no database at")
    assert "pyvalue db migrate" in output.err


def test_load_takes_another_database_path(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--db`` points the command at another file, as for every database command."""
    other = workspace / "other.db"
    assert main(["db", "migrate", "--db", str(other)]) == 0
    capsys.readouterr()

    assert main(["symbols", "load", "--db", str(other)]) == 0

    assert capsys.readouterr().out.splitlines()[0] == f"Database: {other}"


# --- The download ------------------------------------------------------------------------------


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

    It serves the sample lists by the path of the request, answers "not
    found" for every other list, and records each request.
    """

    def __init__(self, samples: Path, refuse_with: int | None = None) -> None:
        """Prepare the sample answers; ``refuse_with`` makes every request fail with a status."""
        self._samples = samples
        self._refuse_with = refuse_with
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        """Record the request and answer it from the sample lists."""
        self.requests.append(request)
        address = urllib.parse.urlsplit(request.full_url)
        assert address.scheme == "https"
        assert address.hostname == "eodhd.com"
        if self._refuse_with is not None:
            raise urllib.error.HTTPError(
                request.full_url, self._refuse_with, "Unauthorized", Message(), io.BytesIO(b"")
            )
        name = (
            "exchanges.json"
            if address.path == "/api/exchanges-list/"
            else f"symbols_{address.path.rsplit('/', 1)[-1]}.json"
        )
        sample = self._samples / name
        if not sample.is_file():
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", Message(), io.BytesIO(b"")
            )
        return _Response(sample.read_bytes())


def _install(monkeypatch: pytest.MonkeyPatch, eodhd: _Eodhd) -> None:
    """Make every request of the command go to the stand-in."""

    def build_opener(*handlers: type[urllib.request.BaseHandler]) -> _Eodhd:
        return eodhd

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)


@pytest.fixture
def subscriber(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a temporary working folder with a key in its settings and nothing else.

    No database and no saved list: the download needs neither.
    """
    monkeypatch.chdir(tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.toml").write_text(f'[eodhd]\napi_key = "{_KEY}"\n', encoding="utf-8")
    return tmp_path


def test_download_saves_the_lists_and_says_what_it_did(
    subscriber: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    eodhd_samples: Path,
) -> None:
    """Against the sample lists: six codes offered, three of them with a list to save.

    The stand-in offers ``KO``, ``US``, ``LSE``, ``F``, ``CC`` and ``HK``.
    The shipped file maps 59 codes, of which the stand-in offers three.
    """
    _install(monkeypatch, _Eodhd(eodhd_samples))

    status = main(["symbols", "download"])

    output = capsys.readouterr()
    not_offered = _without_a_list()
    assert status == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        f"Lists folder: {Path('data') / 'eodhd'}",
        "Exchange codes EODHD offers: 6",
        "Offered and not in the exchange file: 1 (HK)",
        f"In the exchange file and no longer offered: 56 ({', '.join(not_offered)})",
        "Symbol lists saved: 3 of 59, 18 lines",
        "  KO: 5 lines",
        "  LSE: 5 lines",
        "  US: 8 lines",
        "Not in the subscription: 0",
        "Refused as suspiciously short: 0",
        "Nothing was stored in the database. Run `pyvalue symbols load` to store the lists",
    ]
    saved = sorted(path.name for path in (subscriber / "data" / "eodhd").iterdir())
    assert saved == ["exchanges.json", "symbols_KO.json", "symbols_LSE.json", "symbols_US.json"]


def test_download_sends_the_key_to_eodhd_and_shows_it_nowhere(
    subscriber: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    eodhd_samples: Path,
) -> None:
    """In every request, and in no output, no file name and no saved file."""
    eodhd = _Eodhd(eodhd_samples)
    _install(monkeypatch, eodhd)

    assert main(["symbols", "download"]) == 0

    output = capsys.readouterr()
    assert len(eodhd.requests) == 4
    assert all(f"api_token={_KEY}" in request.full_url for request in eodhd.requests)
    assert _KEY not in output.out
    assert _KEY not in output.err
    for path in (subscriber / "data" / "eodhd").iterdir():
        assert _KEY not in path.name
        assert _KEY.encode() not in path.read_bytes()


def test_download_does_not_touch_the_database(
    subscriber: Path, monkeypatch: pytest.MonkeyPatch, eodhd_samples: Path
) -> None:
    """It needs none and creates none: storing the lists is the load's job."""
    _install(monkeypatch, _Eodhd(eodhd_samples))

    assert main(["symbols", "download"]) == 0

    assert not (subscriber / "data" / "pyvalue.db").exists()


def test_the_lists_a_download_saved_are_what_the_load_stores(
    subscriber: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    eodhd_samples: Path,
) -> None:
    """The two commands in the order a person runs them."""
    _install(monkeypatch, _Eodhd(eodhd_samples))
    assert main(["db", "migrate"]) == 0
    assert main(["symbols", "download"]) == 0
    capsys.readouterr()

    assert main(["symbols", "load"]) == 0

    assert "Lists stored: 3 of 59, 12 lines" in capsys.readouterr().out.splitlines()


def test_download_without_a_key_says_what_to_add_and_asks_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    eodhd_samples: Path,
) -> None:
    """One line, status 1, and no request."""
    monkeypatch.chdir(tmp_path)
    eodhd = _Eodhd(eodhd_samples)
    _install(monkeypatch, eodhd)

    status = main(["symbols", "download"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err.startswith("pyvalue: error: ")
    assert "add a section [eodhd] with the line api_key" in output.err
    assert eodhd.requests == []


@pytest.mark.parametrize("status_sent", [401, 402, 403], ids=["no key", "payment", "forbidden"])
def test_a_key_that_is_not_accepted_stops_the_download_at_the_first_request(
    subscriber: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    eodhd_samples: Path,
    status_sent: int,
) -> None:
    """An expired subscription would refuse all sixty requests; one is enough to know."""
    eodhd = _Eodhd(eodhd_samples, refuse_with=status_sent)
    _install(monkeypatch, eodhd)

    status = main(["symbols", "download"])

    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert output.err == (
        "pyvalue: error: cannot download https://eodhd.com/api/exchanges-list/?fmt=json: "
        f"HTTP Error {status_sent}: Unauthorized\n"
    )
    assert _KEY not in output.err
    assert len(eodhd.requests) == 1
    assert not (subscriber / "data").exists()


def test_download_takes_no_database_option(capsys: pytest.CaptureFixture[str]) -> None:
    """There is no database for it to be pointed at."""
    with pytest.raises(SystemExit) as stopped:
        main(["symbols", "download", "--db", "other.db"])

    assert stopped.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
