"""EODHD's financial statements: the yearly rows of a saved fundamentals payload.

A payload holds a company's statements under ``Financials``: one section per
statement (``Income_Statement``, ``Cash_Flow``, ``Balance_Sheet``), each with
a ``currency_symbol`` and the lists ``yearly`` and ``quarterly``. A list is
an object keyed by the period's end date; one entry holds ``date``,
``filing_date``, ``currency_symbol`` and the figures, written as decimal
text (``"331839000000.00"``).

This module turns the yearly lists into the common shape of
``pyvalue.providers.statements``, and it alone knows EODHD's field names.
It reports what the payload says and decides nothing: which rows are a
company's fiscal years, in which currency, and what is wrong with them is
decided by ``pyvalue.fundamentals`` (ADR 0029, ADR 0030).

The reader is strict about the shape, as the readers of the lists are
(ADR 0027): a value that is not what it should be stops the payload with a
message that names the field, instead of becoming a row that silently lacks
a figure. What is absent is simply absent: EODHD writes ``null`` for a
figure it does not have, an empty text for a missing currency label, and an
empty ``yearly`` list for a company it has no statements for. The shape was
checked against all 8,309 payloads saved on 2026-11-27.

Author: Emre Tezel
"""

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from pyvalue.providers.errors import ProviderError
from pyvalue.providers.statements import (
    FIGURES,
    Figure,
    ReportedRow,
    ReportedStatements,
    Statement,
)

# The section of ``Financials`` each statement is in.
_SECTIONS: Mapping[Statement, str] = MappingProxyType(
    {
        Statement.INCOME: "Income_Statement",
        Statement.CASH_FLOW: "Cash_Flow",
        Statement.BALANCE_SHEET: "Balance_Sheet",
    }
)

# The field each figure is read from. Income tax is not here: it has two
# fields, read below.
_FIELDS: Mapping[Figure, str] = MappingProxyType(
    {
        Figure.REVENUE: "totalRevenue",
        Figure.COST_OF_REVENUE: "costOfRevenue",
        Figure.GROSS_PROFIT: "grossProfit",
        # ``operatingIncome`` is the reported operating profit. EODHD's
        # ``ebit`` is another measure: the two are equal on a quarter of the
        # rows that have both (ADR 0029).
        Figure.OPERATING_INCOME: "operatingIncome",
        Figure.PRETAX_INCOME: "incomeBeforeTax",
        Figure.NET_INCOME: "netIncome",
        Figure.INTEREST_EXPENSE: "interestExpense",
        Figure.OPERATING_CASH_FLOW: "totalCashFromOperatingActivities",
        Figure.CAPITAL_EXPENDITURE: "capitalExpenditures",
        Figure.DEPRECIATION_AMORTIZATION: "depreciation",
        Figure.DIVIDENDS_PAID: "dividendsPaid",
        Figure.NET_SHARE_SALES: "salePurchaseOfStock",
        Figure.TOTAL_ASSETS: "totalAssets",
        Figure.TOTAL_LIABILITIES: "totalLiab",
        Figure.EQUITY: "totalStockholderEquity",
        Figure.MINORITY_INTEREST: "noncontrollingInterestInConsolidatedEntity",
        Figure.CASH: "cash",
        Figure.SHORT_TERM_INVESTMENTS: "shortTermInvestments",
        Figure.CASH_AND_SHORT_TERM_INVESTMENTS: "cashAndShortTermInvestments",
        Figure.SHORT_TERM_DEBT: "shortTermDebt",
        Figure.LONG_TERM_DEBT: "longTermDebt",
        Figure.TOTAL_DEBT_STATED: "shortLongTermDebtTotal",
        Figure.LEASE_OBLIGATIONS: "capitalLeaseObligations",
        Figure.CURRENT_ASSETS: "totalCurrentAssets",
        Figure.CURRENT_LIABILITIES: "totalCurrentLiabilities",
        Figure.NONCURRENT_LIABILITIES: "nonCurrentLiabilitiesTotal",
        Figure.SHARES_OUTSTANDING: "commonStockSharesOutstanding",
    }
)

# EODHD gives income tax twice, as two names for one fact. They differ on a
# tenth of the rows that have both, and where they do, the first is nearer to
# pre-tax income minus net income on 70% of them. So it is read first, and
# the second only where the first is missing (ADR 0029).
_TAX_FIELDS: tuple[str, str] = ("incomeTaxExpense", "taxProvision")

# The provider's own total of the right-hand side of the balance sheet. It is
# read for the check that the two sides agree (ADR 0030) and never stored.
_LIABILITIES_AND_EQUITY: str = "liabilitiesAndStockholdersEquity"

_WHAT: str = "an EODHD fundamentals payload"


def _text(value: object, where: str) -> str | None:
    """Read a text field that may be absent: ``null`` and an empty text are."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderError(f"{where} is not a text")
    text = value.strip()
    return text or None


def _amount(value: object, where: str) -> Decimal | None:
    """Read an amount exactly, as EODHD writes it.

    EODHD writes amounts as decimal text. A plain JSON number is read too,
    and exactly: the payload is parsed with every fraction as a decimal.
    """
    if value is None or value == "":
        return None
    # A bool is an int to Python, and never an amount.
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise ProviderError(f"{where} is not an amount")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ProviderError(f"{where} is not an amount: {str(value)[:40]!r}") from error
    if not amount.is_finite():
        raise ProviderError(f"{where} is not a finite amount")
    return amount


def _date(value: object, where: str) -> date:
    """Read a date written as ``YYYY-MM-DD``, and nothing else."""
    if isinstance(value, str):
        try:
            day = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            # fromisoformat also takes ``20251231``; the payload never does.
            if day.isoformat() == value:
                return day
    raise ProviderError(f"{where} is not a date written as YYYY-MM-DD")


def _object(value: object, where: str) -> dict[str, object]:
    """Return a JSON object, or say that the value is not one."""
    if not isinstance(value, dict):
        raise ProviderError(f"{where} is not an object")
    return value


def _row(statement: Statement, entry: dict[str, object], where: str) -> ReportedRow:
    """Read one entry of a yearly list."""
    figures: dict[Figure, Decimal] = {}
    for figure in FIGURES[statement]:
        # Income tax has no single field: the first of its two that is given.
        fields = _TAX_FIELDS if figure is Figure.INCOME_TAX else (_FIELDS[figure],)
        for field in fields:
            amount = _amount(entry.get(field), f"{where} {field}")
            if amount is not None:
                figures[figure] = amount
                break
    liabilities_and_equity: Decimal | None = None
    if statement is Statement.BALANCE_SHEET:
        liabilities_and_equity = _amount(
            entry.get(_LIABILITIES_AND_EQUITY), f"{where} {_LIABILITIES_AND_EQUITY}"
        )
    return ReportedRow(
        statement=statement,
        period_end=_date(entry.get("date"), f"{where} date"),
        currency=_text(entry.get("currency_symbol"), f"{where} currency_symbol"),
        figures=MappingProxyType(figures),
        liabilities_and_equity=liabilities_and_equity,
    )


def read_statements(body: bytes, source: str) -> ReportedStatements:
    """Read the yearly statements of one saved fundamentals payload.

    Args:
        body: The payload as it was saved, unpacked.
        source: What to call it in a message, such as its file name.

    Returns:
        The payload's ISIN, each statement's own currency label, and every
        yearly row of the three statements, ordered by statement and date.
        A payload without statements gives no rows.

    Raises:
        ProviderError: If the payload is not JSON, or a section, an entry, a
            date, a currency label or an amount is not of its expected kind,
            or a statement has two rows for one date.
    """
    try:
        # Every fraction as an exact decimal: an amount must never pass
        # through a binary floating-point number.
        document: object = json.loads(body, parse_float=Decimal)
    except ValueError as error:
        # The parser's message gives a position, never the content.
        raise ProviderError(f"{source} is not {_WHAT}: {error}") from error
    payload = _object(document, f"{source} is not {_WHAT}: the payload")
    general = _object(payload.get("General"), f"{source}: General")
    isin = _text(general.get("ISIN"), f"{source}: General.ISIN")

    statement_currency: dict[Statement, str | None] = dict.fromkeys(Statement)
    rows: list[ReportedRow] = []
    financials = payload.get("Financials")
    if financials is not None:
        financials = _object(financials, f"{source}: Financials")
        for statement, name in _SECTIONS.items():
            if financials.get(name) is None:
                continue
            section = _object(financials[name], f"{source}: {name}")
            statement_currency[statement] = _text(
                section.get("currency_symbol"), f"{source}: {name}.currency_symbol"
            )
            yearly = section.get("yearly")
            if yearly is None:
                continue
            entries = _object(yearly, f"{source}: {name}.yearly")
            read = sorted(
                (
                    _row(statement, _object(entry, where), where)
                    for key, entry in entries.items()
                    for where in (f"{source}: {name}.yearly {key}",)
                ),
                key=lambda row: row.period_end,
            )
            for earlier, later in zip(read, read[1:], strict=False):
                if earlier.period_end == later.period_end:
                    raise ProviderError(
                        f"{source}: {name}.yearly has two rows for {later.period_end.isoformat()}"
                    )
            rows.extend(read)
    return ReportedStatements(
        isin=isin, statement_currency=MappingProxyType(statement_currency), rows=tuple(rows)
    )
