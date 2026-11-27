"""Tests for ``pyvalue.fundamentals.report``: the listings a run has no payload for.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.fundamentals import DEFAULT_REPORT_DIR, FundamentalsError
from pyvalue.fundamentals.report import NotDownloaded, write_not_downloaded

_HEADER: str = "provider_code,provider_exchange_code,provider_symbol,isin,company,reason,detail\n"


def test_the_report_is_kept_under_data() -> None:
    """Generated output, never committed."""
    assert Path("data") / "fundamentals" == DEFAULT_REPORT_DIR


def test_a_run_with_nothing_to_report_writes_the_header_only(tmp_path: Path) -> None:
    """The file always describes the latest run, also when that run left nothing out."""
    path = write_not_downloaded((), tmp_path / "fundamentals")

    assert path == tmp_path / "fundamentals" / "not_downloaded.csv"
    assert path.read_text(encoding="utf-8") == _HEADER


def test_each_listing_is_one_row_in_the_order_given(tmp_path: Path) -> None:
    """A name with a comma is quoted, so the file reads back cell for cell."""
    rows = (
        NotDownloaded("eodhd", "US", "ALPH", "US00000A0014", "Alpha Corp", "not_found", ""),
        NotDownloaded(
            "eodhd", "LSE", "DLT", "GB00000D0016", "Delta, PLC", "request_failed", "timed out"
        ),
    )

    path = write_not_downloaded(rows, tmp_path)

    assert path.read_text(encoding="utf-8") == (
        _HEADER + "eodhd,US,ALPH,US00000A0014,Alpha Corp,not_found,\n"
        'eodhd,LSE,DLT,GB00000D0016,"Delta, PLC",request_failed,timed out\n'
    )


def test_a_later_report_replaces_the_one_that_was_there(tmp_path: Path) -> None:
    """Nothing of the earlier run stays."""
    row = NotDownloaded("eodhd", "US", "ALPH", "US00000A0014", "Alpha Corp", "not_found", "")
    write_not_downloaded((row,), tmp_path)

    path = write_not_downloaded((), tmp_path)

    assert path.read_text(encoding="utf-8") == _HEADER


def test_a_report_that_cannot_be_written_is_the_components_own_error(tmp_path: Path) -> None:
    """The message names the file."""
    blocker = tmp_path / "fundamentals"
    blocker.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(FundamentalsError, match=r"cannot write .*not_downloaded\.csv"):
        write_not_downloaded((), blocker)
