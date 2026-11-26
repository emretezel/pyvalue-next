"""The ``provider_listing`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class ProviderListing:
    """One row of ``provider_listing``: a provider's symbol for a listing of ours (ADR 0002).

    Attributes:
        provider_code: The provider.
        listing_id: Our listing.
        provider_symbol: The symbol the provider itself uses for that
            listing, exactly as given and without any exchange part. It can
            differ from the listing's ticker.
    """

    provider_code: str
    listing_id: int
    provider_symbol: str


class ProviderListingRepository(Repository):
    """Every statement that reads or changes ``provider_listing``."""

    table: ClassVar[str] = "provider_listing"

    def of_provider(self, provider_code: str) -> tuple[ProviderListing, ...]:
        """Return the symbols of one provider, ordered by listing.

        Args:
            provider_code: The provider whose symbols are wanted.
        """
        rows = self._execute(
            "SELECT provider_code, listing_id, provider_symbol FROM provider_listing "
            "WHERE provider_code = ? ORDER BY listing_id",
            (provider_code,),
        ).fetchall()
        return tuple(
            ProviderListing(
                provider_code=str(provider), listing_id=int(listing_id), provider_symbol=str(symbol)
            )
            for provider, listing_id, symbol in rows
        )

    def add(self, provider_listing: ProviderListing) -> None:
        """Record the symbol a provider uses for a listing.

        Args:
            provider_listing: The row as it should be stored.

        Raises:
            ConstraintError: If the provider or the listing does not exist,
                the provider already has a symbol for that listing, or the
                symbol has the wrong shape.
        """
        self._execute(
            "INSERT INTO provider_listing (provider_code, listing_id, provider_symbol) "
            "VALUES (?, ?, ?)",
            (
                provider_listing.provider_code,
                provider_listing.listing_id,
                provider_listing.provider_symbol,
            ),
        )
