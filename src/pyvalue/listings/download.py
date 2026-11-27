"""The symbols download: the provider's lists into files.

``pyvalue symbols download`` contacts the data provider (ADR 0024). It asks
for the list of exchange codes and then for the symbol list of every code our
exchange file gives a market, and keeps each answer as a file. It never opens
the database: storing the lists is the load's job
(``pyvalue.listings.symbols``), which reads these files and cannot reach the
network. The one other thing that contacts the provider is the fundamentals
download (``pyvalue.fundamentals.download``, ADR 0028).

A subscription is bought for a month at a time, so what is saved here has to
be enough to work with afterwards. Two rules protect a good file: an answer
is given its final name only once it reads back as a list of the provider's
shape, and an answer that is suspiciously short does not replace the list
that is already saved.

Author: Emre Tezel
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pyvalue.listings.errors import ListingsError
from pyvalue.listings.saved_lists import (
    DEFAULT_LISTS_DIR,
    EXCHANGE_LIST_FILE,
    suspiciously_short,
    symbol_list_file,
)
from pyvalue.providers import ExchangeCodes, ProviderError, packaged_exchange_codes
from pyvalue.providers.eodhd import (
    EXCHANGE_FILE,
    Fetch,
    NotFoundError,
    exchange_list_url,
    fetch_from_eodhd,
    parse_exchange_list,
    parse_symbol_list,
    symbol_list_url,
)
from pyvalue.saved_file import save_whole


class DownloadStatus(Enum):
    """What happened to the symbol list of one exchange code."""

    SAVED = "saved"
    NOT_OFFERED = "no longer offered by the provider"
    NOT_IN_SUBSCRIPTION = "not in the subscription"
    REFUSED_AS_SHORT = "suspiciously short against the saved list"


@dataclass(frozen=True, slots=True)
class ListDownload:
    """What happened to the symbol list of one exchange code.

    Attributes:
        provider_exchange_code: The code.
        status: Whether the list was saved, and if not, why.
        lines: The number of lines of the answer, or ``None`` when there was
            none.
        saved_before: The number of lines of the list that was saved before,
            or ``None`` when there was none that could be read.
    """

    provider_exchange_code: str
    status: DownloadStatus
    lines: int | None
    saved_before: int | None


@dataclass(frozen=True, slots=True)
class SymbolsDownload:
    """The outcome of one ``pyvalue symbols download``.

    Attributes:
        offered: The exchange codes the provider offers, in its order.
        offered_not_in_file: The offered codes our exchange file does not
            have at all: a market that may be worth a row.
        lists: One outcome per exchange code that has a market in our file,
            in the order of the file.
    """

    offered: tuple[str, ...]
    offered_not_in_file: tuple[str, ...]
    lists: tuple[ListDownload, ...]

    def with_status(self, status: DownloadStatus) -> tuple[ListDownload, ...]:
        """Return the lists that ended with one status."""
        return tuple(each for each in self.lists if each.status is status)


def _saved_lines(path: Path) -> int | None:
    """Return how many lines the saved list has, or ``None`` if there is none to trust.

    A saved file that cannot be read as a symbol list protects nothing, so a
    new answer may replace it.
    """
    try:
        return len(parse_symbol_list(path.read_bytes(), str(path)))
    except OSError, ProviderError:
        return None


def _download_list(
    provider_exchange_code: str, lists_dir: Path, api_key: str, fetch: Fetch
) -> ListDownload:
    """Download the symbol list of one exchange code and keep it, unless it looks wrong.

    Raises:
        ProviderError: If the request fails for another reason than "not
            found", or the answer is not a symbol list.
        ListingsError: If the file cannot be written.
    """
    code = provider_exchange_code
    url = symbol_list_url(code)
    try:
        body = fetch(url, api_key)
    except NotFoundError:
        return ListDownload(code, DownloadStatus.NOT_IN_SUBSCRIPTION, None, None)
    # Read before it is kept: an error page or a changed shape must not get a
    # final name. The address in the message carries no key.
    lines = len(parse_symbol_list(body, url))
    destination = lists_dir / symbol_list_file(code)
    saved_before = _saved_lines(destination)
    if saved_before is not None and suspiciously_short(lines, saved_before):
        return ListDownload(code, DownloadStatus.REFUSED_AS_SHORT, lines, saved_before)
    save_whole(body, destination, ListingsError)
    return ListDownload(code, DownloadStatus.SAVED, lines, saved_before)


def download_symbols(
    api_key: str,
    lists_dir: Path = DEFAULT_LISTS_DIR,
    codes: ExchangeCodes | None = None,
    fetch: Fetch = fetch_from_eodhd,
) -> SymbolsDownload:
    """Download the provider's exchange list and symbol lists into files.

    The symbol list of a code is requested only if the exchange list offers
    the code: the provider once answered for an exchange it had dropped with
    a stub (ADR 0018).

    Args:
        api_key: The provider's API key. It is handed to ``fetch`` and to
            nothing else.
        lists_dir: Where to keep the lists.
        codes: The provider's exchange file. Defaults to the one shipped with
            pyvalue.
        fetch: What performs a request. Tests pass their own.

    Returns:
        What the provider offers and what happened to each list.

    Raises:
        ProviderError: If a request fails for another reason than "not
            found", or an answer is not of the provider's shape. The run
            stops there; what was saved before stays.
        ListingsError: If a file cannot be written.
    """
    theirs = packaged_exchange_codes(EXCHANGE_FILE) if codes is None else codes
    url = exchange_list_url()
    body = fetch(url, api_key)
    offered = parse_exchange_list(body, url)
    save_whole(body, lists_dir / EXCHANGE_LIST_FILE, ListingsError)

    wanted = theirs.codes_with_a_market()
    on_offer = set(offered)
    known = set(wanted) | theirs.codes_left_out()
    lists = tuple(
        _download_list(code, lists_dir, api_key, fetch)
        if code in on_offer
        else ListDownload(code, DownloadStatus.NOT_OFFERED, None, None)
        for code in wanted
    )
    return SymbolsDownload(
        offered=offered,
        offered_not_in_file=tuple(code for code in offered if code not in known),
        lists=lists,
    )
