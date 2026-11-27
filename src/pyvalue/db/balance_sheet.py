"""The ``balance_sheet`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass, fields
from datetime import date
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    """One row of ``balance_sheet``: a company's balance sheet on one date.

    Decided in ADR 0029. Every figure is a whole number in the main unit of
    the period's currency, or ``None`` when it is not known. A balance sheet
    is a snapshot, so it has no length.

    Attributes:
        company_id: The company.
        period_end: The day of the snapshot.
        total_assets: Total assets. Above zero.
        total_liabilities: Total liabilities. Never negative.
        equity: Equity of the company's own shareholders; can be negative.
        minority_interest: Equity that belongs to outside shareholders of
            subsidiaries.
        cash: Cash. Never negative.
        short_term_investments: Short-term investments. Never negative.
        cash_and_short_term_investments: The provider's own total of the two.
            Never negative.
        short_term_debt: Borrowings due within a year. Never negative.
        long_term_debt: Borrowings due later. Never negative.
        total_debt_stated: The provider's own total of debt, which is not the
            sum of the two before it. Never negative.
        lease_obligations: Lease liabilities. Never negative.
        current_assets: Current assets. Never negative.
        current_liabilities: Current liabilities. Never negative.
        noncurrent_liabilities: Liabilities due after a year. Never negative.
        shares_outstanding: The number of shares outstanding: a count, not an
            amount of money. Above zero.
    """

    company_id: int
    period_end: date
    total_assets: int | None
    total_liabilities: int | None
    equity: int | None
    minority_interest: int | None
    cash: int | None
    short_term_investments: int | None
    cash_and_short_term_investments: int | None
    short_term_debt: int | None
    long_term_debt: int | None
    total_debt_stated: int | None
    lease_obligations: int | None
    current_assets: int | None
    current_liabilities: int | None
    noncurrent_liabilities: int | None
    shares_outstanding: int | None


# The columns in the order of the record's fields: the record is the table.
_COLUMNS: tuple[str, ...] = tuple(field.name for field in fields(BalanceSheet))


class BalanceSheetRepository(Repository):
    """Every statement that reads or changes ``balance_sheet``."""

    table: ClassVar[str] = "balance_sheet"

    def add(self, row: BalanceSheet) -> None:
        """Add one balance sheet.

        Args:
            row: The balance sheet as it should be stored.

        Raises:
            ConstraintError: If the company has no reporting period on that
                date, already has a balance sheet on it, the row has no
                figure, or a value is not allowed.
        """
        values = [getattr(row, column) for column in _COLUMNS]
        values[_COLUMNS.index("period_end")] = row.period_end.isoformat()
        self._execute(
            f"INSERT INTO balance_sheet ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
            values,
        )

    def remove_all(self) -> None:
        """Remove every balance sheet.

        The statements load replaces the four statement tables as a whole
        (ADR 0029).
        """
        self._execute("DELETE FROM balance_sheet")
