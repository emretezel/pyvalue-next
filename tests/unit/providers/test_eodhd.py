"""Tests for ``pyvalue.providers.eodhd``: its addresses and how its answers are read.

The requests themselves are tested in ``tests/unit/test_http.py``, with the
other fetches. The sample answers are made up in the shape EODHD gives
(``tests/fixtures/eodhd``); none was downloaded.

Author: Emre Tezel
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import (
    EXCHANGE_FILE,
    FUNDAMENTALS_REQUEST_COST,
    PROVIDER_CODE,
    PROVIDER_NAME,
    Allowance,
    SymbolLine,
    account_url,
    check_fundamentals,
    currency_of,
    fundamentals_url,
    parse_allowance,
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


# --- The fundamentals of one security ------------------------------------------------------------

# The section of a payload that says what it is about. A live payload also
# carries the statements, which the download keeps and does not read.
_GENERAL: dict[str, object] = {
    "Code": "ALFA",
    "Name": "Alpha Corp",
    "Exchange": "NYSE",
    "ISIN": None,
}


def _payload(**general: object) -> bytes:
    """Return a payload whose ``General`` section has the given values changed."""
    return json.dumps({"General": {**_GENERAL, **general}, "Financials": {}}).encode()


def test_a_fundamentals_request_names_the_symbol_and_the_exchange_code() -> None:
    """EODHD names a security ``SYMBOL.EXCHANGE``, both parts its own."""
    assert fundamentals_url("US", "BRK-B") == "https://eodhd.com/api/fundamentals/BRK-B.US?fmt=json"


def test_a_symbol_cannot_change_the_address() -> None:
    """One listed symbol holds an ``&``, which would start a second query part."""
    assert (
        fundamentals_url("MX", "PE&OLES")
        == "https://eodhd.com/api/fundamentals/PE%26OLES.MX?fmt=json"
    )
    assert "/api/fundamentals/A%2FB%3Fx.US?" in fundamentals_url("US", "A/B?x")


@given(
    code=st.text(min_size=1, max_size=8),
    symbol=st.text(min_size=1, max_size=12),
)
def test_a_fundamentals_address_always_stays_under_one_path(code: str, symbol: str) -> None:
    """Whatever the two parts hold, the address has one path segment for them and one query."""
    address = fundamentals_url(code, symbol)

    prefix = "https://eodhd.com/api/fundamentals/"
    assert address.startswith(prefix)
    assert address.endswith("?fmt=json")
    middle = address[len(prefix) : -len("?fmt=json")]
    assert not set(middle) & set("/?#&= ")


def test_the_account_request_has_one_address() -> None:
    """It is the request that says what the account has used today."""
    assert account_url() == "https://eodhd.com/api/user?fmt=json"


def test_a_fundamentals_request_costs_ten_of_the_allowance() -> None:
    """Measured on 2026-11-27 (ADR 0028). The download's arithmetic rests on it."""
    assert FUNDAMENTALS_REQUEST_COST == 10


def test_a_payload_for_the_symbol_is_accepted() -> None:
    """Nothing is returned: the check only has to pass."""
    check_fundamentals(_payload(), "the answer", "ALFA")


def test_a_payload_without_statements_is_still_a_payload() -> None:
    """What a payload holds is not judged by the download (ADR 0028)."""
    check_fundamentals(json.dumps({"General": {"Code": "ALFA"}}).encode(), "the answer", "ALFA")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html>Service unavailable</html>", "the answer is not an EODHD fundamentals payload"),
        (b"[]", "it is not an object"),
        (b'"Not Found"', "it is not an object"),
        (b"{}", "it has no General section"),
        (b'{"General": "ALFA"}', "it has no General section"),
        (b'{"General": {}}', "its General.Code is None"),
        (b'{"General": {"Code": "BETA"}}', "for ALFA: its General.Code is 'BETA'"),
        (b'{"General": {"Code": "alfa"}}', "for ALFA: its General.Code is 'alfa'"),
    ],
    ids=["a page", "a list", "a text", "empty", "no section", "no code", "another", "other case"],
)
def test_an_answer_that_is_not_the_payload_of_the_symbol_is_refused(
    body: bytes, message: str
) -> None:
    """An error page, or a payload for another symbol, must never get a file."""
    with pytest.raises(ProviderError, match=message):
        check_fundamentals(body, "the answer", "ALFA")


# --- The account's allowance ---------------------------------------------------------------------

# An account answer in the shape seen live. The holder is made up; the reader
# must let nothing of the first two fields out.
_HOLDER: str = "Ada Example"
_ADDRESS: str = "ada@example.invalid"
_ACCOUNT: dict[str, object] = {
    "name": _HOLDER,
    "email": _ADDRESS,
    "subscriptionType": "monthly",
    "apiRequests": 65,
    "apiRequestsDate": "2026-11-27",
    "dailyRateLimit": 100000,
    "extraLimit": 74094,
}


def _account(**changed: object) -> bytes:
    """Return an account answer with the given fields changed; ``...`` removes one."""
    fields = {**_ACCOUNT, **changed}
    return json.dumps({name: value for name, value in fields.items() if value is not ...}).encode()


def test_the_allowance_is_three_values_of_the_account_answer() -> None:
    """The daily limit, the count and the day the count belongs to."""
    assert parse_allowance(_account(), "the answer") == Allowance(
        daily_limit=100000, used=65, counted_on=date(2026, 11, 27)
    )


def test_nothing_about_the_account_holder_leaves_the_reader() -> None:
    """The answer names a person. The allowance carries no text at all."""
    allowance = parse_allowance(_account(), "the answer")

    assert _HOLDER not in repr(allowance)
    assert _ADDRESS not in repr(allowance)
    assert {type(value) for value in (allowance.daily_limit, allowance.used)} == {int}


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"dailyRateLimit": ...}, "the field dailyRateLimit is not a count"),
        ({"dailyRateLimit": "100000"}, "the field dailyRateLimit is not a count"),
        ({"dailyRateLimit": True}, "the field dailyRateLimit is not a count"),
        ({"apiRequests": ...}, "the field apiRequests is not a count"),
        ({"apiRequests": -1}, "the field apiRequests is not a count"),
        ({"apiRequests": 6.5}, "the field apiRequests is not a count"),
        ({"apiRequestsDate": ...}, "the field apiRequestsDate is not a date"),
        ({"apiRequestsDate": "yesterday"}, "the field apiRequestsDate is not a date"),
        ({"apiRequestsDate": 20261127}, "the field apiRequestsDate is not a date"),
    ],
    ids=[
        "no limit",
        "limit as text",
        "limit as a flag",
        "no count",
        "negative count",
        "fraction",
        "no date",
        "a word for a date",
        "a number for a date",
    ],
)
def test_an_account_answer_of_another_shape_is_refused_without_quoting_it(
    changed: dict[str, object], message: str
) -> None:
    """The message names the field and never a value: the answer holds personal details."""
    with pytest.raises(ProviderError, match=message) as raised:
        parse_allowance(_account(**changed), "the answer")

    assert _HOLDER not in str(raised.value)
    assert _ADDRESS not in str(raised.value)
    assert "yesterday" not in str(raised.value)


@pytest.mark.parametrize("body", [b"Unauthenticated", b"[]", b'"text"'])
def test_an_account_answer_that_is_not_an_object_is_refused(body: bytes) -> None:
    """A refusal can arrive as plain text."""
    with pytest.raises(ProviderError, match="the answer is not an EODHD account answer"):
        parse_allowance(body, "the answer")


def test_what_was_used_today_is_taken_off_the_daily_limit() -> None:
    """The count belongs to today, so it counts."""
    allowance = Allowance(daily_limit=100000, used=265, counted_on=date(2026, 11, 27))

    assert allowance.left(date(2026, 11, 27)) == 99735


def test_a_count_from_an_earlier_day_says_nothing_about_today() -> None:
    """EODHD's counter stays as it was until the first request of a new day."""
    allowance = Allowance(daily_limit=100000, used=83355, counted_on=date(2026, 11, 27))

    assert allowance.left(date(2026, 11, 28)) == 100000


def test_a_count_dated_ahead_of_our_clock_still_counts() -> None:
    """A clock that runs behind must not hand out a second day's allowance."""
    allowance = Allowance(daily_limit=100000, used=83355, counted_on=date(2026, 11, 28))

    assert allowance.left(date(2026, 11, 27)) == 16645


def test_an_account_that_used_more_than_its_limit_has_nothing_left() -> None:
    """EODHD goes on counting once it draws on the extra reserve."""
    allowance = Allowance(daily_limit=100000, used=100420, counted_on=date(2026, 11, 27))

    assert allowance.left(date(2026, 11, 27)) == 0


@given(
    daily_limit=st.integers(min_value=0, max_value=10**7),
    used=st.integers(min_value=0, max_value=10**7),
    days_apart=st.integers(min_value=-3, max_value=3),
)
def test_what_is_left_is_never_negative_and_never_more_than_the_limit(
    daily_limit: int, used: int, days_apart: int
) -> None:
    """Whatever the account says, the answer is an amount that can be spent."""
    day = date(2026, 11, 27)
    allowance = Allowance(daily_limit=daily_limit, used=used, counted_on=day)

    assert 0 <= allowance.left(day + timedelta(days=days_apart)) <= daily_limit
