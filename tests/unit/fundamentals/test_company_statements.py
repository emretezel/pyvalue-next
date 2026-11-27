"""Tests for ``pyvalue.fundamentals.statements``: one company's rows and findings.

The payloads are built directly in the common shape of
``pyvalue.providers.statements``; reading EODHD's JSON is tested on its own.

Author: Emre Tezel
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.fundamentals.checks import Check, Finding
from pyvalue.fundamentals.statements import (
    BalanceSheetRow,
    CompanyStatements,
    FlowRow,
    Payload,
    Period,
    company_statements,
    whole,
)
from pyvalue.providers.statements import Figure, ReportedRow, ReportedStatements, Statement

_ISIN: str = "US0000000001"
_INCOME, _CASH, _BALANCE = Statement.INCOME, Statement.CASH_FLOW, Statement.BALANCE_SHEET


def _row(
    statement: Statement,
    day: str,
    currency: str | None = "USD",
    liabilities_and_equity: int | None = None,
    **figures: int | str,
) -> ReportedRow:
    """Return one reported row; a figure is named by its column."""
    return ReportedRow(
        statement=statement,
        period_end=date.fromisoformat(day),
        currency=currency,
        figures={Figure(name): Decimal(value) for name, value in figures.items()},
        liabilities_and_equity=(
            None if liabilities_and_equity is None else Decimal(liabilities_and_equity)
        ),
    )


def _year(day: str, currency: str | None = "USD", **figures: int | str) -> list[ReportedRow]:
    """Return a year with all three statements, each with one plain figure."""
    return [
        _row(_INCOME, day, currency, revenue=figures.pop("revenue", 1_000_000_000)),
        _row(_CASH, day, currency, operating_cash_flow=200_000_000),
        _row(_BALANCE, day, currency, total_assets=figures.pop("total_assets", 5_000_000_000)),
    ]


def _payload(
    *rows: ReportedRow,
    isin: str = _ISIN,
    preferred: bool = False,
    named: str | None = None,
    headers: Mapping[Statement, str | None] | None = None,
) -> Payload:
    """Return a payload of the given rows."""
    return Payload(
        isin=isin,
        preferred=preferred,
        reported=ReportedStatements(
            isin=named,
            statement_currency=headers or dict.fromkeys(Statement),
            rows=tuple(
                sorted(rows, key=lambda row: (list(Statement).index(row.statement), row.period_end))
            ),
        ),
    )


def _one(
    *rows: ReportedRow,
    named: str | None = None,
    headers: Mapping[Statement, str | None] | None = None,
) -> CompanyStatements:
    """Return what is stored for a company with one payload of the given rows."""
    return company_statements([_payload(*rows, named=named, headers=headers)])


def _checks(result: CompanyStatements) -> list[tuple[Check, Statement | None, str | None]]:
    """Return each finding as its check, statement and date."""
    return [
        (
            each.check,
            each.statement,
            None if each.period_end is None else each.period_end.isoformat(),
        )
        for each in result.findings
    ]


def _stored(result: CompanyStatements) -> list[tuple[Statement, str, int | None]]:
    """Return each stored row as its statement, date and length."""
    return [
        (
            row.statement,
            row.period_end.isoformat(),
            row.months if isinstance(row, FlowRow) else None,
        )
        for row in result.rows
    ]


def test_every_year_is_stored_and_the_oldest_years_flows_are_left_out() -> None:
    """Nothing before the oldest year proves that its income and cash-flow rows cover a year."""
    result = _one(*_year("2023-12-31"), *_year("2024-12-31"), *_year("2025-12-31"))

    assert result.isin == _ISIN
    assert result.periods == tuple(Period(date(year, 12, 31), "USD") for year in (2023, 2024, 2025))
    assert _stored(result) == [
        (_BALANCE, "2023-12-31", None),
        (_INCOME, "2024-12-31", 12),
        (_CASH, "2024-12-31", 12),
        (_BALANCE, "2024-12-31", None),
        (_INCOME, "2025-12-31", 12),
        (_CASH, "2025-12-31", 12),
        (_BALANCE, "2025-12-31", None),
    ]
    assert _checks(result) == [
        (Check.LENGTH_NOT_PROVEN, _INCOME, "2023-12-31"),
        (Check.LENGTH_NOT_PROVEN, _CASH, "2023-12-31"),
    ]
    assert result.latest == date(2025, 12, 31)


def test_amounts_are_rounded_half_to_even() -> None:
    """The provider's two decimals become whole units."""
    result = _one(
        _row(
            _BALANCE,
            "2025-12-31",
            cash="2.50",
            total_assets="3.50",
            equity="-2.50",
            long_term_debt="7.49",
        )
    )

    assert dict(result.rows[0].figures) == {
        Figure.CASH: 2,
        Figure.TOTAL_ASSETS: 4,
        Figure.EQUITY: -2,
        Figure.LONG_TERM_DEBT: 7,
    }


@given(st.decimals(min_value=-(10**16), max_value=10**16, places=2, allow_nan=False))
def test_rounding_is_never_more_than_half_a_unit_away(amount: Decimal) -> None:
    """Whole units lose at most fifty cents."""
    assert abs(Decimal(whole(amount)) - amount) <= Decimal("0.5")


def test_a_date_off_the_chain_is_left_out_and_reported() -> None:
    """The other series after a change of year end is not stored."""
    result = _one(*_year("2024-12-31"), *_year("2025-06-30"), *_year("2025-12-31"))

    assert [period.period_end.isoformat() for period in result.periods] == [
        "2024-12-31",
        "2025-12-31",
    ]
    assert (Check.OFF_CHAIN, None, "2025-06-30") in _checks(result)


def test_a_year_whose_statements_carry_two_currencies_is_left_out_whole() -> None:
    """Which currency the year is in cannot be told, so none of its rows is stored."""
    rows = [
        *_year("2024-12-31"),
        _row(_INCOME, "2025-12-31", "AUD", revenue=5),
        _row(_BALANCE, "2025-12-31", "USD", total_assets=5),
    ]

    result = _one(*rows)

    assert [period.period_end.year for period in result.periods] == [2024]
    assert (
        Finding(
            isin=_ISIN,
            check=Check.CURRENCIES_DIFFER,
            period_end=date(2025, 12, 31),
            detail="the statements are labelled AUD and USD",
        )
        in result.findings
    )


def test_a_year_without_a_label_takes_the_one_currency_of_the_other_years() -> None:
    """8% of rows carry no label; their company's other years settle it."""
    result = _one(*_year("2024-12-31", "SEK"), *_year("2025-12-31", None))

    assert [period.currency for period in result.periods] == ["SEK", "SEK"]
    assert Check.NO_CURRENCY not in {each.check for each in result.findings}


def test_without_any_label_the_statements_own_header_settles_the_currency() -> None:
    """The header is the last resort, used only when no row carries a label."""
    headers = {_INCOME: "EUR", _CASH: None, _BALANCE: "EUR"}

    result = _one(*_year("2024-12-31", None), *_year("2025-12-31", None), headers=headers)

    assert [period.currency for period in result.periods] == ["EUR", "EUR"]


@pytest.mark.parametrize(
    ("rows", "headers"),
    [
        # Other years in two currencies: the silent year could be in either.
        (
            [*_year("2023-12-31", "AUD"), *_year("2024-12-31", "USD"), *_year("2025-12-31", None)],
            {_INCOME: "USD"},
        ),
        # No label anywhere, and two headers.
        ([*_year("2025-12-31", None)], {_INCOME: "USD", _BALANCE: "AUD"}),
        # No label anywhere, and no header.
        ([*_year("2025-12-31", None)], {}),
    ],
)
def test_a_year_whose_currency_cannot_be_settled_is_left_out(
    rows: list[ReportedRow], headers: dict[Statement, str]
) -> None:
    """Rather no year than a year in a guessed currency."""
    result = _one(*rows, headers={**dict.fromkeys(Statement), **headers})

    assert date(2025, 12, 31) not in {period.period_end for period in result.periods}
    assert (Check.NO_CURRENCY, None, "2025-12-31") in _checks(result)


def test_a_label_that_is_not_a_currency_leaves_the_year_out() -> None:
    """A provider's ``Unknown`` is not a currency."""
    result = _one(*_year("2025-12-31", "Unknown"))

    assert result.periods == ()
    assert _checks(result) == [(Check.NO_CURRENCY, None, "2025-12-31")]


def test_a_sub_unit_label_is_read_as_its_currency_with_the_amounts_unchanged() -> None:
    """Measured: rows labelled GBX hold pounds. Each such row is reported."""
    result = _one(_row(_BALANCE, "2025-12-31", "GBX", total_assets=67_241_000))

    assert result.periods == (Period(date(2025, 12, 31), "GBP"),)
    assert dict(result.rows[0].figures) == {Figure.TOTAL_ASSETS: 67_241_000}
    assert _checks(result) == [(Check.SUB_UNIT_LABEL, _BALANCE, "2025-12-31")]


def test_a_change_of_reporting_currency_is_reported_on_the_later_year() -> None:
    """Both years are stored, each in its own currency."""
    result = _one(
        _row(_BALANCE, "2024-06-30", "AUD", total_assets=9),
        _row(_BALANCE, "2025-06-30", "USD", total_assets=9),
    )

    assert [period.currency for period in result.periods] == ["AUD", "USD"]
    assert _checks(result) == [(Check.CURRENCY_CHANGED, None, "2025-06-30")]


def test_total_assets_off_in_scale_from_both_neighbours_leave_the_balance_sheet_out() -> None:
    """KBC Ancora: thousands between two years in units. The income row of that year stays."""
    rows = [
        *_year("2023-06-30", total_assets=3_098_302_000),
        *_year("2024-06-30", total_assets=3_089_448),
        *_year("2025-06-30", total_assets=3_150_309_364),
    ]

    result = _one(*rows)

    assert (_BALANCE, "2024-06-30", None) not in _stored(result)
    assert (_INCOME, "2024-06-30", 12) in _stored(result)
    assert (Check.SCALE_OUTLIER, _BALANCE, "2024-06-30") in _checks(result)


def test_the_year_after_an_outlier_gets_no_step_warning_against_it() -> None:
    """The step back from a bad year is not news: the outlier is no neighbour."""
    rows = [
        *_year("2022-06-30", total_assets=3_100_000_000),
        *_year("2023-06-30", total_assets=3_098_302_000),
        *_year("2024-06-30", total_assets=3_089_448),
        *_year("2025-06-30", total_assets=3_150_309_364),
    ]

    result = _one(*rows)

    assert [
        (check, day) for check, _, day in _checks(result) if check.value.startswith("scale")
    ] == [(Check.SCALE_OUTLIER, "2024-06-30")]


def test_revenue_off_in_scale_leaves_the_income_statement_out() -> None:
    """The cash-flow statement and the balance sheet of the year are stored."""
    rows = [*_year("2023-06-30"), *_year("2024-06-30", revenue=1_450), *_year("2025-06-30")]

    result = _one(*rows)

    assert (_INCOME, "2024-06-30", 12) not in _stored(result)
    assert (_CASH, "2024-06-30", 12) in _stored(result)
    assert (Check.SCALE_OUTLIER, _INCOME, "2024-06-30") in _checks(result)


def test_years_in_another_currency_are_not_neighbours_for_the_scale_check() -> None:
    """A redenomination is not a change of unit."""
    rows = [
        *_year("2023-12-31", "IDR", total_assets=9_000_000_000_000),
        *_year("2024-12-31", "USD", total_assets=600_000_000),
        *_year("2025-12-31", "IDR", total_assets=9_500_000_000_000),
    ]

    result = _one(*rows)

    assert (_BALANCE, "2024-12-31", None) in _stored(result)
    assert Check.SCALE_OUTLIER not in {each.check for each in result.findings}


def test_a_fifty_fold_step_that_stays_is_a_warning() -> None:
    """A reverse takeover changes the scale for good; the rows are stored."""
    rows = [
        *_year("2023-12-31", total_assets=2_000_000),
        *_year("2024-12-31", total_assets=900_000_000),
        *_year("2025-12-31", total_assets=950_000_000),
    ]

    result = _one(*rows)

    assert (_BALANCE, "2024-12-31", None) in _stored(result)
    assert (Check.SCALE_STEP, _BALANCE, "2024-12-31") in _checks(result)


def test_figures_that_cannot_be_true_are_emptied_and_the_rest_of_the_row_kept() -> None:
    """One bad figure does not cost the year's row."""
    rows = [
        _row(_CASH, "2024-12-31", operating_cash_flow=1),
        _row(
            _CASH,
            "2025-12-31",
            operating_cash_flow=500,
            depreciation_amortization=-60,
            dividends_paid=10**18,
        ),
    ]

    result = _one(*rows)

    assert dict(result.rows[-1].figures) == {Figure.OPERATING_CASH_FLOW: 500}
    assert [(each.check, each.figure, each.detail) for each in result.findings[-2:]] == [
        (Check.IMPOSSIBLE_NEGATIVE, Figure.DEPRECIATION_AMORTIZATION, "-60"),
        (Check.ABSURD_VALUE, Figure.DIVIDENDS_PAID, str(10**18)),
    ]


def test_a_placeholder_capex_is_emptied() -> None:
    """A zero in a cash-flow row that has no operating cash flow."""
    rows = [
        _row(_CASH, "2024-12-31", operating_cash_flow=1),
        _row(_CASH, "2025-12-31", capital_expenditure=0, dividends_paid=7),
    ]

    result = _one(*rows)

    assert dict(result.rows[-1].figures) == {Figure.DIVIDENDS_PAID: 7}
    assert result.findings[-1].check is Check.PLACEHOLDER_CAPEX


def test_zero_interest_beside_debt_on_the_balance_sheet_of_the_same_date_is_emptied() -> None:
    """A metric would read it as unlimited interest cover."""
    rows = [
        _row(_INCOME, "2024-12-31", revenue=1),
        _row(_INCOME, "2025-12-31", revenue=900, interest_expense=0),
        _row(_BALANCE, "2025-12-31", total_assets=5_000, long_term_debt=400),
    ]

    result = _one(*rows)

    income = next(
        row for row in result.rows if row.statement is _INCOME and row.period_end.year == 2025
    )
    assert dict(income.figures) == {Figure.REVENUE: 900}
    assert (Check.ZERO_INTEREST_WITH_DEBT, _INCOME, "2025-12-31") in _checks(result)


def test_zero_interest_without_debt_is_kept() -> None:
    """A company without borrowings pays no interest."""
    rows = [
        _row(_INCOME, "2024-12-31", revenue=1),
        _row(_INCOME, "2025-12-31", revenue=900, interest_expense=0),
    ]

    result = _one(*rows)

    assert result.rows[-1].figures[Figure.INTEREST_EXPENSE] == 0


def test_a_row_without_any_figure_is_left_out() -> None:
    """Whether reported empty or emptied by the checks."""
    rows = [
        _row(_BALANCE, "2024-12-31"),
        _row(_BALANCE, "2025-12-31", cash=-1),
    ]

    result = _one(*rows)

    assert result.rows == () and result.periods == ()
    assert [
        (each.check, each.detail) for each in result.findings if each.check is Check.NO_FIGURE
    ] == [
        (Check.NO_FIGURE, "the row has no figure"),
        (Check.NO_FIGURE, "no figure is left"),
    ]


def test_gross_profit_that_is_not_revenue_minus_cost_is_a_warning() -> None:
    """The row is stored as reported."""
    rows = [
        _row(_INCOME, "2024-12-31", revenue=1),
        _row(_INCOME, "2025-12-31", revenue=1000, cost_of_revenue=600, gross_profit=500),
    ]

    result = _one(*rows)

    assert result.rows[-1].figures[Figure.GROSS_PROFIT] == 500
    assert result.findings[-1].detail == "revenue 1000 minus cost of revenue 600, gross profit 500"


def test_a_balance_sheet_whose_two_sides_differ_is_a_warning() -> None:
    """The provider's total of liabilities and equity is read for this and never stored."""
    result = _one(_row(_BALANCE, "2025-12-31", liabilities_and_equity=1100, total_assets=1000))

    assert dict(result.rows[0].figures) == {Figure.TOTAL_ASSETS: 1000}
    assert _checks(result) == [(Check.BALANCE_SIDES_DIFFER, _BALANCE, "2025-12-31")]


def test_a_payload_that_names_another_isin_is_reported_and_still_read() -> None:
    """The names agree in all eleven such payloads; the ISIN probably changed."""
    result = _one(*_year("2025-12-31"), named="CA0000000002")

    assert result.rows
    assert result.findings[0] == Finding(
        isin=_ISIN, check=Check.OTHER_ISIN, detail="the payload names CA0000000002"
    )


def test_a_company_whose_payloads_have_no_yearly_row_gets_nothing() -> None:
    """As the six Egyptian listings."""
    result = company_statements([_payload()])

    assert result == CompanyStatements(
        isin=None,
        periods=(),
        rows=(),
        findings=(
            Finding(isin=_ISIN, check=Check.NO_FISCAL_YEAR, detail="the payload has no yearly row"),
        ),
    )
    assert result.latest is None


def test_a_common_shares_payload_is_read_before_a_preferred_shares() -> None:
    """Even with fewer years."""
    common = _payload(*_year("2025-12-31"), isin="US0000000002")
    preferred = _payload(
        *_year("2024-12-31"), *_year("2025-12-31"), isin="US0000000001", preferred=True
    )

    assert company_statements([preferred, common]).isin == "US0000000002"


def test_of_two_common_shares_the_payload_with_more_years_is_read() -> None:
    """Then the smaller ISIN."""
    short = _payload(*_year("2025-12-31"), isin="US0000000001")
    long = _payload(*_year("2024-12-31"), *_year("2025-12-31"), isin="US0000000009")
    twin = _payload(*_year("2024-12-31"), *_year("2025-12-31"), isin="US0000000005")

    assert company_statements([short, long]).isin == "US0000000009"
    assert company_statements([long, twin, short]).isin == "US0000000005"


def test_a_payload_without_rows_is_never_read_when_another_has_rows() -> None:
    """A preferred share's statements beat no statements."""
    empty = _payload(isin="US0000000001")
    preferred = _payload(*_year("2025-12-31"), isin="US0000000002", preferred=True)

    assert company_statements([empty, preferred]).isin == "US0000000002"


def test_another_payload_that_disagrees_on_the_latest_shared_year_is_reported() -> None:
    """SEB's two share classes give different revenue for one year."""
    read = _payload(*_year("2025-12-31", revenue=152_476), isin="SE0000000001")
    other = _payload(*_year("2025-12-31", revenue=76_939), isin="SE0000000002")

    result = company_statements([other, read])

    assert result.isin == "SE0000000001"
    assert result.findings[-1] == Finding(
        isin="SE0000000002",
        check=Check.PAYLOADS_DISAGREE,
        statement=_INCOME,
        period_end=date(2025, 12, 31),
        figure=Figure.REVENUE,
        detail="76939 here, 152476 in the payload of SE0000000001, which is read",
    )


def test_payloads_that_agree_within_one_percent_raise_nothing() -> None:
    """A rounding difference between two payloads is not a disagreement."""
    read = _payload(*_year("2025-12-31", revenue=1_000_000), isin="CN0000000001")
    other = _payload(*_year("2025-12-31", revenue=1_005_000), isin="CN0000000002")

    findings = company_statements([read, other]).findings

    assert Check.PAYLOADS_DISAGREE not in {each.check for each in findings}


def test_payloads_without_a_year_in_common_are_reported() -> None:
    """Their figures cannot be compared."""
    read = _payload(*_year("2024-12-31"), *_year("2025-12-31"), isin="CN0000000001")
    other = _payload(*_year("2019-12-31"), isin="CN0000000002")

    result = company_statements([read, other])

    assert result.findings[-1].check is Check.PAYLOADS_DISAGREE
    assert result.findings[-1].detail.startswith("no fiscal year in common")


def test_the_same_payloads_give_the_same_result_in_any_order() -> None:
    """The load's output must not depend on the order the listings come in."""
    one = _payload(*_year("2024-12-31"), *_year("2025-12-31"), isin="US0000000003")
    two = _payload(*_year("2025-12-31", revenue=9), isin="US0000000004", named="US0000000009")

    assert company_statements([one, two]) == company_statements([two, one])


def test_stored_rows_carry_their_figures_under_pyvalues_names() -> None:
    """The load maps each figure to the column of the same name."""
    result = _one(_row(_BALANCE, "2025-12-31", shares_outstanding=7_453_000_000))

    assert result.rows == (
        BalanceSheetRow(
            period_end=date(2025, 12, 31), figures={Figure.SHARES_OUTSTANDING: 7_453_000_000}
        ),
    )
    assert result.rows[0].statement is Statement.BALANCE_SHEET
