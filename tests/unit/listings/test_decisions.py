"""Tests for ``pyvalue.listings.decisions``: the listing decisions file of ADR 0019.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.listings import ListingsError
from pyvalue.listings.decisions import (
    ListingDecision,
    packaged_listing_decisions,
    read_listing_decisions,
)

_HEADER: str = (
    "isin,outcome,provider_code,provider_exchange_code,provider_symbol,"
    "company,decided_on,decided_by,evidence\n"
)

# Maybank: the fund gives a letter code, the provider a number (ADR 0019).
_MAYBANK: str = (
    "MYL1155OO000,listing,eodhd,KLSE,1155,Malayan Banking Bhd,2026-11-26,agent,Bursa code 1155\n"
)
# A Thai foreign-board share: no listing, by the author's decision (ADR 0019).
_DELTA: str = "TH0528A10Z14,none,,,,Delta Electronics (Thailand),2026-11-26,author,ADR 0019\n"


def _write(tmp_path: Path, *rows: str) -> Path:
    """Write a decisions file with the given rows and return its path."""
    path = tmp_path / "listing.csv"
    path.write_text(_HEADER + "".join(rows), encoding="utf-8")
    return path


def test_a_row_can_name_a_line_or_say_that_there_is_none(tmp_path: Path) -> None:
    """The two outcomes of ADR 0019, in the order of the file."""
    assert read_listing_decisions(_write(tmp_path, _MAYBANK, _DELTA)) == (
        ListingDecision(
            isin="MYL1155OO000",
            line=("eodhd", "KLSE", "1155"),
            company="Malayan Banking Bhd",
            decided_on=date(2026, 11, 26),
            decided_by="agent",
            evidence="Bursa code 1155",
        ),
        ListingDecision(
            isin="TH0528A10Z14",
            line=None,
            company="Delta Electronics (Thailand)",
            decided_on=date(2026, 11, 26),
            decided_by="author",
            evidence="ADR 0019",
        ),
    )


def test_a_file_with_only_the_header_decides_nothing(tmp_path: Path) -> None:
    """That is how the file starts."""
    assert read_listing_decisions(_write(tmp_path)) == ()


def test_a_symbol_is_kept_exactly_as_written(tmp_path: Path) -> None:
    """It is compared with the stored symbol letter for letter."""
    row = "US0846707026,listing,eodhd,US,BRK-B,Berkshire Hathaway Inc,2026-11-26,agent,NYSE\n"

    (decision,) = read_listing_decisions(_write(tmp_path, row))

    assert decision.line == ("eodhd", "US", "BRK-B")


@pytest.mark.parametrize(
    ("row", "message"),
    [
        pytest.param(
            "MYL1155OO001,listing,eodhd,KLSE,1155,Maybank,2026-11-26,agent,x\n",
            "is not a valid ISIN",
            id="a wrong check digit",
        ),
        pytest.param(
            "MYL1155OO000,maybe,eodhd,KLSE,1155,Maybank,2026-11-26,agent,x\n",
            "the outcome must be 'listing' or 'none', not 'maybe'",
            id="an unknown outcome",
        ),
        pytest.param(
            "MYL1155OO000,,eodhd,KLSE,1155,Maybank,2026-11-26,agent,x\n",
            "the outcome must be 'listing' or 'none'",
            id="no outcome",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,,Maybank,2026-11-26,agent,x\n",
            "must all be filled in",
            id="a listing without a symbol",
        ),
        pytest.param(
            "MYL1155OO000,listing,,KLSE,1155,Maybank,2026-11-26,agent,x\n",
            "must all be filled in",
            id="a listing without a provider",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,,1155,Maybank,2026-11-26,agent,x\n",
            "must all be filled in",
            id="a listing without an exchange code",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE, 1155,Maybank,2026-11-26,agent,x\n",
            "without spaces around them",
            id="a padded symbol",
        ),
        pytest.param(
            "TH0528A10Z14,none,eodhd,BK,DELTA,Delta,2026-11-26,author,x\n",
            "names no line",
            id="a none row that names a line",
        ),
        pytest.param(
            "TH0528A10Z14,none,,,DELTA,Delta,2026-11-26,author,x\n",
            "names no line",
            id="a none row with a symbol left in",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,1155,,2026-11-26,agent,x\n",
            "the company, who decided and the evidence",
            id="no company",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,1155,Maybank,2026-11-26,,x\n",
            "the company, who decided and the evidence",
            id="nobody decided",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,1155,Maybank,2026-11-26,agent, \n",
            "the company, who decided and the evidence",
            id="no evidence",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,1155,Maybank,26.11.2026,agent,x\n",
            "is not a date",
            id="a date in another form",
        ),
        pytest.param(
            "MYL1155OO000,listing,eodhd,KLSE,1155,Maybank,2026-11-26,agent\n",
            "has 8 cells where 9 are expected",
            id="a cell too few",
        ),
    ],
)
def test_a_bad_row_is_refused_with_where_it_is(tmp_path: Path, row: str, message: str) -> None:
    """A file has no constraints of its own, so every row is checked."""
    path = _write(tmp_path, _DELTA, row)

    with pytest.raises(ListingsError, match=message) as raised:
        read_listing_decisions(path)

    assert f"{path} row 3" in str(raised.value)


def test_a_security_decided_twice_is_refused(tmp_path: Path) -> None:
    """Two answers for one security: the file must say which one holds."""
    again = "MYL1155OO000,none,,,,Malayan Banking Bhd,2026-11-27,author,changed my mind\n"

    with pytest.raises(ListingsError, match="MYL1155OO000 was already decided in row 2"):
        read_listing_decisions(_write(tmp_path, _MAYBANK, again))


def test_a_file_with_another_header_is_refused(tmp_path: Path) -> None:
    """The eight columns of ADR 0019, without the company, are not this file."""
    path = tmp_path / "listing.csv"
    path.write_text(_HEADER.replace("company,", ""), encoding="utf-8")

    with pytest.raises(ListingsError, match="the first row must be isin,outcome,provider_code"):
        read_listing_decisions(path)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(ListingsError, match="cannot read the decisions file"):
        read_listing_decisions(tmp_path / "absent.csv")


def test_the_decisions_shipped_with_the_package_are_valid() -> None:
    """The real file is read with the same checks on every test run.

    Its first rows are the decisions of the first pass on live lists, of
    2026-11-27 (ADR 0027).
    """
    decisions = packaged_listing_decisions()

    assert len({decision.isin for decision in decisions}) == len(decisions)
