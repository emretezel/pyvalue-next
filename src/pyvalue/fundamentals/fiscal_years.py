"""Which yearly rows of a payload are a company's fiscal years (ADR 0029).

A provider's yearly list does not say how long each period is. Most of the
time the dates are a year apart and nothing needs saying. But a payload can
hold two series of dates after a company moved its year end, two rows a few
days apart, or a first annual report that covers a few months only. A metric
that read such a row as a year would be wrong without any sign of it.

So the fiscal years are worked out from the dates alone, once per company
and for all three statements together: walk back from the latest date in
steps of one year. A year whose step back finds the year before it is
**proven** to be twelve months long. A year whose step back finds nothing is
kept, because its balance sheet is a snapshot and needs no length, but its
income and cash-flow rows are not stored.

Author: Emre Tezel
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

# How many fiscal years are kept. The QARP screen reads eleven; older years
# would only be checked and reported for no reader (ADR 0029).
WINDOW_YEARS: int = 12

# The span within which a date ends the year before. A year of 52 weeks is
# 364 days and one of 53 weeks 371, so a retailer's years are found; half a
# year (about 182 days) or two years (about 730) are not.
_SHORTEST_YEAR_DAYS: int = 350
_LONGEST_YEAR_DAYS: int = 380
_YEAR_DAYS: int = 365

# A date less than this before a fiscal year is not the end of a period of
# its own: it is a second row for the same year end, a few days off. Every
# real period, the short one after a change of year end included, is about
# a quarter or longer.
_SHORTEST_PERIOD_DAYS: int = 85


@dataclass(frozen=True, slots=True, order=True)
class FiscalYear:
    """One of a company's fiscal years.

    Attributes:
        period_end: The last day of the year.
        proven: Whether the year before it was found, a year earlier. Only
            then are its income and cash-flow rows known to cover twelve
            months.
    """

    period_end: date
    proven: bool


@dataclass(frozen=True, slots=True)
class FiscalYears:
    """A company's fiscal years, and the dates that are not one.

    Attributes:
        years: The fiscal years, oldest first, at most ``WINDOW_YEARS``.
        off_chain: The dates after the oldest of those years that are not a
            fiscal year: the other series after a change of year end, or a
            second row a few days from a year's end. Their rows are not
            stored. Dates before the oldest year are outside the window and
            are not named.
    """

    years: tuple[FiscalYear, ...]
    off_chain: tuple[date, ...]


def _year_before(day: date, earlier: list[date]) -> date | None:
    """Return the date that ends the year before ``day``, or ``None``.

    Of two dates within the span, the one nearest to a year before wins, and
    of two equally near, the later.

    Args:
        day: The end of a year.
        earlier: The dates before it, oldest first.
    """
    within = [
        each for each in earlier if _SHORTEST_YEAR_DAYS <= (day - each).days <= _LONGEST_YEAR_DAYS
    ]
    if not within:
        return None
    return min(within, key=lambda each: (abs((day - each).days - _YEAR_DAYS), -each.toordinal()))


def fiscal_years(dates: Iterable[date], window: int = WINDOW_YEARS) -> FiscalYears:
    """Work out a company's fiscal years from the dates of its yearly rows.

    The walk starts at the latest date, which always ends a fiscal year. From
    each year it steps to the year before it, when one is there. When none
    is, the year is not proven, and the walk goes on from the nearest date at
    least about three months earlier: after a change of year end, that is the
    last year of the old series. A date closer than that is a second row for
    the same year end and is off the chain. The walk stops after ``window``
    years or when no date is left.

    Args:
        dates: Every date on which the payload has a yearly row, in any of
            the three statements. A date may come more than once.
        window: How many fiscal years to keep.

    Returns:
        The years, oldest first, and the dates inside the window that are
        not one. A year at the edge of the window is proven when the year
        before it is there, even though that year itself is not kept.
    """
    remaining = sorted(set(dates))
    chain: list[FiscalYear] = []
    while remaining and len(chain) < window:
        day = remaining.pop()
        before = _year_before(day, remaining)
        chain.append(FiscalYear(period_end=day, proven=before is not None))
        if before is not None:
            # Every date between the two years is off the chain.
            remaining = [each for each in remaining if each <= before]
        else:
            remaining = [each for each in remaining if (day - each).days >= _SHORTEST_PERIOD_DAYS]
    years = tuple(reversed(chain))
    on_chain = {year.period_end for year in years}
    off_chain = tuple(
        each
        for each in sorted(set(dates))
        if years and each > years[0].period_end and each not in on_chain
    )
    return FiscalYears(years=years, off_chain=off_chain)
