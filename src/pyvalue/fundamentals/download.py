"""The fundamentals download: one payload per provider line, into files.

``pyvalue fundamentals download`` asks the provider for the fundamentals of
every line a listing is on and keeps each answer as a file (ADR 0028). A
saved file is the record that a line was downloaded: a run requests only the
lines that have none, and never overwrites one. To fetch a payload again, a
person sets its file aside.

The database is read, to know the listings, and never written.

A subscription has a daily allowance, and the account has an extra reserve
that the provider draws on once a day's allowance is used up. The run must
never touch that reserve. So it works in batches, and before each batch it
asks the account what is left and takes only what fits, short of a margin.

The work is waiting for the network, so the requests of a batch are made on
a few threads. Each thread writes its own file; nothing is shared.

Author: Emre Tezel
"""

import contextlib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from pyvalue.db import Database
from pyvalue.fundamentals.report import DEFAULT_REPORT_DIR, NotDownloaded, write_not_downloaded
from pyvalue.fundamentals.saved_payloads import DEFAULT_PAYLOADS_DIR, payload_file, save_payload
from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import (
    FUNDAMENTALS_REQUEST_COST,
    PROVIDER_CODE,
    Allowance,
    Fetch,
    NotFoundError,
    account_url,
    check_fundamentals,
    fetch_from_eodhd,
    fundamentals_url,
    parse_allowance,
)

# How many requests are in flight at once. Measured on 2026-11-27: eight
# threads make about 500 requests a minute, against a limit of 1,200, so the
# run needs no pacing (ADR 0028).
WORKERS: int = 8

# How many requests are made between two looks at the account. Small enough
# that a run notices soon when the allowance runs out or the requests fail,
# large enough that the look itself is a small part of the work.
BATCH: int = 500

# What is left unspent of a day's allowance. It keeps the run away from the
# extra reserve even when one batch costs twice what was measured, or
# something else uses the key on the same day.
MARGIN: int = 5_000

# What is told after every request: how many are done, and how many there
# are in all. The command draws its progress bar with it.
type Progress = Callable[[int, int], None]


class Status(Enum):
    """What became of one provider line in a run. The value is the code the report carries."""

    ALREADY_SAVED = "already_saved"
    SAVED = "saved"
    NOT_FOUND = "not_found"
    NOT_A_PAYLOAD = "not_a_payload"
    REQUEST_FAILED = "request_failed"
    NO_ALLOWANCE_LEFT = "no_allowance_left"
    RUN_STOPPED = "run_stopped"


class Stop(Enum):
    """Why a run ended before every line was requested."""

    ALLOWANCE_USED_UP = "the day's allowance is used up"
    MOSTLY_FAILED = "more than half the requests of a batch failed"
    ACCOUNT_NOT_ANSWERED = "the account request failed"


# What a line that was not requested is reported as, by why the run ended.
_LEFT_AS: Mapping[Stop, Status] = MappingProxyType(
    {
        Stop.ALLOWANCE_USED_UP: Status.NO_ALLOWANCE_LEFT,
        Stop.MOSTLY_FAILED: Status.RUN_STOPPED,
        Stop.ACCOUNT_NOT_ANSWERED: Status.RUN_STOPPED,
    }
)

# The statuses of a line that has a saved payload after the run.
_HAS_PAYLOAD: frozenset[Status] = frozenset({Status.ALREADY_SAVED, Status.SAVED})

# The statuses of a line that was requested in the run.
_REQUESTED: frozenset[Status] = frozenset(
    {Status.SAVED, Status.NOT_FOUND, Status.NOT_A_PAYLOAD, Status.REQUEST_FAILED}
)


@dataclass(frozen=True, slots=True, order=True)
class Line:
    """One line of the provider: an exchange code and a symbol, both its own.

    Attributes:
        provider_exchange_code: The provider's exchange code, such as ``US``.
        provider_symbol: The provider's symbol under that code.
    """

    provider_exchange_code: str
    provider_symbol: str


@dataclass(frozen=True, slots=True)
class LineOutcome:
    """What became of one provider line in a run.

    Attributes:
        line: The line.
        status: Whether its payload is saved, and if not, why.
        detail: What the request or the answer said, or nothing.
    """

    line: Line
    status: Status
    detail: str


@dataclass(frozen=True, slots=True)
class FundamentalsDownload:
    """The outcome of one ``pyvalue fundamentals download``.

    Attributes:
        listings: The listings the provider can be asked about.
        lines: One outcome per provider line a listing is on, in the order of
            exchange code and symbol.
        stopped: Why the run ended before every line was requested, or
            ``None`` when it did not.
        stopped_detail: What the first failed request said, or the account
            request; empty otherwise.
        daily_limit: The account's daily allowance, or ``None`` when the
            account was not asked.
        allowance_left: What was left of it when the run ended, or ``None``
            when the account was not asked.
        report: The file that lists the listings without a payload.
    """

    listings: int
    lines: tuple[LineOutcome, ...]
    stopped: Stop | None
    stopped_detail: str
    daily_limit: int | None
    allowance_left: int | None
    report: Path

    def with_status(self, status: Status) -> tuple[LineOutcome, ...]:
        """Return the lines that ended with one status."""
        return tuple(each for each in self.lines if each.status is status)

    @property
    def requests(self) -> int:
        """How many fundamentals requests the run made."""
        return sum(1 for each in self.lines if each.status in _REQUESTED)


@dataclass(frozen=True, slots=True)
class _Listed:
    """One listing of ours with the provider line it is on."""

    line: Line
    isin: str
    company: str


@dataclass(frozen=True, slots=True)
class _Requested:
    """What the batches of a run did."""

    outcomes: tuple[LineOutcome, ...]
    stopped: Stop | None
    stopped_detail: str
    allowance: Allowance | None


def _today_gmt() -> date:
    """Return today's date by GMT, which is the day the provider counts by."""
    return datetime.now(UTC).date()


def _listed(database: Database) -> tuple[_Listed, ...]:
    """Return every listing the provider can be asked about, with its line.

    The line comes from the view ``provider_listing_address`` (ADR 0002). The
    security's ISIN and the company's name are read for the report only.
    """
    with database.unit_of_work() as work:
        instrument_of = {each.listing_id: each.instrument_id for each in work.listings.all()}
        security_of = {each.instrument_id: each for each in work.instruments.all()}
        name_of = {each.company_id: each.name for each in work.companies.all()}
        listed: list[_Listed] = []
        for address in work.provider_listings.addresses_of_provider(PROVIDER_CODE):
            security = security_of[instrument_of[address.listing_id]]
            listed.append(
                _Listed(
                    line=Line(address.provider_exchange_code, address.provider_symbol),
                    isin=security.isin,
                    company=name_of[security.company_id],
                )
            )
    return tuple(listed)


def _requests_that_fit(allowance: Allowance, today: date) -> int:
    """Return how many fundamentals requests the day's allowance still takes.

    The margin stays unspent, and the result is never negative: an account
    that is already inside its margin takes none.
    """
    return max(0, (allowance.left(today) - MARGIN) // FUNDAMENTALS_REQUEST_COST)


def _download_line(line: Line, payloads_dir: Path, api_key: str, fetch: Fetch) -> LineOutcome:
    """Request the payload of one line and keep it, unless it is not one.

    Runs on a worker thread. It touches nothing another thread touches: the
    file it writes is this line's own.

    Raises:
        FundamentalsError: If the file cannot be written. That is not the
            line's fault, so it ends the run.
    """
    url = fundamentals_url(line.provider_exchange_code, line.provider_symbol)
    try:
        body = fetch(url, api_key)
    except NotFoundError:
        return LineOutcome(line, Status.NOT_FOUND, "")
    except ProviderError as error:
        # The message carries the address without the key.
        return LineOutcome(line, Status.REQUEST_FAILED, str(error))
    try:
        # Checked before it is kept: an error page, or a payload for another
        # symbol, must not get a file.
        check_fundamentals(body, url, line.provider_symbol)
    except ProviderError as error:
        return LineOutcome(line, Status.NOT_A_PAYLOAD, str(error))
    save_payload(
        body, payloads_dir / payload_file(line.provider_exchange_code, line.provider_symbol)
    )
    return LineOutcome(line, Status.SAVED, "")


def _request_in_batches(
    wanted: Sequence[Line],
    payloads_dir: Path,
    api_key: str,
    fetch: Fetch,
    today: Callable[[], date],
    workers: int,
    progress: Progress | None,
) -> _Requested:
    """Request the lines batch by batch, as far as the allowance and the answers allow.

    Raises:
        FundamentalsError: If a payload cannot be written.
    """

    def ask() -> Allowance:
        url = account_url()
        return parse_allowance(fetch(url, api_key), url)

    def one(line: Line) -> LineOutcome:
        return _download_line(line, payloads_dir, api_key, fetch)

    outcomes: list[LineOutcome] = []
    stopped: Stop | None = None
    stopped_detail = ""
    allowance: Allowance | None = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while len(outcomes) < len(wanted):
                try:
                    allowance = ask()
                except ProviderError as error:
                    stopped, stopped_detail = Stop.ACCOUNT_NOT_ANSWERED, str(error)
                    break
                fits = min(BATCH, _requests_that_fit(allowance, today()))
                batch = wanted[len(outcomes) : len(outcomes) + fits]
                if not batch:
                    stopped = Stop.ALLOWANCE_USED_UP
                    break
                failures: list[str] = []
                # The answers come back in the order of the batch, so what a
                # run does never depends on which thread was faster.
                for outcome in pool.map(one, batch):
                    outcomes.append(outcome)
                    if outcome.status is Status.REQUEST_FAILED:
                        failures.append(outcome.detail)
                    if progress is not None:
                        progress(len(outcomes), len(wanted))
                # "Not found" is an answer. Only a request that failed counts:
                # when most of a batch did, the next would fail the same way.
                if len(failures) * 2 > len(batch):
                    stopped, stopped_detail = Stop.MOSTLY_FAILED, failures[0]
                    break
        except BaseException:
            # An interrupt, or a file that cannot be written: the requests
            # that have not started must not be made. Without this, leaving
            # the block would first run the whole batch.
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    if outcomes:
        # Read once more for the summary. The account request is free, and if
        # it fails now, what was read before the last batch is still shown.
        with contextlib.suppress(ProviderError):
            allowance = ask()
    return _Requested(tuple(outcomes), stopped, stopped_detail, allowance)


def download_fundamentals(
    database: Database,
    api_key: Callable[[], str],
    payloads_dir: Path = DEFAULT_PAYLOADS_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    fetch: Fetch = fetch_from_eodhd,
    today: Callable[[], date] = _today_gmt,
    workers: int = WORKERS,
    progress: Progress | None = None,
) -> FundamentalsDownload:
    """Download the fundamentals payload of every provider line that has none.

    Two listings on one line share one request and one file. A line that has
    a file is not requested, so a run never overwrites a payload, and a run
    with nothing to do makes no request and needs no key.

    Args:
        database: The database to read the listings from. Nothing is written.
        api_key: What returns the provider's API key. It is called only when
            at least one line needs a request, and the key is handed to
            ``fetch`` and to nothing else.
        payloads_dir: Where the payloads are kept.
        report_dir: The folder the report is written to; created when
            missing.
        fetch: What performs a request. Tests pass their own.
        today: What returns today's date by GMT. Tests pass their own.
        workers: How many requests are in flight at once.
        progress: What is called after every request, with the number done
            and the number in all.

    Returns:
        What became of every line, and why the run ended early if it did.

    Raises:
        DatabaseError: If the database cannot be used.
        ConfigError: If a request is needed and the key is not set.
        FundamentalsError: If a payload or the report cannot be written.
    """
    listed = _listed(database)
    outcome_of: dict[Line, LineOutcome] = {}
    wanted: list[Line] = []
    for line in sorted({each.line for each in listed}):
        saved = payloads_dir / payload_file(line.provider_exchange_code, line.provider_symbol)
        if saved.is_file():
            outcome_of[line] = LineOutcome(line, Status.ALREADY_SAVED, "")
        else:
            wanted.append(line)

    requested = _Requested((), None, "", None)
    if wanted:
        requested = _request_in_batches(
            wanted, payloads_dir, api_key(), fetch, today, workers, progress
        )
        for outcome in requested.outcomes:
            outcome_of[outcome.line] = outcome
        if requested.stopped is not None:
            left_as = _LEFT_AS[requested.stopped]
            for line in wanted[len(requested.outcomes) :]:
                outcome_of[line] = LineOutcome(line, left_as, "")

    report = write_not_downloaded(
        (
            NotDownloaded(
                provider_code=PROVIDER_CODE,
                provider_exchange_code=each.line.provider_exchange_code,
                provider_symbol=each.line.provider_symbol,
                isin=each.isin,
                company=each.company,
                reason=outcome_of[each.line].status.value,
                detail=outcome_of[each.line].detail,
            )
            for each in sorted(listed, key=lambda each: (each.line, each.isin))
            if outcome_of[each.line].status not in _HAS_PAYLOAD
        ),
        report_dir,
    )
    allowance = requested.allowance
    return FundamentalsDownload(
        listings=len(listed),
        lines=tuple(outcome_of[line] for line in sorted(outcome_of)),
        stopped=requested.stopped,
        stopped_detail=requested.stopped_detail,
        daily_limit=None if allowance is None else allowance.daily_limit,
        allowance_left=None if allowance is None else allowance.left(today()),
        report=report,
    )
