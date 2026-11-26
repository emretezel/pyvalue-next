"""The ``exchange`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Exchange:
    """One row of ``exchange``: a market on which companies list (ADR 0001).

    Attributes:
        mic: The market's ISO 10383 code.
        name: The market's name.
        country: The market's ISO 3166 country code, two letters.
    """

    mic: str
    name: str
    country: str


class ExchangeRepository(Repository):
    """Every statement that reads or changes ``exchange``."""

    table: ClassVar[str] = "exchange"

    def all(self) -> tuple[Exchange, ...]:
        """Return every exchange, ordered by its market code."""
        rows = self._execute("SELECT mic, name, country FROM exchange ORDER BY mic").fetchall()
        return tuple(
            Exchange(mic=str(mic), name=str(name), country=str(country))
            for mic, name, country in rows
        )

    def save(self, exchange: Exchange) -> None:
        """Add an exchange, or correct the name and country of one that is there.

        The row is updated in place, never deleted and added again: listings
        and provider codes point at it.

        Args:
            exchange: The exchange as it should be stored.

        Raises:
            ConstraintError: If a value has the wrong shape.
        """
        self._execute(
            "INSERT INTO exchange (mic, name, country) VALUES (?, ?, ?) "
            "ON CONFLICT (mic) DO UPDATE SET name = excluded.name, country = excluded.country",
            (exchange.mic, exchange.name, exchange.country),
        )
