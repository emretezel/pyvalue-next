"""Tests for ``pyvalue.fundamentals.checks``: each check fires, and does not fire.

The cases are the defects measured on the saved payloads (ADR 0030).

Author: Emre Tezel
"""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.fundamentals.checks import (
    ABOVE_ZERO,
    ABSURD,
    NOT_NEGATIVE,
    OUTCOME_OF,
    SCALE_FLOOR,
    Check,
    Finding,
    Outcome,
    balance_sides_differ,
    differ,
    gross_profit_mismatch,
    is_absurd,
    is_impossible,
    is_placeholder_capex,
    is_scale_outlier,
    is_scale_step,
    is_stale,
    is_zero_interest_with_debt,
)
from pyvalue.providers.statements import Figure


def test_every_check_has_the_outcome_of_adr_0030() -> None:
    """Seven leave out, four empty a figure, the rest warn."""
    by_outcome = {
        outcome: {check.value for check in Check if OUTCOME_OF[check] is outcome}
        for outcome in Outcome
    }

    assert by_outcome[Outcome.LEFT_OUT] == {
        "payload_not_readable",
        "off_chain",
        "length_not_proven",
        "currencies_differ",
        "no_currency",
        "scale_outlier",
        "no_figure",
    }
    assert by_outcome[Outcome.FIGURE_LEFT_EMPTY] == {
        "impossible_negative",
        "absurd_value",
        "placeholder_capex",
        "zero_interest_with_debt",
    }
    assert len(by_outcome[Outcome.WARNING]) == 10


def test_a_finding_knows_its_outcome() -> None:
    """The report reads it from the check."""
    assert Finding(isin="US0000000001", check=Check.SCALE_STEP).outcome is Outcome.WARNING


@pytest.mark.parametrize("figure", sorted(NOT_NEGATIVE, key=str))
def test_a_negative_figure_that_cannot_be_negative_is_impossible_and_zero_is_not(
    figure: Figure,
) -> None:
    """Negative short-term investments, debt or capex are errors of sign or scale."""
    assert is_impossible(figure, -1)
    assert not is_impossible(figure, 0)


@pytest.mark.parametrize("figure", sorted(ABOVE_ZERO, key=str))
def test_total_assets_and_the_share_count_must_be_above_zero(figure: Figure) -> None:
    """A zero share count is the provider's sentinel for no data."""
    assert is_impossible(figure, 0)
    assert not is_impossible(figure, 1)


@pytest.mark.parametrize(
    "figure",
    [
        Figure.REVENUE,
        Figure.GROSS_PROFIT,
        Figure.OPERATING_INCOME,
        Figure.PRETAX_INCOME,
        Figure.INCOME_TAX,
        Figure.NET_INCOME,
        Figure.OPERATING_CASH_FLOW,
        Figure.NET_SHARE_SALES,
        Figure.EQUITY,
        Figure.MINORITY_INTEREST,
    ],
)
def test_a_figure_that_can_be_negative_never_is_impossible(figure: Figure) -> None:
    """A loss, an outflow, negative equity or an insurer's negative revenue are facts."""
    assert not is_impossible(figure, -(10**12))


def test_the_two_lists_do_not_overlap() -> None:
    """A figure is either not negative or above zero."""
    assert NOT_NEGATIVE.isdisjoint(ABOVE_ZERO)


@pytest.mark.parametrize(
    ("amount", "absurd"), [(ABSURD, True), (-ABSURD, True), (ABSURD - 1, False)]
)
def test_an_amount_of_ten_to_the_seventeen_or_more_is_absurd(amount: int, absurd: bool) -> None:
    """One payload carries 10^18 in its cash-flow rows."""
    assert is_absurd(amount) is absurd


@pytest.mark.parametrize(
    ("figures", "placeholder"),
    [
        ({Figure.CAPITAL_EXPENDITURE: 0}, True),
        ({Figure.CAPITAL_EXPENDITURE: 0, Figure.DIVIDENDS_PAID: 5}, True),
        ({Figure.CAPITAL_EXPENDITURE: 0, Figure.OPERATING_CASH_FLOW: 10}, False),
        ({Figure.CAPITAL_EXPENDITURE: 4}, False),
        ({}, False),
    ],
)
def test_zero_capex_is_a_placeholder_only_without_operating_cash_flow(
    figures: dict[Figure, int], placeholder: bool
) -> None:
    """A company with real cash flows and no capex keeps its zero."""
    assert is_placeholder_capex(figures) is placeholder


@pytest.mark.parametrize(
    ("income", "balance_sheet", "suspect"),
    [
        ({Figure.INTEREST_EXPENSE: 0}, {Figure.LONG_TERM_DEBT: 5}, True),
        ({Figure.INTEREST_EXPENSE: 0}, {Figure.TOTAL_DEBT_STATED: 5}, True),
        ({Figure.INTEREST_EXPENSE: 0}, {Figure.SHORT_TERM_DEBT: 5}, True),
        ({Figure.INTEREST_EXPENSE: 0}, {Figure.LONG_TERM_DEBT: 0}, False),
        ({Figure.INTEREST_EXPENSE: 0}, {Figure.LONG_TERM_DEBT: -5}, False),
        ({Figure.INTEREST_EXPENSE: 0}, {}, False),
        ({Figure.INTEREST_EXPENSE: 3}, {Figure.LONG_TERM_DEBT: 5}, False),
        ({}, {Figure.LONG_TERM_DEBT: 5}, False),
    ],
)
def test_zero_interest_is_suspect_only_beside_debt(
    income: dict[Figure, int], balance_sheet: dict[Figure, int], suspect: bool
) -> None:
    """A company without debt pays no interest; one with debt does."""
    assert is_zero_interest_with_debt(income, balance_sheet) is suspect


_MILLION = SCALE_FLOOR


@pytest.mark.parametrize(
    ("before", "value", "after", "outlier"),
    [
        # KBC Ancora: total assets in units, then thousands, then units.
        (2_441_801_181, 3_098_302, 3_108_930_196, True),
        (3_815_000, 1_450, 1_501_000, True),
        (100 * _MILLION, 6_000 * _MILLION, 120 * _MILLION, True),
        # A real fall that stays down is a step, not an outlier.
        (5_000 * _MILLION, 50 * _MILLION, 60 * _MILLION, False),
        # Neighbours far apart themselves: no verdict on the middle.
        (_MILLION, 100 * _MILLION, 5_000 * _MILLION, False),
        # A neighbour below the floor: a small company's figures jump for real.
        (999_999, 1, 1_200_000, False),
        (10 * _MILLION, 0, 12 * _MILLION, False),
        (10 * _MILLION, -5, 12 * _MILLION, False),
        (None, 1, 12 * _MILLION, False),
        (10 * _MILLION, None, 12 * _MILLION, False),
        (10 * _MILLION, 1, None, False),
        # Within the factor: not an outlier.
        (10 * _MILLION, 400 * _MILLION, 12 * _MILLION, False),
    ],
)
def test_a_figure_off_in_scale_from_both_neighbours_is_an_outlier(
    before: int | None, value: int | None, after: int | None, outlier: bool
) -> None:
    """Fifty times larger or smaller than the year before and the year after."""
    assert is_scale_outlier(before, value, after) is outlier


@pytest.mark.parametrize(
    ("before", "value", "step"),
    [
        (10 * _MILLION, 500 * _MILLION, True),
        (500 * _MILLION, 10 * _MILLION, True),
        (10 * _MILLION, 499 * _MILLION, False),
        (10, 500 * _MILLION, False),
        (None, 500 * _MILLION, False),
        (10 * _MILLION, None, False),
    ],
)
def test_a_fifty_fold_step_between_two_years_of_a_million_or_more(
    before: int | None, value: int | None, step: bool
) -> None:
    """A reverse takeover or a change of unit: which one, a person decides."""
    assert is_scale_step(before, value) is step


@pytest.mark.parametrize(
    ("one", "other", "different"),
    [(100, 101, False), (100, 102, True), (0, 0, False), (0, 1, False), (0, 2, True)],
)
def test_two_amounts_differ_beyond_one_percent_of_the_larger_and_one_unit(
    one: int, other: int, different: bool
) -> None:
    """A rounding of the provider's decimals never counts."""
    assert differ(one, other) is different


@given(st.integers(min_value=-(10**16), max_value=10**16), st.integers(-(10**16), 10**16))
def test_differ_does_not_depend_on_the_order(one: int, other: int) -> None:
    """Comparing two payloads either way gives one answer."""
    assert differ(one, other) == differ(other, one)


@pytest.mark.parametrize(
    ("figures", "mismatch"),
    [
        ({Figure.REVENUE: 1000, Figure.COST_OF_REVENUE: 600, Figure.GROSS_PROFIT: 400}, False),
        ({Figure.REVENUE: 1000, Figure.COST_OF_REVENUE: 600, Figure.GROSS_PROFIT: 409}, False),
        ({Figure.REVENUE: 1000, Figure.COST_OF_REVENUE: 600, Figure.GROSS_PROFIT: 411}, True),
        ({Figure.REVENUE: 1000, Figure.GROSS_PROFIT: 100}, False),
        ({Figure.REVENUE: 0, Figure.COST_OF_REVENUE: 0, Figure.GROSS_PROFIT: 0}, False),
    ],
)
def test_gross_profit_must_be_revenue_minus_cost_within_one_percent_of_revenue(
    figures: dict[Figure, int], mismatch: bool
) -> None:
    """Only a row that has all three is compared."""
    assert gross_profit_mismatch(figures) is mismatch


@pytest.mark.parametrize(
    ("assets", "other_side", "different"),
    [(1000, 1005, False), (1000, 1020, True), (None, 1000, False), (1000, None, False)],
)
def test_the_two_sides_of_a_balance_sheet_must_agree(
    assets: int | None, other_side: int | None, different: bool
) -> None:
    """The provider's own total of liabilities and equity is the other side."""
    assert balance_sides_differ(assets, other_side) is different


@pytest.mark.parametrize(
    ("latest", "reference", "stale"),
    [
        (date(2025, 4, 29), date(2026, 10, 31), True),
        (date(2025, 4, 30), date(2026, 10, 31), False),
        (date(2025, 4, 30), date(2026, 10, 30), False),
        (date(2024, 12, 31), date(2026, 6, 30), False),
        (date(2024, 12, 29), date(2026, 6, 30), True),
        # The reference's day does not exist 18 months earlier: the month's last day is used.
        (date(2024, 2, 28), date(2025, 8, 31), True),
        (date(2024, 2, 29), date(2025, 8, 31), False),
    ],
)
def test_a_latest_year_more_than_eighteen_months_before_the_newest_in_the_load_is_stale(
    latest: date, reference: date, stale: bool
) -> None:
    """Measured against the data, never against today."""
    assert is_stale(latest, reference) is stale
