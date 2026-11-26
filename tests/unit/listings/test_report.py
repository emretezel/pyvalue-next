"""Tests for ``pyvalue.listings.report``: the file of securities for the agent (ADR 0026).

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.db import ProviderSymbol
from pyvalue.listings import ListingsError
from pyvalue.listings.report import CASES_FOR_AGENT_FILE, case_rows, write_cases
from pyvalue.listings.rule import Case, HeldLine, Line, MatchedBy, Reason, Security, ShownLine

_HEADER: str = (
    "isin,company,reason,detail,trading_countries,fund_tickers,fund_currencies,matched_by,"
    "provider_code,provider_exchange_code,provider_symbol,mic,provider_name,provider_currency,"
    "provider_isin"
)

_MAYBANK: Security = Security(
    instrument_id=1,
    isin="MYL1155OO000",
    company="Malayan Banking Bhd",
    held=(HeldLine(True, "MY", "MYR", "MAYBANK", "MYL1155OO000"),),
)
# Held in two markets, with two tickers, by lines given in this order.
_ENERGY_FUELS: Security = Security(
    instrument_id=2,
    isin="CA2926717083",
    company="Energy Fuels Inc/Canada",
    held=(
        HeldLine(False, "US", "USD", "UUUU", "CA2926717083"),
        HeldLine(True, "CA", "CAD", "EFR", "CA2926717083"),
    ),
)


def _line(
    code: str, symbol: str, mic: str, currency: str, isin: str | None, name: str | None
) -> Line:
    """Return one stored line of the provider."""
    return Line(
        stored=ProviderSymbol(
            provider_code="eodhd",
            provider_exchange_code=code,
            provider_symbol=symbol,
            mic=mic,
            provider_name=name,
            provider_currency=currency,
            isin=isin,
        ),
        country="GB",
        currency="GBP",
    )


def test_a_case_has_one_row_per_line_it_could_be() -> None:
    """Each row repeats the security and names one line the way a decision does."""
    with_isin = _line("KLSE", "1155", "XKLS", "MYR", "MYL1155OO000", "Malayan Banking Bhd")
    by_ticker = _line("KLSE", "MAYBANK", "XKLS", "MYR", None, None)
    case = Case(
        _MAYBANK,
        Reason.TICKER_DIFFERS,
        "",
        (ShownLine(with_isin, MatchedBy.ISIN), ShownLine(by_ticker, MatchedBy.TICKER)),
    )

    about = ("MYL1155OO000", "Malayan Banking Bhd", "ticker_differs", "", "MY", "MAYBANK", "MYR")
    assert case_rows([case]) == [
        (
            *about,
            "isin",
            "eodhd",
            "KLSE",
            "1155",
            "XKLS",
            "Malayan Banking Bhd",
            "MYR",
            "MYL1155OO000",
        ),
        (*about, "ticker", "eodhd", "KLSE", "MAYBANK", "XKLS", "", "MYR", ""),
    ]


def test_a_case_without_a_line_still_has_its_row() -> None:
    """The agent decides ``none``, or finds out why the provider does not list it."""
    case = Case(_MAYBANK, Reason.NOTHING_FOUND, "", ())

    assert case_rows([case]) == [
        ("MYL1155OO000", "Malayan Banking Bhd", "nothing_found", "", "MY", "MAYBANK", "MYR")
        + ("",) * 8
    ]


def test_several_values_share_a_cell() -> None:
    """Countries and currencies in order; tickers in the order the funds give them."""
    case = Case(_ENERGY_FUELS, Reason.SEVERAL_HOME_MARKETS, "", ())

    (row,) = case_rows([case])

    assert row[4:7] == ("CA|US", "UUUU|EFR", "CAD|USD")


def test_the_detail_and_the_providers_own_currency_code_are_written_as_they_are() -> None:
    """A line in pence shows ``GBX``: the report says what the provider says."""
    line = _line("LSE", "RS1", "XLON", "GBX", "GB0003096442", "RS GROUP PLC")
    case = Case(
        _MAYBANK,
        Reason.DECISION_LINE_NOT_ALLOWED,
        "eodhd LSE RS1",
        (ShownLine(line, MatchedBy.ISIN_AND_TICKER),),
    )

    (row,) = case_rows([case])

    assert row[2:4] == ("decision_line_not_allowed", "eodhd LSE RS1")
    assert row[7:] == (
        "isin and ticker",
        "eodhd",
        "LSE",
        "RS1",
        "XLON",
        "RS GROUP PLC",
        "GBX",
        "GB0003096442",
    )


def test_the_file_is_the_header_and_the_rows(tmp_path: Path) -> None:
    """Written where the folder says, under a fixed name."""
    case = Case(_MAYBANK, Reason.NOTHING_FOUND, "", ())

    path = write_cases([case], tmp_path / "listings")

    assert path == tmp_path / "listings" / CASES_FOR_AGENT_FILE
    assert path.read_text(encoding="utf-8") == (
        f"{_HEADER}\nMYL1155OO000,Malayan Banking Bhd,nothing_found,,MY,MAYBANK,MYR,,,,,,,,\n"
    )


def test_a_run_with_nothing_to_report_writes_the_header_only(tmp_path: Path) -> None:
    """An empty report is a file that says so, not a missing file."""
    path = write_cases([], tmp_path)

    assert path.read_text(encoding="utf-8") == f"{_HEADER}\n"


def test_a_report_that_cannot_be_written_is_refused(tmp_path: Path) -> None:
    """A file in the place of the folder: the message names the path."""
    blocked = tmp_path / "listings"
    blocked.write_text("not a folder", encoding="utf-8")

    with pytest.raises(ListingsError, match="cannot write"):
        write_cases([], blocked)
