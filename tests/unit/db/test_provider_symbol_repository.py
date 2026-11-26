"""Tests for ``ProviderSymbolRepository``: every statement on ``provider_symbol``.

Author: Emre Tezel
"""

from dataclasses import replace

import pytest

from pyvalue.db import (
    ConstraintError,
    Database,
    Exchange,
    Provider,
    ProviderExchange,
    ProviderSymbol,
)

_HYNIX: ProviderSymbol = ProviderSymbol(
    provider_code="eodhd",
    provider_exchange_code="KO",
    provider_symbol="000660",
    mic="XKRX",
    provider_venue="KO",
    provider_name="SK Hynix Inc",
    provider_type="Common Stock",
    provider_currency="KRW",
    isin="KR7000660001",
)
_BERKSHIRE: ProviderSymbol = ProviderSymbol(
    provider_code="eodhd",
    provider_exchange_code="US",
    provider_symbol="BRK-B",
    mic="XNYS",
    provider_venue="NYSE",
    provider_name="Berkshire Hathaway Inc",
    provider_type="Common Stock",
    provider_currency="USD",
    isin="US0846707026",
)
# A line for which the provider gives no venue, no name and no ISIN.
_BARE: ProviderSymbol = ProviderSymbol(
    provider_code="eodhd",
    provider_exchange_code="US",
    provider_symbol="XYZ",
    mic="XNAS",
    provider_venue=None,
    provider_name=None,
    provider_type="Preferred Stock",
    provider_currency="USD",
    isin=None,
)


@pytest.fixture
def mapped(database: Database) -> Database:
    """Return a database holding the mappings the symbol lines point at."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        work.exchanges.save(Exchange(mic="XNAS", name="Nasdaq", country="US"))
        work.exchanges.save(Exchange(mic="XKRX", name="Korea Exchange", country="KR"))
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, code in (("XNYS", "US"), ("XNAS", "US"), ("XKRX", "KO")):
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )
    return database


def _count(database: Database, code: str) -> int:
    """Return how many lines are stored under one EODHD code."""
    with database.unit_of_work() as work:
        return work.provider_symbols.count_of_code("eodhd", code)


def test_a_code_has_no_lines_on_a_new_database(mapped: Database) -> None:
    """Nothing is stored until a list is loaded."""
    assert _count(mapped, "US") == 0


def test_add_stores_lines_and_they_are_counted_under_their_code(mapped: Database) -> None:
    """A line with every value and a line with only the required ones are both stored."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.add(_HYNIX)
        work.provider_symbols.add(_BERKSHIRE)
        work.provider_symbols.add(_BARE)

    assert _count(mapped, "KO") == 1
    assert _count(mapped, "US") == 2


def test_the_count_is_per_provider(mapped: Database) -> None:
    """Another provider's code of the same spelling has its own lines."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.add(_HYNIX)

    with mapped.unit_of_work() as work:
        assert work.provider_symbols.count_of_code("other", "KO") == 0


def test_remove_of_code_takes_every_line_of_that_code_and_no_other(mapped: Database) -> None:
    """A list is replaced as a whole (ADR 0018), and only that list."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.add(_HYNIX)
        work.provider_symbols.add(_BERKSHIRE)
        work.provider_symbols.add(_BARE)

    with mapped.unit_of_work() as work:
        work.provider_symbols.remove_of_code("eodhd", "US")

    assert _count(mapped, "US") == 0
    assert _count(mapped, "KO") == 1


def test_removing_the_lines_of_a_code_that_has_none_is_not_an_error(mapped: Database) -> None:
    """The first load of a list removes nothing."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.remove_of_code("eodhd", "KO")

    assert _count(mapped, "KO") == 0


def test_a_removed_list_can_be_stored_again_in_the_same_unit_of_work(mapped: Database) -> None:
    """Replacing is remove and add in one transaction."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.add(_BERKSHIRE)

    with mapped.unit_of_work() as work:
        work.provider_symbols.remove_of_code("eodhd", "US")
        work.provider_symbols.add(_BERKSHIRE)
        work.provider_symbols.add(_BARE)

    assert _count(mapped, "US") == 2


@pytest.mark.parametrize(
    "symbol",
    [
        pytest.param(replace(_BERKSHIRE, mic="XKRX"), id="an exchange the code is not mapped to"),
        pytest.param(replace(_BERKSHIRE, provider_exchange_code="ZZ"), id="an unknown code"),
        pytest.param(replace(_BERKSHIRE, provider_type="ETF"), id="not a share"),
        pytest.param(replace(_BERKSHIRE, provider_symbol=""), id="no symbol"),
        pytest.param(replace(_BERKSHIRE, provider_currency=""), id="no currency"),
        pytest.param(replace(_BERKSHIRE, isin="US084670702"), id="a malformed ISIN"),
        pytest.param(replace(_BERKSHIRE, provider_name=""), id="an empty name"),
    ],
)
def test_add_refuses_a_line_the_schema_does_not_allow(
    mapped: Database, symbol: ProviderSymbol
) -> None:
    """The schema's refusal reaches the component as pyvalue's own error."""
    with mapped.unit_of_work() as work, pytest.raises(ConstraintError, match="provider_symbol"):
        work.provider_symbols.add(symbol)


def test_a_code_has_one_line_per_symbol(mapped: Database) -> None:
    """The same symbol cannot be stored once on New York and once on Nasdaq."""
    with mapped.unit_of_work() as work:
        work.provider_symbols.add(_BERKSHIRE)
        with pytest.raises(ConstraintError, match="provider_symbol"):
            work.provider_symbols.add(replace(_BERKSHIRE, mic="XNAS", provider_venue="NASDAQ"))

    assert _count(mapped, "US") == 1
