"""The ``cash_flow_statement`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass, fields
from datetime import date
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class CashFlowStatement:
    """One row of ``cash_flow_statement``: a company's cash-flow statement for one period.

    Decided in ADR 0029. Every figure is a whole number in the main unit of
    the period's currency, or ``None`` when it is not known. An amount going
    out, such as capital expenditure, is written as a positive number.

    Attributes:
        company_id: The company.
        period_end: The last day of the period.
        months: How many months the row covers, back from ``period_end``:
            3, 6, 9 or 12. A fiscal year is 12.
        operating_cash_flow: Cash from operations.
        capital_expenditure: Cash paid for property, plant and equipment.
            Never negative.
        depreciation_amortization: Depreciation and amortisation added back.
            Never negative.
        dividends_paid: Cash dividends paid. Never negative.
        net_share_sales: Shares sold minus shares bought back; negative when
            the company bought back more than it sold.
    """

    company_id: int
    period_end: date
    months: int
    operating_cash_flow: int | None
    capital_expenditure: int | None
    depreciation_amortization: int | None
    dividends_paid: int | None
    net_share_sales: int | None


# The columns in the order of the record's fields: the record is the table.
_COLUMNS: tuple[str, ...] = tuple(field.name for field in fields(CashFlowStatement))


class CashFlowStatementRepository(Repository):
    """Every statement that reads or changes ``cash_flow_statement``."""

    table: ClassVar[str] = "cash_flow_statement"

    def add(self, row: CashFlowStatement) -> None:
        """Add one cash-flow statement.

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
            f"INSERT INTO cash_flow_statement ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
            values,
        )

    def remove_all(self) -> None:
        """Remove every cash-flow statement.

        The statements load replaces the four statement tables as a whole
        (ADR 0029).
        """
        self._execute("DELETE FROM cash_flow_statement")
