"""Vanguard's own holdings file: download it once, read it afterwards.

Vanguard's fund pages are fed by a holdings list that gives a ticker and a
SEDOL for every holding, which the SEC filing does not (ADR 0016). The list
is served 500 rows at a time. All pages of one fund are saved as one file in
Vanguard's own shape, and the load reads that file from then on.

The address is not documented by Vanguard and shows only the latest month, so
the saved file is the only copy of a past month there will ever be.

Nothing personal is sent to Vanguard. The fetch here takes an address and
nothing else, so the SEC contact string (``pyvalue.universe.sec``) has no way
into a request to this host.

Author: Emre Tezel
"""

import contextlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.universe.errors import SponsorFileError
from pyvalue.universe.http import fetch_https

# The one host the holdings list is fetched from.
VANGUARD_HOST: str = "investor.vanguard.com"

# How pyvalue names itself to Vanguard. A plain client name is enough, and it
# says nothing about who runs the load.
_CLIENT_NAME: str = "pyvalue"

# The most rows Vanguard returns for one request.
_PAGE_SIZE: int = 500

# A fund of this size would be a mistake in the answer, not a fund. The limit
# keeps a wrong "size" from turning into an endless run of requests.
_MAX_ROWS: int = 100_000

# A SEDOL is seven letters or digits. The ``holding`` table accepts nothing
# else, so a value of another shape is read as no SEDOL.
_SEDOL: re.Pattern[str] = re.compile(r"[A-Z0-9]{7}")

# What fetches one page: address -> the bytes of the response. A parameter of
# this type lets tests stand in for the network.
type FetchPage = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class VanguardRow:
    """One holding in Vanguard's file.

    Attributes:
        isin: The security's ISIN, or ``None`` when the row gives none.
        ticker: The ticker as Vanguard writes it, or ``None``.
        sedol: The SEDOL, or ``None`` when the row gives none or one of the
            wrong shape.
    """

    isin: str | None
    ticker: str | None
    sedol: str | None


@dataclass(frozen=True, slots=True)
class VanguardFile:
    """The part of Vanguard's file the load needs.

    Attributes:
        as_of: The day the file states the holdings for.
        rows: Every holding, in the order of the file.
    """

    as_of: date
    rows: tuple[VanguardRow, ...]


def page_url(fund_id: str, start: int) -> str:
    """Return the address of one page of a fund's holdings list.

    Args:
        fund_id: Vanguard's own id of the fund, such as ``0970``.
        start: The position of the page's first row, counted from 1.
    """
    return (
        f"https://{VANGUARD_HOST}/vmf/api/{fund_id}/portfolio-holding/stock.json"
        f"?start={start}&count={_PAGE_SIZE}"
    )


def fetch_from_vanguard(url: str) -> bytes:
    """Fetch one page from ``investor.vanguard.com``.

    Args:
        url: An ``https://investor.vanguard.com/`` address.

    Returns:
        The page's bytes, decompressed.

    Raises:
        SponsorFileError: If the address is on another host or not HTTPS, or
            the download fails.
    """
    return fetch_https(
        url,
        VANGUARD_HOST,
        {"User-Agent": _CLIENT_NAME, "Accept": "application/json"},
        SponsorFileError,
    )


def _page(body: bytes, source: str) -> tuple[int, str, list[object]]:
    """Take one page apart: the stated number of rows, the date, the rows.

    Args:
        body: The page, or a whole saved file, as bytes.
        source: What to call it in an error message.

    Raises:
        SponsorFileError: If it is not JSON of Vanguard's shape.
    """
    try:
        document: object = json.loads(body)
    except ValueError as error:
        raise SponsorFileError(f"{source} is not a Vanguard holdings file: {error}") from error
    if not isinstance(document, dict):
        raise SponsorFileError(f"{source} is not a Vanguard holdings file")
    size: object = document.get("size")
    as_of: object = document.get("asOfDate")
    fund: object = document.get("fund")
    rows: object = fund.get("entity") if isinstance(fund, dict) else None
    # ``bool`` is an ``int`` in Python; a size of ``true`` is not a number of rows.
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not isinstance(as_of, str)
        or not isinstance(rows, list)
    ):
        raise SponsorFileError(
            f"{source} is not a Vanguard holdings file: it lacks the number of rows, the date "
            "or the rows"
        )
    return size, as_of, list(rows)


def download_vanguard_file(
    fund_id: str, destination: Path, fetch: FetchPage = fetch_from_vanguard
) -> None:
    """Download every page of a fund's holdings list and keep them as one file.

    The pages are joined into one document of the same shape as a page and
    written under a temporary name. Only a file that reads back as a complete
    holdings file is given its final name, so a file with the final name is
    always whole, even if the download was interrupted.

    Args:
        fund_id: Vanguard's own id of the fund.
        destination: Where to keep the file.
        fetch: What performs a request. Tests pass their own.

    Raises:
        SponsorFileError: If a page cannot be downloaded or is not of
            Vanguard's shape, the pages disagree on the date or the number of
            rows, the number of rows received is not the number stated, or
            the file cannot be written.
    """
    first_url = page_url(fund_id, 1)
    size, as_of, rows = _page(fetch(first_url), first_url)
    if not 0 < size <= _MAX_ROWS:
        raise SponsorFileError(f"{first_url} states {size} rows, which cannot be right")
    for start in range(_PAGE_SIZE + 1, size + 1, _PAGE_SIZE):
        url = page_url(fund_id, start)
        page_size, page_as_of, page_rows = _page(fetch(url), url)
        if (page_size, page_as_of) != (size, as_of):
            # The list changed while it was being read: the pages belong to
            # two different months, or to two different lists.
            raise SponsorFileError(
                f"{url} states {page_size} rows as of {page_as_of}, where the first page "
                f"stated {size} as of {as_of}; nothing was kept"
            )
        rows.extend(page_rows)
    if len(rows) != size:
        raise SponsorFileError(
            f"{first_url} states {size} rows and {len(rows)} arrived; nothing was kept"
        )

    document = {"size": size, "asOfDate": as_of, "fund": {"entity": rows}}
    partial = destination.with_name(destination.name + ".part")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        try:
            read_vanguard_file(partial)
        except SponsorFileError as error:
            # The reader's message names the temporary file, which is about to
            # be removed. Say where the document came from instead.
            raise SponsorFileError(
                f"{first_url} did not return a usable holdings file; nothing was kept"
            ) from error
        partial.replace(destination)
    except OSError as error:
        raise SponsorFileError(
            f"cannot save Vanguard's holdings file to {destination}: {error}"
        ) from error
    finally:
        # The temporary file must not stay, whatever happened. If it cannot be
        # removed either, the error already on its way is the one to report.
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)


def _value(row: dict[str, object], key: str) -> str | None:
    """Return a text value of a row, or ``None`` when it is absent or empty.

    Vanguard writes an absent value as an empty text.
    """
    value = row.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def read_vanguard_file(path: Path) -> VanguardFile:
    """Read a saved holdings file.

    Args:
        path: The file ``download_vanguard_file`` wrote.

    Returns:
        The date the file states the holdings for, and every row.

    Raises:
        SponsorFileError: If the file cannot be read, is not of Vanguard's
            shape, or holds another number of rows than it states.
    """
    try:
        body = path.read_bytes()
    except OSError as error:
        raise SponsorFileError(f"cannot read Vanguard's holdings file {path}: {error}") from error
    size, stated_date, entries = _page(body, str(path))
    if len(entries) != size:
        raise SponsorFileError(f"{path} states {size} rows and holds {len(entries)}")
    try:
        # The date comes with a time and a time zone: "2026-10-31T00:00:00-04:00".
        as_of = date.fromisoformat(stated_date[:10])
    except ValueError as error:
        raise SponsorFileError(f"{path}: the date '{stated_date}' is not a date") from error

    rows: list[VanguardRow] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise SponsorFileError(f"{path}: row {position} is not a holding")
        row = {str(key): value for key, value in entry.items()}
        sedol = _value(row, "sedol")
        rows.append(
            VanguardRow(
                isin=_value(row, "isin"),
                ticker=_value(row, "ticker"),
                sedol=sedol if sedol is not None and _SEDOL.fullmatch(sedol) else None,
            )
        )
    return VanguardFile(as_of=as_of, rows=tuple(rows))
