"""Tests for ``pyvalue.listings.plan``: what one run of the listing fill does (ADR 0026).

The plan is a pure function of what is stored and what is decided, so no test
here needs a database.

Author: Emre Tezel
"""

from collections.abc import Sequence
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import ProviderSymbol
from pyvalue.listings import ListingsError
from pyvalue.listings.decisions import ListingDecision
from pyvalue.listings.plan import Markets, Plan, StoredListing, by_country, plan_listings
from pyvalue.listings.rule import HeldLine, Line, Lines, Reason, Security

# The exchange and the country each sample code stands for.
_MIC: dict[str, str] = {"KO": "XKRX", "KQ": "XKOS", "US": "XNYS", "KLSE": "XKLS", "LSE": "XLON"}
_COUNTRY: dict[str, str] = {"KO": "KR", "KQ": "KR", "US": "US", "KLSE": "MY", "LSE": "GB"}

_HYNIX: str = "KR7000660001"
_SAMSUNG: str = "KR7005930003"
_MAYBANK: str = "MYL1155OO000"
_TOYOTA: str = "JP3633400001"
_QFIN: str = "KYG8851G1001"


def _line(code: str, symbol: str, currency: str | None, isin: str | None = None) -> Line:
    """Return one provider line. A currency of ``None`` is a code that cannot be read."""
    return Line(
        stored=ProviderSymbol(
            provider_code="eodhd",
            provider_exchange_code=code,
            provider_symbol=symbol,
            mic=_MIC[code],
            provider_name=None,
            provider_currency="Unknown" if currency is None else currency,
            isin=isin,
        ),
        country=_COUNTRY[code],
        currency=currency,
    )


def _security(
    instrument_id: int,
    isin: str,
    country: str | None,
    currency: str = "KRW",
    ticker: str | None = None,
    filed_isin: str | None = None,
) -> Security:
    """Return a security with one holding line, or with none when it has no country."""
    held = (
        ()
        if country is None
        else (
            HeldLine(
                non_us_fund=True,
                country=country,
                currency=currency,
                ticker=ticker,
                filed_isin=isin if filed_isin is None else filed_isin,
            ),
        )
    )
    return Security(instrument_id=instrument_id, isin=isin, company=f"Company {isin}", held=held)


def _decision(isin: str, line: tuple[str, str, str] | None) -> ListingDecision:
    """Return a decision for a security: a line, or no listing."""
    return ListingDecision(
        isin=isin,
        line=line,
        company="Sample Co",
        decided_on=date(2026, 11, 26),
        decided_by="agent",
        evidence="made up",
    )


def _markets(*stored_codes: str) -> Markets:
    """Return the sample markets, with a stored list for the given codes only."""
    codes: dict[str, set[str]] = {}
    for code, country in _COUNTRY.items():
        codes.setdefault(country, set()).add(code)
    return Markets(
        codes_of_country={country: frozenset(each) for country, each in codes.items()},
        stored_codes=frozenset(stored_codes),
    )


_ALL_STORED: Markets = _markets(*_COUNTRY)


def _plan(
    securities: Sequence[Security],
    lines: Sequence[Line],
    decisions: Sequence[ListingDecision] = (),
    stored: Sequence[StoredListing] = (),
    markets: Markets = _ALL_STORED,
) -> Plan:
    """Plan a run on the sample markets."""
    return plan_listings(securities, Lines(lines), markets, decisions, stored)


def _filled(plan: Plan) -> list[tuple[str, str, str, bool]]:
    """Return what a plan writes: ISIN, exchange, ticker, and whether it was decided."""
    return [
        (each.fill.security.isin, each.fill.line.stored.mic, each.fill.ticker, each.decided)
        for each in plan.fills
    ]


def _cases(plan: Plan) -> list[tuple[str, Reason, str]]:
    """Return what a plan reports: ISIN, reason and detail."""
    return [(case.security.isin, case.reason, case.detail) for case in plan.cases]


# --- sorting the securities ---


def test_a_security_the_rule_is_sure_about_is_filled() -> None:
    """Held, served, its list stored, no decision: the rule decides."""
    plan = _plan(
        [_security(1, _HYNIX, "KR", ticker="000660")], [_line("KO", "000660", "KRW", _HYNIX)]
    )

    assert _filled(plan) == [(_HYNIX, "XKRX", "000660", False)]
    assert plan.cases == ()


def test_a_security_that_has_a_listing_is_skipped() -> None:
    """A run never changes a listing (ADR 0019)."""
    plan = _plan(
        [_security(1, _HYNIX, "KR", ticker="000660")],
        [_line("KO", "000660", "KRW", _HYNIX)],
        stored=[StoredListing(1, "XKRX", "000660", ("eodhd", "KO", "000660"))],
    )

    assert (plan.already_listed, plan.fills, plan.cases) == (1, (), ())


def test_a_security_no_fund_holds_gets_no_listing() -> None:
    """Even when the provider has a line with its ISIN."""
    security = _security(1, _HYNIX, None)

    plan = _plan([security], [_line("KO", "000660", "KRW", _HYNIX)])

    assert plan.not_held == (security,)
    assert (plan.fills, plan.cases) == ((), ())


def test_a_security_whose_market_is_not_served_gets_no_listing_and_no_review() -> None:
    """Toyota: the provider has no Japanese exchange, and its US line is no candidate."""
    toyota = _security(1, _TOYOTA, "JP", "JPY", "7203")

    plan = _plan([toyota], [_line("US", "TM", "USD", _TOYOTA)])

    assert plan.not_served == (toyota,)
    assert (plan.fills, plan.cases) == ((), ())


def test_a_security_waits_while_a_list_of_its_country_is_missing() -> None:
    """KOSPI is stored and has the line; KOSDAQ is not, so the rule cannot know yet."""
    hynix = _security(1, _HYNIX, "KR", ticker="000660")

    plan = _plan([hynix], [_line("KO", "000660", "KRW", _HYNIX)], markets=_markets("KO", "US"))

    assert plan.waiting == (hynix,)
    assert plan.missing_lists == ("KQ",)
    assert (plan.fills, plan.cases, plan.not_served) == ((), (), ())


def test_only_the_lists_that_hold_a_security_back_are_named() -> None:
    """Malaysia's and London's lists are missing too, but nothing waits for them."""
    plan = _plan([_security(1, _HYNIX, "KR")], [], markets=_markets("KO", "US"))

    assert plan.missing_lists == ("KQ",)


def test_a_security_held_in_a_served_and_an_unserved_market_goes_to_the_rule() -> None:
    """One served market is enough to look; the rule then sees several markets."""
    security = Security(
        instrument_id=1,
        isin=_HYNIX,
        company="Sample Co",
        held=(
            HeldLine(True, "KR", "KRW", None, _HYNIX),
            HeldLine(True, "JP", "JPY", None, _HYNIX),
        ),
    )

    plan = _plan([security], [_line("KO", "000660", "KRW", _HYNIX)])

    assert _cases(plan) == [(_HYNIX, Reason.SEVERAL_HOME_MARKETS, "")]


def test_every_security_is_in_exactly_one_place() -> None:
    """One of each outcome, and nothing is counted twice or lost."""
    securities = [
        _security(1, _HYNIX, "KR", ticker="000660"),
        _security(2, _SAMSUNG, "KR"),
        _security(3, _TOYOTA, "JP", "JPY"),
        _security(4, "KR7035420009", None),
        _security(5, _MAYBANK, "MY", "MYR", "MAYBANK"),
        _security(6, "KR7051910008", "KR"),
        _security(7, "GB0003096442", "GB", "GBP"),
    ]
    lines = [
        _line("KO", "000660", "KRW", _HYNIX),
        _line("KO", "051910", "KRW", "KR7051910008"),
        _line("KLSE", "1155", "MYR", _MAYBANK),
    ]

    plan = _plan(
        securities,
        lines,
        decisions=[_decision("KR7051910008", None)],
        stored=[StoredListing(1, "XKRX", "000660", ("eodhd", "KO", "000660"))],
        markets=_markets("KO", "KQ", "US", "KLSE"),
    )

    assert plan.already_listed == 1
    assert [each.isin for each in plan.not_served] == [_TOYOTA]
    assert [each.isin for each in plan.not_held] == ["KR7035420009"]
    assert [each.isin for each in plan.waiting] == ["GB0003096442"]
    assert [each.isin for each in plan.decided_none] == ["KR7051910008"]
    assert _cases(plan) == [
        (_SAMSUNG, Reason.NOTHING_FOUND, ""),
        (_MAYBANK, Reason.TICKER_DIFFERS, ""),
    ]
    assert plan.fills == ()


# --- decisions ---


def test_a_decision_gives_a_security_the_line_it_names() -> None:
    """Maybank: the rule would not fill it, because the fund's ticker differs."""
    plan = _plan(
        [_security(1, _MAYBANK, "MY", "MYR", "MAYBANK")],
        [_line("KLSE", "1155", "MYR", _MAYBANK)],
        decisions=[_decision(_MAYBANK, ("eodhd", "KLSE", "1155"))],
    )

    assert _filled(plan) == [(_MAYBANK, "XKLS", "1155", True)]
    assert plan.cases == ()


def test_a_decision_of_none_leaves_a_security_without_a_listing() -> None:
    """Not even the line the rule would have filled."""
    hynix = _security(1, _HYNIX, "KR", ticker="000660")

    plan = _plan(
        [hynix], [_line("KO", "000660", "KRW", _HYNIX)], decisions=[_decision(_HYNIX, None)]
    )

    assert plan.decided_none == (hynix,)
    assert (plan.fills, plan.cases) == ((), ())


def test_a_decision_whose_line_is_not_stored_puts_the_security_on_the_report() -> None:
    """The line has left the provider's list: the decision is out of date."""
    line = _line("KLSE", "1155", "MYR", _MAYBANK)

    plan = _plan(
        [_security(1, _MAYBANK, "MY", "MYR", "MAYBANK")],
        [line],
        decisions=[_decision(_MAYBANK, ("eodhd", "KLSE", "MAYBANK"))],
    )

    assert _cases(plan) == [(_MAYBANK, Reason.DECISION_LINE_NOT_STORED, "eodhd KLSE MAYBANK")]
    assert [shown.line for shown in plan.cases[0].lines] == [line]
    assert plan.fills == ()


def test_a_decision_cannot_name_a_line_outside_the_home_market() -> None:
    """A stand-in line stays out for the agent too (ADR 0019)."""
    plan = _plan(
        [_security(1, _HYNIX, "KR", ticker="000660")],
        [_line("US", "HXSCL", "USD", _HYNIX)],
        decisions=[_decision(_HYNIX, ("eodhd", "US", "HXSCL"))],
    )

    assert _cases(plan) == [(_HYNIX, Reason.DECISION_LINE_NOT_ALLOWED, "eodhd US HXSCL")]
    assert plan.fills == ()


def test_a_receipt_read_as_its_ordinary_share_may_take_the_shares_line_anywhere() -> None:
    """Its holding line names the receipt's market, not the share's (ADR 0026)."""
    qfin = _security(1, _QFIN, "US", "USD", "QFIN", filed_isin="US88557W1018")

    plan = _plan(
        [qfin],
        [_line("KO", "3660", "KRW", _QFIN)],
        decisions=[_decision(_QFIN, ("eodhd", "KO", "3660"))],
    )

    assert _filled(plan) == [(_QFIN, "XKRX", "3660", True)]


def test_a_receipt_read_as_its_ordinary_share_may_not_take_another_securitys_line() -> None:
    """Outside the home market only a line with the share's own ISIN will do."""
    qfin = _security(1, _QFIN, "US", "USD", "QFIN", filed_isin="US88557W1018")

    plan = _plan(
        [qfin],
        [_line("KO", "3660", "KRW", _HYNIX)],
        decisions=[_decision(_QFIN, ("eodhd", "KO", "3660"))],
    )

    assert _cases(plan) == [(_QFIN, Reason.DECISION_LINE_NOT_ALLOWED, "eodhd KO 3660")]


def test_a_decision_for_a_line_whose_currency_cannot_be_read_is_not_applied() -> None:
    """The listing would have no currency to carry."""
    plan = _plan(
        [_security(1, _MAYBANK, "MY", "MYR")],
        [_line("KLSE", "1155", None, _MAYBANK)],
        decisions=[_decision(_MAYBANK, ("eodhd", "KLSE", "1155"))],
    )

    assert _cases(plan) == [(_MAYBANK, Reason.DECISION_CURRENCY_UNREADABLE, "eodhd KLSE 1155")]


def test_a_decision_for_a_security_that_waits_is_neither_applied_nor_out_of_date() -> None:
    """Its line is missing only because its list is."""
    hynix = _security(1, _HYNIX, "KR")

    plan = _plan(
        [hynix],
        [],
        decisions=[_decision(_HYNIX, ("eodhd", "KO", "000660"))],
        markets=_markets("KQ"),
    )

    assert plan.waiting == (hynix,)
    assert (plan.fills, plan.cases, plan.decided_none) == ((), (), ())


def test_a_decision_for_a_security_that_is_not_in_the_universe_is_named() -> None:
    """A later filing may have dropped it; the run goes on."""
    plan = _plan(
        [_security(1, _HYNIX, "KR", ticker="000660")],
        [_line("KO", "000660", "KRW", _HYNIX)],
        decisions=[_decision(_SAMSUNG, None), _decision(_TOYOTA, ("eodhd", "KO", "7203"))],
    )

    assert plan.unknown_decisions == (_SAMSUNG, _TOYOTA)
    assert _filled(plan) == [(_HYNIX, "XKRX", "000660", False)]


# --- an exchange and ticker two securities want ---


def test_the_first_security_in_isin_order_gets_the_exchange_and_ticker() -> None:
    """The second is reported, with the security that holds the pair (ADR 0019)."""
    plan = _plan(
        [_security(2, _SAMSUNG, "KR"), _security(1, _HYNIX, "KR", ticker="ABC")],
        [_line("KO", "abc", "KRW", _SAMSUNG), _line("KO", "ABC", "KRW", _HYNIX)],
    )

    assert _filled(plan) == [(_HYNIX, "XKRX", "ABC", False)]
    assert _cases(plan) == [
        (_SAMSUNG, Reason.EXCHANGE_AND_TICKER_TAKEN, f"XKRX ABC is the listing of {_HYNIX}")
    ]


def test_a_decided_line_wins_over_a_line_the_rule_would_take() -> None:
    """Although the other security comes first in ISIN order (ADR 0026)."""
    plan = _plan(
        [_security(2, _SAMSUNG, "KR", ticker="OTHER"), _security(1, _HYNIX, "KR", ticker="ABC")],
        [_line("KO", "abc", "KRW", _SAMSUNG), _line("KO", "ABC", "KRW", _HYNIX)],
        decisions=[_decision(_SAMSUNG, ("eodhd", "KO", "abc"))],
    )

    assert _filled(plan) == [(_SAMSUNG, "XKRX", "ABC", True)]
    assert _cases(plan) == [
        (_HYNIX, Reason.EXCHANGE_AND_TICKER_TAKEN, f"XKRX ABC is the listing of {_SAMSUNG}")
    ]


def test_a_listing_that_exists_keeps_its_exchange_and_ticker() -> None:
    """A second run reports the same security for the same reason."""
    plan = _plan(
        [_security(2, _SAMSUNG, "KR"), _security(1, _HYNIX, "KR", ticker="ABC")],
        [_line("KO", "abc", "KRW", _SAMSUNG), _line("KO", "ABC", "KRW", _HYNIX)],
        stored=[StoredListing(1, "XKRX", "ABC", ("eodhd", "KO", "ABC"))],
    )

    assert plan.fills == ()
    assert _cases(plan) == [
        (_SAMSUNG, Reason.EXCHANGE_AND_TICKER_TAKEN, f"XKRX ABC is the listing of {_HYNIX}")
    ]


# --- a listing that contradicts a decision ---


@pytest.mark.parametrize(
    "decision",
    [
        pytest.param(_decision(_HYNIX, None), id="the decision says none"),
        pytest.param(_decision(_HYNIX, ("eodhd", "KQ", "000660")), id="another exchange code"),
        pytest.param(_decision(_HYNIX, ("eodhd", "KO", "660")), id="another symbol"),
    ],
)
def test_a_listing_that_is_not_what_the_decision_says_stops_the_run(
    decision: ListingDecision,
) -> None:
    """The database and the file agree, or nothing is done (ADR 0026)."""
    with pytest.raises(ListingsError, match=f"1 securities have a listing.*{_HYNIX}.*rebuilt"):
        _plan(
            [_security(1, _HYNIX, "KR")],
            [_line("KO", "000660", "KRW", _HYNIX)],
            decisions=[decision],
            stored=[StoredListing(1, "XKRX", "000660", ("eodhd", "KO", "000660"))],
        )


def test_a_listing_the_provider_has_no_symbol_for_contradicts_a_decision_that_names_a_line() -> (
    None
):
    """It was not written from that line."""
    with pytest.raises(ListingsError, match="not what the decisions file says"):
        _plan(
            [_security(1, _HYNIX, "KR")],
            [],
            decisions=[_decision(_HYNIX, ("eodhd", "KO", "000660"))],
            stored=[StoredListing(1, "XKRX", "000660", None)],
        )


def test_a_listing_that_is_what_the_decision_says_is_left_alone() -> None:
    """That is every decided security on a second run."""
    plan = _plan(
        [_security(1, _HYNIX, "KR")],
        [_line("KO", "000660", "KRW", _HYNIX)],
        decisions=[_decision(_HYNIX, ("eodhd", "KO", "000660"))],
        stored=[StoredListing(1, "XKRX", "000660", ("eodhd", "KO", "000660"))],
    )

    assert (plan.already_listed, plan.fills, plan.cases) == (1, (), ())


def test_a_refusal_names_the_first_securities_and_counts_the_rest() -> None:
    """A long list would bury the instruction to rebuild."""
    isins = [f"KR70000000{number:02d}" for number in range(12)]

    with pytest.raises(ListingsError) as raised:
        _plan(
            [_security(number, isin, "KR") for number, isin in enumerate(isins, start=1)],
            [],
            decisions=[_decision(isin, None) for isin in isins],
            stored=[
                StoredListing(number, "XKRX", f"T{number}", None)
                for number in range(1, len(isins) + 1)
            ],
        )

    message = str(raised.value)
    assert message.startswith("12 securities have a listing")
    assert isins[9] in message
    assert isins[10] not in message
    assert "and 2 more" in message


# --- counting ---


def test_securities_are_counted_by_home_country_with_the_largest_first() -> None:
    """A security held in two countries is counted under both."""
    both = Security(
        instrument_id=3,
        isin=_QFIN,
        company="Sample Co",
        held=(HeldLine(True, "US", "USD", None, _QFIN), HeldLine(True, "KR", "KRW", None, _QFIN)),
    )

    assert by_country([_security(1, _HYNIX, "KR"), _security(2, _TOYOTA, "JP", "JPY"), both]) == {
        "KR": 2,
        "JP": 1,
        "US": 1,
    }
    assert list(by_country([_security(1, _HYNIX, "KR"), both])) == ["KR", "US"]


# --- the plan as a whole ---

_POOL: tuple[str, ...] = (_HYNIX, _SAMSUNG, "KR7035420009", "US0846707026", _MAYBANK)


@st.composite
def _runs(
    draw: st.DrawFn,
) -> tuple[list[Security], list[Line], list[ListingDecision], Markets]:
    """Draw a small universe, some lines, some decisions and which lists are stored."""
    addresses = draw(
        st.lists(
            st.tuples(st.sampled_from(sorted(_COUNTRY)), st.sampled_from(["A", "a", "B", "0A"])),
            unique=True,
            max_size=8,
        )
    )
    lines = [
        _line(
            code,
            symbol,
            draw(st.sampled_from(["KRW", "USD", None])),
            draw(st.sampled_from([None, *_POOL])),
        )
        for code, symbol in addresses
    ]
    isins = draw(st.lists(st.sampled_from(_POOL), unique=True, max_size=len(_POOL)))
    securities = [
        _security(
            number,
            isin,
            draw(st.sampled_from([None, "KR", "KR", "US", "MY", "JP"])),
            draw(st.sampled_from(["KRW", "USD"])),
            draw(st.sampled_from([None, "A", "a", "B"])),
        )
        for number, isin in enumerate(isins, start=1)
    ]
    decided = draw(st.lists(st.sampled_from(_POOL), unique=True, max_size=3))
    decisions = [
        _decision(
            isin,
            draw(
                st.sampled_from(
                    [
                        None,
                        *(("eodhd", code, symbol) for code, symbol in addresses or [("KO", "A")]),
                    ]
                )
            ),
        )
        for isin in decided
    ]
    stored_codes = draw(st.lists(st.sampled_from(sorted(_COUNTRY)), unique=True))
    return securities, lines, decisions, _markets(*stored_codes)


@given(_runs())
def test_no_two_listings_share_an_exchange_and_ticker(
    run: tuple[list[Security], list[Line], list[ListingDecision], Markets],
) -> None:
    """The table would refuse the second, and with it the whole run."""
    securities, lines, decisions, markets = run

    plan = plan_listings(securities, Lines(lines), markets, decisions, ())

    pairs = [(each.fill.line.stored.mic, each.fill.ticker) for each in plan.fills]
    assert len(set(pairs)) == len(pairs)
    assert len({each.fill.security.isin for each in plan.fills}) == len(plan.fills)


@given(_runs())
def test_every_security_ends_in_exactly_one_place(
    run: tuple[list[Security], list[Line], list[ListingDecision], Markets],
) -> None:
    """Filled, reported, decided as none, not held, not served or waiting."""
    securities, lines, decisions, markets = run

    plan = plan_listings(securities, Lines(lines), markets, decisions, ())

    placed = [
        *(each.fill.security.isin for each in plan.fills),
        *(case.security.isin for case in plan.cases),
        *(security.isin for security in plan.decided_none),
        *(security.isin for security in plan.not_held),
        *(security.isin for security in plan.not_served),
        *(security.isin for security in plan.waiting),
    ]
    assert sorted(placed) == sorted(security.isin for security in securities)
    assert plan.already_listed == 0


@given(_runs())
def test_a_second_run_fills_nothing_and_reports_the_same(
    run: tuple[list[Security], list[Line], list[ListingDecision], Markets],
) -> None:
    """Planning again, with the first plan's listings stored, changes nothing (ADR 0026)."""
    securities, lines, decisions, markets = run
    first = plan_listings(securities, Lines(lines), markets, decisions, ())
    stored = [
        StoredListing(
            instrument_id=each.fill.security.instrument_id,
            mic=each.fill.line.stored.mic,
            ticker=each.fill.ticker,
            line=each.fill.line.address,
        )
        for each in first.fills
    ]

    second = plan_listings(securities, Lines(lines), markets, decisions, stored)

    assert second.fills == ()
    assert second.already_listed == len(first.fills)
    assert second.cases == first.cases
    assert (second.decided_none, second.not_held, second.not_served, second.waiting) == (
        first.decided_none,
        first.not_held,
        first.not_served,
        first.waiting,
    )
