"""What pyvalue asks of any provider's financial statements.

A provider gives a company's income statement, cash-flow statement and
balance sheet in its own field names. This module is the common ground: the
figures pyvalue keeps, under pyvalue's names, and the shape a provider's
reader hands them over in. Each provider has a reader of its own that fills
that shape (``eodhd_statements`` for EODHD) and knows that provider's field
names; nothing else in pyvalue does.

The figures are the ones the QARP screen reads, and each is a column of the
statement tables (ADR 0029). A reader reports what the provider says and
decides nothing: the amounts are exact decimals, the currency is the
provider's label as given, and a figure the provider does not give is simply
absent. Which rows are kept, in which currency, and what is wrong with them
is the business of ``pyvalue.fundamentals``.

Author: Emre Tezel
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from types import MappingProxyType


class Statement(Enum):
    """One of the three financial statements. The value is its table (ADR 0029)."""

    INCOME = "income_statement"
    CASH_FLOW = "cash_flow_statement"
    BALANCE_SHEET = "balance_sheet"


class Figure(Enum):
    """One figure of a statement. The value is its column (ADR 0029)."""

    # Income statement.
    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    PRETAX_INCOME = "pretax_income"
    INCOME_TAX = "income_tax"
    NET_INCOME = "net_income"
    INTEREST_EXPENSE = "interest_expense"
    # Cash-flow statement.
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURE = "capital_expenditure"
    DEPRECIATION_AMORTIZATION = "depreciation_amortization"
    DIVIDENDS_PAID = "dividends_paid"
    NET_SHARE_SALES = "net_share_sales"
    # Balance sheet.
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"
    EQUITY = "equity"
    MINORITY_INTEREST = "minority_interest"
    CASH = "cash"
    SHORT_TERM_INVESTMENTS = "short_term_investments"
    CASH_AND_SHORT_TERM_INVESTMENTS = "cash_and_short_term_investments"
    SHORT_TERM_DEBT = "short_term_debt"
    LONG_TERM_DEBT = "long_term_debt"
    TOTAL_DEBT_STATED = "total_debt_stated"
    LEASE_OBLIGATIONS = "lease_obligations"
    CURRENT_ASSETS = "current_assets"
    CURRENT_LIABILITIES = "current_liabilities"
    NONCURRENT_LIABILITIES = "noncurrent_liabilities"
    SHARES_OUTSTANDING = "shares_outstanding"


# The figures of each statement, in the order of the table's columns.
FIGURES: Mapping[Statement, tuple[Figure, ...]] = MappingProxyType(
    {
        Statement.INCOME: (
            Figure.REVENUE,
            Figure.COST_OF_REVENUE,
            Figure.GROSS_PROFIT,
            Figure.OPERATING_INCOME,
            Figure.PRETAX_INCOME,
            Figure.INCOME_TAX,
            Figure.NET_INCOME,
            Figure.INTEREST_EXPENSE,
        ),
        Statement.CASH_FLOW: (
            Figure.OPERATING_CASH_FLOW,
            Figure.CAPITAL_EXPENDITURE,
            Figure.DEPRECIATION_AMORTIZATION,
            Figure.DIVIDENDS_PAID,
            Figure.NET_SHARE_SALES,
        ),
        Statement.BALANCE_SHEET: (
            Figure.TOTAL_ASSETS,
            Figure.TOTAL_LIABILITIES,
            Figure.EQUITY,
            Figure.MINORITY_INTEREST,
            Figure.CASH,
            Figure.SHORT_TERM_INVESTMENTS,
            Figure.CASH_AND_SHORT_TERM_INVESTMENTS,
            Figure.SHORT_TERM_DEBT,
            Figure.LONG_TERM_DEBT,
            Figure.TOTAL_DEBT_STATED,
            Figure.LEASE_OBLIGATIONS,
            Figure.CURRENT_ASSETS,
            Figure.CURRENT_LIABILITIES,
            Figure.NONCURRENT_LIABILITIES,
            Figure.SHARES_OUTSTANDING,
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ReportedRow:
    """One yearly row of one statement, as a provider reports it.

    Attributes:
        statement: Which statement the row is of.
        period_end: The date the row is drawn up to.
        currency: The provider's currency label for the row, exactly as
            given, or ``None`` when the row carries none. It can be a
            sub-unit code such as ``GBX``.
        figures: The figures the provider gives on the row, as exact
            decimals. A figure it does not give is absent.
        liabilities_and_equity: On a balance sheet, the provider's own total
            of liabilities and equity, when it gives one. It is read for one
            check (ADR 0030) and never stored. ``None`` on every other row.
    """

    statement: Statement
    period_end: date
    currency: str | None
    figures: Mapping[Figure, Decimal]
    liabilities_and_equity: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ReportedStatements:
    """The yearly rows of one payload, as a provider reports them.

    Attributes:
        isin: The ISIN the payload names for its security, or ``None``.
        statement_currency: The currency label the provider puts on each
            statement as a whole, as given, or ``None``. It is the last
            resort for a period whose rows carry no label (ADR 0029).
        rows: The yearly rows, ordered by statement and then by date.
    """

    isin: str | None
    statement_currency: Mapping[Statement, str | None]
    rows: tuple[ReportedRow, ...]
