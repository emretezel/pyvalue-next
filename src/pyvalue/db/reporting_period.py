"""The ``reporting_period`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    """One row of ``reporting_period``: a date a company's statements are drawn up to.

    Decided in ADR 0029. The statements of the date hang off it, so each has
    the period's one currency.

    Attributes:
        company_id: The company.
        period_end: The date the statements are drawn up to.
        currency: The ISO 4217 code of the currency they are in. Never a
            sub-unit such as ``GBX``.
    """

    company_id: int
    period_end: date
    currency: str


class ReportingPeriodRepository(Repository):
    """Every statement that reads or changes ``reporting_period``."""

    table: ClassVar[str] = "reporting_period"

    def add(self, period: ReportingPeriod) -> None:
        """Add one reporting period.

        Args:
            period: The period as it should be stored.

        Raises:
            ConstraintError: If the company does not exist, the company already
                has a period on that date, or a value has the wrong shape.
        """
        self._execute(
            "INSERT INTO reporting_period (company_id, period_end, currency) VALUES (?, ?, ?)",
            (period.company_id, period.period_end.isoformat(), period.currency),
        )

    def remove_all(self) -> None:
        """Remove every reporting period.

        The statements load replaces the four statement tables as a whole
        (ADR 0029). It removes the statements first: a period that a statement
        still points at cannot be removed.

        Raises:
            ConstraintError: If a statement still points at a period.
        """
        self._execute("DELETE FROM reporting_period")
