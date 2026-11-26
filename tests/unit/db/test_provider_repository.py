"""Tests for ``ProviderRepository``: every statement on the ``provider`` table.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import ConstraintError, Database, Exchange, Provider, ProviderExchange

_EODHD: Provider = Provider(provider_code="eodhd", name="EODHD")


def _mapped_exchanges(database: Database, provider_code: str) -> list[str]:
    """Return the exchanges a provider has a code for; empty when the provider is not there."""
    with database.unit_of_work() as work:
        return [mapping.mic for mapping in work.provider_exchanges.of_provider(provider_code)]


def _add_new_york_code(database: Database) -> None:
    """Give the provider a code for New York, which only works if the provider exists."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        work.provider_exchanges.add(
            ProviderExchange(provider_code="eodhd", mic="XNYS", provider_exchange_code="US")
        )


def test_save_adds_a_provider(database: Database) -> None:
    """A code of the provider can be stored afterwards, which needs the provider's row."""
    with database.unit_of_work() as work:
        work.providers.save(_EODHD)

    _add_new_york_code(database)
    assert _mapped_exchanges(database, "eodhd") == ["XNYS"]


def test_a_code_of_a_provider_that_was_not_saved_is_refused(database: Database) -> None:
    """The check that makes the test above mean something."""
    with pytest.raises(ConstraintError, match="provider_exchange"):
        _add_new_york_code(database)


def test_save_corrects_the_name_and_keeps_what_points_at_the_provider(database: Database) -> None:
    """Saving again is an update in place, so the provider's codes stay."""
    with database.unit_of_work() as work:
        work.providers.save(_EODHD)
    _add_new_york_code(database)

    with database.unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EOD Historical Data"))

    assert _mapped_exchanges(database, "eodhd") == ["XNYS"]


@pytest.mark.parametrize(
    "provider",
    [
        pytest.param(Provider(provider_code="EODHD", name="EODHD"), id="upper-case code"),
        pytest.param(Provider(provider_code="9eod", name="EODHD"), id="code starting with a digit"),
        pytest.param(Provider(provider_code="eodhd", name=""), id="no name"),
    ],
)
def test_save_refuses_a_value_of_the_wrong_shape(database: Database, provider: Provider) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    with database.unit_of_work() as work, pytest.raises(ConstraintError, match="provider"):
        work.providers.save(provider)
