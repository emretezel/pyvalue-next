"""Tests for ``pyvalue.fundamentals.fiscal_years``: which dates are fiscal years.

The named cases are the shapes found in the saved payloads (ADR 0029).

Author: Emre Tezel
"""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from pyvalue.fundamentals.fiscal_years import WINDOW_YEARS, FiscalYear, fiscal_years


def _days(*texts: str) -> list[date]:
    """Return the dates written as ``YYYY-MM-DD``."""
    return [date.fromisoformat(text) for text in texts]


def _ends(years: tuple[FiscalYear, ...]) -> list[str]:
    """Return the ends of the years as text, for a readable comparison."""
    return [year.period_end.isoformat() for year in years]


def test_years_a_year_apart_are_all_fiscal_years_and_all_but_the_oldest_proven() -> None:
    """The common case: nothing before the oldest year proves its length."""
    found = fiscal_years(_days("2023-12-31", "2025-12-31", "2024-12-31"))

    assert found.years == (
        FiscalYear(date(2023, 12, 31), proven=False),
        FiscalYear(date(2024, 12, 31), proven=True),
        FiscalYear(date(2025, 12, 31), proven=True),
    )
    assert found.off_chain == ()


def test_only_the_latest_years_are_kept_and_the_oldest_kept_is_proven_by_the_one_before() -> None:
    """Of twenty years, twelve. The year before the oldest still proves it."""
    dates = [date(2005 + offset, 6, 30) for offset in range(20)]

    found = fiscal_years(dates)

    assert len(found.years) == WINDOW_YEARS
    assert found.years[0] == FiscalYear(date(2013, 6, 30), proven=True)
    assert found.years[-1].period_end == date(2024, 6, 30)
    assert found.off_chain == ()


def test_after_a_change_of_year_end_the_old_series_is_followed_and_the_short_year_not_proven() -> (
    None
):
    """A year end moved from June to December: the six months to December are not a year."""
    found = fiscal_years(_days("2023-06-30", "2024-06-30", "2024-12-31", "2025-12-31"))

    assert found.years == (
        FiscalYear(date(2023, 6, 30), proven=False),
        FiscalYear(date(2024, 6, 30), proven=True),
        FiscalYear(date(2024, 12, 31), proven=False),
        FiscalYear(date(2025, 12, 31), proven=True),
    )


def test_two_interleaved_series_keep_the_one_of_the_latest_date() -> None:
    """The provider kept rows for both year ends (Vulcan Energy): the other is off the chain."""
    found = fiscal_years(
        _days(
            "2017-12-31",
            "2018-06-30",
            "2018-12-31",
            "2019-06-30",
            "2019-12-31",
            "2020-06-30",
            "2020-12-31",
        )
    )

    assert _ends(found.years) == ["2017-12-31", "2018-12-31", "2019-12-31", "2020-12-31"]
    assert all(year.proven for year in found.years[1:])
    assert found.off_chain == tuple(_days("2018-06-30", "2019-06-30", "2020-06-30"))


def test_of_two_rows_a_day_apart_the_one_nearest_a_year_back_is_the_year() -> None:
    """As in Trainline's payload: 2024-02-29 is 365 days before 2025-02-28, 2024-02-28 is 366."""
    found = fiscal_years(_days("2023-02-28", "2024-02-28", "2024-02-29", "2025-02-28"))

    assert _ends(found.years) == ["2023-02-28", "2024-02-29", "2025-02-28"]
    assert found.off_chain == (date(2024, 2, 28),)


def test_a_second_row_days_before_an_unproven_year_is_not_a_year_of_its_own() -> None:
    """Without a year before, the walk skips a date less than three months back."""
    found = fiscal_years(_days("2024-12-25", "2024-12-31", "2025-12-31"))

    assert found.years == (
        FiscalYear(date(2024, 12, 31), proven=False),
        FiscalYear(date(2025, 12, 31), proven=True),
    )
    assert found.off_chain == ()


def test_a_short_period_of_a_quarter_is_still_a_period() -> None:
    """A year end moved by three months leaves a three-month period, which is kept unproven."""
    found = fiscal_years(_days("2023-09-30", "2024-09-30", "2024-12-31", "2025-12-31"))

    assert _ends(found.years) == ["2023-09-30", "2024-09-30", "2024-12-31", "2025-12-31"]
    assert [year.proven for year in found.years] == [False, True, False, True]


def test_of_two_dates_equally_near_a_year_back_the_later_is_taken() -> None:
    """The tie-break is fixed, so the answer never depends on the order of the rows."""
    found = fiscal_years(_days("2023-07-05", "2024-06-25", "2024-07-05", "2025-06-30"))

    assert _ends(found.years) == ["2023-07-05", "2024-07-05", "2025-06-30"]
    assert found.off_chain == (date(2024, 6, 25),)


def test_years_of_52_and_53_weeks_are_all_proven() -> None:
    """A retailer's years are 364 or 371 days long."""
    found = fiscal_years(_days("2021-01-30", "2022-01-29", "2023-01-28", "2024-02-03"))

    assert [year.proven for year in found.years] == [False, True, True, True]


def test_a_missing_year_leaves_the_year_after_it_unproven() -> None:
    """With 2023 missing, nothing says how long the row to 2024 is."""
    found = fiscal_years(_days("2021-12-31", "2022-12-31", "2024-12-31", "2025-12-31"))

    assert [(year.period_end.year, year.proven) for year in found.years] == [
        (2021, False),
        (2022, True),
        (2024, False),
        (2025, True),
    ]


def test_a_single_date_is_one_year_that_is_not_proven() -> None:
    """A company with one annual report so far."""
    assert fiscal_years(_days("2025-12-31")).years == (FiscalYear(date(2025, 12, 31), False),)


def test_no_date_gives_no_year() -> None:
    """A payload without statements."""
    assert fiscal_years([]) == fiscal_years(()) and fiscal_years([]).years == ()


def test_a_date_given_twice_is_one_year() -> None:
    """The three statements give the same dates; each counts once."""
    found = fiscal_years(_days("2025-12-31", "2025-12-31", "2024-12-31"))

    assert _ends(found.years) == ["2024-12-31", "2025-12-31"]


def test_the_window_can_be_set() -> None:
    """The choice among several payloads counts every year a payload holds."""
    dates = [date(2000 + offset, 12, 31) for offset in range(20)]

    assert len(fiscal_years(dates, window=len(dates)).years) == 20


_DATES = st.lists(st.dates(min_value=date(1990, 1, 1), max_value=date(2030, 12, 31)), max_size=40)


@given(_DATES)
def test_the_latest_date_always_ends_the_latest_year(dates: list[date]) -> None:
    """The walk starts from the newest row the payload has."""
    years = fiscal_years(dates).years

    assert (years[-1].period_end if years else None) == (max(dates) if dates else None)


@given(_DATES)
def test_years_are_in_order_at_most_twelve_and_a_proven_year_has_its_year_before(
    dates: list[date],
) -> None:
    """A proven year is 350 to 380 days after the year before it, when that is kept."""
    years = fiscal_years(dates).years

    assert len(years) <= WINDOW_YEARS
    assert list(years) == sorted(years) and len({year.period_end for year in years}) == len(years)
    for earlier, later in zip(years, years[1:], strict=False):
        if later.proven:
            assert (
                timedelta(days=350) <= later.period_end - earlier.period_end <= timedelta(days=380)
            )


@given(_DATES)
def test_every_date_in_the_window_is_a_year_or_off_the_chain_and_never_both(
    dates: list[date],
) -> None:
    """Nothing in the window is lost without being named."""
    found = fiscal_years(dates)
    if not found.years:
        return
    in_window = {each for each in dates if each >= found.years[0].period_end}
    years = {year.period_end for year in found.years}

    assert years.isdisjoint(found.off_chain)
    assert years | set(found.off_chain) == in_window


@given(_DATES)
def test_running_the_rule_on_its_own_years_gives_the_same_years(dates: list[date]) -> None:
    """The chain is stable: no other dates were needed to find it."""
    years = fiscal_years(dates).years

    again = fiscal_years(year.period_end for year in years).years

    assert [year.period_end for year in again] == [year.period_end for year in years]
