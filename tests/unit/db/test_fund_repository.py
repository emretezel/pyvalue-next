"""Tests for ``FundRepository``: every statement on the ``fund`` table.

Author: Emre Tezel
"""

from dataclasses import replace
from datetime import date

import pytest

from pyvalue.db import ConstraintError, Database, Fund, Holding

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
    sponsor_file_date=None,
)

# A made-up ISIN with a correct check digit.
_ISIN: str = "US00000A0014"


def test_all_is_empty_on_a_new_database(database: Database) -> None:
    """A migrated database holds no fund."""
    with database.unit_of_work() as work:
        assert work.funds.all() == ()


def test_save_adds_a_fund_and_all_reads_it_back(database: Database) -> None:
    """Every column survives the round trip, the dates as dates."""
    with database.unit_of_work() as work:
        work.funds.save(_VTI)

    with database.unit_of_work() as work:
        assert work.funds.all() == (_VTI,)


def test_a_fund_without_a_sponsor_file_keeps_that_date_empty(database: Database) -> None:
    """No sponsor file is a valid state, stored as an empty column."""
    with database.unit_of_work() as work:
        work.funds.save(_VXUS)

    with database.unit_of_work() as work:
        assert work.funds.all() == (_VXUS,)


def test_all_orders_the_funds_by_code(database: Database) -> None:
    """The order does not depend on which fund was saved first."""
    with database.unit_of_work() as work:
        work.funds.save(_VXUS)
        work.funds.save(_VTI)

    with database.unit_of_work() as work:
        assert work.funds.all() == (_VTI, _VXUS)


def test_save_brings_an_existing_fund_up_to_date(database: Database) -> None:
    """A newer filing changes the fund's row; it does not add a second one."""
    newer = replace(
        _VTI,
        sec_filing_number="0000036405-26-000611",
        holdings_date=date(2026, 9, 30),
        sponsor_file_date=None,
    )
    with database.unit_of_work() as work:
        work.funds.save(_VTI)
        work.funds.save(newer)

    with database.unit_of_work() as work:
        assert work.funds.all() == (newer,)


def test_save_updates_a_fund_whose_holding_lines_point_at_it(database: Database) -> None:
    """The row is changed in place, so the lines that point at it never lose their fund."""
    line = Holding(
        fund_code="VTI",
        line_number=1,
        instrument_id=1,
        isin=_ISIN,
        issuer_name="ALPHA CORP",
        title=None,
        lei=None,
        cusip=None,
        sedol=None,
        ticker=None,
        asset_category="EC",
        trading_country="US",
        currency="USD",
    )
    renamed = replace(_VTI, name="Vanguard Total Stock Market ETF")
    with database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", None)
        work.instruments.add(company.company_id, _ISIN)
        work.funds.save(_VTI)
        work.holdings.add(line)
        work.funds.save(renamed)

    with database.unit_of_work() as work:
        assert work.funds.all() == (renamed,)
        assert work.holdings.all() == (line,)


def test_save_twice_with_the_same_values_changes_nothing(database: Database) -> None:
    """Loading the same filing again leaves the fund as it was."""
    with database.unit_of_work() as work:
        work.funds.save(_VTI)
        work.funds.save(_VTI)

    with database.unit_of_work() as work:
        assert work.funds.all() == (_VTI,)


@pytest.mark.parametrize(
    "fund",
    [
        pytest.param(replace(_VTI, fund_code="vti"), id="lower-case code"),
        pytest.param(replace(_VTI, name=""), id="empty name"),
        pytest.param(replace(_VTI, scope="WORLD"), id="unknown scope"),
        pytest.param(replace(_VTI, sec_series_id="2848"), id="series id of the wrong shape"),
        pytest.param(replace(_VTI, sec_filing_number="480"), id="filing number of the wrong shape"),
    ],
)
def test_save_refuses_a_value_of_the_wrong_shape(database: Database, fund: Fund) -> None:
    """The schema's check reaches the caller as pyvalue's own error."""
    with database.unit_of_work() as work:
        with pytest.raises(ConstraintError, match="the fund table refused a row"):
            work.funds.save(fund)

        assert work.funds.all() == ()


def test_save_refuses_a_second_fund_for_one_sec_series(database: Database) -> None:
    """One SEC series is one fund, whatever code it is given."""
    with database.unit_of_work() as work:
        work.funds.save(_VTI)

        with pytest.raises(ConstraintError, match="UNIQUE constraint failed: fund.sec_series_id"):
            work.funds.save(
                replace(_VTI, fund_code="VTSAX", sec_filing_number="0000036405-26-000999")
            )


def test_save_refuses_one_filing_loaded_as_two_funds(database: Database) -> None:
    """A filing states the holdings of one fund."""
    with database.unit_of_work() as work:
        work.funds.save(_VTI)

        with pytest.raises(
            ConstraintError, match="UNIQUE constraint failed: fund.sec_filing_number"
        ):
            work.funds.save(replace(_VXUS, sec_filing_number=_VTI.sec_filing_number))
