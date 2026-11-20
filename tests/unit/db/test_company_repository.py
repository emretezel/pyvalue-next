"""Tests for ``CompanyRepository``: every statement on the ``company`` table.

Author: Emre Tezel
"""

import pytest

from pyvalue.db import Company, ConstraintError, Database, DatabaseError

# Made-up identifiers with correct check digits.
_LEI: str = "549300ALPHA000000003"
_OTHER_LEI: str = "549300DELTA000000010"


def test_all_is_empty_on_a_new_database(database: Database) -> None:
    """A migrated database holds no company."""
    with database.unit_of_work() as work:
        assert work.companies.all() == ()


def test_add_returns_the_row_with_its_id(database: Database) -> None:
    """The caller gets the id the database chose, without a second query."""
    with database.unit_of_work() as work:
        first = work.companies.add("Alpha Corp", _LEI)
        second = work.companies.add("Beta Inc", None)

    assert first == Company(company_id=1, name="Alpha Corp", lei=_LEI)
    assert second == Company(company_id=2, name="Beta Inc", lei=None)


def test_all_returns_the_rows_in_the_order_they_were_added(database: Database) -> None:
    """The order is fixed, so a load that reads it behaves the same every run."""
    with database.unit_of_work() as work:
        work.companies.add("Gamma Ltd", None)
        work.companies.add("Alpha Corp", _LEI)
        work.companies.add("Beta Inc", None)

    with database.unit_of_work() as work:
        assert work.companies.all() == (
            Company(company_id=1, name="Gamma Ltd", lei=None),
            Company(company_id=2, name="Alpha Corp", lei=_LEI),
            Company(company_id=3, name="Beta Inc", lei=None),
        )


def test_two_companies_may_share_a_name(database: Database) -> None:
    """A name is not unique: two legal entities can be called the same."""
    with database.unit_of_work() as work:
        work.companies.add("Alpha Corp", None)
        work.companies.add("Alpha Corp", None)

        assert len(work.companies.all()) == 2


def test_set_lei_fills_in_the_identifier(database: Database) -> None:
    """A company loaded without an identifier can be given one later."""
    with database.unit_of_work() as work:
        company = work.companies.add("Alpha Corp", None)
        work.companies.set_lei(company.company_id, _LEI)

        assert work.companies.all() == (Company(company_id=1, name="Alpha Corp", lei=_LEI),)


def test_set_lei_refuses_an_identifier_another_company_has(database: Database) -> None:
    """The identifier is unique across companies."""
    with database.unit_of_work() as work:
        work.companies.add("Alpha Corp", _LEI)
        other = work.companies.add("Beta Inc", None)

        with pytest.raises(ConstraintError, match="UNIQUE constraint failed: company.lei"):
            work.companies.set_lei(other.company_id, _LEI)


def test_set_lei_refuses_a_company_that_does_not_exist(database: Database) -> None:
    """An update that matches no row is an error, not a silent success."""
    with database.unit_of_work() as work:
        work.companies.add("Alpha Corp", None)

        with pytest.raises(DatabaseError, match="there is no company with id 99"):
            work.companies.set_lei(99, _LEI)


@pytest.mark.parametrize(
    ("name", "lei"),
    [
        pytest.param("", None, id="empty name"),
        pytest.param(" Alpha Corp", None, id="name with a leading space"),
        pytest.param("Alpha Corp ", None, id="name with a trailing space"),
        pytest.param("Alpha Corp", "N/A", id="identifier that is a placeholder"),
        pytest.param("Alpha Corp", _LEI[:19], id="identifier one character short"),
        pytest.param("Alpha Corp", _LEI.lower(), id="identifier in lower case"),
        pytest.param("Alpha Corp", "", id="empty identifier"),
    ],
)
def test_add_refuses_a_row_of_the_wrong_shape(
    database: Database, name: str, lei: str | None
) -> None:
    """The schema's checks reach the caller as pyvalue's own error."""
    with database.unit_of_work() as work:
        with pytest.raises(ConstraintError, match="the company table refused a row"):
            work.companies.add(name, lei)

        assert work.companies.all() == ()


def test_add_refuses_a_repeated_identifier(database: Database) -> None:
    """Two companies cannot carry the same legal-entity identifier."""
    with database.unit_of_work() as work:
        work.companies.add("Alpha Corp", _LEI)
        work.companies.add("Delta PLC", _OTHER_LEI)

        with pytest.raises(ConstraintError, match="UNIQUE constraint failed: company.lei"):
            work.companies.add("Alpha Corporation", _LEI)
