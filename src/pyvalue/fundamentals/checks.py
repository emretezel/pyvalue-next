"""The checks of the statements load, and the record of what they find (ADR 0030).

Each check is a small pure function that answers one question about one
figure, one row or one company. Which check runs on what, and in which
order, is decided in ``pyvalue.fundamentals.statements``.

Every check has one outcome, fixed here: the row is left out, one figure is
left empty, or the row is stored with a warning. A check leaves something
out only when its verdict is certain. A check whose verdict is not yet known
to be reliable is a warning, until a later record makes it stricter.

Author: Emre Tezel
"""

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType

from pyvalue.providers.statements import Figure, Statement


class Outcome(Enum):
    """What a finding did to the stored statements."""

    LEFT_OUT = "left_out"
    FIGURE_LEFT_EMPTY = "figure_left_empty"
    WARNING = "warning"


class Check(Enum):
    """One check of ADR 0030. The value is its name in the report."""

    # Left out.
    PAYLOAD_NOT_READABLE = "payload_not_readable"
    OFF_CHAIN = "off_chain"
    LENGTH_NOT_PROVEN = "length_not_proven"
    CURRENCIES_DIFFER = "currencies_differ"
    NO_CURRENCY = "no_currency"
    SCALE_OUTLIER = "scale_outlier"
    NO_FIGURE = "no_figure"
    # Figure left empty.
    IMPOSSIBLE_NEGATIVE = "impossible_negative"
    ABSURD_VALUE = "absurd_value"
    PLACEHOLDER_CAPEX = "placeholder_capex"
    ZERO_INTEREST_WITH_DEBT = "zero_interest_with_debt"
    # Warning.
    GROSS_PROFIT_MISMATCH = "gross_profit_mismatch"
    BALANCE_SIDES_DIFFER = "balance_sides_differ"
    SCALE_STEP = "scale_step"
    CURRENCY_CHANGED = "currency_changed"
    SUB_UNIT_LABEL = "sub_unit_label"
    STALE_PAYLOAD = "stale_payload"
    OTHER_ISIN = "other_isin"
    PAYLOADS_DISAGREE = "payloads_disagree"
    NO_PAYLOAD = "no_payload"
    NO_FISCAL_YEAR = "no_fiscal_year"


_LEFT_OUT: frozenset[Check] = frozenset(
    {
        Check.PAYLOAD_NOT_READABLE,
        Check.OFF_CHAIN,
        Check.LENGTH_NOT_PROVEN,
        Check.CURRENCIES_DIFFER,
        Check.NO_CURRENCY,
        Check.SCALE_OUTLIER,
        Check.NO_FIGURE,
    }
)
_FIGURE_LEFT_EMPTY: frozenset[Check] = frozenset(
    {
        Check.IMPOSSIBLE_NEGATIVE,
        Check.ABSURD_VALUE,
        Check.PLACEHOLDER_CAPEX,
        Check.ZERO_INTEREST_WITH_DEBT,
    }
)

# The outcome of every check.
OUTCOME_OF: Mapping[Check, Outcome] = MappingProxyType(
    {
        check: (
            Outcome.LEFT_OUT
            if check in _LEFT_OUT
            else Outcome.FIGURE_LEFT_EMPTY
            if check in _FIGURE_LEFT_EMPTY
            else Outcome.WARNING
        )
        for check in Check
    }
)

# The figures that cannot be below zero. A provider writes capital
# expenditure, dividends and interest as positive amounts going out, so a
# negative one is an error of sign or of scale, never a fact. The schema has
# the same list as constraints (ADR 0029), and a test holds the two together:
# a row the schema refused would stop the whole load.
NOT_NEGATIVE: frozenset[Figure] = frozenset(
    {
        Figure.COST_OF_REVENUE,
        Figure.INTEREST_EXPENSE,
        Figure.CAPITAL_EXPENDITURE,
        Figure.DEPRECIATION_AMORTIZATION,
        Figure.DIVIDENDS_PAID,
        Figure.TOTAL_LIABILITIES,
        Figure.CASH,
        Figure.SHORT_TERM_INVESTMENTS,
        Figure.CASH_AND_SHORT_TERM_INVESTMENTS,
        Figure.SHORT_TERM_DEBT,
        Figure.LONG_TERM_DEBT,
        Figure.TOTAL_DEBT_STATED,
        Figure.LEASE_OBLIGATIONS,
        Figure.CURRENT_ASSETS,
        Figure.CURRENT_LIABILITIES,
        Figure.NONCURRENT_LIABILITIES,
    }
)

# The figures that must be above zero: a company has assets and shares.
ABOVE_ZERO: frozenset[Figure] = frozenset({Figure.TOTAL_ASSETS, Figure.SHARES_OUTSTANDING})

# A value this large, either way, is a provider's artefact: 10^17 is a
# hundred times the largest total in any currency of the payloads.
ABSURD: int = 10**17

# A change of this factor or more between two years is a change of unit.
SCALE_FACTOR: int = 50

# The smallest neighbour a scale check compares with. Tiny figures of a
# company without revenue jump for real.
SCALE_FLOOR: int = 1_000_000

# How far apart two figures that should agree may be, as a share of the
# larger one: 1%.
TOLERANCE_PERCENT: int = 1

# A payload whose latest year is older than this, against the latest year of
# any company in the load, is stale.
STALE_MONTHS: int = 18

# The figures that tell whether a balance sheet shows debt.
_DEBT: tuple[Figure, ...] = (
    Figure.SHORT_TERM_DEBT,
    Figure.LONG_TERM_DEBT,
    Figure.TOTAL_DEBT_STATED,
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem the load met.

    Attributes:
        isin: The security whose payload the finding is about.
        check: The check that made it.
        statement: The statement, or ``None`` when the finding is about a
            whole period, payload or company.
        period_end: The period, or ``None`` when the finding is about a
            whole payload or company.
        figure: The figure, or ``None`` when the finding is not about one.
        detail: The values that made the check fire, in words.
    """

    isin: str
    check: Check
    statement: Statement | None = None
    period_end: date | None = None
    figure: Figure | None = None
    detail: str = ""

    @property
    def outcome(self) -> Outcome:
        """What the finding did to the stored statements."""
        return OUTCOME_OF[self.check]


def is_impossible(figure: Figure, amount: int) -> bool:
    """Say whether a figure's amount cannot be true.

    Args:
        figure: The figure.
        amount: Its amount, rounded to a whole unit.
    """
    if figure in ABOVE_ZERO:
        return amount <= 0
    return figure in NOT_NEGATIVE and amount < 0


def is_absurd(amount: int) -> bool:
    """Say whether an amount is too large, either way, to be a figure."""
    return abs(amount) >= ABSURD


def is_placeholder_capex(figures: Mapping[Figure, int]) -> bool:
    """Say whether a cash-flow row's zero capital expenditure is a placeholder.

    EODHD fills a cash-flow row it has almost nothing for with a zero for
    capital expenditure. With no operating cash flow beside it, that zero
    says nothing (the legacy project measured it on 2,300 listings).
    """
    return (
        figures.get(Figure.CAPITAL_EXPENDITURE) == 0
        and figures.get(Figure.OPERATING_CASH_FLOW) is None
    )


def is_zero_interest_with_debt(
    income: Mapping[Figure, int], balance_sheet: Mapping[Figure, int]
) -> bool:
    """Say whether a zero interest expense sits beside debt on the same date.

    With debt on the balance sheet, a zero is more likely a figure that was
    not reported than free borrowing, and a metric would read it as
    unlimited interest cover.

    Args:
        income: The income statement's figures.
        balance_sheet: The figures of the balance sheet of the same date, or
            an empty mapping when there is none.
    """
    return income.get(Figure.INTEREST_EXPENSE) == 0 and any(
        balance_sheet.get(each, 0) > 0 for each in _DEBT
    )


def _apart(one: int, other: int) -> bool:
    """Say whether two positive amounts differ by the scale factor or more."""
    return one >= other * SCALE_FACTOR or other >= one * SCALE_FACTOR


def is_scale_outlier(before: int | None, value: int | None, after: int | None) -> bool:
    """Say whether a year's figure is off in scale from both its neighbours.

    It is when the figure is at least ``SCALE_FACTOR`` times larger or
    smaller than the year before and the year after, while those two are
    within that factor of each other. The three are in the same currency;
    the caller sees to that.

    Args:
        before: The figure of the year before, or ``None``.
        value: The figure of the year.
        after: The figure of the year after, or ``None``.
    """
    if before is None or value is None or after is None:
        return False
    if min(before, after) < SCALE_FLOOR or value <= 0:
        return False
    return _apart(value, before) and _apart(value, after) and not _apart(before, after)


def is_scale_step(before: int | None, value: int | None) -> bool:
    """Say whether a figure moved by the scale factor or more from the year before.

    Both years must be at least ``SCALE_FLOOR``, in the same currency.

    Args:
        before: The figure of the year before, or ``None``.
        value: The figure of the year.
    """
    if before is None or value is None:
        return False
    return min(before, value) >= SCALE_FLOOR and _apart(before, value)


def differ(one: int, other: int) -> bool:
    """Say whether two amounts that should agree differ by more than the tolerance.

    The tolerance is a share of the larger amount, and at least one unit,
    so two zeros, or a rounding of the provider's decimals, never differ.
    """
    allowed = max(abs(one), abs(other)) * TOLERANCE_PERCENT // 100
    return abs(one - other) > max(allowed, 1)


def gross_profit_mismatch(figures: Mapping[Figure, int]) -> bool:
    """Say whether revenue minus cost of revenue differs from gross profit.

    Only a row that has all three can be compared. The tolerance is a share
    of revenue.
    """
    revenue = figures.get(Figure.REVENUE)
    cost = figures.get(Figure.COST_OF_REVENUE)
    gross = figures.get(Figure.GROSS_PROFIT)
    if revenue is None or cost is None or gross is None:
        return False
    allowed = abs(revenue) * TOLERANCE_PERCENT // 100
    return abs(revenue - cost - gross) > max(allowed, 1)


def balance_sides_differ(total_assets: int | None, liabilities_and_equity: int | None) -> bool:
    """Say whether the two sides of a balance sheet differ.

    The provider's own total of liabilities and equity is compared, not the
    sum of the two: minority interest is often not broken out, and the sum
    misses it (ADR 0030).
    """
    if total_assets is None or liabilities_and_equity is None:
        return False
    return differ(total_assets, liabilities_and_equity)


def _months_before(day: date, months: int) -> date:
    """Return the same day ``months`` calendar months earlier, or that month's last day."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def is_stale(latest: date, reference: date) -> bool:
    """Say whether a company's latest fiscal year is old against the load's newest.

    The load measures against the data, never against today's date, so the
    same payloads always give the same report.

    Args:
        latest: The end of the company's latest fiscal year.
        reference: The end of the latest fiscal year of any company in the
            load.
    """
    return latest < _months_before(reference, STALE_MONTHS)
