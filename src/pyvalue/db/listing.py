"""The ``listing`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Listing:
    """One row of ``listing``: the exchange line a security trades on (ADR 0003).

    Attributes:
        listing_id: The row's id.
        instrument_id: The security. It has at most one listing.
        mic: The exchange the security trades on.
        ticker: The exchange's ticker for the security, in upper case.
        currency: The ISO 4217 currency the security trades in. Never a
            quote unit: a London line is ``GBP``, not pence.
    """

    listing_id: int
    instrument_id: int
    mic: str
    ticker: str
    currency: str


class ListingRepository(Repository):
    """Every statement that reads or changes ``listing``."""

    table: ClassVar[str] = "listing"

    def all(self) -> tuple[Listing, ...]:
        """Return every listing, in the order the rows were added."""
        rows = self._execute(
            "SELECT listing_id, instrument_id, mic, ticker, currency FROM listing "
            "ORDER BY listing_id"
        ).fetchall()
        return tuple(
            Listing(
                listing_id=int(listing_id),
                instrument_id=int(instrument_id),
                mic=str(mic),
                ticker=str(ticker),
                currency=str(currency),
            )
            for listing_id, instrument_id, mic, ticker, currency in rows
        )

    def add(self, instrument_id: int, mic: str, ticker: str, currency: str) -> Listing:
        """Give a security its listing.

        Args:
            instrument_id: The security.
            mic: The exchange it trades on.
            ticker: The exchange's ticker for it, in upper case.
            currency: The ISO 4217 currency it trades in.

        Returns:
            The new row, with the id the database gave it.

        Raises:
            ConstraintError: If the security or the exchange does not exist,
                the security already has a listing, another listing has this
                exchange and ticker, or a value has the wrong shape.
        """
        # RETURNING hands back the new id with the insert itself. Fetching the
        # one row also finishes the statement, which the commit needs.
        row = self._execute(
            "INSERT INTO listing (instrument_id, mic, ticker, currency) VALUES (?, ?, ?, ?) "
            "RETURNING listing_id",
            (instrument_id, mic, ticker, currency),
        ).fetchone()
        return Listing(
            listing_id=int(row[0]),
            instrument_id=instrument_id,
            mic=mic,
            ticker=ticker,
            currency=currency,
        )
