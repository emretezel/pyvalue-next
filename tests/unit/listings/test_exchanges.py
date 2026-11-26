"""Tests for ``pyvalue.listings.exchanges``: the file of our exchanges.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.db import Database, Exchange, Provider, ProviderExchange
from pyvalue.listings import (
    ListingsError,
    packaged_exchanges,
    read_exchanges,
    require_our_exchanges,
)
from pyvalue.providers import packaged_exchange_codes, read_exchange_codes

_HEADER: str = "mic,name,country\n"
_CODES_HEADER: str = "provider_exchange_code,provider_venue,mic\n"


def _write(tmp_path: Path, text: str, name: str = "exchange.csv") -> Path:
    """Write a file into the temporary folder and return its path."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_is_read_row_by_row(tmp_path: Path) -> None:
    """The rows come back as the records the ``exchange`` table takes."""
    path = _write(tmp_path, _HEADER + "XKRX,Korea Exchange,KR\nXLON,London Stock Exchange,GB\n")

    assert read_exchanges(path) == (
        Exchange(mic="XKRX", name="Korea Exchange", country="KR"),
        Exchange(mic="XLON", name="London Stock Exchange", country="GB"),
    )


def test_a_file_with_only_the_header_has_no_exchange(tmp_path: Path) -> None:
    """Before the first row, the file is its header."""
    assert read_exchanges(_write(tmp_path, _HEADER)) == ()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "the first row must be mic,name,country", id="empty"),
        pytest.param(
            _HEADER + "XKRX,Korea Exchange\n",
            "row 2 has 2 cells where 3 are expected",
            id="a cell missing",
        ),
        pytest.param(
            _HEADER + "xkrx,Korea Exchange,KR\n",
            "row 2: 'xkrx' is not a market code",
            id="lower-case code",
        ),
        pytest.param(
            _HEADER + "XKRXX,Korea Exchange,KR\n",
            "row 2: 'XKRXX' is not a market code",
            id="five letters",
        ),
        pytest.param(_HEADER + "XKRX,,KR\n", "row 2: the name must be filled in", id="no name"),
        pytest.param(
            _HEADER + "XKRX, Korea Exchange,KR\n",
            "row 2: the name must be filled in",
            id="padded name",
        ),
        pytest.param(
            _HEADER + "XKRX,Korea Exchange,KOR\n",
            "row 2: 'KOR' is not a country code",
            id="three-letter country",
        ),
        pytest.param(
            _HEADER + "XKRX,Korea Exchange,kr\n",
            "row 2: 'kr' is not a country code",
            id="lower-case country",
        ),
        pytest.param(
            _HEADER + "XKRX,Korea Exchange,KR\nXKRX,Korea Exchange again,KR\n",
            "row 3: XKRX already has a row, at .* row 2",
            id="a market twice",
        ),
    ],
)
def test_a_wrong_file_is_refused_with_the_row(tmp_path: Path, content: str, message: str) -> None:
    """A file has no constraints of its own, so the reader checks every row."""
    with pytest.raises(ListingsError, match=message):
        read_exchanges(_write(tmp_path, content))


def test_a_missing_file_is_reported_as_the_exchanges_file(tmp_path: Path) -> None:
    """The message says which kind of file could not be read."""
    with pytest.raises(ListingsError, match="cannot read the exchanges file"):
        read_exchanges(tmp_path / "missing.csv")


def test_a_provider_file_that_names_only_our_exchanges_passes(tmp_path: Path) -> None:
    """A code that is left out names no exchange, so it needs none."""
    exchanges = read_exchanges(_write(tmp_path, _HEADER + "XKRX,Korea Exchange,KR\n"))
    codes = read_exchange_codes(_write(tmp_path, _CODES_HEADER + "KO,,XKRX\nF,,\n", "codes.csv"))

    require_our_exchanges(codes, exchanges)


def test_a_provider_file_that_names_an_exchange_we_do_not_have_is_refused(tmp_path: Path) -> None:
    """Every such exchange is named at once, in order."""
    exchanges = read_exchanges(_write(tmp_path, _HEADER + "XKRX,Korea Exchange,KR\n"))
    codes = read_exchange_codes(
        _write(tmp_path, _CODES_HEADER + "KO,,XKRX\nUS,NYSE,XNYS\nUS,NASDAQ,XNAS\n", "codes.csv")
    )

    with pytest.raises(ListingsError, match="does not have: XNAS, XNYS"):
        require_our_exchanges(codes, exchanges)


# --- The shipped files -------------------------------------------------------------------------


def test_the_shipped_file_is_valid_and_holds_the_exchanges_of_the_records() -> None:
    """The example rows of ADR 0001 and ADR 0018 are among them."""
    by_mic = {exchange.mic: exchange for exchange in packaged_exchanges()}

    assert by_mic["XNYS"] == Exchange(mic="XNYS", name="New York Stock Exchange", country="US")
    assert by_mic["XNAS"] == Exchange(mic="XNAS", name="Nasdaq", country="US")
    assert by_mic["XETR"] == Exchange(mic="XETR", name="Xetra", country="DE")
    assert by_mic["XKOS"] == Exchange(mic="XKOS", name="KOSDAQ", country="KR")


def test_only_xetra_is_a_german_exchange() -> None:
    """Decided by the author on 2026-11-26 (ADR 0018): the regional exchanges get no row."""
    german = [exchange.mic for exchange in packaged_exchanges() if exchange.country == "DE"]

    assert german == ["XETR"]


def test_the_shipped_files_agree_with_each_other() -> None:
    """Every exchange EODHD's file names is one of ours."""
    require_our_exchanges(packaged_exchange_codes("eodhd_exchange.csv"), packaged_exchanges())


def test_every_shipped_exchange_is_one_a_provider_serves() -> None:
    """A market no provider serves needs no row (ADR 0018), so none is there by mistake."""
    served = {mic for mic, _ in packaged_exchange_codes("eodhd_exchange.csv").markets()}

    assert {exchange.mic for exchange in packaged_exchanges()} == served


def test_the_database_accepts_every_shipped_row(database: Database) -> None:
    """What the reader lets through, the tables let in: exchanges, then their codes."""
    exchanges = packaged_exchanges()
    codes = packaged_exchange_codes("eodhd_exchange.csv")
    with database.unit_of_work() as work:
        for exchange in exchanges:
            work.exchanges.save(exchange)
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        for mic, code in codes.markets():
            work.provider_exchanges.add(
                ProviderExchange(provider_code="eodhd", mic=mic, provider_exchange_code=code)
            )

    with database.unit_of_work() as work:
        assert work.exchanges.all() == tuple(sorted(exchanges, key=lambda exchange: exchange.mic))
        assert len(work.provider_exchanges.of_provider("eodhd")) == len(codes.markets())
