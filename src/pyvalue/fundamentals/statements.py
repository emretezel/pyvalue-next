"""One company's statements: from what a provider reports to what is stored.

The load hands this module the payloads of one company, already read into
the common shape of ``pyvalue.providers.statements``. It returns the rows to
store and everything it found on the way. It touches no file and no
database, reads no clock, and gives the same answer for the same payloads.

What it does, in order (ADR 0029, ADR 0030):

1. **Which payload.** A company with several listed securities has a payload
   for each. One is read: a common share's before a preferred share's, then
   the one with more fiscal years, then the one of the smaller ISIN. The
   others are only compared with it.
2. **Which rows are fiscal years.** ``fiscal_years`` works out the chain from
   the dates. A date off the chain is left out.
3. **The currency of each year.** One currency per year, for all three
   statements. Nothing is converted.
4. **The rows.** An income or cash-flow row is stored only for a year whose
   length is proven. Every amount is rounded to a whole unit, and each row
   goes through the checks of ``pyvalue.fundamentals.checks``.

Author: Emre Tezel
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType

from pyvalue.fundamentals.checks import (
    Check,
    Finding,
    balance_sides_differ,
    differ,
    gross_profit_mismatch,
    is_absurd,
    is_impossible,
    is_placeholder_capex,
    is_scale_outlier,
    is_scale_step,
    is_zero_interest_with_debt,
)
from pyvalue.fundamentals.fiscal_years import FiscalYear, fiscal_years
from pyvalue.providers.eodhd import currency_of
from pyvalue.providers.statements import (
    Figure,
    ReportedRow,
    ReportedStatements,
    Statement,
)

# The length of a fiscal year's income and cash-flow rows. Interim rows of
# 3, 6 and 9 months come with the next step (ADR 0029).
YEAR_MONTHS: int = 12

# The statements whose rows cover a period, and so need a proven length.
_FLOWS: frozenset[Statement] = frozenset({Statement.INCOME, Statement.CASH_FLOW})

# The one figure of a statement whose scale is checked against its
# neighbours: the total that a change of unit moves most visibly.
_SCALE_FIGURE: Mapping[Statement, Figure] = MappingProxyType(
    {Statement.INCOME: Figure.REVENUE, Statement.BALANCE_SHEET: Figure.TOTAL_ASSETS}
)

# The figures two payloads of one company are compared on.
_COMPARED: tuple[tuple[Statement, Figure], ...] = (
    (Statement.INCOME, Figure.REVENUE),
    (Statement.INCOME, Figure.NET_INCOME),
    (Statement.BALANCE_SHEET, Figure.TOTAL_ASSETS),
)

_ONE: Decimal = Decimal(1)


@dataclass(frozen=True, slots=True)
class Payload:
    """One saved payload of a company, read.

    Attributes:
        isin: The security the payload was downloaded for.
        preferred: Whether that security is a preferred share.
        reported: What the payload reports.
    """

    isin: str
    preferred: bool
    reported: ReportedStatements


@dataclass(frozen=True, slots=True)
class Period:
    """A date a company's statements are drawn up to, with their currency."""

    period_end: date
    currency: str


@dataclass(frozen=True, slots=True)
class FlowRow:
    """An income or cash-flow statement to store: it covers a period.

    Attributes:
        statement: ``Statement.INCOME`` or ``Statement.CASH_FLOW``.
        period_end: The last day of the period.
        months: How many months the row covers.
        figures: The figures, in whole units of the period's currency. A
            figure not reported, or emptied by a check, is absent.
    """

    statement: Statement
    period_end: date
    months: int
    figures: Mapping[Figure, int]


@dataclass(frozen=True, slots=True)
class BalanceSheetRow:
    """A balance sheet to store: a snapshot, so it has no length.

    Attributes:
        period_end: The day of the snapshot.
        figures: The figures, in whole units of the period's currency. A
            figure not reported, or emptied by a check, is absent.
    """

    period_end: date
    figures: Mapping[Figure, int]

    @property
    def statement(self) -> Statement:
        """The statement the row is of: always the balance sheet."""
        return Statement.BALANCE_SHEET


# One row to store.
type StatementRow = FlowRow | BalanceSheetRow


@dataclass(frozen=True, slots=True)
class CompanyStatements:
    """What is stored for one company, and what was found.

    Attributes:
        isin: The security whose payload was read, or ``None`` when none
            could be.
        periods: The periods that have at least one stored row, oldest first.
        rows: The rows to store, by period and then by statement.
        findings: Everything the checks found, in the order they found it.
    """

    isin: str | None
    periods: tuple[Period, ...]
    rows: tuple[StatementRow, ...]
    findings: tuple[Finding, ...]

    @property
    def latest(self) -> date | None:
        """The end of the latest period stored, or ``None``."""
        return self.periods[-1].period_end if self.periods else None


def whole(amount: Decimal) -> int:
    """Round an amount to a whole unit, a half to the even one (ADR 0029)."""
    return int(amount.quantize(_ONE, rounding=ROUND_HALF_EVEN))


def _rounded(row: ReportedRow) -> dict[Figure, int]:
    """Return a row's figures in whole units."""
    return {figure: whole(amount) for figure, amount in row.figures.items()}


def _fiscal_year_count(reported: ReportedStatements) -> int:
    """Return how many fiscal years a payload holds, without the window."""
    dates = {row.period_end for row in reported.rows}
    return len(fiscal_years(dates, window=len(dates)).years)


def _chosen(payloads: Sequence[Payload]) -> Payload:
    """Return the payload a company's statements are read from (ADR 0029)."""
    return min(
        payloads,
        key=lambda each: (each.preferred, -_fiscal_year_count(each.reported), each.isin),
    )


class _Reader:
    """The statements of one payload, worked through once.

    A class only to keep the payload's rows and the findings at hand while
    the steps run; it is used once and thrown away.
    """

    def __init__(self, payload: Payload) -> None:
        """Index the payload's rows by date and statement."""
        self._isin = payload.isin
        self._reported = payload.reported
        self._rows: dict[date, dict[Statement, ReportedRow]] = {}
        for row in payload.reported.rows:
            self._rows.setdefault(row.period_end, {})[row.statement] = row
        self.findings: list[Finding] = []
        # The rows left out as off in scale. They are no neighbour for the
        # year after: the step back from a bad year is not news.
        self._outliers: set[tuple[Statement, date]] = set()

    def _find(
        self,
        check: Check,
        detail: str,
        statement: Statement | None = None,
        period_end: date | None = None,
        figure: Figure | None = None,
    ) -> None:
        """Record one finding about this payload."""
        self.findings.append(
            Finding(
                isin=self._isin,
                check=check,
                statement=statement,
                period_end=period_end,
                figure=figure,
                detail=detail,
            )
        )

    def _labels(self, day: date) -> tuple[set[str], list[str]]:
        """Return the currencies a year's rows carry, and the labels that are none."""
        currencies: set[str] = set()
        unreadable: list[str] = []
        for row in self._rows[day].values():
            if row.currency is not None:
                currency = currency_of(row.currency)
                if currency is None:
                    unreadable.append(row.currency)
                else:
                    currencies.add(currency)
        return currencies, unreadable

    def _currencies(self, years: Sequence[FiscalYear]) -> dict[date, str]:
        """Settle the currency of each year, and report a year that has none.

        A year's own rows decide when they carry one currency between them.
        A year whose rows carry none takes the one currency the other years
        carry. When no row of any year carries a label, it takes the one
        currency the statements name in their own header. Anything else
        leaves the year out: a year without a label among years in two
        currencies could be in either.
        """
        own: dict[date, str] = {}
        silent: list[date] = []
        labelled = False
        for year in years:
            day = year.period_end
            currencies, unreadable = self._labels(day)
            labelled = labelled or bool(currencies or unreadable)
            if unreadable:
                self._find(
                    Check.NO_CURRENCY,
                    f"the label {unreadable[0]!r} is not a currency",
                    period_end=day,
                )
            elif len(currencies) > 1:
                self._find(
                    Check.CURRENCIES_DIFFER,
                    f"the statements are labelled {' and '.join(sorted(currencies))}",
                    period_end=day,
                )
            elif currencies:
                own[day] = currencies.pop()
            else:
                silent.append(day)
        others = set(own.values())
        headers = {
            currency_of(label)
            for label in self._reported.statement_currency.values()
            if label is not None
        }
        settled = dict(own)
        for day in silent:
            if len(others) == 1:
                settled[day] = next(iter(others))
            elif not labelled and len(headers) == 1 and None not in headers:
                settled[day] = str(next(iter(headers)))
            else:
                self._find(
                    Check.NO_CURRENCY,
                    "no row of the year carries a currency, and the other years and the "
                    f"statements settle none ({', '.join(sorted(others)) or 'none'})",
                    period_end=day,
                )
        return settled

    def _scale(
        self,
        statement: Statement,
        index: int,
        years: Sequence[FiscalYear],
        currency: Mapping[date, str],
    ) -> tuple[int | None, int | None, int | None]:
        """Return the scale figure of a year and of its neighbours in the same currency."""
        figure = _SCALE_FIGURE[statement]

        def value(position: int) -> int | None:
            if not 0 <= position < len(years):
                return None
            day = years[position].period_end
            row = self._rows[day].get(statement)
            if (
                row is None
                or (statement, day) in self._outliers
                or currency.get(day) != currency[years[index].period_end]
            ):
                return None
            amount = row.figures.get(figure)
            return None if amount is None else whole(amount)

        return value(index - 1), value(index), value(index + 1)

    def _clean(
        self, statement: Statement, day: date, figures: dict[Figure, int]
    ) -> dict[Figure, int]:
        """Empty the figures that cannot be true, and report each."""
        kept: dict[Figure, int] = {}
        for figure, amount in figures.items():
            if is_absurd(amount):
                self._find(Check.ABSURD_VALUE, str(amount), statement, day, figure)
            elif is_impossible(figure, amount):
                self._find(Check.IMPOSSIBLE_NEGATIVE, str(amount), statement, day, figure)
            else:
                kept[figure] = amount
        if statement is Statement.CASH_FLOW and is_placeholder_capex(kept):
            del kept[Figure.CAPITAL_EXPENDITURE]
            self._find(
                Check.PLACEHOLDER_CAPEX,
                "capital expenditure 0 in a row without operating cash flow",
                statement,
                day,
                Figure.CAPITAL_EXPENDITURE,
            )
        if statement is Statement.INCOME:
            balance_row = self._rows[day].get(Statement.BALANCE_SHEET)
            balance_sheet = {} if balance_row is None else _rounded(balance_row)
            if is_zero_interest_with_debt(kept, balance_sheet):
                del kept[Figure.INTEREST_EXPENSE]
                self._find(
                    Check.ZERO_INTEREST_WITH_DEBT,
                    "interest expense 0 with debt on the balance sheet",
                    statement,
                    day,
                    Figure.INTEREST_EXPENSE,
                )
        return kept

    def _warn(self, row: ReportedRow, figures: Mapping[Figure, int], before: int | None) -> None:
        """Report what is odd about a row that is stored."""
        statement, day = row.statement, row.period_end
        if statement is Statement.INCOME and gross_profit_mismatch(figures):
            self._find(
                Check.GROSS_PROFIT_MISMATCH,
                f"revenue {figures[Figure.REVENUE]} minus cost of revenue "
                f"{figures[Figure.COST_OF_REVENUE]}, gross profit {figures[Figure.GROSS_PROFIT]}",
                statement,
                day,
                Figure.GROSS_PROFIT,
            )
        if statement is Statement.BALANCE_SHEET:
            total = figures.get(Figure.TOTAL_ASSETS)
            other = (
                None if row.liabilities_and_equity is None else whole(row.liabilities_and_equity)
            )
            if balance_sides_differ(total, other):
                self._find(
                    Check.BALANCE_SIDES_DIFFER,
                    f"total assets {total}, liabilities and equity {other}",
                    statement,
                    day,
                    Figure.TOTAL_ASSETS,
                )
        if statement in _SCALE_FIGURE:
            figure = _SCALE_FIGURE[statement]
            value = figures.get(figure)
            if is_scale_step(before, value):
                self._find(
                    Check.SCALE_STEP,
                    f"{figure.value} {value} after {before} the year before",
                    statement,
                    day,
                    figure,
                )
        if row.currency is not None and currency_of(row.currency) != row.currency:
            self._find(
                Check.SUB_UNIT_LABEL,
                f"labelled {row.currency}, read as {currency_of(row.currency)} "
                "with the amounts unchanged",
                statement,
                day,
            )

    def read(self) -> tuple[tuple[Period, ...], tuple[StatementRow, ...]]:
        """Work through the payload and return the periods and rows to store."""
        chain = fiscal_years(self._rows)
        for day in chain.off_chain:
            self._find(
                Check.OFF_CHAIN, "the date is not one of the company's fiscal years", None, day
            )
        years = chain.years
        currency = self._currencies(years)
        periods: list[Period] = []
        rows: list[StatementRow] = []
        for index, year in enumerate(years):
            day = year.period_end
            if day not in currency:
                continue
            stored = self._year(index, years, currency)
            if stored:
                periods.append(Period(period_end=day, currency=currency[day]))
                rows.extend(stored)
        for earlier, later in zip(periods, periods[1:], strict=False):
            if earlier.currency != later.currency:
                self._find(
                    Check.CURRENCY_CHANGED,
                    f"{later.currency} after {earlier.currency} on "
                    f"{earlier.period_end.isoformat()}",
                    period_end=later.period_end,
                )
        return tuple(periods), tuple(rows)

    def _year(
        self, index: int, years: Sequence[FiscalYear], currency: Mapping[date, str]
    ) -> list[StatementRow]:
        """Return the rows stored for one fiscal year, and report the rest."""
        year = years[index]
        day = year.period_end
        stored: list[StatementRow] = []
        for statement in Statement:
            row = self._rows[day].get(statement)
            if row is None:
                continue
            if statement in _FLOWS and not year.proven:
                self._find(
                    Check.LENGTH_NOT_PROVEN,
                    "no fiscal year ends 350 to 380 days before it",
                    statement,
                    day,
                )
                continue
            before: int | None = None
            if statement in _SCALE_FIGURE:
                before, value, after = self._scale(statement, index, years, currency)
                if is_scale_outlier(before, value, after):
                    self._find(
                        Check.SCALE_OUTLIER,
                        f"{_SCALE_FIGURE[statement].value} {value} between {before} "
                        f"the year before and {after} the year after",
                        statement,
                        day,
                        _SCALE_FIGURE[statement],
                    )
                    self._outliers.add((statement, day))
                    continue
            figures = self._clean(statement, day, _rounded(row))
            if not figures:
                self._find(
                    Check.NO_FIGURE,
                    "the row has no figure" if not row.figures else "no figure is left",
                    statement,
                    day,
                )
                continue
            self._warn(row, figures, before)
            stored.append(
                FlowRow(
                    statement=statement,
                    period_end=day,
                    months=YEAR_MONTHS,
                    figures=MappingProxyType(figures),
                )
                if statement in _FLOWS
                else BalanceSheetRow(period_end=day, figures=MappingProxyType(figures))
            )
        return stored


def _compared(reported: ReportedStatements) -> dict[date, dict[tuple[Statement, Figure], int]]:
    """Return the figures two payloads are compared on, by date."""
    values: dict[date, dict[tuple[Statement, Figure], int]] = {}
    for row in reported.rows:
        for statement, figure in _COMPARED:
            amount = row.figures.get(figure)
            if row.statement is statement and amount is not None:
                values.setdefault(row.period_end, {})[(statement, figure)] = whole(amount)
    return values


def _disagreements(chosen: Payload, other: Payload) -> list[Finding]:
    """Compare another payload of the company with the one that is read.

    They are compared on the latest date both have a compared figure for.
    """
    mine = _compared(chosen.reported)
    theirs = _compared(other.reported)
    shared = sorted(set(mine) & set(theirs))
    if not shared:
        return [
            Finding(
                isin=other.isin,
                check=Check.PAYLOADS_DISAGREE,
                detail=f"no fiscal year in common with the payload of {chosen.isin}, which is read",
            )
        ]
    day = shared[-1]
    found: list[Finding] = []
    for key in _COMPARED:
        if key in mine[day] and key in theirs[day] and differ(mine[day][key], theirs[day][key]):
            statement, figure = key
            found.append(
                Finding(
                    isin=other.isin,
                    check=Check.PAYLOADS_DISAGREE,
                    statement=statement,
                    period_end=day,
                    figure=figure,
                    detail=f"{theirs[day][key]} here, {mine[day][key]} in the payload of "
                    f"{chosen.isin}, which is read",
                )
            )
    return found


def company_statements(payloads: Sequence[Payload]) -> CompanyStatements:
    """Work out what is stored for one company, from its payloads.

    Args:
        payloads: Every readable payload of the company, one per listed
            security.

    Returns:
        The periods and rows to store, and the findings. A company none of
        whose payloads has a yearly row gets no rows.
    """
    findings: list[Finding] = []
    candidates: list[Payload] = []
    for payload in sorted(payloads, key=lambda each: each.isin):
        named = payload.reported.isin
        if named is not None and named != payload.isin:
            findings.append(
                Finding(
                    isin=payload.isin, check=Check.OTHER_ISIN, detail=f"the payload names {named}"
                )
            )
        if payload.reported.rows:
            candidates.append(payload)
        else:
            findings.append(
                Finding(
                    isin=payload.isin,
                    check=Check.NO_FISCAL_YEAR,
                    detail="the payload has no yearly row",
                )
            )
    if not candidates:
        return CompanyStatements(isin=None, periods=(), rows=(), findings=tuple(findings))
    chosen = _chosen(candidates)
    reader = _Reader(chosen)
    periods, rows = reader.read()
    findings.extend(reader.findings)
    for other in candidates:
        if other is not chosen:
            findings.extend(_disagreements(chosen, other))
    return CompanyStatements(isin=chosen.isin, periods=periods, rows=rows, findings=tuple(findings))
