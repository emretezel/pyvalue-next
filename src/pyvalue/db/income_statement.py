"""The ``income_statement`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass, fields
from datetime import date
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class IncomeStatement:
    """One row of ``income_statement``: a company's income statement for one period.

    Decided in ADR 0029. Every figure is a whole number in the main unit of
    the period's currency, or ``None`` when it is not known.

    Attributes:
        company_id: The company.
        period_end: The last day of the period.
        months: How many months the row covers, back from ``period_end``:
            3, 6, 9 or 12. A fiscal year is 12.
        revenue: Revenue.
        cost_of_revenue: Cost of the goods and services sold. Never negative.
        gross_profit: Gross profit, as reported.
        operating_income: Operating profit, as reported.
        pretax_income: Profit before income tax.
        income_tax: Income tax charged to the period; negative for a credit.
        net_income: Net profit.
        interest_expense: Interest charged to the period. Never negative.
    """

    company_id: int
    period_end: date
    months: int
    revenue: int | None
    cost_of_revenue: int | None
    gross_profit: int | None
    operating_income: int | None
    pretax_income: int | None
    income_tax: int | None
    net_income: int | None
    interest_expense: int | None


# The columns in the order of the record's fields: the record is the table.
_COLUMNS: tuple[str, ...] = tuple(field.name for field in fields(IncomeStatement))


class IncomeStatementRepository(Repository):
    """Every statement that reads or changes ``income_statement``."""

    table: ClassVar[str] = "income_statement"

    def add(self, row: IncomeStatement) -> None:
        """Add one income statement.

        Args:
            row: The statement as it should be stored.

        Raises:
            ConstraintError: If the company has no reporting period on that
                date, already has a statement of that length on it, the row
                has no figure, or a value is not allowed.
        """
        values = [getattr(row, column) for column in _COLUMNS]
        values[_COLUMNS.index("period_end")] = row.period_end.isoformat()
        self._execute(
            f"INSERT INTO income_statement ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
            values,
        )

    def remove_all(self) -> None:
        """Remove every income statement.

        The statements load replaces the four statement tables as a whole
        (ADR 0029).
        """
        self._execute("DELETE FROM income_statement")
