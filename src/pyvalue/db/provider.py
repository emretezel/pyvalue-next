"""The ``provider`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Provider:
    """One row of ``provider``: a data provider (ADR 0002).

    Attributes:
        provider_code: pyvalue's own short code for the provider, such as
            ``eodhd``.
        name: The provider's name.
    """

    provider_code: str
    name: str


class ProviderRepository(Repository):
    """Every statement that reads or changes ``provider``."""

    table: ClassVar[str] = "provider"

    def save(self, provider: Provider) -> None:
        """Add a provider, or correct the name of one that is there.

        The row is updated in place, never deleted and added again: exchange
        codes and symbols point at it.

        Args:
            provider: The provider as it should be stored.

        Raises:
            ConstraintError: If a value has the wrong shape.
        """
        self._execute(
            "INSERT INTO provider (provider_code, name) VALUES (?, ?) "
            "ON CONFLICT (provider_code) DO UPDATE SET name = excluded.name",
            (provider.provider_code, provider.name),
        )
