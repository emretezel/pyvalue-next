"""Tests for ``ExchangeRepository``: every statement on the ``exchange`` table.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import ConstraintError, Database, Exchange, Provider, ProviderExchange

_NEW_YORK: Exchange = Exchange(mic="XNYS", name="New York Stock Exchange", country="US")
_LONDON: Exchange = Exchange(mic="XLON", name="London Stock Exchange", country="GB")


def test_all_is_empty_on_a_new_database(database: Database) -> None:
    """A migrated database holds no exchange."""
    with database.unit_of_work() as work:
        assert work.exchanges.all() == ()


def test_save_adds_an_exchange_and_all_reads_it_back(database: Database) -> None:
    """Every column survives the round trip."""
    with database.unit_of_work() as work:
        work.exchanges.save(_NEW_YORK)

    with database.unit_of_work() as work:
        assert work.exchanges.all() == (_NEW_YORK,)


def test_all_orders_the_exchanges_by_market_code(database: Database) -> None:
    """The order does not depend on which exchange was saved first."""
    with database.unit_of_work() as work:
        work.exchanges.save(_NEW_YORK)
        work.exchanges.save(_LONDON)

    with database.unit_of_work() as work:
        assert work.exchanges.all() == (_LONDON, _NEW_YORK)


def test_save_corrects_the_name_and_country_of_an_exchange_that_is_there(
    database: Database,
) -> None:
    """The row is updated in place: there is still one exchange with that code."""
    corrected = Exchange(mic="XNYS", name="NYSE", country="CA")
    with database.unit_of_work() as work:
        work.exchanges.save(_NEW_YORK)
        work.exchanges.save(corrected)

    with database.unit_of_work() as work:
        assert work.exchanges.all() == (corrected,)


def test_save_keeps_what_points_at_the_exchange(database: Database) -> None:
    """Deleting and adding the row again would be refused; correcting it is not."""
    with database.unit_of_work() as work:
        work.exchanges.save(_NEW_YORK)
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        work.provider_exchanges.add(
            ProviderExchange(provider_code="eodhd", mic="XNYS", provider_exchange_code="US")
        )
        work.exchanges.save(Exchange(mic="XNYS", name="NYSE", country="US"))

    with database.unit_of_work() as work:
        assert [mapping.mic for mapping in work.provider_exchanges.of_provider("eodhd")] == ["XNYS"]


@pytest.mark.parametrize(
    "exchange",
    [
        pytest.param(Exchange(mic="xnys", name="New York", country="US"), id="lower-case code"),
        pytest.param(Exchange(mic="XNYS", name="", country="US"), id="no name"),
        pytest.param(
            Exchange(mic="XNYS", name="New York", country="USA"), id="three-letter country"
        ),
    ],
)
def test_save_refuses_a_value_of_the_wrong_shape(database: Database, exchange: Exchange) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    with database.unit_of_work() as work, pytest.raises(ConstraintError, match="exchange"):
        work.exchanges.save(exchange)
