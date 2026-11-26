"""Tests for ``ProviderExchangeRepository``: every statement on ``provider_exchange``.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import ConstraintError, Database, Exchange, Provider, ProviderExchange

_NEW_YORK: ProviderExchange = ProviderExchange(
    provider_code="eodhd", mic="XNYS", provider_exchange_code="US"
)
_NASDAQ: ProviderExchange = ProviderExchange(
    provider_code="eodhd", mic="XNAS", provider_exchange_code="US"
)
_KOREA: ProviderExchange = ProviderExchange(
    provider_code="eodhd", mic="XKRX", provider_exchange_code="KO"
)


@pytest.fixture
def referenced(database: Database) -> Database:
    """Return a database holding the exchanges and providers the mappings point at."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        work.exchanges.save(Exchange(mic="XNAS", name="Nasdaq", country="US"))
        work.exchanges.save(Exchange(mic="XKRX", name="Korea Exchange", country="KR"))
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        work.providers.save(Provider(provider_code="other", name="Another Provider"))
    return database


def test_a_provider_has_no_codes_on_a_new_database(referenced: Database) -> None:
    """Nothing is mapped until the load says so."""
    with referenced.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == ()


def test_add_stores_a_code_and_of_provider_reads_it_back(referenced: Database) -> None:
    """Every column survives the round trip."""
    with referenced.unit_of_work() as work:
        work.provider_exchanges.add(_KOREA)

    with referenced.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == (_KOREA,)


def test_two_exchanges_can_share_one_code(referenced: Database) -> None:
    """EODHD's ``US`` covers New York and Nasdaq (ADR 0002)."""
    with referenced.unit_of_work() as work:
        work.provider_exchanges.add(_NEW_YORK)
        work.provider_exchanges.add(_NASDAQ)

    with referenced.unit_of_work() as work:
        assert len(work.provider_exchanges.of_provider("eodhd")) == 2


def test_of_provider_orders_by_code_and_then_exchange(referenced: Database) -> None:
    """The order does not depend on which row was added first."""
    with referenced.unit_of_work() as work:
        work.provider_exchanges.add(_NEW_YORK)
        work.provider_exchanges.add(_KOREA)
        work.provider_exchanges.add(_NASDAQ)

    with referenced.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == (_KOREA, _NASDAQ, _NEW_YORK)


def test_of_provider_leaves_out_the_codes_of_other_providers(referenced: Database) -> None:
    """Each provider has its own codes for the same exchanges."""
    other = ProviderExchange(provider_code="other", mic="XKRX", provider_exchange_code="KRX")
    with referenced.unit_of_work() as work:
        work.provider_exchanges.add(_KOREA)
        work.provider_exchanges.add(other)

    with referenced.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == (_KOREA,)
        assert work.provider_exchanges.of_provider("other") == (other,)


@pytest.mark.parametrize(
    "mapping",
    [
        pytest.param(
            ProviderExchange(provider_code="eodhd", mic="XLON", provider_exchange_code="LSE"),
            id="an exchange that is not there",
        ),
        pytest.param(
            ProviderExchange(provider_code="nobody", mic="XKRX", provider_exchange_code="KO"),
            id="a provider that is not there",
        ),
        pytest.param(
            ProviderExchange(provider_code="eodhd", mic="XKRX", provider_exchange_code=""),
            id="no code",
        ),
    ],
)
def test_add_refuses_a_row_the_schema_does_not_allow(
    referenced: Database, mapping: ProviderExchange
) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    with (
        referenced.unit_of_work() as work,
        pytest.raises(ConstraintError, match="provider_exchange"),
    ):
        work.provider_exchanges.add(mapping)


def test_a_provider_has_one_code_for_an_exchange(referenced: Database) -> None:
    """A second code for the same exchange is refused, not stored beside the first."""
    second = ProviderExchange(provider_code="eodhd", mic="XKRX", provider_exchange_code="KQ")
    with referenced.unit_of_work() as work:
        work.provider_exchanges.add(_KOREA)
        with pytest.raises(ConstraintError, match="provider_exchange"):
            work.provider_exchanges.add(second)

    with referenced.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == (_KOREA,)
