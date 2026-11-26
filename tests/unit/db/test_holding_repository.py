"""Tests for ``HoldingRepository``: every statement on the ``holding`` table.

Author: Emre Tezel
"""

from dataclasses import replace
from datetime import date

import pytest

from pyvalue.db import ConstraintError, Database, Fund, Holding, UnitOfWork

# Made-up ISINs with correct check digits.
_ISIN: str = "US00000A0014"
_SECOND_ISIN: str = "GB00000D0016"
_RECEIPT_ISIN: str = "US00000A0022"

_VTI: Fund = Fund(
    fund_code="VTI",
    name="Vanguard Total Stock Market Index Fund",
    scope="US",
    sec_series_id="S000002848",
    sec_filing_number="0000036405-26-000480",
    holdings_date=date(2026, 6, 30),
    sponsor_file_date=date(2026, 10, 31),
)
_VXUS: Fund = Fund(
    fund_code="VXUS",
    name="Vanguard Total International Stock Index Fund",
    scope="NON_US",
    sec_series_id="S000002932",
    sec_filing_number="0000736054-26-000275",
    holdings_date=date(2026, 7, 31),
    sponsor_file_date=date(2026, 10, 31),
)

# A loaded line that carries every optional value.
_FULL: Holding = Holding(
    fund_code="VTI",
    line_number=1,
    instrument_id=1,
    isin=_ISIN,
    issuer_name="ALPHA CORP",
    title="ALPHA CORP COM",
    lei="5493000C01ZX7D35SD85",
    cusip="00000A001",
    sedol="B000001",
    ticker="ALPH",
    asset_category="EC",
    asset_category_label=None,
    issuer_type="CORP",
    trading_country="US",
    currency="USD",
)
# A loaded line that carries none of them.
_BARE: Holding = Holding(
    fund_code="VXUS",
    line_number=2,
    instrument_id=2,
    isin=_SECOND_ISIN,
    issuer_name="DELTA PLC",
    title=None,
    lei=None,
    cusip=None,
    sedol=None,
    ticker=None,
    asset_category="EP",
    asset_category_label=None,
    issuer_type="CORP",
    trading_country="GB",
    currency="GBP",
)
# A receipt read as its ordinary share: it points at the share's instrument and
# keeps the ISIN and the label its fund filed.
_RECEIPT: Holding = Holding(
    fund_code="VXUS",
    line_number=1,
    instrument_id=2,
    isin=_RECEIPT_ISIN,
    issuer_name="DELTA PLC",
    title="DELTA PLC ADR",
    lei=None,
    cusip=None,
    sedol=None,
    ticker=None,
    asset_category="OTHER",
    asset_category_label="ADR",
    issuer_type="CORP",
    trading_country="US",
    currency="USD",
)


def _seed(work: UnitOfWork) -> None:
    """Add the two funds and the two instruments the lines above point at."""
    alpha = work.companies.add("Alpha Corp", None)
    delta = work.companies.add("Delta PLC", None)
    work.instruments.add(alpha.company_id, _ISIN)
    work.instruments.add(delta.company_id, _SECOND_ISIN)
    work.funds.save(_VTI)
    work.funds.save(_VXUS)


def test_all_is_empty_on_a_new_database(database: Database) -> None:
    """A migrated database holds no holding line."""
    with database.unit_of_work() as work:
        assert work.holdings.all() == ()


def test_add_stores_every_column_of_a_line(database: Database) -> None:
    """A line reads back as it was stored, with every optional value."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_FULL)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_FULL,)


def test_an_empty_value_reads_back_as_none(database: Database) -> None:
    """A missing title, identifier or ticker is an empty column, not an empty text."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_BARE)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_BARE,)


def test_a_line_keeps_the_isin_and_the_label_its_fund_filed(database: Database) -> None:
    """The filed ISIN may differ from the instrument's: a receipt read as its ordinary share."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_RECEIPT)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_RECEIPT,)
        instrument = work.instruments.all()[1]
    assert (instrument.instrument_id, instrument.isin) == (2, _SECOND_ISIN)


def test_all_orders_the_lines_by_fund_and_then_by_position(database: Database) -> None:
    """The order is the order of the filings, whatever order the rows were added in."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_BARE)
        work.holdings.add(_RECEIPT)
        work.holdings.add(_FULL)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_FULL, _RECEIPT, _BARE)


def test_two_lines_may_point_at_one_instrument(database: Database) -> None:
    """A security held by both funds, or on two lines of one, is one instrument."""
    second = replace(_FULL, fund_code="VXUS", line_number=7)
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_FULL)
        work.holdings.add(second)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_FULL, second)


def test_remove_of_fund_removes_that_funds_lines_only(database: Database) -> None:
    """Replacing one fund's copy of its filing leaves the other fund's alone."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_FULL)
        work.holdings.add(_RECEIPT)
        work.holdings.add(_BARE)

        work.holdings.remove_of_fund("VXUS")

    with database.unit_of_work() as work:
        assert work.holdings.all() == (_FULL,)
        # The fund itself and the instruments stay.
        assert work.funds.all() == (_VTI, _VXUS)
        assert len(work.instruments.all()) == 2


def test_remove_of_fund_accepts_a_fund_without_lines(database: Database) -> None:
    """The first load of a fund has nothing to replace."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.remove_of_fund("VTI")
        work.holdings.remove_of_fund("NOT_A_FUND")

        assert work.holdings.all() == ()


def test_lines_can_be_added_again_after_they_were_removed(database: Database) -> None:
    """Remove and add in one unit of work is how a fund's lines are replaced."""
    changed = replace(_FULL, ticker="ALPHA")
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_FULL)

    with database.unit_of_work() as work:
        work.holdings.remove_of_fund("VTI")
        work.holdings.add(changed)

    with database.unit_of_work() as work:
        assert work.holdings.all() == (changed,)


def test_add_refuses_a_fund_that_does_not_exist(database: Database) -> None:
    """A line always belongs to a fund that is there."""
    with database.unit_of_work() as work:
        _seed(work)

        with pytest.raises(ConstraintError, match="FOREIGN KEY constraint failed"):
            work.holdings.add(replace(_FULL, fund_code="VT"))

        assert work.holdings.all() == ()


def test_add_refuses_an_instrument_that_does_not_exist(database: Database) -> None:
    """A loaded line points at an instrument that is there."""
    with database.unit_of_work() as work:
        _seed(work)

        with pytest.raises(ConstraintError, match="FOREIGN KEY constraint failed"):
            work.holdings.add(replace(_FULL, instrument_id=99))


def test_add_refuses_a_second_line_with_the_same_number(database: Database) -> None:
    """A fund and a position name one line of one filing."""
    with database.unit_of_work() as work:
        _seed(work)
        work.holdings.add(_FULL)

        with pytest.raises(
            ConstraintError,
            match="UNIQUE constraint failed: holding.fund_code, holding.line_number",
        ):
            work.holdings.add(replace(_BARE, fund_code="VTI", line_number=1))


@pytest.mark.parametrize(
    "holding",
    [
        pytest.param(replace(_FULL, isin="N/A"), id="placeholder ISIN"),
        pytest.param(replace(_FULL, lei="N/A"), id="placeholder identifier"),
        pytest.param(replace(_FULL, cusip="N/A"), id="placeholder CUSIP"),
        pytest.param(replace(_FULL, sedol="B0001"), id="short SEDOL"),
        pytest.param(replace(_FULL, ticker=""), id="empty ticker"),
        pytest.param(replace(_FULL, title=""), id="empty title"),
        pytest.param(replace(_FULL, asset_category="DBT"), id="debt category"),
        pytest.param(replace(_FULL, asset_category_label="ADR"), id="label without OTHER"),
        pytest.param(replace(_FULL, issuer_type="corp"), id="lower-case issuer type"),
        pytest.param(replace(_FULL, trading_country="USA"), id="three-letter country"),
        pytest.param(replace(_FULL, currency="US"), id="two-letter currency"),
        pytest.param(replace(_FULL, line_number=0), id="line zero"),
    ],
)
def test_add_refuses_a_line_that_breaks_a_rule(database: Database, holding: Holding) -> None:
    """The schema's check reaches the caller as pyvalue's own error."""
    with database.unit_of_work() as work:
        _seed(work)

        with pytest.raises(ConstraintError, match="the holding table refused a row"):
            work.holdings.add(holding)

        assert work.holdings.all() == ()
