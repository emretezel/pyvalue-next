"""The ``provider_symbol`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class ProviderSymbol:
    """One row of ``provider_symbol``: a share line of a provider's symbol list.

    Decided in ADR 0018. The provider's venue label and its type for the line
    are not kept (ADR 0025): the first only says how ``mic`` was worked out,
    and the load stores nothing but common and preferred shares.

    Attributes:
        provider_code: The provider.
        provider_exchange_code: The provider's exchange code whose list the
            line is in.
        provider_symbol: The symbol the provider uses, exactly as given.
        mic: Our exchange the line is on.
        provider_name: The provider's name for the security, or ``None``.
        provider_currency: The currency code as the provider gives it. It can
            be a sub-unit, such as ``GBX`` for pence.
        isin: The ISIN the provider gives for the line, or ``None`` when it
            gives none or a malformed one.
    """

    provider_code: str
    provider_exchange_code: str
    provider_symbol: str
    mic: str
    provider_name: str | None
    provider_currency: str
    isin: str | None


class ProviderSymbolRepository(Repository):
    """Every statement that reads or changes ``provider_symbol``."""

    table: ClassVar[str] = "provider_symbol"

    def of_provider(self, provider_code: str) -> tuple[ProviderSymbol, ...]:
        """Return every stored line of one provider, ordered by exchange code and symbol.

        The listing rule reads them once and looks them up in memory
        (ADR 0026): one of its comparisons, between a fund's ticker and a
        symbol, cannot be made by the database.

        Args:
            provider_code: The provider whose lines are wanted.
        """
        rows = self._execute(
            "SELECT provider_code, provider_exchange_code, provider_symbol, mic, provider_name, "
            "provider_currency, isin FROM provider_symbol WHERE provider_code = ? "
            "ORDER BY provider_exchange_code, provider_symbol",
            (provider_code,),
        ).fetchall()
        return tuple(
            ProviderSymbol(
                provider_code=str(provider),
                provider_exchange_code=str(code),
                provider_symbol=str(symbol),
                mic=str(mic),
                provider_name=None if name is None else str(name),
                provider_currency=str(currency),
                isin=None if isin is None else str(isin),
            )
            for provider, code, symbol, mic, name, currency, isin in rows
        )

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
            "mic, provider_name, provider_currency, isin) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                symbol.provider_code,
                symbol.provider_exchange_code,
                symbol.provider_symbol,
                symbol.mic,
                symbol.provider_name,
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
