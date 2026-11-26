"""Tests for ``pyvalue.providers.eodhd``: reading EODHD's two lists.

The requests themselves are tested in ``tests/unit/test_http.py``, with the
other fetches. The sample answers are made up in the shape EODHD documents
(``tests/fixtures/eodhd``); nothing here has been seen live.

Author: Emre Tezel
"""

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import (
    EXCHANGE_FILE,
    PROVIDER_CODE,
    PROVIDER_NAME,
    SymbolLine,
    currency_of,
    parse_exchange_list,
    parse_symbol_list,
)
from pyvalue.providers.exchange_codes import packaged_exchange_codes

# A valid line, as EODHD documents it. A test changes only what it is about.
_LINE: dict[str, object] = {
    "Code": "ALFA",
    "Name": "Alpha Corp",
    "Country": "USA",
    "Exchange": "NYSE",
    "Currency": "USD",
    "Type": "Common Stock",
    "Isin": "US00000A0014",
}


def _answer(*entries: object) -> bytes:
    """Return a list answer holding the given entries."""
    return json.dumps(list(entries)).encode()


def test_the_provider_is_called_eodhd_in_our_tables() -> None:
    """The code and the name are its row in ``provider`` (ADR 0002)."""
    assert (PROVIDER_CODE, PROVIDER_NAME) == ("eodhd", "EODHD")


def test_the_exchange_file_of_the_provider_is_shipped() -> None:
    """The constant names a file that is there and valid."""
    assert packaged_exchange_codes(EXCHANGE_FILE).codes_with_a_market()


# --- The exchange list -------------------------------------------------------------------------


def test_the_exchange_list_gives_the_codes_in_order(eodhd_samples: Path) -> None:
    """Only the codes are read; our exchanges are our own reference data."""
    path = eodhd_samples / "exchanges.json"

    assert parse_exchange_list(path.read_bytes(), str(path)) == ("KO", "US", "LSE", "F", "CC", "HK")


def test_an_empty_exchange_list_has_no_codes() -> None:
    """Whether that is plausible is for the caller to judge."""
    assert parse_exchange_list(b"[]", "the answer") == ()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(b"Unauthorized", "the answer is not an EODHD exchange list", id="a text"),
        pytest.param(
            b'{"error": "x"}', "is not an EODHD exchange list: it is not a list", id="an object"
        ),
        pytest.param(b'["KO"]', "entry 1 is not an object", id="a list of texts"),
        pytest.param(_answer({"Name": "Korea"}), "entry 1 has no field Code", id="no code field"),
        pytest.param(_answer({"Code": ""}), "entry 1 has an empty Code", id="an empty code"),
        pytest.param(_answer({"Code": None}), "entry 1 has an empty Code", id="a null code"),
        pytest.param(_answer({"Code": 7}), "the field Code of entry 1 is not text", id="a number"),
        pytest.param(
            _answer({"Code": "KO"}, {"Code": "  "}), "entry 2 has an empty Code", id="a blank code"
        ),
    ],
)
def test_an_exchange_list_of_another_shape_is_refused(body: bytes, message: str) -> None:
    """An error page or a changed shape must not be read as a list of nothing."""
    with pytest.raises(ProviderError, match=message):
        parse_exchange_list(body, "the answer")


# --- A symbol list -----------------------------------------------------------------------------


def test_a_symbol_list_is_read_line_by_line(eodhd_samples: Path) -> None:
    """Every line comes back, whatever its type: nothing is judged here."""
    path = eodhd_samples / "symbols_KO.json"

    assert parse_symbol_list(path.read_bytes(), str(path)) == (
        SymbolLine(
            "000100", "Alpha Electronics Co Ltd", "KO", "KRW", "Common Stock", "KR7000100008"
        ),
        SymbolLine(
            "000105",
            "Alpha Electronics Co Ltd Pref",
            "KO",
            "KRW",
            "Preferred Stock",
            "KR7000101006",
        ),
        SymbolLine("000200", "Beta Chemical Co Ltd", "KO", "KRW", "Common Stock", None),
        SymbolLine("000300", "Gamma Index Fund", "KO", "KRW", "ETF", "KR7000300004"),
        # The ISIN is cut short. It is passed on as given; the load decides.
        SymbolLine("000400", "Delta Holdings Co Ltd", "KO", "KRW", "Common Stock", "KR7000400"),
    )


@pytest.mark.parametrize(
    ("field", "attribute"),
    [
        ("Code", "symbol"),
        ("Name", "name"),
        ("Exchange", "venue"),
        ("Currency", "currency"),
        ("Type", "kind"),
        ("Isin", "isin"),
    ],
)
@pytest.mark.parametrize("empty", [None, "", "   "], ids=["null", "empty", "blank"])
def test_a_value_the_provider_leaves_empty_is_read_as_absent(
    field: str, attribute: str, empty: str | None
) -> None:
    """Null, an empty text and a blank text all mean that nothing was given."""
    (line,) = parse_symbol_list(_answer({**_LINE, field: empty}), "the answer")

    assert getattr(line, attribute) is None


def test_spaces_around_a_value_are_dropped() -> None:
    """The table accepts no padded value, and a padded label would match no row."""
    (line,) = parse_symbol_list(
        _answer({**_LINE, "Code": " ALFA ", "Exchange": "NYSE ", "Name": " Alpha Corp"}),
        "the answer",
    )

    assert (line.symbol, line.venue, line.name) == ("ALFA", "NYSE", "Alpha Corp")


def test_fields_that_are_not_read_may_be_anything() -> None:
    """The country of a line is not used, so its value is no concern."""
    (line,) = parse_symbol_list(_answer({**_LINE, "Country": 7, "Extra": [1, 2]}), "the answer")

    assert line.symbol == "ALFA"


@pytest.mark.parametrize("field", ["Code", "Name", "Exchange", "Currency", "Type", "Isin"])
def test_a_line_that_lacks_a_field_is_not_the_shape_this_reader_knows(field: str) -> None:
    """A missing field would otherwise be read as an empty value on every line.

    That matters most for the ISIN: read from a field of another spelling, a
    whole list would silently lose the value the listing rule looks up first.
    """
    entry = {name: value for name, value in _LINE.items() if name != field}

    with pytest.raises(ProviderError, match=f"entry 1 has no field {field}"):
        parse_symbol_list(_answer(entry), "the answer")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(b"", "the answer is not an EODHD symbol list", id="nothing"),
        pytest.param(b"<html>busy</html>", "the answer is not an EODHD symbol list", id="a page"),
        pytest.param(
            b'"Unauthorized"', "is not an EODHD symbol list: it is not a list", id="a text"
        ),
        pytest.param(_answer(_LINE, "x"), "entry 2 is not an object", id="a text among the lines"),
        pytest.param(
            _answer({**_LINE, "Code": 1155}),
            "the field Code of entry 1 is not text",
            id="a symbol given as a number",
        ),
    ],
)
def test_a_symbol_list_of_another_shape_is_refused(body: bytes, message: str) -> None:
    """The message names the source and what is wrong, and quotes no content."""
    with pytest.raises(ProviderError, match=message):
        parse_symbol_list(body, "the answer")


def test_the_message_names_the_source_it_was_given() -> None:
    """A saved file is named by its path, an answer by its address without the key."""
    with pytest.raises(ProviderError, match="data/eodhd/symbols_KO.json is not an EODHD"):
        parse_symbol_list(b"{}", "data/eodhd/symbols_KO.json")


@pytest.mark.parametrize(
    ("code", "currency"),
    [
        pytest.param("GBX", "GBP", id="pence"),
        pytest.param("ZAC", "ZAR", id="South African cents"),
        pytest.param("ILA", "ILS", id="Israeli agorot"),
    ],
)
def test_a_sub_unit_is_turned_into_its_currency(code: str, currency: str) -> None:
    """A listing's currency is never a quote unit (ADR 0019)."""
    assert currency_of(code) == currency


@pytest.mark.parametrize("code", ["USD", "GBP", "KRW", "ZAR", "ILS"])
def test_a_currency_code_is_taken_as_it_is(code: str) -> None:
    """Most lines carry the currency itself."""
    assert currency_of(code) == code


@pytest.mark.parametrize("code", ["Unknown", "", "usd", "GBp", "US", "USDX", " USD", "U$D", "123"])
def test_a_code_that_cannot_be_a_currency_is_not_read(code: str) -> None:
    """Such a line can never become a listing (ADR 0026)."""
    assert currency_of(code) is None


@given(st.text(max_size=8))
def test_what_is_read_always_has_the_shape_the_listing_table_takes(code: str) -> None:
    """Three capital letters, or nothing: the schema would refuse anything else."""
    currency = currency_of(code)

    assert currency is None or (
        len(currency) == 3 and currency.isascii() and currency.isalpha() and currency.isupper()
    )


@given(st.text(max_size=8))
def test_reading_a_currency_that_was_read_changes_nothing(code: str) -> None:
    """No sub-unit maps to another sub-unit."""
    currency = currency_of(code)

    assert currency is None or currency_of(currency) == currency
