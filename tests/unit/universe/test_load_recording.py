"""Tests for what ``pyvalue.universe.load`` records: the ``fund`` and ``holding`` rows.

The rules that decide which lines become companies and instruments are tested
in ``test_load.py``. These tests pin ADR 0017: which lines get a holding row,
what the row says, which instrument it points at, and that a fund's rows are
replaced as a whole.

Author: Emre Tezel
"""

from dataclasses import replace
from datetime import date

import pytest

from pyvalue.db import ConstraintError, Database, Fund, Holding, Instrument
from pyvalue.universe import (
    Exclusion,
    FundDefinition,
    FundHoldings,
    HoldingLine,
    OrdinaryShare,
    Scope,
    Sponsor,
    UniverseError,
    load_holdings,
)

# Made-up identifiers with correct check digits.
_ALPHA_LEI: str = "549300ALPHA000000003"
_ISIN: str = "US00000A0014"
_SECOND_ISIN: str = "GB00000D0016"
_RECEIPT_ISIN: str = "US00000Z0015"
_ORDINARY_ISIN: str = "KYG0000Z0015"

_VTI: FundDefinition = FundDefinition(
    code="VTI",
    name="Sample Total US Stock Fund",
    scope=Scope.US,
    sponsor=Sponsor.VANGUARD,
    series_id="S000002848",
    registrant_cik=36405,
    filing_number="0000036405-26-000480",
    holdings_date=date(2026, 6, 30),
)
_VXUS: FundDefinition = FundDefinition(
    code="VXUS",
    name="Sample Total International Stock Fund",
    scope=Scope.NON_US,
    sponsor=Sponsor.VANGUARD,
    series_id="S000002932",
    registrant_cik=736054,
    filing_number="0000736054-26-000275",
    holdings_date=date(2026, 7, 31),
)
_FILE_DATE: date = date(2026, 10, 31)


def _line(
    issuer_name: str = "ALPHA CORP",
    isin: str | None = _ISIN,
    *,
    title: str = "ALPHA CORP COM",
    lei: str | None = None,
    cusip: str | None = None,
    category: str = "EC",
    label: str | None = None,
    issuer_type: str = "CORP",
    country: str | None = "US",
    currency: str = "USD",
    ticker: str | None = None,
    sedol: str | None = None,
) -> HoldingLine:
    """Build a common holding line; ``_fund`` numbers it."""
    return HoldingLine(
        number=0,
        issuer_name=issuer_name,
        title=title,
        lei=lei,
        isin=isin,
        cusip=cusip,
        category=category,
        category_label=label,
        issuer_type=issuer_type,
        trading_country=country,
        currency=currency,
        ticker=ticker,
        sedol=sedol,
    )


def _fund(
    definition: FundDefinition, *lines: HoldingLine, file_date: date | None = _FILE_DATE
) -> FundHoldings:
    """Build a fund's holdings from lines, numbering them from 1 as a filing does."""
    return FundHoldings(
        fund=definition,
        sponsor_file_date=file_date,
        lines=tuple(replace(line, number=number) for number, line in enumerate(lines, start=1)),
    )


def _row(
    fund: str = "VTI",
    number: int = 1,
    instrument_id: int | None = 1,
    *,
    reason: str | None = None,
    isin: str = _ISIN,
    issuer_name: str = "ALPHA CORP",
    title: str | None = "ALPHA CORP COM",
    lei: str | None = None,
    cusip: str | None = None,
    sedol: str | None = None,
    ticker: str | None = None,
    category: str = "EC",
    label: str | None = None,
    issuer_type: str = "CORP",
    country: str = "US",
    currency: str = "USD",
) -> Holding:
    """Build the row a line built by ``_line`` with the same arguments is stored as."""
    return Holding(
        fund_code=fund,
        line_number=number,
        instrument_id=instrument_id,
        not_loaded_reason=reason,
        isin=isin,
        issuer_name=issuer_name,
        title=title,
        lei=lei,
        cusip=cusip,
        sedol=sedol,
        ticker=ticker,
        asset_category=category,
        asset_category_label=label,
        issuer_type=issuer_type,
        trading_country=country,
        currency=currency,
    )


def _funds(database: Database) -> tuple[Fund, ...]:
    """Read every fund."""
    with database.unit_of_work() as work:
        return work.funds.all()


def _holdings(database: Database) -> tuple[Holding, ...]:
    """Read every holding line."""
    with database.unit_of_work() as work:
        return work.holdings.all()


def _instruments(database: Database) -> tuple[Instrument, ...]:
    """Read every instrument."""
    with database.unit_of_work() as work:
        return work.instruments.all()


def _exclusion(isin: str) -> Exclusion:
    """Build a decision that keeps the security out of the universe."""
    return Exclusion(
        isin=isin, company="Sample Co", decided_on=date(2026, 11, 21), evidence="Made up for a test"
    )


def _ordinary_share(isin: str, ordinary_isin: str) -> OrdinaryShare:
    """Build a decision that the first security is a receipt of the second."""
    return OrdinaryShare(
        isin=isin,
        ordinary_isin=ordinary_isin,
        company="Sample Co",
        decided_on=date(2026, 11, 21),
        evidence="Made up for a test",
    )


# --- The fund row ----------------------------------------------------------------------------


def test_each_fund_gets_a_row_that_says_which_documents_were_loaded(database: Database) -> None:
    """The filing number and the two dates are the record of where the lines come from."""
    load_holdings(database, [_fund(_VTI, _line()), _fund(_VXUS, _line("DELTA PLC", _SECOND_ISIN))])

    assert _funds(database) == (
        Fund(
            fund_code="VTI",
            name="Sample Total US Stock Fund",
            scope="US",
            sec_series_id="S000002848",
            sec_filing_number="0000036405-26-000480",
            holdings_date=date(2026, 6, 30),
            sponsor_file_date=_FILE_DATE,
        ),
        Fund(
            fund_code="VXUS",
            name="Sample Total International Stock Fund",
            scope="NON_US",
            sec_series_id="S000002932",
            sec_filing_number="0000736054-26-000275",
            holdings_date=date(2026, 7, 31),
            sponsor_file_date=_FILE_DATE,
        ),
    )


def test_a_fund_without_a_sponsor_file_has_no_date_for_it(database: Database) -> None:
    """A sponsor that has no file of its own is a valid state."""
    load_holdings(database, [_fund(_VTI, _line(), file_date=None)])

    (fund,) = _funds(database)
    assert fund.sponsor_file_date is None


def test_a_fund_whose_lines_are_all_left_out_still_gets_its_row(database: Database) -> None:
    """The fund was loaded; it happens to hold nothing that is recorded."""
    result = load_holdings(database, [_fund(_VTI, _line(isin=None), _line(category="DBT"))])

    assert [fund.fund_code for fund in _funds(database)] == ["VTI"]
    assert _holdings(database) == ()
    assert result.holdings_stored == 0


# --- The row of a loaded line ----------------------------------------------------------------


def test_a_loaded_line_is_recorded_with_everything_its_documents_say(database: Database) -> None:
    """Identifiers, names, category, issuer type, country, currency, ticker and SEDOL."""
    line = _line(
        lei=_ALPHA_LEI,
        cusip="00000A001",
        ticker="ALPH",
        sedol="B000A01",
        country="US",
        currency="USD",
    )

    result = load_holdings(database, [_fund(_VTI, line)])

    assert _holdings(database) == (
        _row(lei=_ALPHA_LEI, cusip="00000A001", ticker="ALPH", sedol="B000A01"),
    )
    assert (result.holdings_stored, result.holdings_with_ticker, result.holdings_with_sedol) == (
        1,
        1,
        1,
    )
    assert result.instruments_not_held == 0


def test_a_line_trading_abroad_keeps_its_country_and_currency(database: Database) -> None:
    """The listing rule reads the home market from exactly these two values."""
    line = _line("ZETA LTD", _ORDINARY_ISIN, title="ZETA LTD", country="HK", currency="HKD")

    load_holdings(database, [_fund(_VXUS, line)])

    (row,) = _holdings(database)
    assert (row.trading_country, row.currency) == ("HK", "HKD")


def test_two_funds_that_hold_one_security_point_at_one_instrument(database: Database) -> None:
    """The second fund's line adds no instrument; its row points at the first's."""
    funds = [
        _fund(_VTI, _line(ticker="ALPH")),
        _fund(_VXUS, _line("Alpha Corp", title="ALPHA")),
    ]

    load_holdings(database, funds)

    assert _instruments(database) == (Instrument(1, 1, _ISIN),)
    assert _holdings(database) == (
        _row("VTI", 1, 1, ticker="ALPH"),
        # Each row keeps its own fund's spelling; the company keeps the first.
        _row("VXUS", 1, 1, issuer_name="Alpha Corp", title="ALPHA"),
    )


def test_two_lines_of_one_fund_for_one_security_both_point_at_it(database: Database) -> None:
    """A share held on two markets is two lines and one instrument."""
    funds = [
        _fund(
            _VXUS,
            _line(country="CA", currency="CAD"),
            _line(country="US", currency="USD"),
        )
    ]

    load_holdings(database, funds)

    rows = _holdings(database)
    assert [(row.line_number, row.instrument_id, row.trading_country) for row in rows] == [
        (1, 1, "CA"),
        (2, 1, "US"),
    ]


def test_the_row_keeps_what_was_filed_not_what_was_decided(database: Database) -> None:
    """A filed name with stray spaces is stored trimmed, but still as the fund's own."""
    load_holdings(database, [_fund(_VTI, _line("  ALPHA   CORP ", title=" ALPHA "))])

    (row,) = _holdings(database)
    assert (row.issuer_name, row.title) == ("ALPHA   CORP", "ALPHA")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(_line(title=""), _row(title=None), id="no title"),
        pytest.param(_line(lei="549300ALPHA000000004"), _row(), id="identifier with a wrong check"),
        pytest.param(_line(lei="NOT AN IDENTIFIER"), _row(), id="identifier of the wrong shape"),
        pytest.param(_line(cusip="12345"), _row(), id="CUSIP too short"),
        pytest.param(_line(cusip="00000a001"), _row(), id="CUSIP in lower case"),
        pytest.param(_line(sedol="B0001"), _row(), id="SEDOL too short"),
        pytest.param(_line(ticker="  "), _row(), id="blank ticker"),
        pytest.param(_line(ticker=" NOVO B "), _row(ticker="NOVO B"), id="padded ticker"),
        pytest.param(
            _line(category="EP", label="ADR"),
            _row(category="EP"),
            id="a label outside the conditional category",
        ),
    ],
)
def test_a_value_that_is_no_value_is_recorded_as_empty(
    database: Database, line: HoldingLine, expected: Holding
) -> None:
    """A placeholder or a typing error must not sit in the table as if it were an identifier."""
    load_holdings(database, [_fund(_VTI, line)])

    assert _holdings(database) == (expected,)


def test_a_line_in_the_conditional_category_keeps_its_label(database: Database) -> None:
    """Units are loaded like any share, and the row says what the filer called them."""
    line = _line("MU PROPERTY TRUST", _SECOND_ISIN, title="MU", category="OTHER", label="UNITS")

    load_holdings(database, [_fund(_VXUS, line)])

    (row,) = _holdings(database)
    assert (row.asset_category, row.asset_category_label, row.instrument_id) == (
        "OTHER",
        "UNITS",
        1,
    )


# --- Lines that were not loaded --------------------------------------------------------------


def test_a_line_kept_out_by_a_decision_is_recorded_without_an_instrument(
    database: Database,
) -> None:
    """The table shows that the fund holds it, and why it is not in the universe."""
    funds = [_fund(_VTI, _line(), _line("BETA INC", _SECOND_ISIN, title="BETA"))]

    result = load_holdings(database, funds, exclusions=[_exclusion(_SECOND_ISIN)])

    assert _holdings(database) == (
        _row("VTI", 1, 1),
        _row(
            "VTI",
            2,
            None,
            reason="excluded_by_decision",
            isin=_SECOND_ISIN,
            issuer_name="BETA INC",
            title="BETA",
        ),
    )
    assert result.holdings_stored == 2
    assert [instrument.isin for instrument in _instruments(database)] == [_ISIN]


def test_a_receipt_whose_company_is_already_loaded_is_recorded_without_an_instrument(
    database: Database,
) -> None:
    """ADR 0006: the receipt adds nothing to the universe, but the fund does hold it."""
    funds = [
        _fund(
            _VXUS,
            _line("ZETA LTD", _RECEIPT_ISIN, title="ZETA LTD ADR", lei=_ALPHA_LEI),
            _line("ZETA LTD", _ORDINARY_ISIN, title="ZETA LTD", lei=_ALPHA_LEI, country="HK"),
        )
    ]

    load_holdings(database, funds)

    rows = _holdings(database)
    assert [(row.line_number, row.instrument_id, row.not_loaded_reason) for row in rows] == [
        (1, None, "receipt_company_already_loaded"),
        (2, 1, None),
    ]
    assert rows[0].isin == _RECEIPT_ISIN


def test_a_receipt_that_is_the_companys_only_line_is_recorded_with_its_instrument(
    database: Database,
) -> None:
    """A kept receipt is an instrument like any other, and its row points at it."""
    load_holdings(database, [_fund(_VXUS, _line("ETA LTD", _RECEIPT_ISIN, title="ETA LTD ADR"))])

    (row,) = _holdings(database)
    assert (row.instrument_id, row.not_loaded_reason, row.isin) == (1, None, _RECEIPT_ISIN)


def test_a_receipt_read_as_its_ordinary_share_keeps_its_filed_isin(database: Database) -> None:
    """ADR 0015 and ADR 0019: the row points at the share and still shows the receipt."""
    funds = [_fund(_VXUS, _line("ZETA LTD", _RECEIPT_ISIN, title="ZETA LTD ADR", ticker="ZETA"))]

    load_holdings(database, funds, ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ORDINARY_ISIN)])

    assert _instruments(database) == (Instrument(1, 1, _ORDINARY_ISIN),)
    (row,) = _holdings(database)
    assert (row.instrument_id, row.isin, row.ticker) == (1, _RECEIPT_ISIN, "ZETA")
    assert row.not_loaded_reason is None


@pytest.mark.parametrize(
    "line",
    [
        pytest.param(_line(isin=None), id="no ISIN"),
        pytest.param(_line(isin="US00000X0018"), id="an ISIN with a wrong check digit"),
        pytest.param(_line(category="DBT"), id="debt"),
        pytest.param(_line(category="DFE", country=None), id="a derivative without a country"),
    ],
)
def test_a_line_that_is_no_share_line_gets_no_row(database: Database, line: HoldingLine) -> None:
    """Such a line stays in the output file; the table holds share lines with a valid ISIN."""
    result = load_holdings(database, [_fund(_VTI, _line(), line)])

    assert [row.line_number for row in _holdings(database)] == [1]
    assert len(result.not_loaded) == 1
    assert result.holdings_stored == 1


def test_a_share_line_that_does_not_say_where_it_trades_stops_the_load(
    database: Database,
) -> None:
    """A row without a country would mislead the listing rule; nothing is written."""
    with pytest.raises(UniverseError, match="VTI line 2 .* carries a valid ISIN and no country"):
        load_holdings(
            database, [_fund(_VTI, _line(), _line("BETA INC", _SECOND_ISIN, country=None))]
        )

    assert _funds(database) == ()
    assert _instruments(database) == ()


# --- Counting --------------------------------------------------------------------------------


def test_the_result_counts_the_rows_and_what_they_carry(database: Database) -> None:
    """What the command line reports about the holding lines."""
    funds = [
        _fund(
            _VTI,
            _line(ticker="ALPH", sedol="B000A01"),
            _line("BETA INC", _SECOND_ISIN, title="BETA", sedol="B000B01"),
            _line("GAMMA INC", None, title="GAMMA"),
        ),
        _fund(_VXUS, _line("ZETA LTD", _ORDINARY_ISIN, title="ZETA", country="HK", currency="HKD")),
    ]

    result = load_holdings(database, funds)

    assert (result.holdings_stored, result.holdings_with_ticker, result.holdings_with_sedol) == (
        3,
        1,
        2,
    )
    assert result.instruments_not_held == 0


# --- Running again, and newer filings --------------------------------------------------------


def _mixed() -> list[FundHoldings]:
    """Two funds with a loaded line each, an excluded line and a line with no ISIN."""
    return [
        _fund(
            _VTI,
            _line(lei=_ALPHA_LEI, ticker="ALPH", sedol="B000A01"),
            _line("BETA INC", _SECOND_ISIN, title="BETA"),
            _line("GAMMA INC", None, title="GAMMA"),
        ),
        _fund(_VXUS, _line("ZETA LTD", _ORDINARY_ISIN, title="ZETA", country="HK", currency="HKD")),
    ]


def test_a_second_run_leaves_both_tables_exactly_as_they_were(database: Database) -> None:
    """ADR 0009 and ADR 0017: the same documents give the same rows, however often."""
    exclusions = [_exclusion(_SECOND_ISIN)]
    first = load_holdings(database, _mixed(), exclusions=exclusions)
    before = (_funds(database), _holdings(database), _instruments(database))

    second = load_holdings(database, _mixed(), exclusions=exclusions)

    assert (_funds(database), _holdings(database), _instruments(database)) == before
    assert (second.companies_added, second.instruments_added) == (0, 0)
    assert second.holdings_stored == first.holdings_stored == 3


def test_a_newer_filing_replaces_the_funds_lines_and_keeps_the_instruments(
    database: Database,
) -> None:
    """A line the newer filing no longer has does not linger; its instrument does."""
    load_holdings(
        database,
        [_fund(_VTI, _line(ticker="ALPH"), _line("BETA INC", _SECOND_ISIN, title="BETA"))],
    )
    newer = replace(_VTI, filing_number="0000036405-26-000611", holdings_date=date(2026, 9, 30))

    result = load_holdings(
        database, [_fund(newer, _line(ticker="ALPHA"), file_date=date(2026, 11, 30))]
    )

    (fund,) = _funds(database)
    assert (fund.sec_filing_number, fund.holdings_date, fund.sponsor_file_date) == (
        "0000036405-26-000611",
        date(2026, 9, 30),
        date(2026, 11, 30),
    )
    assert _holdings(database) == (_row(ticker="ALPHA"),)
    # ADR 0006: nothing is ever deleted from the universe itself.
    assert [instrument.isin for instrument in _instruments(database)] == [_ISIN, _SECOND_ISIN]
    assert result.instruments_not_held == 1


def test_loading_one_fund_leaves_the_lines_of_another_alone(database: Database) -> None:
    """Only the funds of the run are replaced."""
    load_holdings(database, _mixed())

    load_holdings(database, [_fund(_VTI, _line(lei=_ALPHA_LEI))])

    assert [(row.fund_code, row.line_number) for row in _holdings(database)] == [
        ("VTI", 1),
        ("VXUS", 1),
    ]
    assert [fund.fund_code for fund in _funds(database)] == ["VTI", "VXUS"]


def test_an_instrument_no_line_points_at_is_counted(database: Database) -> None:
    """A security added by hand, or one only a dropped fund held, is in no fund's holdings."""
    with database.unit_of_work() as work:
        company = work.companies.add("Hand Added Co", None)
        work.instruments.add(company.company_id, _SECOND_ISIN)

    result = load_holdings(database, [_fund(_VTI, _line())])

    assert (result.instruments, result.instruments_not_held) == (2, 1)


def test_a_row_the_database_refuses_undoes_the_whole_load(database: Database) -> None:
    """One unit of work: no company, instrument, fund or line of a failed load is kept."""
    funds = [_fund(_VTI, _line(), _line("BETA INC", _SECOND_ISIN, currency="dollars"))]

    with pytest.raises(ConstraintError, match="the holding table refused a row"):
        load_holdings(database, funds)

    assert _funds(database) == ()
    assert _holdings(database) == ()
    assert _instruments(database) == ()
