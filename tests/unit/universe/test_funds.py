"""Tests for ``pyvalue.universe.funds``: the funds of ADR 0016 and their pinned filings.

Author: Emre Tezel
"""

import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import FUNDS, FilingError, FundDefinition, Scope, Sponsor
from pyvalue.universe.funds import read_pinned_filing


def test_the_two_funds_are_defined_in_the_order_of_loading() -> None:
    """ADR 0016 names the funds; ADR 0006 loads them in a fixed order, VTI first."""
    assert [fund.code for fund in FUNDS] == ["VTI", "VXUS"]
    assert [fund.series_id for fund in FUNDS] == ["S000002848", "S000002932"]


def test_each_fund_names_its_sponsor_and_its_scope() -> None:
    """The sponsor selects the adapter; the scope tells the listing rule where receipts hide."""
    assert [(fund.sponsor, fund.scope) for fund in FUNDS] == [
        (Sponsor.VANGUARD, Scope.US),
        (Sponsor.VANGUARD, Scope.NON_US),
    ]
    assert [fund.name for fund in FUNDS] == [
        "Vanguard Total Stock Market Index Fund",
        "Vanguard Total International Stock Index Fund",
    ]


def test_the_scope_values_are_the_ones_the_fund_table_accepts() -> None:
    """The ``fund`` table checks ``scope`` against exactly these two words."""
    assert [scope.value for scope in Scope] == ["US", "NON_US"]


def test_the_pins_are_the_filings_recorded_in_adr_0016() -> None:
    """Changing a pin changes the universe, so the current ones are spelled out here."""
    assert [(fund.filing_number, fund.holdings_date) for fund in FUNDS] == [
        ("0000036405-26-000480", date(2026, 6, 30)),
        ("0000736054-26-000275", date(2026, 7, 31)),
    ]


@pytest.mark.parametrize("fund", FUNDS, ids=lambda fund: str(fund.code))
def test_a_definition_has_the_shape_the_sec_uses(fund: FundDefinition) -> None:
    """A mistyped number would only show up as a failed download."""
    assert re.fullmatch(r"S[0-9]{9}", fund.series_id)
    assert re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", fund.filing_number)
    assert fund.registrant_cik > 0
    # The code is the key of the ``fund`` table: upper-case letters and digits.
    assert re.fullmatch(r"[A-Z0-9]+", fund.code)


def test_the_address_is_the_permanent_one_at_the_sec() -> None:
    """Registrant number without leading zeros, filing number without dashes."""
    fund = FundDefinition(
        code="VTI",
        name="Vanguard Total Stock Market Index Fund",
        scope=Scope.US,
        sponsor=Sponsor.VANGUARD,
        series_id="S000002848",
        registrant_cik=36405,
        filing_number="0000036405-26-000480",
        holdings_date=date(2026, 6, 30),
    )

    assert fund.filing_url == (
        "https://www.sec.gov/Archives/edgar/data/36405/000003640526000480/primary_doc.xml"
    )


def test_the_local_file_is_named_by_code_and_filing_number() -> None:
    """A newer pin gets a new file name, so an old download is never mistaken for it."""
    assert FUNDS[0].filing_file_name == "VTI_0000036405-26-000480.xml"
    assert len({fund.filing_file_name for fund in FUNDS}) == 2


def test_a_file_that_is_the_pinned_filing_is_read(filings_dir: Path) -> None:
    """The sample filings carry the series ids and dates of the pins."""
    vti, vxus = FUNDS

    assert len(read_pinned_filing(filings_dir / vti.filing_file_name, vti)) == 7
    assert len(read_pinned_filing(filings_dir / vxus.filing_file_name, vxus)) == 24


def test_a_file_of_another_fund_is_refused(filings_dir: Path) -> None:
    """A filing saved under the wrong name must not be loaded as that fund."""
    vti, vxus = FUNDS
    shutil.copyfile(filings_dir / vxus.filing_file_name, filings_dir / vti.filing_file_name)

    with pytest.raises(
        FilingError, match="is not the pinned VTI filing: it states fund S000002932"
    ):
        read_pinned_filing(filings_dir / vti.filing_file_name, vti)


def test_a_file_for_another_holdings_date_is_refused(filings_dir: Path) -> None:
    """An older or newer filing of the right fund is still not the pinned one."""
    vti = FUNDS[0]
    path = filings_dir / vti.filing_file_name
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
        read_pinned_filing(path, FUNDS[0])
