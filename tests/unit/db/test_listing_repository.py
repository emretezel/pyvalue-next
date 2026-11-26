"""Tests for ``ListingRepository``: every statement on ``listing``.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import ConstraintError, Database, Exchange, Listing

_HYNIX_ISIN: str = "KR7000660001"
_BERKSHIRE_ISIN: str = "US0846707026"


@pytest.fixture
def referenced(database: Database) -> tuple[Database, int, int]:
    """Return a database with two exchanges and two securities, and the securities' ids."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XKRX", name="Korea Exchange", country="KR"))
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        hynix = work.instruments.add(
            work.companies.add("SK Hynix Inc", None).company_id, _HYNIX_ISIN
        )
        berkshire = work.instruments.add(
            work.companies.add("Berkshire Hathaway Inc", None).company_id, _BERKSHIRE_ISIN
        )
    return database, hynix.instrument_id, berkshire.instrument_id


def test_a_new_database_has_no_listing(referenced: tuple[Database, int, int]) -> None:
    """A security has no listing until the rule or a decision gives it one."""
    database, _, _ = referenced

    with database.unit_of_work() as work:
        assert work.listings.all() == ()


def test_add_returns_the_new_row_and_all_reads_it_back(
    referenced: tuple[Database, int, int],
) -> None:
    """Every column survives the round trip, with the id the database gave."""
    database, hynix, _ = referenced

    with database.unit_of_work() as work:
        added = work.listings.add(hynix, "XKRX", "000660", "KRW")

    assert added == Listing(
        listing_id=added.listing_id,
        instrument_id=hynix,
        mic="XKRX",
        ticker="000660",
        currency="KRW",
    )
    with database.unit_of_work() as work:
        assert work.listings.all() == (added,)


def test_all_returns_the_listings_in_the_order_they_were_added(
    referenced: tuple[Database, int, int],
) -> None:
    """The order does not depend on the exchange or the ticker."""
    database, hynix, berkshire = referenced

    with database.unit_of_work() as work:
        first = work.listings.add(berkshire, "XNYS", "BRK.B", "USD")
        second = work.listings.add(hynix, "XKRX", "000660", "KRW")

    with database.unit_of_work() as work:
        assert work.listings.all() == (first, second)


def test_a_security_has_at_most_one_listing(referenced: tuple[Database, int, int]) -> None:
    """A listing is the primary line; there is no second one (ADR 0003)."""
    database, hynix, _ = referenced

    with database.unit_of_work() as work:
        work.listings.add(hynix, "XKRX", "000660", "KRW")
        with pytest.raises(ConstraintError, match="listing"):
            work.listings.add(hynix, "XNYS", "HXSCL", "USD")


def test_an_exchange_and_ticker_belong_to_one_listing(
    referenced: tuple[Database, int, int],
) -> None:
    """Two securities cannot both be the same ticker on the same exchange."""
    database, hynix, berkshire = referenced

    with database.unit_of_work() as work:
        work.listings.add(hynix, "XKRX", "000660", "KRW")
        with pytest.raises(ConstraintError, match="listing"):
            work.listings.add(berkshire, "XKRX", "000660", "KRW")


@pytest.mark.parametrize(
    ("mic", "ticker", "currency"),
    [
        pytest.param("XXXX", "000660", "KRW", id="an exchange that does not exist"),
        pytest.param("XKRX", "", "KRW", id="no ticker"),
        pytest.param("XKRX", "abc", "KRW", id="a ticker in small letters"),
        pytest.param("XKRX", " 000660", "KRW", id="a padded ticker"),
        pytest.param("XKRX", "000660", "krw", id="a currency in small letters"),
        pytest.param("XKRX", "000660", "Unknown", id="a currency that is not a code"),
    ],
)
def test_add_refuses_a_row_the_schema_does_not_allow(
    referenced: tuple[Database, int, int], mic: str, ticker: str, currency: str
) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    database, hynix, _ = referenced

    with database.unit_of_work() as work, pytest.raises(ConstraintError, match="listing"):
        work.listings.add(hynix, mic, ticker, currency)


def test_add_refuses_a_security_that_does_not_exist(
    referenced: tuple[Database, int, int],
) -> None:
    """A listing always belongs to an instrument."""
    database, _, _ = referenced

    with database.unit_of_work() as work, pytest.raises(ConstraintError, match="listing"):
        work.listings.add(999, "XKRX", "000660", "KRW")
