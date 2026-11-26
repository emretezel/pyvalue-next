"""The ``provider_symbol`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class ProviderSymbol:
    """One row of ``provider_symbol``: a share line of a provider's symbol list (ADR 0018).

    Attributes:
        provider_code: The provider.
        provider_exchange_code: The provider's exchange code whose list the
            line is in.
        provider_symbol: The symbol the provider uses, exactly as given.
        mic: Our exchange the line is on.
        provider_venue: The provider's venue label for the line, or ``None``
            when it gives none.
        provider_name: The provider's name for the security, or ``None``.
        provider_type: ``Common Stock`` or ``Preferred Stock``.
        provider_currency: The currency code as the provider gives it. It can
            be a sub-unit, such as ``GBX`` for pence.
        isin: The ISIN the provider gives for the line, or ``None`` when it
            gives none or a malformed one.
    """

    provider_code: str
    provider_exchange_code: str
    provider_symbol: str
    mic: str
    provider_venue: str | None
    provider_name: str | None
    provider_type: str
    provider_currency: str
    isin: str | None


class ProviderSymbolRepository(Repository):
    """Every statement that reads or changes ``provider_symbol``."""

    table: ClassVar[str] = "provider_symbol"

    def count_of_code(self, provider_code: str, provider_exchange_code: str) -> int:
        """Return how many lines are stored under one exchange code of a provider.

        Args:
            provider_code: The provider.
            provider_exchange_code: The provider's exchange code.
        """
        (count,) = self._execute(
            "SELECT COUNT(*) FROM provider_symbol "
            "WHERE provider_code = ? AND provider_exchange_code = ?",
            (provider_code, provider_exchange_code),
        ).fetchone()
        return int(count)

    def add(self, symbol: ProviderSymbol) -> None:
        """Add one line of a provider's symbol list.

        Args:
            symbol: The line as it should be stored.

        Raises:
            ConstraintError: If a value has the wrong shape, the code is not
                mapped to that exchange for that provider, or the code already
                has a line with this symbol.
        """
        self._execute(
            "INSERT INTO provider_symbol (provider_code, provider_exchange_code, provider_symbol, "
            "mic, provider_venue, provider_name, provider_type, provider_currency, isin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol.provider_code,
                symbol.provider_exchange_code,
                symbol.provider_symbol,
                symbol.mic,
                symbol.provider_venue,
                symbol.provider_name,
                symbol.provider_type,
                symbol.provider_currency,
                symbol.isin,
            ),
        )

    def remove_of_code(self, provider_code: str, provider_exchange_code: str) -> None:
        """Remove every line stored under one exchange code of a provider.

        The lines of a code are a copy of one list. When the list is stored
        again it is replaced as a whole (ADR 0018). Removing the lines of a
        code that has none is not an error.

        Args:
            provider_code: The provider.
            provider_exchange_code: The provider's exchange code.
        """
        self._execute(
            "DELETE FROM provider_symbol WHERE provider_code = ? AND provider_exchange_code = ?",
            (provider_code, provider_exchange_code),
        )
