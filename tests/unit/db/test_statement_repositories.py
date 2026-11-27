"""Tests for the repositories of the four statement tables (ADR 0029).

Each repository has the two methods the statements load calls: add a row,
and remove every row. What was written is read back with ``sqlite3``, as only
the tests of ``pyvalue.db`` may.

Author: Emre Tezel
"""

from datetime import date

import pytest

from pyvalue.db import (
    BalanceSheet,
    CashFlowStatement,
    ConstraintError,
    Database,
    IncomeStatement,
    ReportingPeriod,
)
from pyvalue.db.connection import connect

_DAY: date = date(2026, 6, 30)


def _income(company_id: int, revenue: int | None = 331_839_000_000) -> IncomeStatement:
    """Return Microsoft's income statement for its fiscal year to June 2026."""
    return IncomeStatement(
        company_id=company_id,
        period_end=_DAY,
        months=12,
        revenue=revenue,
        cost_of_revenue=106_374_000_000,
        gross_profit=225_465_000_000,
        operating_income=155_237_000_000,
        pretax_income=165_934_000_000,
        income_tax=32_185_000_000,
        net_income=133_749_000_000,
        interest_expense=3_051_000_000,
    )


def _cash_flow(company_id: int) -> CashFlowStatement:
    """Return the cash-flow statement of the same year."""
    return CashFlowStatement(
        company_id=company_id,
        period_end=_DAY,
        months=12,
        operating_cash_flow=182_935_000_000,
        capital_expenditure=115_948_000_000,
        depreciation_amortization=38_534_000_000,
        dividends_paid=26_445_000_000,
        net_share_sales=-22_271_000_000,
    )


def _balance_sheet(company_id: int) -> BalanceSheet:
    """Return the balance sheet of the same date, minority interest not reported."""
    return BalanceSheet(
        company_id=company_id,
        period_end=_DAY,
        total_assets=758_376_000_000,
        total_liabilities=315_989_000_000,
        equity=442_387_000_000,
        minority_interest=None,
        cash=20_935_000_000,
        short_term_investments=55_908_000_000,
        cash_and_short_term_investments=76_843_000_000,
        short_term_debt=18_905_300_000,
        long_term_debt=31_067_000_000,
        total_debt_stated=128_808_300_000,
        lease_obligations=16_532_000_000,
        current_assets=207_710_000_000,
        current_liabilities=168_825_000_000,
        noncurrent_liabilities=147_164_000_000,
        shares_outstanding=7_453_000_000,
    )


def _rows(database: Database, table: str) -> list[tuple[object, ...]]:
    """Return every row of a table, as ``sqlite3`` reads it."""
    connection = connect(database.path)
    try:
        return connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
    finally:
        connection.close()


@pytest.fixture
def company_id(database: Database) -> int:
    """Return the id of a company with a reporting period on 2026-06-30."""
    with database.unit_of_work() as work:
        company = work.companies.add(name="Microsoft Corp", lei=None)
        work.reporting_periods.add(ReportingPeriod(company.company_id, _DAY, "USD"))
    return company.company_id


def test_a_period_is_stored_with_its_date_written_as_yyyy_mm_dd(
    database: Database, company_id: int
) -> None:
    """The schema only takes a date in that form."""
    assert _rows(database, "reporting_period") == [(company_id, "2026-06-30", "USD")]


def test_each_statement_is_stored_column_for_column(database: Database, company_id: int) -> None:
    """Every figure lands in the column of its name, and an empty one is NULL."""
    with database.unit_of_work() as work:
        work.income_statements.add(_income(company_id))
        work.cash_flow_statements.add(_cash_flow(company_id))
        work.balance_sheets.add(_balance_sheet(company_id))

    assert _rows(database, "income_statement") == [
        (
            company_id,
            "2026-06-30",
            12,
            331_839_000_000,
            106_374_000_000,
            225_465_000_000,
            155_237_000_000,
            165_934_000_000,
            32_185_000_000,
            133_749_000_000,
            3_051_000_000,
        )
    ]
    assert _rows(database, "cash_flow_statement") == [
        (
            company_id,
            "2026-06-30",
            12,
            182_935_000_000,
            115_948_000_000,
            38_534_000_000,
            26_445_000_000,
            -22_271_000_000,
        )
    ]
    (balance,) = _rows(database, "balance_sheet")
    assert balance[:5] == (
        company_id,
        "2026-06-30",
        758_376_000_000,
        315_989_000_000,
        442_387_000_000,
    )
    assert balance[5] is None
    assert balance[-1] == 7_453_000_000


def test_removing_all_rows_empties_the_four_tables_statements_first(
    database: Database, company_id: int
) -> None:
    """The order the load uses: a period with statements cannot go first."""
    with database.unit_of_work() as work:
        work.income_statements.add(_income(company_id))
        work.cash_flow_statements.add(_cash_flow(company_id))
        work.balance_sheets.add(_balance_sheet(company_id))

    with database.unit_of_work() as work:
        work.income_statements.remove_all()
        work.cash_flow_statements.remove_all()
        work.balance_sheets.remove_all()
        work.reporting_periods.remove_all()

    for table in ("income_statement", "cash_flow_statement", "balance_sheet", "reporting_period"):
        assert _rows(database, table) == []


def test_removing_the_periods_before_their_statements_is_refused(
    database: Database, company_id: int
) -> None:
    """Nothing is deleted implicitly, and the unit of work undoes the attempt."""
    with database.unit_of_work() as work:
        work.balance_sheets.add(_balance_sheet(company_id))

    with pytest.raises(ConstraintError, match="reporting_period"), database.unit_of_work() as work:
        work.reporting_periods.remove_all()

    assert len(_rows(database, "reporting_period")) == 1


def test_a_statement_without_its_period_is_refused_as_pyvalues_own_error(
    database: Database, company_id: int
) -> None:
    """No raw ``sqlite3`` error reaches a component."""
    with pytest.raises(ConstraintError, match="income_statement"), database.unit_of_work() as work:
        work.income_statements.add(_income(company_id + 1))


def test_a_whole_number_too_large_for_the_database_is_refused_as_pyvalues_own_error(
    database: Database, company_id: int
) -> None:
    """Python's driver refuses 2^63 before SQLite sees it; the load empties such values first."""
    with pytest.raises(ConstraintError, match="income_statement"), database.unit_of_work() as work:
        work.income_statements.add(_income(company_id, revenue=2**63))

    assert _rows(database, "income_statement") == []


def test_everything_added_in_a_unit_of_work_is_undone_when_it_fails(
    database: Database, company_id: int
) -> None:
    """The load replaces the tables in one transaction, or not at all."""
    with pytest.raises(ConstraintError), database.unit_of_work() as work:
        work.income_statements.add(_income(company_id))
        work.balance_sheets.add(_balance_sheet(company_id))
        work.cash_flow_statements.add(_cash_flow(company_id + 1))

    assert _rows(database, "income_statement") == []
    assert _rows(database, "balance_sheet") == []
