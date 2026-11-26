"""EODHD: its two list requests, and how their answers are read.

EODHD names a security ``SYMBOL.EXCHANGE``, both parts its own. Two requests
give what pyvalue needs to find a security there (ADR 0018): the list of
exchange codes it offers, and the list of symbols under one code.

The API key travels in the address, as EODHD requires. So every request goes
through ``pyvalue.http``, which sends it to ``eodhd.com`` only, never along a
redirect, and keeps it out of every message. This module is handed the key;
it never reads the settings file.

Nothing has been seen live yet (ADR 0024): the shape below is EODHD's
documentation and what the legacy client read. The readers are strict on
purpose, so that a difference shows at the first live download as a message
that names the field, instead of as lines that silently lack a value.

Author: Emre Tezel
"""

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from pyvalue.http import fetch_https
from pyvalue.providers.errors import ProviderError

# pyvalue's own code and name for the provider: its row in ``provider``.
PROVIDER_CODE: str = "eodhd"
PROVIDER_NAME: str = "EODHD"

# The file in ``pyvalue/providers`` that maps EODHD's exchange codes to ours.
EXCHANGE_FILE: str = "eodhd_exchange.csv"

# The one host the API key may be sent to.
EODHD_HOST: str = "eodhd.com"

# How pyvalue names itself to EODHD. A plain client name says nothing about
# who runs the download.
_CLIENT_NAME: str = "pyvalue"

# The fields of a symbol line that are read. Each must be there on every
# line, even if empty: a field that is missing means the provider's shape is
# not the one this reader was written for.
_SYMBOL_FIELDS: tuple[str, ...] = ("Code", "Name", "Exchange", "Currency", "Type", "Isin")

# What fetches a list: (address without the key, the key) -> the bytes of the
# answer. A parameter of this type lets tests stand in for the network.
type Fetch = Callable[[str, str], bytes]


class ListNotFoundError(ProviderError):
    """EODHD has no list at the address.

    It answers so for the symbol list of an exchange that is not in the
    subscription (ADR 0024).
    """


@dataclass(frozen=True, slots=True)
class SymbolLine:
    """One line of a symbol list, as EODHD gives it.

    Every value is the provider's text with the spaces around it removed, or
    ``None`` where the provider gives nothing. Nothing is judged here: which
    lines are shares, and which exchange a line is on, is for the component
    that stores the list.

    Attributes:
        symbol: The symbol, ``Code`` in the answer.
        name: The security's name.
        venue: The venue label, ``Exchange`` in the answer.
        currency: The currency code, which can be a sub-unit such as ``GBX``.
        kind: The type of security, ``Type`` in the answer.
        isin: The ISIN as given, valid or not.
    """

    symbol: str | None
    name: str | None
    venue: str | None
    currency: str | None
    kind: str | None
    isin: str | None


def exchange_list_url() -> str:
    """Return the address of the list of exchange codes, without the key."""
    return f"https://{EODHD_HOST}/api/exchanges-list/?fmt=json"


def symbol_list_url(provider_exchange_code: str) -> str:
    """Return the address of the symbol list of one exchange code, without the key.

    Args:
        provider_exchange_code: EODHD's exchange code, such as ``US``.
    """
    # A code comes from a committed file, not from a person at a prompt, but
    # it is still escaped: it must not be able to change the address.
    code = urllib.parse.quote(provider_exchange_code, safe="")
    return f"https://{EODHD_HOST}/api/exchange-symbol-list/{code}?fmt=json"


def fetch_from_eodhd(url: str, api_key: str) -> bytes:
    """Fetch one list from ``eodhd.com``.

    Args:
        url: An ``https://eodhd.com/`` address, without the key.
        api_key: The API key. It is added to the address for the request and
            appears in no message.

    Returns:
        The answer's bytes, decompressed.

    Raises:
        ListNotFoundError: If EODHD answers that it has no such list.
        ProviderError: If the address is not on ``eodhd.com`` over HTTPS, or
            the download fails for any other reason, such as a key that is
            not accepted.
    """
    return fetch_https(
        url,
        EODHD_HOST,
        {"User-Agent": _CLIENT_NAME, "Accept": "application/json"},
        ProviderError,
        secret_query={"api_token": api_key},
        not_found=ListNotFoundError,
    )


def _entries(body: bytes, source: str, what: str) -> list[dict[str, object]]:
    """Read an answer as a list of objects, or say that it is not one.

    Args:
        body: The answer, or a saved file, as bytes.
        source: What to call it in a message.
        what: The kind of list expected, for the message.

    Raises:
        ProviderError: If the bytes are not JSON, not a list, or hold an
            element that is not an object.
    """
    try:
        document: object = json.loads(body)
    except ValueError as error:
        # The parser's message gives a position, never the content.
        raise ProviderError(f"{source} is not {what}: {error}") from error
    if not isinstance(document, list):
        # An error from EODHD arrives as an object or a text, not as a list.
        raise ProviderError(f"{source} is not {what}: it is not a list")
    entries: list[dict[str, object]] = []
    for position, entry in enumerate(document, start=1):
        if not isinstance(entry, dict):
            raise ProviderError(f"{source} is not {what}: entry {position} is not an object")
        entries.append(entry)
    return entries


def _text(
    entry: dict[str, object], field: str, source: str, position: int, what: str
) -> str | None:
    """Return one field of an entry as text, or ``None`` when it is empty.

    Raises:
        ProviderError: If the entry has no such field, or its value is
            neither text nor empty.
    """
    if field not in entry:
        raise ProviderError(f"{source} is not {what}: entry {position} has no field {field}")
    value = entry[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderError(
            f"{source} is not {what}: the field {field} of entry {position} is not text"
        )
    return value.strip() or None


def parse_exchange_list(body: bytes, source: str) -> tuple[str, ...]:
    """Read the list of exchange codes EODHD offers.

    Only the codes are read. The names, countries and market codes EODHD
    states for them are not used: our exchanges are our own reference data
    (ADR 0018).

    Args:
        body: The answer, or a saved file, as bytes.
        source: What to call it in a message.

    Returns:
        The codes, in the order of the list.

    Raises:
        ProviderError: If it is not a list of objects that each carry a code.
    """
    what = "an EODHD exchange list"
    codes: list[str] = []
    for position, entry in enumerate(_entries(body, source, what), start=1):
        code = _text(entry, "Code", source, position, what)
        if code is None:
            raise ProviderError(f"{source} is not {what}: entry {position} has an empty Code")
        codes.append(code)
    return tuple(codes)


def parse_symbol_list(body: bytes, source: str) -> tuple[SymbolLine, ...]:
    """Read the symbol list of one exchange code.

    Args:
        body: The answer, or a saved file, as bytes.
        source: What to call it in a message.

    Returns:
        Every line, in the order of the list, whatever its type.

    Raises:
        ProviderError: If it is not a list of objects that each carry the
            six fields that are read.
    """
    what = "an EODHD symbol list"
    lines: list[SymbolLine] = []
    for position, entry in enumerate(_entries(body, source, what), start=1):
        symbol, name, venue, currency, kind, isin = (
            _text(entry, field, source, position, what) for field in _SYMBOL_FIELDS
        )
        lines.append(
            SymbolLine(
                symbol=symbol, name=name, venue=venue, currency=currency, kind=kind, isin=isin
            )
        )
    return tuple(lines)
