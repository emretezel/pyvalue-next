"""The listing rule: which of the provider's lines is a security.

A listing is the provider's line in the security's home market, found by ISIN
and confirmed by ticker (ADR 0019). This module is the rule itself, for one
security at a time and with no database in it: it is given what the funds say
about the security and the provider's lines, and answers "fill with this
line" or "a person or an agent has to look, and here is why".

What is decided around the rule is not here: whether a security is held at
all, whether its market is served and its symbol lists are stored, what a
decision says, and which of two securities gets an exchange and ticker both
want. That is ``pyvalue.listings.plan`` (ADR 0026).

Author: Emre Tezel
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pyvalue.db import ProviderSymbol

# Everything but letters and digits, in a text that is already upper case.
_NOT_LETTER_OR_DIGIT: re.Pattern[str] = re.compile(r"[^A-Z0-9]")

# How an ISIN issued in the United States starts.
_US_PREFIX: str = "US"


class Reason(StrEnum):
    """Why a security was not given a listing and is on the report.

    The values are written to the report file, so they are part of what an
    agent reads. The first ten come from the rule, in the order the rule
    tests them (ADR 0026); the last four from applying a decision or a fill.
    """

    RECEIPT_READ_AS_ORDINARY_SHARE = "receipt_read_as_ordinary_share"
    US_ISIN_IN_NON_US_FUND = "us_isin_in_non_us_fund"
    SEVERAL_HOME_MARKETS = "several_home_markets"
    SEVERAL_LINES_WITH_ISIN = "several_lines_with_isin"
    TICKER_FINDS_ONE_LINE = "ticker_finds_one_line"
    TICKER_FINDS_SEVERAL_LINES = "ticker_finds_several_lines"
    NOTHING_FOUND = "nothing_found"
    OTHER_CURRENCY = "other_currency"
    SYMBOL_ON_ANOTHER_LINE = "symbol_on_another_line"
    TICKER_DIFFERS = "ticker_differs"
    DECISION_LINE_NOT_STORED = "decision_line_not_stored"
    DECISION_LINE_NOT_ALLOWED = "decision_line_not_allowed"
    DECISION_CURRENCY_UNREADABLE = "decision_currency_unreadable"
    EXCHANGE_AND_TICKER_TAKEN = "exchange_and_ticker_taken"


class MatchedBy(StrEnum):
    """Why a line is shown for a security on the report."""

    ISIN = "isin"
    TICKER = "ticker"
    ISIN_AND_TICKER = "isin and ticker"
    # The line shares the symbol of a line that carries the ISIN.
    SYMBOL = "symbol"


def ticker_key(text: str) -> str:
    """Return what is compared when two tickers are compared (ADR 0019).

    A fund and a provider write one ticker in different ways: ``NOVO B`` and
    ``NOVO-B``, ``BBD.A`` and ``BBD-A``, ``700`` and ``0700``. The key puts
    the text in upper case, drops everything but letters and digits, and
    drops leading zeros.

    Args:
        text: A fund's ticker or a provider's symbol.

    Returns:
        The key. It is empty when the text holds no letter and no digit; a
        text of zeros only has the key ``0``.
    """
    kept = _NOT_LETTER_OR_DIGIT.sub("", text.upper())
    # "000" and "0" are the same ticker, and neither is no ticker at all.
    return kept.lstrip("0") or kept[:1]


def same_ticker(one: str, other: str) -> bool:
    """Say whether two tickers are equal by the comparison of ADR 0019.

    A ticker without a key, such as ``-``, equals nothing, not even itself
    (ADR 0026): there is nothing in it to compare.

    Args:
        one: A fund's ticker or a provider's symbol.
        other: The one it is compared with.
    """
    key = ticker_key(one)
    return key != "" and key == ticker_key(other)


@dataclass(frozen=True, slots=True)
class HeldLine:
    """What one holding line says about a security, as far as the rule reads it.

    Attributes:
        non_us_fund: Whether the fund that reports the line is one that is
            not expected to hold US-coded ISINs (its scope is ``NON_US``).
        country: The country the line trades in: a home market.
        currency: The currency the fund holds the line in.
        ticker: The ticker the fund's sponsor gives, or ``None``.
        filed_isin: The ISIN the line was filed under. It differs from the
            security's for a depositary receipt read as its ordinary share
            (ADR 0015).
    """

    non_us_fund: bool
    country: str
    currency: str
    ticker: str | None
    filed_isin: str


@dataclass(frozen=True, slots=True)
class Security:
    """One security and what the funds say about it.

    Attributes:
        instrument_id: The security's id.
        isin: Its ISIN.
        company: The company's name, for the report.
        held: Its holding lines, by fund and then in the order of the filing.
    """

    instrument_id: int
    isin: str
    company: str
    held: tuple[HeldLine, ...]

    @property
    def home_countries(self) -> frozenset[str]:
        """The countries a holding line trades in. Most securities have one."""
        return frozenset(line.country for line in self.held)

    @property
    def tickers(self) -> tuple[str, ...]:
        """The tickers the holding lines give, each once, in the order of the lines."""
        return tuple(dict.fromkeys(line.ticker for line in self.held if line.ticker is not None))

    @property
    def currencies(self) -> frozenset[str]:
        """The currencies the funds hold the security in."""
        return frozenset(line.currency for line in self.held)

    @property
    def read_as_ordinary_share(self) -> bool:
        """Whether a holding line was filed under another ISIN: a receipt's (ADR 0015)."""
        return any(line.filed_isin != self.isin for line in self.held)


@dataclass(frozen=True, slots=True)
class Line:
    """One of the provider's lines, with what the rule needs worked out.

    Attributes:
        stored: The line as it is stored.
        country: The country of the exchange the line is on.
        currency: The currency the line trades in, a sub-unit turned into its
            currency, or ``None`` when the provider's code cannot be read.
            Such a line can never become a listing, but it still counts as a
            line (ADR 0026).
    """

    stored: ProviderSymbol
    country: str
    currency: str | None

    @property
    def symbol(self) -> str:
        """The provider's symbol for the line, exactly as given."""
        return self.stored.provider_symbol

    @property
    def address(self) -> tuple[str, str, str]:
        """What names the line at the provider: provider, exchange code and symbol."""
        return (
            self.stored.provider_code,
            self.stored.provider_exchange_code,
            self.stored.provider_symbol,
        )


class Lines:
    """The provider's lines, ready for the lookups of the rule.

    Whatever order the lines are given in, every lookup returns its lines in
    the order of exchange code and symbol, so that the same lines always give
    the same outcome and the same report.
    """

    def __init__(self, lines: Iterable[Line]) -> None:
        """Index the lines.

        Args:
            lines: Every stored line of the provider.
        """
        self._by_address: dict[tuple[str, str, str], Line] = {}
        self._by_isin: dict[str, list[Line]] = defaultdict(list)
        self._by_country_and_isin: dict[tuple[str, str], list[Line]] = defaultdict(list)
        self._by_country_and_key: dict[tuple[str, str], list[Line]] = defaultdict(list)
        self._by_country_and_symbol: dict[tuple[str, str], list[Line]] = defaultdict(list)
        for line in sorted(lines, key=lambda each: each.address):
            self._by_address[line.address] = line
            isin = line.stored.isin
            if isin is not None:
                self._by_isin[isin].append(line)
                self._by_country_and_isin[(line.country, isin)].append(line)
            key = ticker_key(line.symbol)
            if key:
                self._by_country_and_key[(line.country, key)].append(line)
            self._by_country_and_symbol[(line.country, line.symbol)].append(line)

    def at(self, provider_code: str, provider_exchange_code: str, symbol: str) -> Line | None:
        """Return the line a provider, an exchange code and a symbol name, if it is stored."""
        return self._by_address.get((provider_code, provider_exchange_code, symbol))

    def with_isin(self, countries: frozenset[str], isin: str) -> tuple[Line, ...]:
        """Return the lines in the given countries that carry an ISIN."""
        return _in_order(
            line
            for country in countries
            for line in self._by_country_and_isin.get((country, isin), ())
        )

    def with_isin_anywhere(self, isin: str) -> tuple[Line, ...]:
        """Return the lines that carry an ISIN, in whatever country."""
        return tuple(self._by_isin.get(isin, ()))

    def with_ticker(self, countries: frozenset[str], tickers: Iterable[str]) -> tuple[Line, ...]:
        """Return the lines in the given countries whose symbol equals one of the tickers."""
        keys = {key for key in map(ticker_key, tickers) if key}
        return _in_order(
            line
            for country in countries
            for key in keys
            for line in self._by_country_and_key.get((country, key), ())
        )

    def with_symbol(self, country: str, symbol: str) -> tuple[Line, ...]:
        """Return the lines in one country whose symbol is this text, letter for letter."""
        return tuple(self._by_country_and_symbol.get((country, symbol), ()))


def _in_order(lines: Iterable[Line]) -> tuple[Line, ...]:
    """Return each line once, in the order of exchange code and symbol."""
    return tuple(sorted({line.address: line for line in lines}.values(), key=_address))


def _address(line: Line) -> tuple[str, str, str]:
    """Return what the lines are ordered by."""
    return line.address


@dataclass(frozen=True, slots=True)
class ShownLine:
    """A line the report shows for a security.

    Attributes:
        line: The line.
        matched_by: Why it is shown.
    """

    line: Line
    matched_by: MatchedBy


@dataclass(frozen=True, slots=True)
class Fill:
    """The rule's answer "this line is the security".

    Attributes:
        security: The security.
        line: The provider's line it is given.
        ticker: What the listing's ticker is (see ``listing_ticker``).
        currency: The currency the line trades in.
    """

    security: Security
    line: Line
    ticker: str
    currency: str


@dataclass(frozen=True, slots=True)
class Case:
    """A security that is not filled and goes on the report.

    Attributes:
        security: The security.
        reason: Why it was not filled.
        detail: What the reason refers to, such as the line a decision names.
            Empty for the reasons of the rule.
        lines: The lines it could be, in the order of exchange code and symbol.
    """

    security: Security
    reason: Reason
    detail: str
    lines: tuple[ShownLine, ...]


def listing_ticker(security: Security, line: Line) -> str:
    """Return the ticker a listing on this line gets (ADR 0019, ADR 0026).

    The fund's ticker is how the exchange writes it more often than the
    provider's symbol is: ``NOVO B`` against ``NOVO-B`` in Copenhagen,
    ``BBD.A`` against ``BBD-A`` in Toronto. So it is taken, in upper case,
    when every ticker the holding lines give equals the symbol and they are
    spelled alike. In every other case the listing's ticker is the symbol in
    upper case: a fund's ticker that does not equal the symbol may belong to
    another market.

    The spelling is the fund's, whatever it is. Vanguard writes a share class
    in New York with a space as well, so Berkshire's B share is ``BRK B``
    here, not ``BRK.B``.

    Args:
        security: The security.
        line: The line it is listed on.
    """
    tickers = security.tickers
    if tickers and all(same_ticker(ticker, line.symbol) for ticker in tickers):
        spellings = {ticker.upper() for ticker in tickers}
        if len(spellings) == 1:
            return spellings.pop()
    return line.symbol.upper()


def shown_lines(security: Security, lines: Lines) -> tuple[ShownLine, ...]:
    """Return the lines the report shows for a security (ADR 0019).

    They are every line in a home market that carries the ISIN or whose
    symbol equals a fund's ticker, and every line that shares the symbol of
    one that carries the ISIN. For a receipt read as its ordinary share the
    lines that carry the share's ISIN are shown from every country: the
    holding line names the receipt's market, not the share's.

    Args:
        security: The security.
        lines: The provider's lines.
    """
    home = security.home_countries
    by_isin = (
        lines.with_isin_anywhere(security.isin)
        if security.read_as_ordinary_share
        else lines.with_isin(home, security.isin)
    )
    by_ticker = lines.with_ticker(home, security.tickers)
    shown: dict[tuple[str, str, str], ShownLine] = {}
    for line in by_isin:
        for other in lines.with_symbol(line.country, line.symbol):
            shown[other.address] = ShownLine(other, MatchedBy.SYMBOL)
    for line in by_ticker:
        shown[line.address] = ShownLine(line, MatchedBy.TICKER)
    ticker_matches = {line.address for line in by_ticker}
    for line in by_isin:
        both = line.address in ticker_matches
        shown[line.address] = ShownLine(line, MatchedBy.ISIN_AND_TICKER if both else MatchedBy.ISIN)
    return tuple(shown[address] for address in sorted(shown))


def judge(security: Security, lines: Lines) -> Fill | Case:
    """Apply the rule of ADR 0019 to one security.

    The security has to be held: the rule starts from its home markets.

    The conditions are tested in a fixed order (ADR 0026), so that a security
    is counted under one reason and the counts of two runs can be compared.

    Args:
        security: A security with at least one holding line.
        lines: The provider's lines.

    Returns:
        The line to fill with, when all six conditions hold; otherwise the
        case for the report, with the first reason that applies.
    """
    with_isin = lines.with_isin(security.home_countries, security.isin)
    reason = _no_single_line(security, with_isin, lines)
    if reason is None:
        (line,) = with_isin
        currency = line.currency
        if currency is None or security.currencies != {currency}:
            reason = Reason.OTHER_CURRENCY
        # The same text, not the ticker comparison: a duplicate in the
        # provider's own lists is spelled the same, and the looser comparison
        # would take London's `0RS1` for a second line of `RS1` (ADR 0026).
        elif len(lines.with_symbol(line.country, line.symbol)) > 1:
            reason = Reason.SYMBOL_ON_ANOTHER_LINE
        elif not all(same_ticker(ticker, line.symbol) for ticker in security.tickers):
            reason = Reason.TICKER_DIFFERS
        else:
            return Fill(security, line, listing_ticker(security, line), currency)
    return Case(security, reason, "", shown_lines(security, lines))


def _no_single_line(security: Security, with_isin: tuple[Line, ...], lines: Lines) -> Reason | None:
    """Return why there is not exactly one line to look at, or ``None`` when there is.

    Args:
        security: The security.
        with_isin: The lines in its home markets that carry its ISIN.
        lines: The provider's lines.
    """
    home = security.home_countries
    # A receipt case: the line with the right ISIN in the holding's market
    # would be the receipt, not the share.
    if security.read_as_ordinary_share:
        return Reason.RECEIPT_READ_AS_ORDINARY_SHARE
    if security.isin.startswith(_US_PREFIX) and any(line.non_us_fund for line in security.held):
        return Reason.US_ISIN_IN_NON_US_FUND
    # Which of two markets is the home one is a choice, not a lookup.
    if len(home) > 1:
        return Reason.SEVERAL_HOME_MARKETS
    if len(with_isin) > 1:
        return Reason.SEVERAL_LINES_WITH_ISIN
    if with_isin:
        return None
    # A ticker proposes a line but never fills one: a reused ticker looks the
    # same as a changed ISIN (ADR 0019).
    found = len(lines.with_ticker(home, security.tickers))
    if found == 0:
        return Reason.NOTHING_FOUND
    return Reason.TICKER_FINDS_ONE_LINE if found == 1 else Reason.TICKER_FINDS_SEVERAL_LINES
