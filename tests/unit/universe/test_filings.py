"""Tests for ``pyvalue.universe.filings``: the pinned filings of ADR 0009.

Author: Emre Tezel
"""

import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import PINNED_FILINGS, FilingError, PinnedFiling
from pyvalue.universe.filings import read_pinned_filing


def test_the_three_funds_are_pinned_in_the_order_of_loading() -> None:
    """ADR 0004 names the funds; ADR 0006 fixes the order VTI, VXUS, DFAX."""
    assert [pinned.ticker for pinned in PINNED_FILINGS] == ["VTI", "VXUS", "DFAX"]
    assert [pinned.series_id for pinned in PINNED_FILINGS] == [
        "S000002848",
        "S000002932",
        "S000070905",
    ]


def test_the_pins_are_the_filings_recorded_in_adr_0004() -> None:
    """Changing a pin changes the universe, so the current ones are spelled out here."""
    assert [(pinned.filing_number, pinned.holdings_date) for pinned in PINNED_FILINGS] == [
        ("0000036405-26-000480", date(2026, 6, 30)),
        ("0000736054-26-000275", date(2026, 7, 31)),
        ("0001004726-26-009205", date(2026, 7, 31)),
    ]


@pytest.mark.parametrize("pinned", PINNED_FILINGS, ids=lambda pinned: str(pinned.ticker))
def test_a_pin_has_the_shape_the_sec_uses(pinned: PinnedFiling) -> None:
    """A mistyped number would only show up as a failed download."""
    assert re.fullmatch(r"S[0-9]{9}", pinned.series_id)
    assert re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", pinned.filing_number)
    assert pinned.registrant_cik > 0


def test_the_address_is_the_permanent_one_at_the_sec() -> None:
    """Registrant number without leading zeros, filing number without dashes."""
    pinned = PinnedFiling(
        ticker="VTI",
        series_id="S000002848",
        registrant_cik=36405,
        filing_number="0000036405-26-000480",
        holdings_date=date(2026, 6, 30),
    )

    assert pinned.url == (
        "https://www.sec.gov/Archives/edgar/data/36405/000003640526000480/primary_doc.xml"
    )


def test_the_local_file_is_named_by_ticker_and_filing_number() -> None:
    """A newer pin gets a new file name, so an old download is never mistaken for it."""
    assert PINNED_FILINGS[0].file_name == "VTI_0000036405-26-000480.xml"
    assert len({pinned.file_name for pinned in PINNED_FILINGS}) == 3


def test_a_file_that_is_the_pinned_filing_is_read(filings_dir: Path) -> None:
    """The sample filings carry the series ids and dates of the pins."""
    vti, vxus, dfax = PINNED_FILINGS

    assert len(read_pinned_filing(filings_dir / vti.file_name, vti)) == 7
    assert len(read_pinned_filing(filings_dir / vxus.file_name, vxus)) == 10
    assert len(read_pinned_filing(filings_dir / dfax.file_name, dfax)) == 14


def test_a_file_of_another_fund_is_refused(filings_dir: Path) -> None:
    """A filing saved under the wrong name must not be loaded as that fund."""
    vti, vxus, _ = PINNED_FILINGS
    shutil.copyfile(filings_dir / vxus.file_name, filings_dir / vti.file_name)

    with pytest.raises(
        FilingError, match="is not the pinned VTI filing: it states fund S000002932"
    ):
        read_pinned_filing(filings_dir / vti.file_name, vti)


def test_a_file_for_another_holdings_date_is_refused(filings_dir: Path) -> None:
    """An older or newer filing of the right fund is still not the pinned one."""
    vti = PINNED_FILINGS[0]
    path = filings_dir / vti.file_name
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "<repPdDate>2026-06-30</repPdDate>", "<repPdDate>2026-03-31</repPdDate>"
        ),
        encoding="utf-8",
    )

    with pytest.raises(FilingError, match="holdings date 2026-03-31, where .* 2026-06-30"):
        read_pinned_filing(path, vti)


def test_a_file_that_is_no_filing_is_refused(tmp_path: Path) -> None:
    """The reader's own refusal passes through unchanged."""
    path = tmp_path / "page.xml"
    path.write_text("<html><body>Not found</body></html>", encoding="utf-8")

    with pytest.raises(FilingError, match="is not an N-PORT filing"):
        read_pinned_filing(path, PINNED_FILINGS[0])
