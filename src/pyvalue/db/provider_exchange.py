"""The ``provider_exchange`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class ProviderExchange:
    """One row of ``provider_exchange``: a provider's code for an exchange of ours (ADR 0002).

    Attributes:
        provider_code: The provider.
        mic: Our exchange.
        provider_exchange_code: The code the provider itself uses for that
            exchange. Several exchanges can share one code, as New York and
            Nasdaq share EODHD's ``US``.
    """

    provider_code: str
    mic: str
    provider_exchange_code: str


class ProviderExchangeRepository(Repository):
    """Every statement that reads or changes ``provider_exchange``."""

    table: ClassVar[str] = "provider_exchange"

    def of_provider(self, provider_code: str) -> tuple[ProviderExchange, ...]:
        """Return the exchange codes of one provider, ordered by code and exchange.

        Args:
            provider_code: The provider whose codes are wanted.
        """
        rows = self._execute(
            "SELECT provider_code, mic, provider_exchange_code FROM provider_exchange "
            "WHERE provider_code = ? ORDER BY provider_exchange_code, mic",
            (provider_code,),
        ).fetchall()
        return tuple(
            ProviderExchange(
                provider_code=str(provider), mic=str(mic), provider_exchange_code=str(code)
            )
            for provider, mic, code in rows
        )

    def add(self, mapping: ProviderExchange) -> None:
        """Add one code of a provider for one of our exchanges.

        There is no method that changes a code in place, on purpose: the
        symbol rows stored under a code follow a changed code (ADR 0018), so
        a correction would silently move a stored list under another code.

        Args:
            mapping: The row as it should be stored.

        Raises:
            ConstraintError: If the provider or the exchange does not exist,
                the provider already has a code for that exchange, or the
                code has the wrong shape.
        """
        self._execute(
            "INSERT INTO provider_exchange (provider_code, mic, provider_exchange_code) "
            "VALUES (?, ?, ?)",
            (mapping.provider_code, mapping.mic, mapping.provider_exchange_code),
        )
