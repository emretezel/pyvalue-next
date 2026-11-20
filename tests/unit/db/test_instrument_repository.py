"""Tests for ``InstrumentRepository``: every statement on the ``instrument`` table.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import ConstraintError, Database, Instrument

# Made-up ISINs with correct check digits.
_ISIN: str = "US00000A0014"
_SECOND_ISIN: str = "US00000A0022"
_THIRD_ISIN: str = "GB00000D0016"


def test_all_is_empty_on_a_new_database(database: Database) -> None:
    """A migrated database holds no instrument."""
    with database.unit_of_work() as work:
        assert work.instruments.all() == ()


def test_add_returns_the_row_with_its_id(database: Database) -> None:
    """The caller gets the id the database chose, without a second query."""
    with database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", None)
        instrument = work.instruments.add(company.company_id, _ISIN)

    assert instrument == Instrument(instrument_id=1, company_id=1, isin=_ISIN)


def test_all_returns_the_rows_in_the_order_they_were_added(database: Database) -> None:
    """A company may have several instruments; the order is the order of loading."""
    with database.unit_of_work() as work:
        alpha = work.companies.add("Alpha Corp", None)
        delta = work.companies.add("Delta PLC", None)
        work.instruments.add(delta.company_id, _THIRD_ISIN)
        work.instruments.add(alpha.company_id, _SECOND_ISIN)
        work.instruments.add(alpha.company_id, _ISIN)

    with database.unit_of_work() as work:
        assert work.instruments.all() == (
            Instrument(instrument_id=1, company_id=2, isin=_THIRD_ISIN),
            Instrument(instrument_id=2, company_id=1, isin=_SECOND_ISIN),
            Instrument(instrument_id=3, company_id=1, isin=_ISIN),
        )


@pytest.mark.parametrize(
    "isin",
    [
        pytest.param("", id="empty"),
        pytest.param(_ISIN[:11], id="one character short"),
        pytest.param(_ISIN + "0", id="one character long"),
        pytest.param(_ISIN.lower(), id="lower case"),
        pytest.param("0S00000A0014", id="digit in the country part"),
        pytest.param("US00000A001X", id="letter where the check digit belongs"),
        pytest.param("US00000 0014", id="space inside"),
    ],
)
def test_add_refuses_an_isin_of_the_wrong_shape(database: Database, isin: str) -> None:
    """The schema's check reaches the caller as pyvalue's own error."""
    with database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", None)

        with pytest.raises(ConstraintError, match="the instrument table refused a row"):
            work.instruments.add(company.company_id, isin)

        assert work.instruments.all() == ()


def test_add_refuses_a_repeated_isin(database: Database) -> None:
    """An ISIN is one security: it cannot belong to two instruments."""
    with database.unit_of_work() as work:
        alpha = work.companies.add("Alpha Corp", None)
        delta = work.companies.add("Delta PLC", None)
        work.instruments.add(alpha.company_id, _ISIN)

        with pytest.raises(ConstraintError, match="UNIQUE constraint failed: instrument.isin"):
            work.instruments.add(delta.company_id, _ISIN)


def test_add_refuses_a_company_that_does_not_exist(database: Database) -> None:
    """An instrument always belongs to a company that is there."""
    with database.unit_of_work() as work:
        with pytest.raises(ConstraintError, match="FOREIGN KEY constraint failed"):
            work.instruments.add(1, _ISIN)

        assert work.instruments.all() == ()
