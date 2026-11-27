"""Tests for ``pyvalue.fundamentals.download``: the fundamentals download of ADR 0028.

No test reaches the network: each passes a stand-in for EODHD that answers
from prepared payloads, keeps the account's daily count as EODHD does, and
records what was asked. The requests themselves are tested in
``tests/unit/test_http.py``.

Unless a test is about threads, the run uses one, so the order of the
requests is the order of the lines.

Author: Emre Tezel
"""

import gzip
import json
import threading
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest

from pyvalue.db import Database, Exchange, Provider, ProviderExchange, ProviderListing
from pyvalue.fundamentals import (
    FundamentalsDownload,
    FundamentalsError,
    Line,
    Status,
    Stop,
    download_fundamentals,
    payload_file,
)
from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import (
    FUNDAMENTALS_REQUEST_COST,
    NotFoundError,
    account_url,
    fundamentals_url,
)

# Stands in for an API key.
_KEY: str = "sample-api-key-0123456789"

# The day every test runs on, by GMT.
_TODAY: date = date(2026, 11, 27)

# Our exchanges in the tests, with EODHD's code for each. New York and Nasdaq
# share one code, as they do at EODHD.
_EXCHANGES: tuple[tuple[str, str, str], ...] = (
    ("XNYS", "US", "US"),
    ("XNAS", "US", "US"),
    ("XLON", "GB", "LSE"),
    ("XMEX", "MX", "MX"),
)

# The account holder of the stand-in. Nothing of it may leave the run.
_HOLDER: str = "Ada Example"

_HEADER: str = "provider_code,provider_exchange_code,provider_symbol,isin,company,reason,detail\n"


def _payload(symbol: str) -> bytes:
    """Return a payload for one symbol, cut down to what the download checks."""
    return json.dumps({"General": {"Code": symbol}, "Financials": {}}).encode()


class _Eodhd:
    """Stands in for EODHD: an account with a daily count, and payloads by line.

    A fundamentals request raises the account's count by what such a request
    costs, whatever the answer, so a test of the allowance sees what a real
    run would see.
    """

    def __init__(self, used: int = 0, limit: int = 100_000, counted_on: date = _TODAY) -> None:
        """Prepare an account that has used so much of its limit on a day."""
        self.used = used
        self.limit = limit
        self.counted_on = counted_on
        # The first account request that fails, counted from 1, and every one
        # after it; ``None`` when the account always answers.
        self.account_fails_from: int | None = None
        self.account_requests = 0
        self.answers: dict[str, bytes | Exception] = {}
        self.requests: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def has(self, code: str, symbol: str, body: bytes | None = None) -> None:
        """Prepare a payload for a line; by default the one of its symbol."""
        self.answers[fundamentals_url(code, symbol)] = _payload(symbol) if body is None else body

    def lacks(self, code: str, symbol: str) -> None:
        """Prepare "not found" for a line."""
        url = fundamentals_url(code, symbol)
        self.answers[url] = NotFoundError(f"cannot download {url}: HTTP Error 404: Not Found")

    def fails(self, code: str, symbol: str) -> None:
        """Prepare a failed request for a line."""
        url = fundamentals_url(code, symbol)
        self.answers[url] = ProviderError(f"cannot download {url}: timed out")

    def fetch(self, url: str, api_key: str) -> bytes:
        """Answer one request, or fail as prepared."""
        with self._lock:
            self.requests.append((url, api_key))
            if url == account_url():
                self.account_requests += 1
                if (
                    self.account_fails_from is not None
                    and self.account_requests >= self.account_fails_from
                ):
                    raise ProviderError(f"cannot download {url}: HTTP Error 401: Unauthorized")
                return json.dumps(
                    {
                        "name": _HOLDER,
                        "email": "ada@example.invalid",
                        "apiRequests": self.used,
                        "apiRequestsDate": self.counted_on.isoformat(),
                        "dailyRateLimit": self.limit,
                        "extraLimit": 74094,
                    }
                ).encode()
            self.used += FUNDAMENTALS_REQUEST_COST
        answer = self.answers.get(url)
        if answer is None:
            pytest.fail(f"{url} was requested and no answer is prepared for it")
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def asked(self) -> list[str]:
        """What was requested, in order: ``account``, or the line as ``SYMBOL.CODE``."""
        prefix = "https://eodhd.com/api/fundamentals/"
        return [
            "account"
            if url == account_url()
            else url.removeprefix(prefix).removesuffix("?fmt=json")
            for url, _ in self.requests
        ]

    @property
    def lines_asked(self) -> list[str]:
        """The lines whose fundamentals were requested, in order."""
        return [each for each in self.asked if each != "account"]


@pytest.fixture
def market(database: Database) -> Database:
    """Return a database with the sample exchanges and EODHD's codes for them."""
    with database.unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, country, code in _EXCHANGES:
            work.exchanges.save(Exchange(mic=mic, name=f"Exchange {mic}", country=country))
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )
    return database


def _list(database: Database, *listings: tuple[str, str]) -> None:
    """Add one security and its listing per pair of exchange and provider symbol.

    The securities are numbered on from the ones that are there, so each has
    an ISIN and a company name of its own.
    """
    with database.unit_of_work() as work:
        number = len(work.instruments.all())
        for mic, symbol in listings:
            number += 1
            isin = f"XX{number:09d}0"
            company = work.companies.add(f"Company {number}", None)
            security = work.instruments.add(company.company_id, isin)
            listing = work.listings.add(security.instrument_id, mic, symbol.upper(), "USD")
            work.provider_listings.add(
                ProviderListing(
                    provider_code="eodhd", listing_id=listing.listing_id, provider_symbol=symbol
                )
            )


def _symbols(count: int) -> list[str]:
    """Return that many symbols, in the order the download takes them."""
    return [f"S{number:03d}" for number in range(1, count + 1)]


def _list_on_new_york(database: Database, eodhd: _Eodhd, count: int) -> list[str]:
    """Add that many New York listings, prepare a payload for each, and return the symbols."""
    symbols = _symbols(count)
    _list(database, *(("XNYS", symbol) for symbol in symbols))
    for symbol in symbols:
        eodhd.has("US", symbol)
    return symbols


def _never_read() -> str:
    """Stand in for the settings file in a run that must not need the key."""
    pytest.fail("the key was read")


def _run(
    database: Database,
    eodhd: _Eodhd,
    folder: Path,
    *,
    api_key: Callable[[], str] = lambda: _KEY,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> FundamentalsDownload:
    """Run the download against the stand-in, into a temporary folder."""
    return download_fundamentals(
        database,
        api_key,
        folder / "payloads",
        folder / "report",
        fetch=eodhd.fetch,
        today=lambda: _TODAY,
        workers=workers,
        progress=progress,
    )


def _saved(folder: Path, code: str, symbol: str) -> Path:
    """Return where the payload of a line is kept in a test's folder."""
    return folder / "payloads" / payload_file(code, symbol)


def _statuses(outcome: FundamentalsDownload) -> dict[str, Status]:
    """Return what became of each line, by its symbol."""
    return {each.line.provider_symbol: each.status for each in outcome.lines}


def _batches_of(monkeypatch: pytest.MonkeyPatch, size: int) -> None:
    """Make the run look at the account after every few requests instead of 500."""
    monkeypatch.setattr("pyvalue.fundamentals.download.BATCH", size)


# --- What is requested and what is kept ----------------------------------------------------------


def test_a_line_without_a_file_is_requested_and_its_payload_kept(
    market: Database, tmp_path: Path
) -> None:
    """The file holds the answer as it arrived, gzip-compressed."""
    eodhd = _Eodhd()
    _list(market, ("XNYS", "BRK-B"))
    eodhd.has("US", "BRK-B")

    outcome = _run(market, eodhd, tmp_path)

    assert gzip.decompress(_saved(tmp_path, "US", "BRK-B").read_bytes()) == _payload("BRK-B")
    assert outcome.lines[0].line == Line("US", "BRK-B")
    assert _statuses(outcome) == {"BRK-B": Status.SAVED}
    assert (outcome.listings, outcome.requests, outcome.stopped) == (1, 1, None)
    assert eodhd.asked == ["account", "BRK-B.US", "account"]


def test_the_lines_are_taken_in_the_order_of_exchange_code_and_symbol(
    market: Database, tmp_path: Path
) -> None:
    """Whatever order the listings were written in."""
    eodhd = _Eodhd()
    _list(market, ("XNYS", "ZED"), ("XLON", "MID"), ("XNAS", "ABE"))
    for code, symbol in (("US", "ZED"), ("LSE", "MID"), ("US", "ABE")):
        eodhd.has(code, symbol)

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.lines_asked == ["MID.LSE", "ABE.US", "ZED.US"]
    assert [each.line for each in outcome.lines] == [
        Line("LSE", "MID"),
        Line("US", "ABE"),
        Line("US", "ZED"),
    ]


def test_a_line_that_has_a_file_is_not_requested_and_never_overwritten(
    market: Database, tmp_path: Path
) -> None:
    """A saved file is the record that the line was downloaded."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 2)
    kept = _saved(tmp_path, "US", "S001")
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"what an earlier run kept")

    outcome = _run(market, eodhd, tmp_path)

    assert kept.read_bytes() == b"what an earlier run kept"
    assert eodhd.lines_asked == ["S002.US"]
    assert _statuses(outcome) == {"S001": Status.ALREADY_SAVED, "S002": Status.SAVED}
    assert outcome.requests == 1


def test_a_run_with_nothing_to_download_makes_no_request_and_reads_no_key(
    market: Database, tmp_path: Path
) -> None:
    """Not even the account is asked."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 2)
    _run(market, eodhd, tmp_path)
    eodhd.requests.clear()

    outcome = _run(market, eodhd, tmp_path, api_key=_never_read)

    assert eodhd.requests == []
    assert set(_statuses(outcome).values()) == {Status.ALREADY_SAVED}
    assert (outcome.daily_limit, outcome.allowance_left) == (None, None)


def test_a_database_without_listings_has_nothing_to_download(
    market: Database, tmp_path: Path
) -> None:
    """The report is written all the same, with its header only."""
    eodhd = _Eodhd()

    outcome = _run(market, eodhd, tmp_path, api_key=_never_read)

    assert (outcome.listings, outcome.lines, outcome.requests) == (0, (), 0)
    assert outcome.report.read_text(encoding="utf-8") == _HEADER
    assert eodhd.requests == []


def test_a_listing_on_an_exchange_eodhd_has_no_code_for_is_not_asked_about(
    market: Database, tmp_path: Path
) -> None:
    """The provider cannot be addressed there (ADR 0002)."""
    eodhd = _Eodhd()
    with market.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XTKS", name="Tokyo", country="JP"))
    _list(market, ("XTKS", "7203"))

    outcome = _run(market, eodhd, tmp_path, api_key=_never_read)

    assert (outcome.listings, outcome.lines) == (0, ())


def test_two_listings_on_one_line_share_one_request_and_one_file(
    market: Database, tmp_path: Path
) -> None:
    """New York and Nasdaq share EODHD's code, and the schema allows one symbol on both."""
    eodhd = _Eodhd()
    _list(market, ("XNYS", "DUAL"), ("XNAS", "DUAL"))
    eodhd.has("US", "DUAL")

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.lines_asked == ["DUAL.US"]
    assert (outcome.listings, len(outcome.lines), outcome.requests) == (2, 1, 1)
    assert _saved(tmp_path, "US", "DUAL").is_file()


def test_a_symbol_with_an_unusual_character_is_asked_for_and_kept_under_an_escaped_name(
    market: Database, tmp_path: Path
) -> None:
    """One listed symbol holds an ``&``."""
    eodhd = _Eodhd()
    _list(market, ("XMEX", "PE&OLES"))
    eodhd.has("MX", "PE&OLES")

    _run(market, eodhd, tmp_path)

    assert eodhd.lines_asked == ["PE%26OLES.MX"]
    assert (tmp_path / "payloads" / "MX" / "PE%26OLES.json.gz").is_file()


# --- Answers that give no payload ----------------------------------------------------------------


def test_a_symbol_eodhd_has_nothing_for_is_reported_and_the_run_goes_on(
    market: Database, tmp_path: Path
) -> None:
    """ "Not found" is an answer about one symbol."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 3)
    eodhd.lacks("US", "S002")

    outcome = _run(market, eodhd, tmp_path)

    assert _statuses(outcome) == {
        "S001": Status.SAVED,
        "S002": Status.NOT_FOUND,
        "S003": Status.SAVED,
    }
    assert not _saved(tmp_path, "US", "S002").exists()
    assert (outcome.requests, outcome.stopped) == (3, None)


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (b"<html>Service unavailable</html>", "is not an EODHD fundamentals payload"),
        (b"{}", "it has no General section"),
        (_payload("OTHER"), "its General.Code is 'OTHER'"),
    ],
    ids=["an error page", "an empty object", "a payload for another symbol"],
)
def test_an_answer_that_is_not_the_payload_of_the_symbol_gets_no_file(
    market: Database, tmp_path: Path, body: bytes, said: str
) -> None:
    """It is reported with what was wrong, and the next line is taken."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 2)
    eodhd.has("US", "S001", body)

    outcome = _run(market, eodhd, tmp_path)

    refused = outcome.with_status(Status.NOT_A_PAYLOAD)
    assert [each.line.provider_symbol for each in refused] == ["S001"]
    assert said in refused[0].detail
    assert not _saved(tmp_path, "US", "S001").exists()
    assert _saved(tmp_path, "US", "S002").is_file()


def test_a_request_that_fails_is_reported_and_the_run_goes_on(
    market: Database, tmp_path: Path
) -> None:
    """One timeout must not stop a run of thousands."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 3)
    eodhd.fails("US", "S001")

    outcome = _run(market, eodhd, tmp_path)

    failed = outcome.with_status(Status.REQUEST_FAILED)
    assert [each.line.provider_symbol for each in failed] == ["S001"]
    assert failed[0].detail.endswith("fundamentals/S001.US?fmt=json: timed out")
    assert len(outcome.with_status(Status.SAVED)) == 2
    assert outcome.stopped is None


# --- When the run stops by itself ----------------------------------------------------------------


def test_a_batch_in_which_most_requests_failed_stops_the_run(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The next batch would fail the same way: a refused plan must not make 8,000 requests."""
    _batches_of(monkeypatch, 4)
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 8)
    for symbol in ("S001", "S002", "S004"):
        eodhd.fails("US", symbol)

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.stopped is Stop.MOSTLY_FAILED
    assert outcome.stopped_detail.endswith("fundamentals/S001.US?fmt=json: timed out")
    assert eodhd.lines_asked == ["S001.US", "S002.US", "S003.US", "S004.US"]
    assert _statuses(outcome) == {
        "S001": Status.REQUEST_FAILED,
        "S002": Status.REQUEST_FAILED,
        "S003": Status.SAVED,
        "S004": Status.REQUEST_FAILED,
        "S005": Status.RUN_STOPPED,
        "S006": Status.RUN_STOPPED,
        "S007": Status.RUN_STOPPED,
        "S008": Status.RUN_STOPPED,
    }


def test_a_batch_in_which_half_the_requests_failed_does_not_stop_the_run(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More than half, not half."""
    _batches_of(monkeypatch, 4)
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 8)
    for symbol in ("S001", "S002"):
        eodhd.fails("US", symbol)

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.stopped is None
    assert outcome.requests == 8
    assert len(outcome.with_status(Status.SAVED)) == 6


def test_not_found_does_not_count_as_a_failure(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A market EODHD has no fundamentals for must not hold back the markets after it."""
    _batches_of(monkeypatch, 4)
    eodhd = _Eodhd()
    symbols = _list_on_new_york(market, eodhd, 8)
    for symbol in symbols[:4]:
        eodhd.lacks("US", symbol)

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.stopped is None
    assert len(outcome.with_status(Status.NOT_FOUND)) == 4
    assert len(outcome.with_status(Status.SAVED)) == 4


def test_an_answer_that_is_not_a_payload_does_not_count_as_a_failure(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request was answered. Whether EODHD answers so for a whole market is not known."""
    _batches_of(monkeypatch, 4)
    eodhd = _Eodhd()
    symbols = _list_on_new_york(market, eodhd, 8)
    for symbol in symbols[:4]:
        eodhd.has("US", symbol, b"{}")

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.stopped is None
    assert outcome.requests == 8


# --- The daily allowance -------------------------------------------------------------------------


def test_the_account_is_asked_before_every_batch_and_once_at_the_end(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So the run works from the account's own count, not from its own arithmetic."""
    _batches_of(monkeypatch, 2)
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 5)

    _run(market, eodhd, tmp_path)

    assert eodhd.asked == [
        "account",
        "S001.US",
        "S002.US",
        "account",
        "S003.US",
        "S004.US",
        "account",
        "S005.US",
        "account",
    ]
    assert {key for _, key in eodhd.requests} == {_KEY}


def test_the_run_stops_five_thousand_short_of_the_daily_limit(
    market: Database, tmp_path: Path
) -> None:
    """EODHD draws on the extra reserve once the allowance is used up; the run never gets there."""
    eodhd = _Eodhd(used=94_970)
    _list_on_new_york(market, eodhd, 5)

    outcome = _run(market, eodhd, tmp_path)

    # 5,030 are left; less the margin of 5,000 that is room for three requests.
    assert eodhd.lines_asked == ["S001.US", "S002.US", "S003.US"]
    assert eodhd.used == 95_000
    assert outcome.stopped is Stop.ALLOWANCE_USED_UP
    assert _statuses(outcome) == {
        "S001": Status.SAVED,
        "S002": Status.SAVED,
        "S003": Status.SAVED,
        "S004": Status.NO_ALLOWANCE_LEFT,
        "S005": Status.NO_ALLOWANCE_LEFT,
    }
    assert (outcome.daily_limit, outcome.allowance_left) == (100_000, 5_000)


@pytest.mark.parametrize("used", [95_000, 96_000, 100_000, 174_094])
def test_an_account_inside_its_margin_gets_no_request(
    market: Database, tmp_path: Path, used: int
) -> None:
    """Also one that is past its limit and already on the reserve: nothing is taken."""
    eodhd = _Eodhd(used=used)
    _list_on_new_york(market, eodhd, 3)

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.asked == ["account"]
    assert outcome.stopped is Stop.ALLOWANCE_USED_UP
    assert set(_statuses(outcome).values()) == {Status.NO_ALLOWANCE_LEFT}
    assert outcome.requests == 0


def test_a_count_from_an_earlier_day_does_not_hold_the_run_back(
    market: Database, tmp_path: Path
) -> None:
    """EODHD's count stays as it was until the first request of a new day."""
    eodhd = _Eodhd(used=99_990, counted_on=_TODAY - timedelta(days=1))
    _list_on_new_york(market, eodhd, 3)

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.requests == 3
    assert outcome.stopped is None


def test_a_refused_account_request_stops_the_run_before_any_other_request(
    market: Database, tmp_path: Path
) -> None:
    """A key that is not accepted shows here, with one request."""
    eodhd = _Eodhd()
    eodhd.account_fails_from = 1
    _list_on_new_york(market, eodhd, 3)

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.asked == ["account"]
    assert outcome.stopped is Stop.ACCOUNT_NOT_ANSWERED
    assert outcome.stopped_detail == (
        "cannot download https://eodhd.com/api/user?fmt=json: HTTP Error 401: Unauthorized"
    )
    assert set(_statuses(outcome).values()) == {Status.RUN_STOPPED}
    assert (outcome.daily_limit, outcome.allowance_left) == (None, None)
    assert outcome.report.read_text(encoding="utf-8").count("run_stopped") == 3


def test_an_account_request_that_fails_later_keeps_what_was_saved(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run stops there, and what the account said before is still shown."""
    _batches_of(monkeypatch, 2)
    eodhd = _Eodhd()
    eodhd.account_fails_from = 2
    _list_on_new_york(market, eodhd, 4)

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.asked == ["account", "S001.US", "S002.US", "account", "account"]
    assert outcome.stopped is Stop.ACCOUNT_NOT_ANSWERED
    assert _statuses(outcome) == {
        "S001": Status.SAVED,
        "S002": Status.SAVED,
        "S003": Status.RUN_STOPPED,
        "S004": Status.RUN_STOPPED,
    }
    assert outcome.daily_limit == 100_000


# --- The report ----------------------------------------------------------------------------------


def test_the_report_lists_every_listing_without_a_payload_and_why(
    market: Database, tmp_path: Path
) -> None:
    """One row per listing, in the order of exchange code, symbol and ISIN."""
    eodhd = _Eodhd()
    _list(market, ("XNYS", "AAA"), ("XNYS", "BBB"), ("XLON", "CCC"), ("XNAS", "BBB"))
    eodhd.has("US", "AAA")
    eodhd.lacks("US", "BBB")
    eodhd.fails("LSE", "CCC")

    outcome = _run(market, eodhd, tmp_path)

    assert outcome.report == tmp_path / "report" / "not_downloaded.csv"
    assert outcome.report.read_text(encoding="utf-8") == (
        _HEADER + "eodhd,LSE,CCC,XX0000000030,Company 3,request_failed,"
        "cannot download https://eodhd.com/api/fundamentals/CCC.LSE?fmt=json: timed out\n"
        "eodhd,US,BBB,XX0000000020,Company 2,not_found,\n"
        "eodhd,US,BBB,XX0000000040,Company 4,not_found,\n"
    )


def test_a_second_run_asks_only_for_what_is_on_the_report_and_writes_the_same_report(
    market: Database, tmp_path: Path
) -> None:
    """Reproducible: the same answers give the same bytes, and nothing saved is asked again."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 4)
    eodhd.lacks("US", "S002")
    eodhd.fails("US", "S004")
    first = _run(market, eodhd, tmp_path).report.read_bytes()
    eodhd.requests.clear()

    outcome = _run(market, eodhd, tmp_path)

    assert eodhd.lines_asked == ["S002.US", "S004.US"]
    assert outcome.report.read_bytes() == first
    assert _statuses(outcome) == {
        "S001": Status.ALREADY_SAVED,
        "S002": Status.NOT_FOUND,
        "S003": Status.ALREADY_SAVED,
        "S004": Status.REQUEST_FAILED,
    }


def test_the_key_and_the_account_holder_are_in_no_file_and_no_file_name(
    market: Database, tmp_path: Path
) -> None:
    """Not in a payload, not in the report, not in what the run returns."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 4)
    eodhd.lacks("US", "S002")
    eodhd.fails("US", "S003")
    eodhd.has("US", "S004", b"{}")

    outcome = _run(market, eodhd, tmp_path)

    written = [path for path in tmp_path.rglob("*") if path.is_file() and path.suffix != ".db"]
    assert len(written) == 2
    for path in written:
        content = path.read_bytes()
        if path.suffix == ".gz":
            content = gzip.decompress(content)
        for secret in (_KEY, _HOLDER):
            assert secret.encode() not in content
            assert secret not in str(path)
    assert _KEY not in repr(outcome)
    assert _HOLDER not in repr(outcome)


# --- Progress, threads, and a run that is cut off ------------------------------------------------


def test_progress_is_told_after_every_request(market: Database, tmp_path: Path) -> None:
    """The number done and the number of lines that needed a request."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 4)
    kept = _saved(tmp_path, "US", "S001")
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"what an earlier run kept")
    told: list[tuple[int, int]] = []

    _run(market, eodhd, tmp_path, progress=lambda done, total: told.append((done, total)))

    assert told == [(1, 3), (2, 3), (3, 3)]


def test_on_several_threads_every_line_still_gets_its_own_payload(
    market: Database, tmp_path: Path
) -> None:
    """Each thread writes its own file, and the outcome is in the order of the lines."""
    eodhd = _Eodhd()
    symbols = _list_on_new_york(market, eodhd, 40)

    outcome = _run(market, eodhd, tmp_path, workers=8)

    assert [each.line.provider_symbol for each in outcome.lines] == symbols
    assert set(_statuses(outcome).values()) == {Status.SAVED}
    for symbol in symbols:
        assert gzip.decompress(_saved(tmp_path, "US", symbol).read_bytes()) == _payload(symbol)
    assert sorted(eodhd.lines_asked) == [f"{symbol}.US" for symbol in symbols]


def test_a_payload_that_cannot_be_written_ends_the_run(market: Database, tmp_path: Path) -> None:
    """A full disk is not one line's fault. The message names the file."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 3)
    (tmp_path / "payloads").write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(FundamentalsError, match=r"cannot save .*S001\.json\.gz"):
        _run(market, eodhd, tmp_path)

    assert not (tmp_path / "report").exists()


def test_an_interrupt_does_not_run_the_rest_of_the_batch(market: Database, tmp_path: Path) -> None:
    """Ctrl-C stops after the requests in flight, not after the 500 that were queued."""
    eodhd = _Eodhd()
    _list_on_new_york(market, eodhd, 50)
    interrupted = threading.Event()
    plain = eodhd.fetch

    def fetch(url: str, api_key: str) -> bytes:
        # Every fundamentals request after the first waits until the run was
        # interrupted, as a request in flight would still be under way.
        if url != account_url() and eodhd.lines_asked:
            interrupted.wait(timeout=10)
        return plain(url, api_key)

    def interrupt(done: int, total: int) -> None:
        interrupted.set()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        download_fundamentals(
            market,
            lambda: _KEY,
            tmp_path / "payloads",
            tmp_path / "report",
            fetch=fetch,
            today=lambda: _TODAY,
            workers=1,
            progress=interrupt,
        )

    # The first request, and at most the one that had already started.
    assert 1 <= len(eodhd.lines_asked) <= 2
    assert _saved(tmp_path, "US", "S001").is_file()
