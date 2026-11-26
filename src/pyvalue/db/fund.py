"""The ``fund`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Fund:
    """One row of ``fund``: a fund whose holdings are loaded (ADR 0017).

    Attributes:
        fund_code: pyvalue's own code for the fund: its ticker.
        name: The fund's name.
        scope: ``US`` or ``NON_US``: whether the fund is expected to hold
            US-coded ISINs.
        sec_series_id: The SEC's id for the fund.
        sec_filing_number: The filing whose lines are in ``holding`` now.
        holdings_date: The day that filing states the holdings for.
        sponsor_file_date: The day the sponsor's own file states the holdings
            for, or ``None`` for a sponsor that has no such file.
    """

    fund_code: str
    name: str
    scope: str
    sec_series_id: str
    sec_filing_number: str
    holdings_date: date
    sponsor_file_date: date | None


class FundRepository(Repository):
    """Every statement that reads or changes ``fund``."""

    table: ClassVar[str] = "fund"

    def all(self) -> tuple[Fund, ...]:
        """Return every fund, ordered by its code."""
        rows = self._execute(
            "SELECT fund_code, name, scope, sec_series_id, sec_filing_number, holdings_date, "
            "sponsor_file_date FROM fund ORDER BY fund_code"
        ).fetchall()
        return tuple(
            Fund(
                fund_code=str(fund_code),
                name=str(name),
                scope=str(scope),
                sec_series_id=str(sec_series_id),
                sec_filing_number=str(sec_filing_number),
                # The schema only lets a date written as YYYY-MM-DD in.
                holdings_date=date.fromisoformat(str(holdings_date)),
                sponsor_file_date=(
                    None
                    if sponsor_file_date is None
                    else date.fromisoformat(str(sponsor_file_date))
                ),
            )
            for (
                fund_code,
                name,
                scope,
                sec_series_id,
                sec_filing_number,
                holdings_date,
                sponsor_file_date,
            ) in rows
        )

    def save(self, fund: Fund) -> None:
        """Add a fund, or bring the row of a fund that is already there up to date.

        A fund keeps its row from load to load; what changes is the filing it
        was loaded from. So the row is updated in place, never deleted and
        added again: its holding lines point at it.

        Args:
            fund: The fund as it should be stored.

        Raises:
            ConstraintError: If a value has the wrong shape, or another fund
                already has the SEC series id or the filing number.
        """
        sponsor_file_date = fund.sponsor_file_date
        self._execute(
            "INSERT INTO fund (fund_code, name, scope, sec_series_id, sec_filing_number, "
            "holdings_date, sponsor_file_date) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (fund_code) DO UPDATE SET name = excluded.name, scope = excluded.scope, "
            "sec_series_id = excluded.sec_series_id, "
            "sec_filing_number = excluded.sec_filing_number, "
            "holdings_date = excluded.holdings_date, "
            "sponsor_file_date = excluded.sponsor_file_date",
            (
                fund.fund_code,
                fund.name,
                fund.scope,
                fund.sec_series_id,
                fund.sec_filing_number,
                fund.holdings_date.isoformat(),
                None if sponsor_file_date is None else sponsor_file_date.isoformat(),
            ),
        )
