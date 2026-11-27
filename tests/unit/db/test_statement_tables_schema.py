"""Tests for the four statement tables of migration 0008 (ADR 0029).

The tests pin which rows the database accepts, which it refuses and by which
constraint, that the schema's figures that cannot be negative are exactly the
load's list (ADR 0030), that each record is its table, which index a lookup
uses, and what the migration does to a database that already has rows.

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

import pytest

from pyvalue.db import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    ReportingPeriod,
    migrate,
    packaged_migrations,
)
from pyvalue.db.connection import connect
from pyvalue.fundamentals.checks import ABOVE_ZERO, NOT_NEGATIVE
from pyvalue.providers.statements import FIGURES, Figure, Statement

_CHECK = "CHECK constraint failed"
_FOREIGN_KEY = "FOREIGN KEY constraint failed"
_UNIQUE = "UNIQUE constraint failed"
_NOT_NULL = "NOT NULL constraint failed"
_STRICT = "cannot store"

# The record of each statement table, and of the periods.
_RECORDS: dict[str, type] = {
    "reporting_period": ReportingPeriod,
    "income_statement": IncomeStatement,
    "cash_flow_statement": CashFlowStatement,
    "balance_sheet": BalanceSheet,
}

# The key columns in front of each statement's figures.
_KEYS: dict[Statement, tuple[str, ...]] = {
    Statement.INCOME: ("company_id", "period_end", "months"),
    Statement.CASH_FLOW: ("company_id", "period_end", "months"),
    Statement.BALANCE_SHEET: ("company_id", "period_end"),
}

# One company with two periods: Microsoft's last two fiscal years.
_SEED: tuple[str, ...] = (
    "INSERT INTO company (name) VALUES ('Microsoft Corp')",
    "INSERT INTO reporting_period VALUES (1, '2026-06-30', 'USD'), (1, '2025-06-30', 'USD')",
)


@pytest.fixture
def seeded(migrated_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Yield the migrated database with one company and two periods."""
    for statement in _SEED:
        migrated_db.execute(statement)
    yield migrated_db


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Return a table's columns, in order."""
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]


def _insert(table: str, **values: object) -> str:
    """Return an insert of one row on the period 2026-06-30 of company 1."""
    row: dict[str, object] = {"company_id": 1, "period_end": "'2026-06-30'"}
    if table != "balance_sheet":
        row["months"] = 12
    row.update(values)
    return f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join(map(str, row.values()))})"


@pytest.mark.parametrize("table", list(_RECORDS))
def test_each_record_is_its_table_column_for_column(
    migrated_db: sqlite3.Connection, table: str
) -> None:
    """The repositories write the record's fields, in order, as the columns."""
    assert _columns(migrated_db, table) == [field.name for field in fields(_RECORDS[table])]


@pytest.mark.parametrize("statement", list(Statement))
def test_each_figure_of_pyvalue_has_its_column_and_nothing_else_does(
    migrated_db: sqlite3.Connection, statement: Statement
) -> None:
    """The figures read from a provider (``FIGURES``) are the table's columns after the key."""
    expected = [*_KEYS[statement], *(figure.value for figure in FIGURES[statement])]

    assert _columns(migrated_db, statement.value) == expected


def test_valid_statements_are_accepted(seeded: sqlite3.Connection) -> None:
    """Negative profits, outflows and equity are facts; a fiscal year and a quarter share a date."""
    for statement in (
        _insert("income_statement", revenue=331_839_000_000, net_income=-5, income_tax=-3),
        _insert("income_statement", months=3, revenue=92_279_000_000),
        _insert("cash_flow_statement", operating_cash_flow=-7, capital_expenditure=0),
        _insert("balance_sheet", total_assets=758_376_000_000, equity=-1, minority_interest=-2),
        _insert("income_statement", period_end="'2025-06-30'", revenue=99_999_999_999_999_999),
    ):
        seeded.execute(statement)

    assert seeded.execute("SELECT count(*) FROM income_statement").fetchone() == (3,)


def test_an_amount_given_as_a_whole_float_is_stored_as_an_integer(
    seeded: sqlite3.Connection,
) -> None:
    """STRICT converts 5.0 without loss, and keeps the column's type."""
    seeded.execute(_insert("balance_sheet", total_assets=5.0))

    assert seeded.execute("SELECT typeof(total_assets) FROM balance_sheet").fetchone() == (
        "integer",
    )


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        ("INSERT INTO reporting_period VALUES (9, '2026-06-30', 'USD')", _FOREIGN_KEY),
        ("INSERT INTO reporting_period VALUES (1, '2026-06-30', 'EUR')", _UNIQUE),
        ("INSERT INTO reporting_period VALUES (1, '30/06/2024', 'USD')", _CHECK),
        ("INSERT INTO reporting_period VALUES (1, '2024-02-30', 'USD')", _CHECK),
        ("INSERT INTO reporting_period VALUES (1, '2024-06-30', 'usd')", _CHECK),
        ("INSERT INTO reporting_period VALUES (1, '2024-06-30', 'USDX')", _CHECK),
        ("INSERT INTO reporting_period VALUES (1, '2024-06-30', NULL)", _NOT_NULL),
        (_insert("income_statement", period_end="'2024-06-30'", revenue=1), _FOREIGN_KEY),
        (_insert("balance_sheet", period_end="'2024-06-30'", cash=1), _FOREIGN_KEY),
        (_insert("income_statement", months=4, revenue=1), _CHECK),
        (_insert("cash_flow_statement", months=0, dividends_paid=1), _CHECK),
        (_insert("income_statement", revenue=1.5), _STRICT),
        (_insert("income_statement", revenue="'abc'"), _STRICT),
        (_insert("income_statement"), _CHECK),
        (_insert("cash_flow_statement"), _CHECK),
        (_insert("balance_sheet"), _CHECK),
    ],
)
def test_invalid_rows_are_refused_by_the_intended_constraint(
    seeded: sqlite3.Connection, statement: str, message: str
) -> None:
    """A wrong currency, date, length, kind of amount or an empty row never gets in."""
    with pytest.raises(sqlite3.IntegrityError, match=message):
        seeded.execute(statement)


def test_a_statement_twice_for_one_period_and_length_is_refused(
    seeded: sqlite3.Connection,
) -> None:
    """One income statement per company, date and length."""
    seeded.execute(_insert("income_statement", revenue=1))

    with pytest.raises(sqlite3.IntegrityError, match=_UNIQUE):
        seeded.execute(_insert("income_statement", revenue=2))


@pytest.mark.parametrize(
    ("statement", "figure"),
    [(statement, figure) for statement, figures in FIGURES.items() for figure in figures],
    ids=lambda each: str(each.value),
)
def test_the_schema_refuses_exactly_the_values_the_load_empties(
    seeded: sqlite3.Connection, statement: Statement, figure: Figure
) -> None:
    """One list in two places: a row the schema refused would stop the whole load (ADR 0030)."""
    column = figure.value
    lowest = 0 if figure in ABOVE_ZERO else -1 if figure in NOT_NEGATIVE else None
    if lowest is None:
        seeded.execute(_insert(statement.value, **{column: -1}))
        return
    with pytest.raises(sqlite3.IntegrityError, match=_CHECK):
        seeded.execute(_insert(statement.value, **{column: lowest}))
    seeded.execute(_insert(statement.value, **{column: lowest + 1}))


def test_a_period_with_statements_and_a_company_with_periods_cannot_be_deleted(
    seeded: sqlite3.Connection,
) -> None:
    """Nothing is deleted implicitly; the load removes the statements first."""
    seeded.execute(_insert("balance_sheet", cash=1))

    with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
        seeded.execute("DELETE FROM reporting_period WHERE period_end = '2026-06-30'")
    with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
        seeded.execute("DELETE FROM company")


@pytest.mark.parametrize("table", ["income_statement", "cash_flow_statement", "balance_sheet"])
def test_the_statements_of_one_company_are_found_through_the_primary_key(
    seeded: sqlite3.Connection, table: str
) -> None:
    """No other index is needed: nothing looks a statement up except by company."""
    plan = seeded.execute(
        f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE company_id = 1 ORDER BY period_end"
    ).fetchall()

    assert "USING INDEX sqlite_autoindex" in str(plan) or "USING PRIMARY KEY" in str(plan)


def test_migration_0008_adds_four_empty_tables_and_changes_nothing_else(tmp_path: Path) -> None:
    """A database built before it keeps its rows; the load fills the new tables."""
    path = tmp_path / "pyvalue.db"
    migrate(path, packaged_migrations()[:7])
    connection = connect(path)
    try:
        connection.execute("INSERT INTO company (name) VALUES ('Microsoft Corp')")
        before = connection.execute("SELECT company_id, name, lei FROM company").fetchall()
    finally:
        connection.close()

    report = migrate(path, packaged_migrations()[:8])

    assert [migration.label for migration in report.applied] == ["0008_statements"]
    connection = connect(path)
    try:
        assert connection.execute("SELECT company_id, name, lei FROM company").fetchall() == before
        for table in ("reporting_period", "income_statement", "cash_flow_statement"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM balance_sheet").fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
