"""The ``instrument`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Instrument:
    """One row of ``instrument``: one security of a company.

    Attributes:
        instrument_id: The row's id.
        company_id: The company that issued the security.
        isin: The security's ISIN.
    """

    instrument_id: int
    company_id: int
    isin: str


class InstrumentRepository(Repository):
    """Every statement that reads or changes ``instrument``."""

    table: ClassVar[str] = "instrument"

    def all(self) -> tuple[Instrument, ...]:
        """Return every instrument, in the order the rows were added."""
        rows = self._execute(
            "SELECT instrument_id, company_id, isin FROM instrument ORDER BY instrument_id"
        ).fetchall()
        return tuple(
            Instrument(instrument_id=int(instrument_id), company_id=int(company_id), isin=str(isin))
            for instrument_id, company_id, isin in rows
        )

    def add(self, company_id: int, isin: str) -> Instrument:
        """Add an instrument to a company.

        Args:
            company_id: The company that issued the security.
            isin: The security's ISIN.

        Returns:
            The new row, with the id the database gave it.

        Raises:
            ConstraintError: If the ISIN has the wrong shape or is already an
                instrument, or there is no company with this id.
        """
        # RETURNING hands back the new id with the insert itself. Fetching the
        # one row also finishes the statement, which the commit needs.
        row = self._execute(
            "INSERT INTO instrument (company_id, isin) VALUES (?, ?) RETURNING instrument_id",
            (company_id, isin),
        ).fetchone()
        return Instrument(instrument_id=int(row[0]), company_id=company_id, isin=isin)
