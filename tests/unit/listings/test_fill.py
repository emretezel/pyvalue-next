"""Tests for ``pyvalue.listings.fill``: the listing fill on a database (ADR 0019, ADR 0026).

The rule and the plan are tested without a database, in ``test_rule.py`` and
``test_plan.py``. These tests are about what the fill reads from the tables
and what it writes to them and to the report. No test reaches the network:
the fill only reads the database.

Author: Emre Tezel
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from pyvalue.db import (
    Database,
    Exchange,
    Fund,
    Holding,
    Listing,
    Provider,
    ProviderExchange,
    ProviderListing,
    ProviderSymbol,
)
from pyvalue.listings import ListingsError
from pyvalue.listings.decisions import ListingDecision
from pyvalue.listings.fill import ListingsFill, fill_listings
from pyvalue.listings.rule import Reason

# Our exchanges in the samples, with EODHD's code for each. Korea has two.
_EXCHANGES: tuple[tuple[str, str, str], ...] = (
    ("XKRX", "KR", "KO"),
    ("XKOS", "KR", "KQ"),
    ("XNYS", "US", "US"),
    ("XLON", "GB", "LSE"),
    ("XKLS", "MY", "KLSE"),
)

_HYNIX: str = "KR7000660001"
_BERKSHIRE: str = "US0846707026"
_SHELL: str = "GB00BP6MXD84"
_MAYBANK: str = "MYL1155OO000"
_TOYOTA: str = "JP3633400001"
_DAQO: str = "US23703Q2030"
_QFIN: str = "KYG8851G1001"

# One holding line: fund, country, currency, ticker, and the ISIN it was
# filed under when that is not the security's own.
type _Held = tuple[str, str, str, str | None, str | None]


def _held(
    fund: str, country: str, currency: str, ticker: str | None = None, filed: str | None = None
) -> _Held:
    """Return one holding line of a sample security."""
    return (fund, country, currency, ticker, filed)


@pytest.fixture
def market(database: Database) -> Database:
    """Return a database with the sample exchanges, EODHD's codes and the two funds."""
    with database.unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, country, code in _EXCHANGES:
            work.exchanges.save(Exchange(mic=mic, name=f"Exchange {mic}", country=country))
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )
        for number, (code, scope) in enumerate((("VTI", "US"), ("VXUS", "NON_US")), start=1):
            work.funds.save(
                Fund(
                    fund_code=code,
                    name=f"Fund {code}",
                    scope=scope,
                    sec_series_id=f"S00000000{number}",
                    sec_filing_number=f"0000000000-26-00000{number}",
                    holdings_date=date(2026, 6, 30),
                    sponsor_file_date=None,
                )
            )
    return database


def _hold(database: Database, securities: dict[str, Sequence[_Held]]) -> dict[str, int]:
    """Add securities with their holding lines, and return each security's id by ISIN."""
    ids: dict[str, int] = {}
    with database.unit_of_work() as work:
        line_number = len(work.holdings.all())
        for isin, held in securities.items():
            company = work.companies.add(f"Company {isin}", None)
            ids[isin] = work.instruments.add(company.company_id, isin).instrument_id
            for fund, country, currency, ticker, filed in held:
                line_number += 1
                work.holdings.add(
                    Holding(
                        fund_code=fund,
                        line_number=line_number,
                        instrument_id=ids[isin],
                        isin=isin if filed is None else filed,
                        issuer_name=f"Company {isin}",
                        title=None,
                        lei=None,
                        cusip=None,
                        sedol=None,
                        ticker=ticker,
                        asset_category="EC",
                        trading_country=country,
                        currency=currency,
                    )
                )
    return ids


def _list(database: Database, *lines: tuple[str, str, str, str | None]) -> None:
    """Store provider lines: exchange code, symbol, the provider's currency code, ISIN."""
    mic_of = {code: mic for mic, _, code in _EXCHANGES}
    with database.unit_of_work() as work:
        for code, symbol, currency, isin in lines:
            work.provider_symbols.add(
                ProviderSymbol(
                    provider_code="eodhd",
                    provider_exchange_code=code,
                    provider_symbol=symbol,
                    mic=mic_of[code],
                    provider_name=f"Line {symbol}",
                    provider_currency=currency,
                    isin=isin,
                )
            )


def _every_list_stored(database: Database) -> None:
    """Give each code a line of some other security, so that no security waits for a list."""
    _list(
        database,
        *((code, "ZZZZ", "USD", None) for _, _, code in _EXCHANGES),
    )


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


def _fill(
    database: Database, tmp_path: Path, decisions: Sequence[ListingDecision] = ()
) -> ListingsFill:
    """Run the fill with the given decisions, writing the report into the temporary folder."""
    return fill_listings(database, decisions, tmp_path / "listings")


def _listings(database: Database) -> list[tuple[int, str, str, str]]:
    """Return the stored listings: security, exchange, ticker, currency."""
    with database.unit_of_work() as work:
        return [
            (each.instrument_id, each.mic, each.ticker, each.currency)
            for each in work.listings.all()
        ]


def _symbols(database: Database) -> list[str]:
    """Return EODHD's symbols for the stored listings, in the order of the listings."""
    with database.unit_of_work() as work:
        return [each.provider_symbol for each in work.provider_listings.of_provider("eodhd")]


def test_a_listing_and_the_providers_symbol_for_it_are_written(
    market: Database, tmp_path: Path
) -> None:
    """Berkshire: the fund's ticker in the listing, the provider's symbol beside it."""
    ids = _hold(market, {_BERKSHIRE: [_held("VTI", "US", "USD", "BRK B")]})
    _every_list_stored(market)
    _list(market, ("US", "BRK-B", "USD", _BERKSHIRE))

    outcome = _fill(market, tmp_path)

    assert _listings(market) == [(ids[_BERKSHIRE], "XNYS", "BRK B", "USD")]
    assert _symbols(market) == ["BRK-B"]
    assert outcome.securities == 1
    assert [each.decided for each in outcome.plan.fills] == [False]


def test_the_listing_and_the_symbol_row_belong_together(market: Database, tmp_path: Path) -> None:
    """Two securities filled in one run: each symbol hangs on its own listing."""
    ids = _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _BERKSHIRE: [_held("VTI", "US", "USD", "BRK B")],
        },
    )
    _every_list_stored(market)
    _list(market, ("US", "BRK-B", "USD", _BERKSHIRE), ("KO", "000660", "KRW", _HYNIX))

    _fill(market, tmp_path)

    with market.unit_of_work() as work:
        listings: dict[int, Listing] = {each.listing_id: each for each in work.listings.all()}
        symbols: tuple[ProviderListing, ...] = work.provider_listings.of_provider("eodhd")
    assert {
        (listings[each.listing_id].instrument_id, each.provider_symbol) for each in symbols
    } == {(ids[_HYNIX], "000660"), (ids[_BERKSHIRE], "BRK-B")}


def test_a_line_quoted_in_a_sub_unit_gives_a_listing_in_the_currency(
    market: Database, tmp_path: Path
) -> None:
    """Shell trades in pence at the provider and in pounds in the listing (ADR 0019)."""
    ids = _hold(market, {_SHELL: [_held("VXUS", "GB", "GBP", "SHEL")]})
    _every_list_stored(market)
    _list(market, ("LSE", "SHEL", "GBX", _SHELL))

    _fill(market, tmp_path)

    assert _listings(market) == [(ids[_SHELL], "XLON", "SHEL", "GBP")]


def test_the_scope_of_the_fund_decides_whether_a_us_coded_isin_is_a_receipt(
    market: Database, tmp_path: Path
) -> None:
    """Berkshire in the US fund is filled; Daqo's receipt in the non-US fund is not."""
    ids = _hold(
        market,
        {
            _BERKSHIRE: [_held("VTI", "US", "USD", "BRK B")],
            _DAQO: [_held("VXUS", "US", "USD", "DQ")],
        },
    )
    _every_list_stored(market)
    _list(market, ("US", "BRK-B", "USD", _BERKSHIRE), ("US", "DQ", "USD", _DAQO))

    outcome = _fill(market, tmp_path)

    assert [each[0] for each in _listings(market)] == [ids[_BERKSHIRE]]
    assert [(case.security.isin, case.reason) for case in outcome.plan.cases] == [
        (_DAQO, Reason.US_ISIN_IN_NON_US_FUND)
    ]


def test_a_holding_line_filed_under_another_isin_makes_a_receipt_case(
    market: Database, tmp_path: Path
) -> None:
    """Qfin is held through its receipt and read as its ordinary share (ADR 0015)."""
    _hold(market, {_QFIN: [_held("VXUS", "US", "USD", "QFIN", "US88557W1018")]})
    _every_list_stored(market)
    _list(market, ("US", "QFIN", "USD", _QFIN))

    outcome = _fill(market, tmp_path)

    assert _listings(market) == []
    assert [case.reason for case in outcome.plan.cases] == [Reason.RECEIPT_READ_AS_ORDINARY_SHARE]


def test_each_security_gets_its_outcome(market: Database, tmp_path: Path) -> None:
    """Not held, not served, waiting, filled and reported, in one run."""
    _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _TOYOTA: [_held("VXUS", "JP", "JPY", "7203")],
            _SHELL: [_held("VXUS", "GB", "GBP", "SHEL")],
            _MAYBANK: [_held("VXUS", "MY", "MYR", "MAYBANK")],
            _BERKSHIRE: [],
        },
    )
    # London's list is not stored; the others are.
    _list(
        market,
        ("KO", "000660", "KRW", _HYNIX),
        ("KQ", "ZZZZ", "KRW", None),
        ("KLSE", "1155", "MYR", _MAYBANK),
        ("US", "BRK-B", "USD", _BERKSHIRE),
    )

    plan = _fill(market, tmp_path).plan

    assert [each.fill.security.isin for each in plan.fills] == [_HYNIX]
    assert [each.isin for each in plan.not_served] == [_TOYOTA]
    assert [each.isin for each in plan.waiting] == [_SHELL]
    assert plan.missing_lists == ("LSE",)
    assert [each.isin for each in plan.not_held] == [_BERKSHIRE]
    assert [(case.security.isin, case.reason) for case in plan.cases] == [
        (_MAYBANK, Reason.TICKER_DIFFERS)
    ]


def test_before_any_list_is_stored_every_served_security_waits(
    market: Database, tmp_path: Path
) -> None:
    """The state before the first download: nothing is filled and nothing is reported."""
    _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _TOYOTA: [_held("VXUS", "JP", "JPY", "7203")],
        },
    )

    outcome = _fill(market, tmp_path)

    assert [each.isin for each in outcome.plan.waiting] == [_HYNIX]
    assert outcome.plan.missing_lists == ("KO", "KQ")
    assert [each.isin for each in outcome.plan.not_served] == [_TOYOTA]
    assert _listings(market) == []
    assert outcome.report.read_text(encoding="utf-8").count("\n") == 1


def test_a_decision_is_applied_and_a_none_decision_leaves_no_listing(
    market: Database, tmp_path: Path
) -> None:
    """Maybank gets the line the agent chose; SK Hynix, which the rule would fill, gets none."""
    ids = _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _MAYBANK: [_held("VXUS", "MY", "MYR", "MAYBANK")],
        },
    )
    _every_list_stored(market)
    _list(market, ("KO", "000660", "KRW", _HYNIX), ("KLSE", "1155", "MYR", _MAYBANK))

    outcome = _fill(
        market,
        tmp_path,
        [_decision(_MAYBANK, ("eodhd", "KLSE", "1155")), _decision(_HYNIX, None)],
    )

    assert _listings(market) == [(ids[_MAYBANK], "XKLS", "1155", "MYR")]
    assert _symbols(market) == ["1155"]
    assert [each.decided for each in outcome.plan.fills] == [True]
    assert [each.isin for each in outcome.plan.decided_none] == [_HYNIX]
    assert outcome.plan.cases == ()


def test_a_symbol_in_small_letters_is_stored_as_given_under_an_upper_case_ticker(
    market: Database, tmp_path: Path
) -> None:
    """The listing table takes upper case only; the provider's symbol is kept exactly."""
    ids = _hold(market, {_HYNIX: [_held("VXUS", "KR", "KRW")]})
    _every_list_stored(market)
    _list(market, ("KO", "hynix", "KRW", _HYNIX))

    _fill(market, tmp_path)

    assert _listings(market) == [(ids[_HYNIX], "XKRX", "HYNIX", "KRW")]
    assert _symbols(market) == ["hynix"]


def test_a_second_run_changes_nothing_and_writes_the_same_report(
    market: Database, tmp_path: Path
) -> None:
    """A security that has a listing is skipped; the report depends on the data only."""
    _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _MAYBANK: [_held("VXUS", "MY", "MYR", "MAYBANK")],
            _SHELL: [_held("VXUS", "GB", "GBP", "SHEL")],
        },
    )
    _every_list_stored(market)
    _list(
        market,
        ("KO", "000660", "KRW", _HYNIX),
        ("KLSE", "1155", "MYR", _MAYBANK),
        ("LSE", "SHEL", "GBX", None),
    )
    decisions = [_decision(_SHELL, ("eodhd", "LSE", "SHEL"))]

    first = _fill(market, tmp_path, decisions)
    listings, report = _listings(market), first.report.read_bytes()
    second = _fill(market, tmp_path, decisions)

    assert len(first.plan.fills) == 2
    assert (second.plan.fills, second.plan.already_listed) == ((), 2)
    assert _listings(market) == listings
    assert second.report.read_bytes() == report
    assert second.plan.cases == first.plan.cases


def test_the_report_names_the_security_the_reason_and_the_lines(
    market: Database, tmp_path: Path
) -> None:
    """One row per line the security could be, as a decision would name it."""
    _hold(market, {_MAYBANK: [_held("VXUS", "MY", "MYR", "MAYBANK")]})
    _list(market, ("KLSE", "1155", "MYR", _MAYBANK), ("KLSE", "MAYBANK", "MYR", None))
    _list(market, *((code, "ZZZZ", "USD", None) for code in ("KO", "KQ", "US", "LSE")))

    outcome = _fill(market, tmp_path)

    assert outcome.report == tmp_path / "listings" / "cases_for_agent.csv"
    assert outcome.report.read_text(encoding="utf-8").splitlines()[1:] == [
        f"{_MAYBANK},Company {_MAYBANK},ticker_differs,,MY,MAYBANK,MYR,isin,eodhd,KLSE,1155,"
        f"XKLS,Line 1155,MYR,{_MAYBANK}",
        f"{_MAYBANK},Company {_MAYBANK},ticker_differs,,MY,MAYBANK,MYR,ticker,eodhd,KLSE,MAYBANK,"
        "XKLS,Line MAYBANK,MYR,",
    ]


def test_a_listing_that_contradicts_a_decision_stops_the_run_and_writes_nothing(
    market: Database, tmp_path: Path
) -> None:
    """The first run filled SK Hynix; then a decision says it has no listing."""
    _hold(
        market,
        {
            _HYNIX: [_held("VXUS", "KR", "KRW", "000660")],
            _BERKSHIRE: [_held("VTI", "US", "USD", "BRK B")],
        },
    )
    _every_list_stored(market)
    _list(market, ("KO", "000660", "KRW", _HYNIX))
    first = _fill(market, tmp_path)
    listings, report = _listings(market), first.report.read_bytes()
    # A line the second run could fill, were it not stopped first.
    _list(market, ("US", "BRK-B", "USD", _BERKSHIRE))

    with pytest.raises(ListingsError, match=f"{_HYNIX}.*has to be rebuilt"):
        _fill(market, tmp_path, [_decision(_HYNIX, None)])

    assert _listings(market) == listings
    assert first.report.read_bytes() == report


def test_lines_whose_currency_cannot_be_read_are_counted_by_code(
    market: Database, tmp_path: Path
) -> None:
    """They can never become a listing, so the run says how many there are (ADR 0026)."""
    _hold(market, {_HYNIX: [_held("VXUS", "KR", "KRW", "000660")]})
    _every_list_stored(market)
    _list(
        market,
        ("KO", "000660", "Unknown", _HYNIX),
        ("KO", "000661", "Unknown", None),
        ("KQ", "000662", "GBp", None),
    )

    outcome = _fill(market, tmp_path)

    assert dict(outcome.unreadable_currencies) == {"GBp": 1, "Unknown": 2}
    assert [case.reason for case in outcome.plan.cases] == [Reason.OTHER_CURRENCY]
    assert _listings(market) == []


def test_without_decisions_given_the_shipped_file_is_used(
    market: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller that gives no decisions gets the ones shipped with pyvalue.

    The shipped file holds decisions on real securities, so the test puts its
    own in its place: one that the rule would never arrive at.
    """
    _hold(market, {_HYNIX: [_held("VXUS", "KR", "KRW", "000660")]})
    _every_list_stored(market)
    _list(market, ("KO", "000660", "KRW", _HYNIX))
    shipped = (_decision(_HYNIX, None),)
    monkeypatch.setattr("pyvalue.listings.fill.packaged_listing_decisions", lambda: shipped)

    outcome = fill_listings(market, report_dir=tmp_path)

    assert [security.isin for security in outcome.plan.decided_none] == [_HYNIX]
    assert _listings(market) == []
