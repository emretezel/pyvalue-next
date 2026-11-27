"""Tests for ``ProviderListingRepository``: every statement on ``provider_listing``.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import (
    ConstraintError,
    Database,
    Exchange,
    Provider,
    ProviderExchange,
    ProviderListing,
    ProviderListingAddress,
)


@pytest.fixture
def listed(database: Database) -> tuple[Database, int, int]:
    """Return a database with two providers and two listings, and the listings' ids."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XKRX", name="Korea Exchange", country="KR"))
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        work.providers.save(Provider(provider_code="other", name="Another Provider"))
        hynix = work.instruments.add(
            work.companies.add("SK Hynix Inc", None).company_id, "KR7000660001"
        )
        berkshire = work.instruments.add(
            work.companies.add("Berkshire Hathaway Inc", None).company_id, "US0846707026"
        )
        first = work.listings.add(hynix.instrument_id, "XKRX", "000660", "KRW")
        second = work.listings.add(berkshire.instrument_id, "XNYS", "BRK.B", "USD")
    return database, first.listing_id, second.listing_id


def test_a_provider_has_no_symbols_on_a_new_database(listed: tuple[Database, int, int]) -> None:
    """A listing is not mapped at a provider until a row says so."""
    database, _, _ = listed

    with database.unit_of_work() as work:
        assert work.provider_listings.of_provider("eodhd") == ()


def test_add_stores_a_symbol_and_of_provider_reads_it_back(
    listed: tuple[Database, int, int],
) -> None:
    """The symbol is kept exactly as given: it can differ from the listing's ticker."""
    database, _, berkshire = listed
    row = ProviderListing(provider_code="eodhd", listing_id=berkshire, provider_symbol="BRK-B")

    with database.unit_of_work() as work:
        work.provider_listings.add(row)

    with database.unit_of_work() as work:
        assert work.provider_listings.of_provider("eodhd") == (row,)


def test_of_provider_orders_by_listing_and_leaves_other_providers_out(
    listed: tuple[Database, int, int],
) -> None:
    """The order does not depend on which row was added first."""
    database, hynix, berkshire = listed
    rows = (
        ProviderListing(provider_code="eodhd", listing_id=berkshire, provider_symbol="BRK-B"),
        ProviderListing(provider_code="other", listing_id=hynix, provider_symbol="HYNIX KS"),
        ProviderListing(provider_code="eodhd", listing_id=hynix, provider_symbol="000660"),
    )

    with database.unit_of_work() as work:
        for row in rows:
            work.provider_listings.add(row)

    with database.unit_of_work() as work:
        assert work.provider_listings.of_provider("eodhd") == (rows[2], rows[0])
        assert work.provider_listings.of_provider("other") == (rows[1],)


def test_a_provider_has_one_symbol_per_listing(listed: tuple[Database, int, int]) -> None:
    """The key is the listing and the provider (ADR 0002)."""
    database, hynix, _ = listed

    with database.unit_of_work() as work:
        work.provider_listings.add(ProviderListing("eodhd", hynix, "000660"))
        with pytest.raises(ConstraintError, match="provider_listing"):
            work.provider_listings.add(ProviderListing("eodhd", hynix, "660"))


@pytest.mark.parametrize(
    ("provider_code", "listing_id", "symbol"),
    [
        pytest.param("nobody", None, "000660", id="a provider that does not exist"),
        pytest.param("eodhd", 999, "000660", id="a listing that does not exist"),
        pytest.param("eodhd", None, "", id="no symbol"),
        pytest.param("eodhd", None, " 000660", id="a padded symbol"),
    ],
)
def test_add_refuses_a_row_the_schema_does_not_allow(
    listed: tuple[Database, int, int], provider_code: str, listing_id: int | None, symbol: str
) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    database, hynix, _ = listed
    row = ProviderListing(
        provider_code=provider_code,
        listing_id=hynix if listing_id is None else listing_id,
        provider_symbol=symbol,
    )

    with database.unit_of_work() as work, pytest.raises(ConstraintError, match="provider_listing"):
        work.provider_listings.add(row)


# --- How a provider addresses a listing --------------------------------------------------------


def test_an_address_is_the_providers_exchange_code_and_its_symbol(
    listed: tuple[Database, int, int],
) -> None:
    """The exchange part comes from the exchange the listing trades on (ADR 0002)."""
    database, hynix, berkshire = listed

    with database.unit_of_work() as work:
        work.provider_exchanges.add(ProviderExchange("eodhd", "XKRX", "KO"))
        work.provider_exchanges.add(ProviderExchange("eodhd", "XNYS", "US"))
        work.provider_listings.add(ProviderListing("eodhd", berkshire, "BRK-B"))
        work.provider_listings.add(ProviderListing("eodhd", hynix, "000660"))

    with database.unit_of_work() as work:
        assert work.provider_listings.addresses_of_provider("eodhd") == (
            ProviderListingAddress("eodhd", hynix, "KO", "000660"),
            ProviderListingAddress("eodhd", berkshire, "US", "BRK-B"),
        )


def test_addresses_leave_other_providers_out(listed: tuple[Database, int, int]) -> None:
    """Each provider has its own code for an exchange and its own symbol."""
    database, hynix, _ = listed

    with database.unit_of_work() as work:
        work.provider_exchanges.add(ProviderExchange("eodhd", "XKRX", "KO"))
        work.provider_exchanges.add(ProviderExchange("other", "XKRX", "KS"))
        work.provider_listings.add(ProviderListing("eodhd", hynix, "000660"))
        work.provider_listings.add(ProviderListing("other", hynix, "HYNIX"))

    with database.unit_of_work() as work:
        assert work.provider_listings.addresses_of_provider("other") == (
            ProviderListingAddress("other", hynix, "KS", "HYNIX"),
        )


def test_a_listing_on_an_exchange_the_provider_has_no_code_for_has_no_address(
    listed: tuple[Database, int, int],
) -> None:
    """Such a symbol row is inert: the provider cannot be asked about it (ADR 0002)."""
    database, hynix, _ = listed

    with database.unit_of_work() as work:
        work.provider_listings.add(ProviderListing("eodhd", hynix, "000660"))

    with database.unit_of_work() as work:
        assert work.provider_listings.addresses_of_provider("eodhd") == ()
