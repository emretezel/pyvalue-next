"""EODHD: its requests, and how their answers are read.

EODHD names a security ``SYMBOL.EXCHANGE``, both parts its own. Two requests
give what pyvalue needs to find a security there (ADR 0018): the list of
exchange codes it offers, and the list of symbols under one code. A third
gives the fundamentals of one security, and a fourth says how much of the
day's allowance the account has used (ADR 0028).

The API key travels in the address, as EODHD requires. So every request goes
through ``pyvalue.http``, which sends it to ``eodhd.com`` only, never along a
redirect, and keeps it out of every message. This module is handed the key;
it never reads the settings file.

EODHD also has its own codes for currencies: a market quoted in a sub-unit
carries the sub-unit's code. ``currency_of`` turns such a code into the
currency (ADR 0019).

The shape below was confirmed on the live lists of 2026-11-27 (ADR 0027): the
readers took all 59 symbol lists as they came. A line also carries a
``Country``, which is not read. The readers are strict on purpose, so that a
change of shape shows as a message that names the field, instead of as lines
that silently lack a value.

A fundamentals payload is not read here beyond the one thing the download
has to know before it keeps an answer: that it is a payload, and for the
symbol that was asked for. The account answer names the account holder, so
its reader takes the three values of the allowance and nothing else.

Author: Emre Tezel
"""

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

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

# EODHD quotes some markets in a sub-unit of their currency and gives the
# sub-unit a code of its own (ADR 0019): pence, South African cents, Israeli
# agorot. A listing's currency is the currency itself, never the quote unit.
_SUB_UNITS: Mapping[str, str] = MappingProxyType({"GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"})

# The shape of an ISO 4217 code, which is what a listing's currency has to be.
_CURRENCY: re.Pattern[str] = re.compile(r"[A-Z]{3}")

# What one fundamentals request costs of the daily allowance. Measured on
# 2026-11-27: the account's counter rose by ten for each (ADR 0028).
FUNDAMENTALS_REQUEST_COST: int = 10

# What fetches a document: (address without the key, the key) -> the bytes of
# the answer. A parameter of this type lets tests stand in for the network.
type Fetch = Callable[[str, str], bytes]


class NotFoundError(ProviderError):
    """EODHD has nothing at the address.

    It answers so for the symbol list of an exchange that is not in the
    subscription (ADR 0024), and for the fundamentals of a symbol it has none
    for (ADR 0028).
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


@dataclass(frozen=True, slots=True)
class Allowance:
    """How much of a day's requests the account has used, as EODHD counts it.

    Attributes:
        daily_limit: What the account may use in one day.
        used: What it has used on ``counted_on``.
        counted_on: The day the count belongs to. EODHD's day starts at
            midnight GMT, and the count stays as it was until the first
            request of a new day.
    """

    daily_limit: int
    used: int
    counted_on: date

    def left(self, today: date) -> int:
        """Return what is left of the day's allowance, never less than nothing.

        A count from an earlier day says nothing about today: the whole
        allowance is left.

        Args:
            today: Today's date by GMT.
        """
        used_today = self.used if self.counted_on >= today else 0
        return max(0, self.daily_limit - used_today)


def currency_of(provider_currency: str) -> str | None:
    """Return the currency a symbol line trades in, from EODHD's code for it.

    A sub-unit becomes its currency: a London line in ``GBX`` trades in
    ``GBP``. Any other code is taken as it is when it has the shape of a
    currency code. That shape is all that is checked: a code EODHD made up
    passes if it is three capital letters, and it is the listing rule that
    keeps such a line from being filled without review, because the code
    never equals the currency a fund holds the security in (ADR 0026).

    Args:
        provider_currency: The line's ``Currency`` as EODHD gives it.

    Returns:
        The ISO 4217 code, or ``None`` when the code cannot be read as a
        currency, such as ``Unknown``.
    """
    currency = _SUB_UNITS.get(provider_currency, provider_currency)
    return currency if _CURRENCY.fullmatch(currency) is not None else None


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


def fundamentals_url(provider_exchange_code: str, provider_symbol: str) -> str:
    """Return the address of the fundamentals of one security, without the key.

    Args:
        provider_exchange_code: EODHD's exchange code, such as ``US``.
        provider_symbol: EODHD's symbol under that code, such as ``BRK-B``.
    """
    # Both parts are escaped: a symbol can hold a character that would change
    # the address, as the ``&`` of ``PE&OLES`` would.
    symbol = urllib.parse.quote(provider_symbol, safe="")
    code = urllib.parse.quote(provider_exchange_code, safe="")
    return f"https://{EODHD_HOST}/api/fundamentals/{symbol}.{code}?fmt=json"


def account_url() -> str:
    """Return the address that says what the account has used today, without the key."""
    return f"https://{EODHD_HOST}/api/user?fmt=json"


def fetch_from_eodhd(url: str, api_key: str) -> bytes:
    """Fetch one document from ``eodhd.com``.

    Args:
        url: An ``https://eodhd.com/`` address, without the key.
        api_key: The API key. It is added to the address for the request and
            appears in no message.

    Returns:
        The answer's bytes, decompressed.

    Raises:
        NotFoundError: If EODHD answers that it has nothing at the address.
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
        not_found=NotFoundError,
    )


def _json(body: bytes, source: str, what: str) -> object:
    """Read an answer as JSON, or say that it is not what was expected.

    Args:
        body: The answer, or a saved file, as bytes.
        source: What to call it in a message.
        what: The kind of answer expected, for the message.

    Raises:
        ProviderError: If the bytes are not JSON.
    """
    try:
        document: object = json.loads(body)
    except ValueError as error:
        # The parser's message gives a position, never the content.
        raise ProviderError(f"{source} is not {what}: {error}") from error
    return document


def _entries(body: bytes, source: str, what: str) -> list[dict[str, object]]:
    """Read an answer as a list of objects, or say that it is not one.

    Raises:
        ProviderError: If the bytes are not JSON, not a list, or hold an
            element that is not an object.
    """
    document = _json(body, source, what)
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


def _document(body: bytes, source: str, what: str) -> dict[str, object]:
    """Read an answer as one JSON object, or say that it is not one.

    Raises:
        ProviderError: If the bytes are not JSON, or not an object.
    """
    document = _json(body, source, what)
    if not isinstance(document, dict):
        raise ProviderError(f"{source} is not {what}: it is not an object")
    return document


def check_fundamentals(body: bytes, source: str, provider_symbol: str) -> None:
    """Make sure an answer is the fundamentals payload of one symbol.

    This is all the download needs to know before it keeps an answer
    (ADR 0028): an error page or a payload for another symbol must not get a
    file. What the payload holds is not judged.

    Args:
        body: The answer, or a saved payload, as bytes.
        source: What to call it in a message.
        provider_symbol: The symbol that was asked for.

    Raises:
        ProviderError: If it is not a JSON object whose ``General.Code`` is
            the symbol.
    """
    what = "an EODHD fundamentals payload"
    general = _document(body, source, what).get("General")
    if not isinstance(general, dict):
        raise ProviderError(f"{source} is not {what}: it has no General section")
    code = general.get("Code")
    if code != provider_symbol:
        raise ProviderError(
            f"{source} is not {what} for {provider_symbol}: its General.Code is {code!r}"
        )


def _whole_number(document: dict[str, object], field: str, source: str, what: str) -> int:
    """Return one field of an answer as a whole number that is not negative.

    Raises:
        ProviderError: If the field is missing or is anything else. The
            message names the field and never its value.
    """
    value = document.get(field)
    # A bool is an int in Python, and it is not a count.
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProviderError(f"{source} is not {what}: the field {field} is not a count")
    return value


def parse_allowance(body: bytes, source: str) -> Allowance:
    """Read what the account has used of its daily allowance.

    The answer also names the account holder. Three values are read and
    nothing else, and no message quotes a value of the answer.

    Args:
        body: The answer as bytes.
        source: What to call it in a message.

    Returns:
        The daily limit, the count and the day the count belongs to.

    Raises:
        ProviderError: If it is not an object with the three values.
    """
    what = "an EODHD account answer"
    document = _document(body, source, what)
    counted_on = document.get("apiRequestsDate")
    try:
        day = date.fromisoformat(counted_on) if isinstance(counted_on, str) else None
    except ValueError:
        day = None
    if day is None:
        raise ProviderError(f"{source} is not {what}: the field apiRequestsDate is not a date")
    return Allowance(
        daily_limit=_whole_number(document, "dailyRateLimit", source, what),
        used=_whole_number(document, "apiRequests", source, what),
        counted_on=day,
    )
