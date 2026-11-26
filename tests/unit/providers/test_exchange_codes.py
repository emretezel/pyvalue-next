"""Tests for ``pyvalue.providers.exchange_codes``: a provider's exchange file.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.providers import (
    ExchangeCode,
    ExchangeCodes,
    ProviderError,
    VenueStatus,
    packaged_exchange_codes,
    read_exchange_codes,
)

_HEADER: str = "provider_exchange_code,provider_venue,mic\n"

# A file with every kind of row: a code on one exchange, a code told apart by
# label (with one label left out), and a code left out as a whole.
_SAMPLE: str = _HEADER + (
    "KO,,XKRX\nUS,NYSE,XNYS\nUS,NASDAQ,XNAS\nUS,NYSE ARCA,XNYS\nUS,PINK,\nF,,\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    """Write an exchange file into the temporary folder and return its path."""
    path = tmp_path / "sample_exchange.csv"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def codes(tmp_path: Path) -> ExchangeCodes:
    """Return the sample file, read."""
    return read_exchange_codes(_write(tmp_path, _SAMPLE))


def test_a_file_is_read_row_by_row(codes: ExchangeCodes) -> None:
    """An empty label and an empty market are read as absent, not as empty text."""
    assert codes.rows == (
        ExchangeCode(provider_exchange_code="KO", provider_venue=None, mic="XKRX"),
        ExchangeCode(provider_exchange_code="US", provider_venue="NYSE", mic="XNYS"),
        ExchangeCode(provider_exchange_code="US", provider_venue="NASDAQ", mic="XNAS"),
        ExchangeCode(provider_exchange_code="US", provider_venue="NYSE ARCA", mic="XNYS"),
        ExchangeCode(provider_exchange_code="US", provider_venue="PINK", mic=None),
        ExchangeCode(provider_exchange_code="F", provider_venue=None, mic=None),
    )


def test_the_codes_with_a_market_are_the_lists_to_fetch(codes: ExchangeCodes) -> None:
    """Each once, in file order; a code that is left out is not among them."""
    assert codes.codes_with_a_market() == ("KO", "US")


def test_the_codes_left_out_are_those_without_any_market(codes: ExchangeCodes) -> None:
    """A code with one label left out still has a market."""
    assert codes.codes_left_out() == frozenset({"F"})


def test_a_code_whose_labels_are_all_left_out_is_left_out(tmp_path: Path) -> None:
    """It has no exchange of ours, so its list is not fetched."""
    codes = read_exchange_codes(_write(tmp_path, _HEADER + "OTC,PINK,\nOTC,GREY,\nKO,,XKRX\n"))

    assert codes.codes_with_a_market() == ("KO",)
    assert codes.codes_left_out() == frozenset({"OTC"})


def test_each_pair_of_exchange_and_code_is_one_mapping(codes: ExchangeCodes) -> None:
    """Two labels of one code on the same exchange are one row of ``provider_exchange``."""
    assert codes.markets() == (("XKRX", "KO"), ("XNYS", "US"), ("XNAS", "US"))


@pytest.mark.parametrize(
    ("code", "venue", "expected"),
    [
        pytest.param("KO", "KO", "XKRX", id="a code on one exchange"),
        pytest.param("KO", None, "XKRX", id="a code on one exchange, line without a label"),
        pytest.param("KO", "ANYTHING", "XKRX", id="a code on one exchange, any label"),
        pytest.param("US", "NYSE", "XNYS", id="a label"),
        pytest.param("US", "NYSE ARCA", "XNYS", id="a second label for the same exchange"),
        pytest.param("US", "NASDAQ", "XNAS", id="a label for another exchange"),
        pytest.param("US", "PINK", VenueStatus.LEFT_OUT, id="a label left out on purpose"),
        pytest.param("US", "BATS", VenueStatus.UNKNOWN, id="a label the file does not have"),
        pytest.param("US", "nyse", VenueStatus.UNKNOWN, id="a label in another spelling"),
        pytest.param("US", None, VenueStatus.UNKNOWN, id="no label under a code with labels"),
    ],
)
def test_the_market_of_a_line(
    codes: ExchangeCodes, code: str, venue: str | None, expected: str | VenueStatus
) -> None:
    """The code and the label together say which exchange of ours a line is on."""
    assert codes.market_of(code, venue) == expected


@pytest.mark.parametrize("code", ["F", "ZZ"], ids=["a code left out", "a code not in the file"])
def test_asking_for_a_code_without_a_market_is_a_mistake(codes: ExchangeCodes, code: str) -> None:
    """Its list is never fetched, so no line of it should ever be asked about."""
    with pytest.raises(ProviderError, match=f"the exchange code {code} has no exchange"):
        codes.market_of(code, "NYSE")


def test_a_file_with_only_the_header_maps_nothing(tmp_path: Path) -> None:
    """Before the first row, the file is its header."""
    codes = read_exchange_codes(_write(tmp_path, _HEADER))

    assert codes.rows == ()
    assert codes.codes_with_a_market() == ()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(
            "", "the first row must be provider_exchange_code,provider_venue,mic", id="empty"
        ),
        pytest.param(
            _HEADER + "KO,XKRX\n", "row 2 has 2 cells where 3 are expected", id="a cell missing"
        ),
        pytest.param(
            _HEADER + ",,XKRX\n", "row 2: the exchange code must be filled in", id="no code"
        ),
        pytest.param(
            _HEADER + " KO,,XKRX\n", "row 2: the exchange code must be filled in", id="padded code"
        ),
        pytest.param(
            _HEADER + "US, NYSE,XNYS\n",
            "row 2: the venue label ' NYSE' has spaces around it",
            id="padded label",
        ),
        pytest.param(
            _HEADER + "KO,,xkrx\n", "row 2: 'xkrx' is not a market code", id="lower-case market"
        ),
        pytest.param(
            _HEADER + "KO,,XKR\n", "row 2: 'XKR' is not a market code", id="three-letter market"
        ),
        pytest.param(
            _HEADER + "US,NYSE,XNYS\nUS,NYSE,XNAS\n",
            "row 3: US already has this row, at .* row 2",
            id="a label twice",
        ),
        pytest.param(
            _HEADER + "F,,\nF,,\n", "row 3: F already has this row", id="a left-out code twice"
        ),
        pytest.param(
            _HEADER + "US,,XNYS\nUS,NASDAQ,XNAS\n",
            "row 3: US has a row without a venue label and a row with one",
            id="a row without a label, then one with",
        ),
        pytest.param(
            _HEADER + "US,NASDAQ,XNAS\nUS,,\n",
            "row 3: US has a row without a venue label and a row with one",
            id="a row with a label, then one without",
        ),
        pytest.param(
            _HEADER + "KO,,XKRX\nKQ,,XKRX\n",
            "row 3: the exchange XKRX already has the code KO",
            id="two codes for one exchange",
        ),
    ],
)
def test_a_wrong_file_is_refused_with_the_row(tmp_path: Path, content: str, message: str) -> None:
    """A file has no constraints of its own, so the reader checks every row."""
    with pytest.raises(ProviderError, match=message):
        read_exchange_codes(_write(tmp_path, content))


def test_a_missing_file_is_reported_as_the_exchange_codes_file(tmp_path: Path) -> None:
    """The message says which kind of file could not be read."""
    with pytest.raises(ProviderError, match="cannot read the exchange codes file"):
        read_exchange_codes(tmp_path / "missing.csv")


# --- The shipped file --------------------------------------------------------------------------


def test_the_shipped_eodhd_file_is_valid() -> None:
    """Reading it runs every check above on the real rows."""
    codes = packaged_exchange_codes("eodhd_exchange.csv")

    assert len(codes.rows) > 50


def test_the_shipped_file_maps_the_us_code_by_label() -> None:
    """EODHD's ``US`` covers several exchanges; the label on a line picks one (ADR 0018)."""
    codes = packaged_exchange_codes("eodhd_exchange.csv")

    assert codes.market_of("US", "NYSE") == "XNYS"
    assert codes.market_of("US", "NASDAQ") == "XNAS"
    # NYSE American and NYSE Arca are segments of New York (ADR 0001).
    assert codes.market_of("US", "AMEX") == "XNYS"
    assert codes.market_of("US", "NYSE ARCA") == "XNYS"
    assert codes.market_of("US", "BATS") == "XCBO"


@pytest.mark.parametrize(
    "label", ["PINK", "OTCQB", "OTCQX", "OTCGREY", "OTCCE", "OTCMKTS", "OTCBB"]
)
def test_the_shipped_file_leaves_us_over_the_counter_lines_out(label: str) -> None:
    """Decided by the author on 2026-11-26 (ADR 0024)."""
    assert (
        packaged_exchange_codes("eodhd_exchange.csv").market_of("US", label) is VenueStatus.LEFT_OUT
    )


def test_the_shipped_file_leaves_out_what_was_decided() -> None:
    """Germany's regional exchanges (ADR 0018) and the lists that are not stock exchanges."""
    left_out = packaged_exchange_codes("eodhd_exchange.csv").codes_left_out()

    assert {"F", "STU", "MU", "DU", "HM", "HA"} <= left_out
    assert {"CC", "FOREX", "GBOND", "MONEY", "EUFUND"} <= left_out


def test_the_shipped_file_keeps_the_two_korean_markets_apart() -> None:
    """KOSDAQ is a listing market of its own (ADR 0001), and only Xetra is German."""
    codes = packaged_exchange_codes("eodhd_exchange.csv")

    assert codes.market_of("KO", None) == "XKRX"
    assert codes.market_of("KQ", None) == "XKOS"
    assert codes.market_of("XETRA", None) == "XETR"
