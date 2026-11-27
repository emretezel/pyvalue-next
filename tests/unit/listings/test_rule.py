"""Tests for ``pyvalue.listings.rule``: the listing rule of ADR 0019, read as ADR 0026 says.

The rule is a pure function of one security and the provider's lines, so no
test here needs a database. The first group replays the worked examples of
ADR 0019; the others take the conditions one by one.

Author: Emre Tezel
"""

import string
from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import ProviderSymbol
from pyvalue.listings.rule import (
    Case,
    Fill,
    HeldLine,
    Line,
    Lines,
    MatchedBy,
    Reason,
    Security,
    judge,
    listing_ticker,
    same_ticker,
    shown_lines,
    ticker_key,
)

# The exchange each sample code stands for. The rule does not read it; it is
# there so that the sample lines look like stored ones.
_MIC: dict[str, str] = {
    "KO": "XKRX",
    "KQ": "XKOS",
    "CO": "XCSE",
    "XETRA": "XETR",
    "US": "XNYS",
    "BK": "XBKK",
    "KLSE": "XKLS",
    "JSE": "XJSE",
    "TO": "XTSE",
    "LSE": "XLON",
}

_HYNIX: str = "KR7000660001"


def _line(
    code: str,
    symbol: str,
    country: str,
    currency: str | None,
    isin: str | None = None,
    name: str | None = None,
) -> Line:
    """Return one provider line. A currency of ``None`` is a code that cannot be read."""
    return Line(
        stored=ProviderSymbol(
            provider_code="eodhd",
            provider_exchange_code=code,
            provider_symbol=symbol,
            mic=_MIC[code],
            provider_name=name,
            provider_currency="Unknown" if currency is None else currency,
            isin=isin,
        ),
        country=country,
        currency=currency,
    )


def _held(
    isin: str,
    country: str,
    currency: str,
    ticker: str | None = None,
    *,
    non_us_fund: bool = True,
    filed_isin: str | None = None,
) -> HeldLine:
    """Return one holding line of the security with this ISIN."""
    return HeldLine(
        non_us_fund=non_us_fund,
        country=country,
        currency=currency,
        ticker=ticker,
        filed_isin=isin if filed_isin is None else filed_isin,
    )


def _security(isin: str, *held: HeldLine) -> Security:
    """Return a security with the given holding lines."""
    return Security(instrument_id=1, isin=isin, company="Sample Co", held=held)


def _hynix(ticker: str | None = "000660", currency: str = "KRW") -> Security:
    """Return SK Hynix as VXUS holds it, or with another ticker or currency."""
    return _security(_HYNIX, _held(_HYNIX, "KR", currency, ticker))


def _reason(outcome: Fill | Case) -> Reason:
    """Return the reason of an outcome that must be a case."""
    assert isinstance(outcome, Case)
    return outcome.reason


def _filled(outcome: Fill | Case) -> Fill:
    """Return an outcome that must be a fill."""
    assert isinstance(outcome, Fill)
    return outcome


# --- the worked examples of ADR 0019 ---


def test_sk_hynix_is_filled_from_its_one_line() -> None:
    """One line, ISIN and ticker agree."""
    line = _line("KO", "000660", "KR", "KRW", _HYNIX)

    fill = _filled(judge(_hynix(), Lines([line])))

    assert (fill.line, fill.ticker, fill.currency) == (line, "000660", "KRW")


def test_novo_nordisk_is_filled_although_the_ticker_is_written_differently() -> None:
    """``NOVO B`` equals ``NOVO-B``; the listing keeps the fund's spelling."""
    isin = "DK0062498333"
    security = _security(isin, _held(isin, "DK", "DKK", "NOVO B"))

    fill = _filled(judge(security, Lines([_line("CO", "NOVO-B", "DK", "DKK", isin)])))

    assert (fill.ticker, fill.line.symbol) == ("NOVO B", "NOVO-B")


def test_sap_is_filled_on_xetra() -> None:
    """Only Xetra is an exchange of ours in Germany, so there is one line."""
    isin = "DE0007164600"
    security = _security(isin, _held(isin, "DE", "EUR", "SAP"))

    assert _filled(judge(security, Lines([_line("XETRA", "SAP", "DE", "EUR", isin)]))).ticker == (
        "SAP"
    )


def test_bank_of_america_goes_to_the_agent_because_two_lines_carry_its_isin() -> None:
    """The provider gives a preferred series the common share's ISIN."""
    isin = "US0605051046"
    security = _security(isin, _held(isin, "US", "USD", "BAC", non_us_fund=False))
    lines = Lines([_line("US", "BAC", "US", "USD", isin), _line("US", "BAC-PS", "US", "USD", isin)])

    assert _reason(judge(security, lines)) is Reason.SEVERAL_LINES_WITH_ISIN


def test_delta_electronics_finds_nothing_for_its_foreign_board_share() -> None:
    """The local share is another ISIN, and ``DELTA-F`` is not ``DELTA``."""
    isin = "TH0528A10Z14"
    security = _security(isin, _held(isin, "TH", "THB", "DELTA-F"))
    lines = Lines([_line("BK", "DELTA", "TH", "THB", "TH0528010Z18")])

    assert _reason(judge(security, lines)) is Reason.NOTHING_FOUND


def test_maybank_goes_to_the_agent_because_the_ticker_differs() -> None:
    """The fund gives a letter code, the provider a number."""
    isin = "MYL1155OO000"
    security = _security(isin, _held(isin, "MY", "MYR", "MAYBANK"))

    outcome = judge(security, Lines([_line("KLSE", "1155", "MY", "MYR", isin)]))

    assert _reason(outcome) is Reason.TICKER_DIFFERS


def test_naspers_is_proposed_by_its_ticker_and_not_filled() -> None:
    """No line has the ISIN; the ticker finds one, with an older ISIN."""
    isin = "ZAE000351946"
    security = _security(isin, _held(isin, "ZA", "ZAR", "NPN"))
    line = _line("JSE", "NPN", "ZA", "ZAR", "ZAE000325783")

    outcome = judge(security, Lines([line]))

    assert _reason(outcome) is Reason.TICKER_FINDS_ONE_LINE
    assert isinstance(outcome, Case)
    assert [(shown.line, shown.matched_by) for shown in outcome.lines] == [(line, MatchedBy.TICKER)]


def test_qfin_is_a_receipt_read_as_its_ordinary_share() -> None:
    """The holding line was filed under the receipt's ISIN, so nothing is filled."""
    isin = "KYG8851G1001"
    security = _security(isin, _held(isin, "US", "USD", "QFIN", filed_isin="US88557W1018"))
    lines = Lines([_line("US", "QFIN", "US", "USD", isin)])

    assert _reason(judge(security, lines)) is Reason.RECEIPT_READ_AS_ORDINARY_SHARE


def test_barrick_is_held_in_several_markets() -> None:
    """Which of them is the home market is a choice."""
    isin = "CA06849F1080"
    security = _security(
        isin, _held(isin, "CA", "CAD"), _held(isin, "GB", "GBP"), _held(isin, "US", "USD")
    )
    lines = Lines([_line("TO", "ABX", "CA", "CAD", isin), _line("US", "B", "US", "USD", isin)])

    assert _reason(judge(security, lines)) is Reason.SEVERAL_HOME_MARKETS


# --- the conditions, one by one ---


def test_a_security_without_a_fund_ticker_is_filled_by_its_isin() -> None:
    """The listing's ticker is then the provider's symbol."""
    fill = _filled(judge(_hynix(ticker=None), Lines([_line("KO", "000660", "KR", "KRW", _HYNIX)])))

    assert fill.ticker == "000660"


def test_a_line_outside_the_home_market_is_never_a_candidate() -> None:
    """A company is not analysed on a foreign line (ADR 0019)."""
    lines = Lines([_line("US", "HXSCL", "US", "USD", _HYNIX)])

    outcome = judge(_hynix(), lines)

    assert _reason(outcome) is Reason.NOTHING_FOUND
    assert isinstance(outcome, Case)
    assert outcome.lines == ()


def test_a_line_in_another_currency_is_not_filled() -> None:
    """A second line of the same share in another currency looks just like it."""
    lines = Lines([_line("KO", "000660", "KR", "USD", _HYNIX)])

    assert _reason(judge(_hynix(), lines)) is Reason.OTHER_CURRENCY


def test_a_line_whose_currency_cannot_be_read_is_not_filled() -> None:
    """It can never become the listing (ADR 0026)."""
    lines = Lines([_line("KO", "000660", "KR", None, _HYNIX)])

    assert _reason(judge(_hynix(), lines)) is Reason.OTHER_CURRENCY


def test_holding_lines_in_two_currencies_are_not_filled() -> None:
    """Every line must be held in the line's currency."""
    security = _security(_HYNIX, _held(_HYNIX, "KR", "KRW"), _held(_HYNIX, "KR", "USD"))
    lines = Lines([_line("KO", "000660", "KR", "KRW", _HYNIX)])

    assert _reason(judge(security, lines)) is Reason.OTHER_CURRENCY


def test_a_symbol_that_is_on_another_line_is_not_filled() -> None:
    """The provider's KOSDAQ list has repeated a KOSPI share, without its ISIN."""
    kospi = _line("KO", "000660", "KR", "KRW", _HYNIX)
    kosdaq = _line("KQ", "000660", "KR", "KRW")

    outcome = judge(_hynix(), Lines([kospi, kosdaq]))

    assert _reason(outcome) is Reason.SYMBOL_ON_ANOTHER_LINE
    assert isinstance(outcome, Case)
    assert [(shown.line, shown.matched_by) for shown in outcome.lines] == [
        (kospi, MatchedBy.ISIN_AND_TICKER),
        (kosdaq, MatchedBy.TICKER),
    ]


def test_a_symbol_that_only_looks_alike_is_not_a_duplicate() -> None:
    """London's ``0RS1`` is another company's line; ``RS1`` is still filled (ADR 0026)."""
    isin = "GB0003096442"
    security = _security(isin, _held(isin, "GB", "GBP", "RS1"))
    lines = Lines(
        [_line("LSE", "RS1", "GB", "GBP", isin), _line("LSE", "0RS1", "GB", "EUR", "DE0006459324")]
    )

    assert _filled(judge(security, lines)).line.symbol == "RS1"


def test_a_duplicate_whose_currency_cannot_be_read_still_counts() -> None:
    """Leaving it out would hide that two lines carry the ISIN (ADR 0026)."""
    lines = Lines(
        [_line("KO", "000660", "KR", "KRW", _HYNIX), _line("KQ", "660", "KR", None, _HYNIX)]
    )

    assert _reason(judge(_hynix(), lines)) is Reason.SEVERAL_LINES_WITH_ISIN


def test_a_ticker_that_finds_several_lines_is_reported_as_such() -> None:
    """No line has the ISIN, and the ticker does not settle it either."""
    lines = Lines([_line("KO", "000660", "KR", "KRW"), _line("KQ", "660", "KR", "KRW")])

    assert _reason(judge(_hynix(), lines)) is Reason.TICKER_FINDS_SEVERAL_LINES


def test_a_us_coded_isin_in_the_non_us_fund_is_not_filled() -> None:
    """It is a depositary receipt: the share itself trades elsewhere."""
    isin = "US23703Q2030"
    security = _security(isin, _held(isin, "US", "USD", "DQ", non_us_fund=True))
    lines = Lines([_line("US", "DQ", "US", "USD", isin)])

    assert _reason(judge(security, lines)) is Reason.US_ISIN_IN_NON_US_FUND


def test_a_us_coded_isin_in_the_us_fund_is_filled() -> None:
    """That is where a US share is expected."""
    isin = "US0846707026"
    security = _security(isin, _held(isin, "US", "USD", "BRK B", non_us_fund=False))

    fill = _filled(judge(security, Lines([_line("US", "BRK-B", "US", "USD", isin)])))

    assert (fill.ticker, fill.line.symbol) == ("BRK B", "BRK-B")


def test_every_ticker_the_holding_lines_give_must_equal_the_symbol() -> None:
    """One line that says otherwise is enough to send the security to the agent."""
    security = _security(
        _HYNIX, _held(_HYNIX, "KR", "KRW", "000660"), _held(_HYNIX, "KR", "KRW", "HYNIX")
    )
    lines = Lines([_line("KO", "000660", "KR", "KRW", _HYNIX)])

    assert _reason(judge(security, lines)) is Reason.TICKER_DIFFERS


def test_a_ticker_with_nothing_to_compare_does_not_confirm_a_line() -> None:
    """A ticker of punctuation only equals nothing (ADR 0026)."""
    lines = Lines([_line("KO", "000660", "KR", "KRW", _HYNIX)])

    assert _reason(judge(_hynix(ticker="-"), lines)) is Reason.TICKER_DIFFERS


@pytest.mark.parametrize(
    ("security", "expected"),
    [
        pytest.param(
            _security(
                "US23703Q2030",
                _held("US23703Q2030", "US", "USD", filed_isin="US0000000002"),
                _held("US23703Q2030", "GB", "GBP"),
            ),
            Reason.RECEIPT_READ_AS_ORDINARY_SHARE,
            id="a receipt read as its ordinary share comes first",
        ),
        pytest.param(
            _security(
                "US23703Q2030",
                _held("US23703Q2030", "US", "USD"),
                _held("US23703Q2030", "GB", "GBP"),
            ),
            Reason.US_ISIN_IN_NON_US_FUND,
            id="a US-coded ISIN in the non-US fund comes before several markets",
        ),
        pytest.param(
            _security(_HYNIX, _held(_HYNIX, "KR", "USD", "HYNIX"), _held(_HYNIX, "US", "USD")),
            Reason.SEVERAL_HOME_MARKETS,
            id="several markets come before what the lines say",
        ),
        pytest.param(
            _hynix(ticker="HYNIX", currency="USD"),
            Reason.SEVERAL_LINES_WITH_ISIN,
            id="several lines with the ISIN come before currency and ticker",
        ),
    ],
)
def test_the_first_reason_in_the_fixed_order_is_the_one_reported(
    security: Security, expected: Reason
) -> None:
    """A security that fails several conditions is counted once (ADR 0026)."""
    lines = Lines(
        [
            _line("KO", "000660", "KR", "KRW", security.isin),
            _line("KQ", "000660", "KR", "KRW", security.isin),
        ]
    )

    assert _reason(judge(security, lines)) is expected


def test_the_currency_is_looked_at_before_the_symbol_and_the_ticker() -> None:
    """The order of the three checks on the one line with the ISIN."""
    line = _line("KO", "000660", "KR", "KRW", _HYNIX)
    duplicate = _line("KQ", "000660", "KR", "KRW")

    assert _reason(judge(_hynix("HYNIX", "USD"), Lines([line, duplicate]))) is (
        Reason.OTHER_CURRENCY
    )
    assert _reason(judge(_hynix("HYNIX"), Lines([line, duplicate]))) is (
        Reason.SYMBOL_ON_ANOTHER_LINE
    )


# --- the ticker that is written ---


def test_the_funds_ticker_is_written_in_upper_case() -> None:
    """The listing table takes upper case only."""
    security = _security(_HYNIX, _held(_HYNIX, "KR", "KRW", "novo b"))

    assert listing_ticker(security, _line("CO", "NOVO-B", "DK", "DKK")) == "NOVO B"


def test_tickers_that_are_spelled_differently_give_way_to_the_symbol() -> None:
    """Two funds agree on the ticker but not on its spelling: neither is taken."""
    security = _security(
        _HYNIX, _held(_HYNIX, "US", "USD", "BRK B"), _held(_HYNIX, "US", "USD", "BRK.B")
    )

    assert listing_ticker(security, _line("US", "BRK-B", "US", "USD")) == "BRK-B"


def test_a_ticker_that_does_not_equal_the_symbol_is_not_written() -> None:
    """A decision can pick such a line; the fund's ticker may be another market's."""
    security = _security(_HYNIX, _held(_HYNIX, "MY", "MYR", "MAYBANK"))

    assert listing_ticker(security, _line("KLSE", "1155", "MY", "MYR")) == "1155"


def test_a_symbol_in_small_letters_is_written_in_upper_case() -> None:
    """Otherwise the table would refuse the row and the whole run with it."""
    assert listing_ticker(_hynix(ticker=None), _line("KO", "abc", "KR", "KRW")) == "ABC"


# --- the lines the report shows ---


def test_the_report_shows_the_lines_by_isin_by_ticker_and_by_shared_symbol() -> None:
    """Each line once, with the strongest reason, in the order of code and symbol."""
    by_isin = _line("KQ", "660X", "KR", "KRW", _HYNIX)
    shares_symbol = _line("KO", "660X", "KR", "KRW")
    by_ticker = _line("KO", "000660", "KR", "KRW")
    both = _line("KQ", "0660", "KR", "KRW", _HYNIX)
    elsewhere = _line("US", "000660", "US", "USD", _HYNIX)
    unrelated = _line("KO", "005930", "KR", "KRW", "KR7005930003")

    shown = shown_lines(
        _hynix(), Lines([unrelated, elsewhere, both, by_ticker, shares_symbol, by_isin])
    )

    assert [(each.line, each.matched_by) for each in shown] == [
        (by_ticker, MatchedBy.TICKER),
        (shares_symbol, MatchedBy.SYMBOL),
        (both, MatchedBy.ISIN_AND_TICKER),
        (by_isin, MatchedBy.ISIN),
    ]


def test_a_receipt_read_as_its_ordinary_share_is_shown_its_lines_in_every_country() -> None:
    """The holding line names the receipt's market, not the share's (ADR 0019)."""
    isin = "KYG8851G1001"
    security = _security(isin, _held(isin, "US", "USD", "QFIN", filed_isin="US88557W1018"))
    receipt = _line("US", "QFIN", "US", "USD", "US88557W1018")
    share = _line("KO", "3660", "KR", "KRW", isin)

    assert [
        (each.line, each.matched_by) for each in shown_lines(security, Lines([receipt, share]))
    ] == [
        (share, MatchedBy.ISIN),
        (receipt, MatchedBy.TICKER),
    ]


def test_a_stored_line_is_found_by_what_names_it() -> None:
    """A decision names a line by provider, exchange code and symbol."""
    line = _line("KO", "000660", "KR", "KRW", _HYNIX)
    lines = Lines([line])

    assert lines.at("eodhd", "KO", "000660") == line
    assert lines.at("eodhd", "KQ", "000660") is None
    assert lines.at("other", "KO", "000660") is None


# --- the ticker comparison ---


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("NOVO B", "NOVOB"),
        ("novo-b", "NOVOB"),
        ("BRK.B", "BRKB"),
        ("BRK/B", "BRKB"),
        ("0700", "700"),
        ("700", "700"),
        ("005930", "5930"),
        ("000", "0"),
        ("0", "0"),
        ("0A", "A"),
        ("A0", "A0"),
        ("-", ""),
        ("", ""),
    ],
)
def test_the_key_of_a_ticker(text: str, key: str) -> None:
    """Upper case, letters and digits only, no leading zeros (ADR 0019)."""
    assert ticker_key(text) == key


@pytest.mark.parametrize(
    ("one", "other"), [("NOVO B", "NOVO-B"), ("BRK.B", "BRK-B"), ("700", "0700"), ("000", "0")]
)
def test_tickers_that_are_equal(one: str, other: str) -> None:
    """The examples of ADR 0019."""
    assert same_ticker(one, other)
    assert same_ticker(other, one)


@pytest.mark.parametrize(
    ("one", "other"), [("DELTA-F", "DELTA"), ("MAYBANK", "1155"), ("-", "-"), ("", ""), ("A", "")]
)
def test_tickers_that_are_not_equal(one: str, other: str) -> None:
    """A ticker with nothing to compare equals nothing, not even itself (ADR 0026)."""
    assert not same_ticker(one, other)


@given(st.text(max_size=12))
def test_the_key_of_a_key_is_the_key(text: str) -> None:
    """Comparing twice changes nothing."""
    assert ticker_key(ticker_key(text)) == ticker_key(text)


@given(st.text(max_size=12))
def test_a_key_holds_capital_letters_and_digits_only(text: str) -> None:
    """Whatever is put in, and a key never starts with a zero unless it is the zero."""
    key = ticker_key(text)

    assert set(key) <= set(string.ascii_uppercase + string.digits)
    assert key == "0" or not key.startswith("0")


@given(st.text(alphabet=string.ascii_letters + string.digits + " .-/&", max_size=12))
def test_case_and_punctuation_make_no_difference(text: str) -> None:
    """How a fund and a provider differ in writing one ticker."""
    spaced = " ".join(text)

    assert ticker_key(text.lower()) == ticker_key(text.upper()) == ticker_key(spaced)


@given(st.text(max_size=8), st.text(max_size=8))
def test_the_comparison_does_not_depend_on_which_ticker_comes_first(one: str, other: str) -> None:
    """Equal is equal from both sides."""
    assert same_ticker(one, other) == same_ticker(other, one)


# --- the rule as a whole ---

_ISINS: tuple[str, ...] = ("KR7000660001", "KR7005930003", "US0846707026")
_COUNTRY_OF: dict[str, str] = {"KO": "KR", "KQ": "KR", "US": "US"}


@st.composite
def _worlds(draw: st.DrawFn) -> tuple[Security, list[Line]]:
    """Draw a security and a handful of lines that may or may not be it."""
    addresses = draw(
        st.lists(
            st.tuples(st.sampled_from(sorted(_COUNTRY_OF)), st.sampled_from(["A", "0A", "B", "a"])),
            unique=True,
            max_size=6,
        )
    )
    lines = [
        _line(
            code,
            symbol,
            _COUNTRY_OF[code],
            draw(st.sampled_from(["KRW", "USD", None])),
            draw(st.sampled_from([None, *_ISINS])),
        )
        for code, symbol in addresses
    ]
    isin = draw(st.sampled_from(_ISINS))
    held = draw(
        st.lists(
            st.builds(
                HeldLine,
                non_us_fund=st.booleans(),
                country=st.sampled_from(["KR", "US"]),
                currency=st.sampled_from(["KRW", "USD"]),
                ticker=st.sampled_from([None, "A", "a", "B", "-"]),
                filed_isin=st.sampled_from([isin, isin, isin, _ISINS[0]]),
            ),
            min_size=1,
            max_size=2,
        )
    )
    return Security(instrument_id=1, isin=isin, company="Sample Co", held=tuple(held)), lines


@given(_worlds(), st.randoms())
def test_the_order_of_the_lines_makes_no_difference(
    world: tuple[Security, list[Line]], random: Random
) -> None:
    """The same lines always give the same outcome and the same report."""
    security, lines = world
    shuffled = list(lines)
    random.shuffle(shuffled)

    assert judge(security, Lines(shuffled)) == judge(security, Lines(lines))


@given(_worlds())
def test_a_filled_line_always_meets_the_conditions(world: tuple[Security, list[Line]]) -> None:
    """Whatever the lines are, a fill is never a guess (ADR 0019)."""
    security, lines = world
    outcome = judge(security, Lines(lines))
    if isinstance(outcome, Case):
        return

    line = outcome.line
    # One home market, and the line is in it and carries the ISIN.
    assert security.home_countries == {line.country}
    assert line.stored.isin == security.isin
    assert [
        each for each in lines if each.country == line.country and each.stored.isin == security.isin
    ] == [line]
    # The currency the funds hold it in, and no second line of that symbol.
    assert security.currencies == {outcome.currency} == {line.currency}
    assert [
        each for each in lines if each.country == line.country and each.symbol == line.symbol
    ] == [line]
    # No ticker contradicts it, and it is no receipt case.
    assert all(same_ticker(ticker, line.symbol) for ticker in security.tickers)
    assert not security.read_as_ordinary_share
    assert not (security.isin.startswith("US") and any(each.non_us_fund for each in security.held))
    assert outcome.ticker == outcome.ticker.upper()
