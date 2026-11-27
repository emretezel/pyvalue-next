"""Tests for ``pyvalue.providers.eodhd_statements``: the yearly rows of a payload.

The payloads are made up in the shape EODHD gives (ADR 0028); none was
downloaded.

Author: Emre Tezel
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd_statements import read_statements
from pyvalue.providers.statements import FIGURES, Figure, ReportedRow, Statement

# Every field the reader takes, with the figure it becomes. Income tax and
# the provider's total of liabilities and equity are tested on their own.
_FIELD_OF: dict[Figure, tuple[str, str]] = {
    Figure.REVENUE: ("Income_Statement", "totalRevenue"),
    Figure.COST_OF_REVENUE: ("Income_Statement", "costOfRevenue"),
    Figure.GROSS_PROFIT: ("Income_Statement", "grossProfit"),
    Figure.OPERATING_INCOME: ("Income_Statement", "operatingIncome"),
    Figure.PRETAX_INCOME: ("Income_Statement", "incomeBeforeTax"),
    Figure.NET_INCOME: ("Income_Statement", "netIncome"),
    Figure.INTEREST_EXPENSE: ("Income_Statement", "interestExpense"),
    Figure.OPERATING_CASH_FLOW: ("Cash_Flow", "totalCashFromOperatingActivities"),
    Figure.CAPITAL_EXPENDITURE: ("Cash_Flow", "capitalExpenditures"),
    Figure.DEPRECIATION_AMORTIZATION: ("Cash_Flow", "depreciation"),
    Figure.DIVIDENDS_PAID: ("Cash_Flow", "dividendsPaid"),
    Figure.NET_SHARE_SALES: ("Cash_Flow", "salePurchaseOfStock"),
    Figure.TOTAL_ASSETS: ("Balance_Sheet", "totalAssets"),
    Figure.TOTAL_LIABILITIES: ("Balance_Sheet", "totalLiab"),
    Figure.EQUITY: ("Balance_Sheet", "totalStockholderEquity"),
    Figure.MINORITY_INTEREST: ("Balance_Sheet", "noncontrollingInterestInConsolidatedEntity"),
    Figure.CASH: ("Balance_Sheet", "cash"),
    Figure.SHORT_TERM_INVESTMENTS: ("Balance_Sheet", "shortTermInvestments"),
    Figure.CASH_AND_SHORT_TERM_INVESTMENTS: ("Balance_Sheet", "cashAndShortTermInvestments"),
    Figure.SHORT_TERM_DEBT: ("Balance_Sheet", "shortTermDebt"),
    Figure.LONG_TERM_DEBT: ("Balance_Sheet", "longTermDebt"),
    Figure.TOTAL_DEBT_STATED: ("Balance_Sheet", "shortLongTermDebtTotal"),
    Figure.LEASE_OBLIGATIONS: ("Balance_Sheet", "capitalLeaseObligations"),
    Figure.CURRENT_ASSETS: ("Balance_Sheet", "totalCurrentAssets"),
    Figure.CURRENT_LIABILITIES: ("Balance_Sheet", "totalCurrentLiabilities"),
    Figure.NONCURRENT_LIABILITIES: ("Balance_Sheet", "nonCurrentLiabilitiesTotal"),
    Figure.SHARES_OUTSTANDING: ("Balance_Sheet", "commonStockSharesOutstanding"),
}

_SECTION_OF: dict[str, Statement] = {
    "Income_Statement": Statement.INCOME,
    "Cash_Flow": Statement.CASH_FLOW,
    "Balance_Sheet": Statement.BALANCE_SHEET,
}


def _entry(day: str, currency: str | None = "USD", **fields: object) -> dict[str, object]:
    """Return one entry of a yearly list, as EODHD writes it."""
    return {"date": day, "filing_date": day, "currency_symbol": currency, **fields}


def _payload(
    isin: object = "US0000000001",
    financials: object = None,
    **sections: dict[str, dict[str, object]],
) -> bytes:
    """Return a payload whose sections hold the given yearly entries, keyed by date."""
    if financials is None:
        financials = {
            name: {"currency_symbol": "USD", "quarterly": {}, "yearly": entries}
            for name, entries in sections.items()
        }
    return json.dumps(
        {"General": {"Code": "ALPH", "ISIN": isin}, "Financials": financials}
    ).encode()


def _only_row(body: bytes) -> ReportedRow:
    """Return the one row a payload gives."""
    (row,) = read_statements(body, "the payload").rows
    return row


def test_every_figure_is_read_from_its_field() -> None:
    """Each statement's figures come from the fields of ADR 0029, and nothing else is read."""
    sections: dict[str, dict[str, object]] = {name: {} for name in _SECTION_OF}
    for number, (section, field) in enumerate(_FIELD_OF.values(), start=1):
        sections[section][field] = f"{number}.00"
    sections["Income_Statement"]["ebit"] = "999.00"
    body = _payload(
        **{
            name: {"2025-12-31": {**_entry("2025-12-31"), **fields}}
            for name, fields in sections.items()
        }
    )

    rows = {row.statement: row for row in read_statements(body, "the payload").rows}

    for number, (figure, (section, _)) in enumerate(_FIELD_OF.items(), start=1):
        assert rows[_SECTION_OF[section]].figures[figure] == Decimal(number)
    assert Decimal(999) not in rows[Statement.INCOME].figures.values()


def test_the_list_of_fields_covers_every_figure_but_income_tax() -> None:
    """A figure added to the vocabulary without a field here would never be read."""
    every = {figure for figures in FIGURES.values() for figure in figures}
    assert every - set(_FIELD_OF) == {Figure.INCOME_TAX}


def test_each_figure_belongs_to_one_statement() -> None:
    """The three lists of figures do not overlap, and together name every figure."""
    listed = [figure for figures in FIGURES.values() for figure in figures]
    assert sorted(listed, key=str) == sorted(Figure, key=str)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"incomeTaxExpense": "30.00", "taxProvision": "31.00"}, Decimal(30)),
        ({"incomeTaxExpense": None, "taxProvision": "31.00"}, Decimal(31)),
        ({"taxProvision": "-4.00"}, Decimal(-4)),
    ],
)
def test_income_tax_is_the_first_of_its_two_fields_that_is_given(
    fields: dict[str, object], expected: Decimal
) -> None:
    """``incomeTaxExpense``, and ``taxProvision`` only where the first is missing."""
    body = _payload(Income_Statement={"2025-12-31": {**_entry("2025-12-31"), **fields}})

    assert _only_row(body).figures[Figure.INCOME_TAX] == expected


def test_income_tax_is_absent_when_neither_field_is_given() -> None:
    """Two nulls give no income tax, not a zero."""
    body = _payload(
        Income_Statement={
            "2025-12-31": _entry(
                "2025-12-31", totalRevenue="5.00", incomeTaxExpense=None, taxProvision=None
            )
        }
    )

    assert Figure.INCOME_TAX not in _only_row(body).figures


def test_the_providers_total_of_liabilities_and_equity_is_read_on_the_balance_sheet() -> None:
    """It is read for the check of ADR 0030, beside the figures, never as one of them."""
    body = _payload(
        Balance_Sheet={
            "2025-12-31": _entry(
                "2025-12-31", totalAssets="10.00", liabilitiesAndStockholdersEquity="10.00"
            )
        }
    )

    row = _only_row(body)

    assert row.liabilities_and_equity == Decimal(10)
    assert set(row.figures) == {Figure.TOTAL_ASSETS}


def test_a_figure_given_as_null_or_empty_text_is_absent() -> None:
    """EODHD writes ``null`` for a figure it does not have."""
    body = _payload(
        Cash_Flow={
            "2025-12-31": _entry(
                "2025-12-31", capitalExpenditures=None, dividendsPaid="", depreciation="3.00"
            )
        }
    )

    assert dict(_only_row(body).figures) == {Figure.DEPRECIATION_AMORTIZATION: Decimal(3)}


@given(
    st.decimals(min_value=Decimal(-(10**18)), max_value=Decimal(10**18), places=2, allow_nan=False)
)
def test_an_amount_written_as_decimal_text_is_read_exactly(amount: Decimal) -> None:
    """No amount passes through a binary floating-point number."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31", totalRevenue=str(amount))})

    assert _only_row(body).figures[Figure.REVENUE] == amount


def test_an_amount_written_as_a_json_number_is_read_exactly() -> None:
    """0.1 as a JSON number would be 0.1000000000000000055 as a float."""
    body = (
        b'{"General": {"ISIN": null}, "Financials": {"Income_Statement": {"yearly": '
        b'{"2025-12-31": {"date": "2025-12-31", "totalRevenue": 0.1, "netIncome": 7}}}}}'
    )

    figures = _only_row(body).figures

    assert figures[Figure.REVENUE] == Decimal("0.1")
    assert figures[Figure.NET_INCOME] == Decimal(7)


@pytest.mark.parametrize("value", ["abc", "1,000", "NaN", "Infinity", True, [1], {"a": 1}])
def test_an_amount_that_is_not_an_amount_stops_the_payload_and_names_the_field(
    value: object,
) -> None:
    """A change of shape shows as a message, not as a row without the figure."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31", totalRevenue=value)})

    with pytest.raises(ProviderError, match="Income_Statement.yearly 2025-12-31 totalRevenue"):
        read_statements(body, "the payload")


@pytest.mark.parametrize("day", ["31/12/2025", "20251231", "2025-02-30", None, 20251231])
def test_a_date_that_is_not_written_as_yyyy_mm_dd_stops_the_payload(day: object) -> None:
    """The date of a row is the period's end, so it must be read for certain."""
    body = _payload(Income_Statement={"2025-12-31": {"date": day, "totalRevenue": "5.00"}})

    with pytest.raises(ProviderError, match="date"):
        read_statements(body, "the payload")


def test_the_currency_label_of_a_row_is_taken_as_given() -> None:
    """A sub-unit label is the provider's claim; what it means is decided later (ADR 0029)."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31", "GBX", netIncome="5.00")})

    assert _only_row(body).currency == "GBX"


@pytest.mark.parametrize("label", [None, "", " "])
def test_a_row_without_a_currency_label_has_none(label: str | None) -> None:
    """EODHD writes a missing label as ``null`` or as an empty text."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31", label, netIncome="5.00")})

    assert _only_row(body).currency is None


def test_a_currency_label_that_is_not_a_text_stops_the_payload() -> None:
    """A number in the label's place is a change of shape."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31", None, netIncome="5.00")})
    document = json.loads(body)
    document["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["currency_symbol"] = 840

    with pytest.raises(ProviderError, match="currency_symbol is not a text"):
        read_statements(json.dumps(document).encode(), "the payload")


def test_each_statements_own_label_is_read() -> None:
    """The label on a statement as a whole is the last resort for a period's currency."""
    financials = {
        "Income_Statement": {"currency_symbol": "EUR", "yearly": {}},
        "Cash_Flow": {"currency_symbol": None, "yearly": {}},
    }

    read = read_statements(_payload(financials=financials), "the payload")

    assert dict(read.statement_currency) == {
        Statement.INCOME: "EUR",
        Statement.CASH_FLOW: None,
        Statement.BALANCE_SHEET: None,
    }
    assert read.rows == ()


@pytest.mark.parametrize("isin", ["US0000000001", None, ""])
def test_the_payloads_isin_is_read_and_a_missing_one_is_none(isin: str | None) -> None:
    """Most US payloads name no ISIN."""
    read = read_statements(_payload(isin=isin, financials={}), "the payload")

    assert read.isin == (isin or None)


def test_the_rows_are_ordered_by_statement_and_date_whatever_the_order_of_the_payload() -> None:
    """EODHD lists the newest year first; the rows come out oldest first."""
    entries = {
        day: _entry(day, netIncome="1.00", totalAssets="2.00")
        for day in ("2025-12-31", "2023-12-31", "2024-12-31")
    }
    body = _payload(Balance_Sheet=entries, Income_Statement=entries)

    rows = read_statements(body, "the payload").rows

    assert [(row.statement, row.period_end.year) for row in rows] == [
        (Statement.INCOME, 2023),
        (Statement.INCOME, 2024),
        (Statement.INCOME, 2025),
        (Statement.BALANCE_SHEET, 2023),
        (Statement.BALANCE_SHEET, 2024),
        (Statement.BALANCE_SHEET, 2025),
    ]


def test_the_interim_rows_are_not_read() -> None:
    """Only the yearly lists are read in this step (ADR 0029)."""
    financials = {
        "Income_Statement": {
            "currency_symbol": "USD",
            "quarterly": {"2026-09-30": _entry("2026-09-30", totalRevenue="5.00")},
            "yearly": {},
        }
    }

    assert read_statements(_payload(financials=financials), "the payload").rows == ()


def test_a_row_without_any_figure_is_still_a_row() -> None:
    """Whether an empty row is kept is the load's decision (ADR 0030), not the reader's."""
    body = _payload(Income_Statement={"2025-12-31": _entry("2025-12-31")})

    row = _only_row(body)

    assert (row.period_end, dict(row.figures)) == (date(2025, 12, 31), {})


@pytest.mark.parametrize("financials", [{}, {"Income_Statement": None}])
def test_a_payload_without_statements_gives_no_rows(financials: dict[str, object]) -> None:
    """As for the Egyptian payloads, whose yearly lists are empty."""
    assert read_statements(_payload(financials=financials), "the payload").rows == ()


def test_a_section_without_a_yearly_list_gives_no_rows() -> None:
    """Its own currency label is still read."""
    financials = {"Balance_Sheet": {"currency_symbol": "SEK"}}

    read = read_statements(_payload(financials=financials), "the payload")

    assert (read.rows, read.statement_currency[Statement.BALANCE_SHEET]) == ((), "SEK")


def test_a_payload_without_financials_gives_no_rows() -> None:
    """A section that is not there is not a change of shape: there is nothing to read."""
    body = json.dumps({"General": {"ISIN": None}}).encode()

    assert read_statements(body, "the payload").rows == ()


def test_two_rows_of_one_statement_for_one_date_stop_the_payload() -> None:
    """Which of the two is the statement could not be told."""
    body = _payload(
        Income_Statement={
            "2025-12-31": _entry("2025-12-31", netIncome="1.00"),
            "2025-12-31 again": _entry("2025-12-31", netIncome="2.00"),
        }
    )

    with pytest.raises(ProviderError, match="two rows for 2025-12-31"):
        read_statements(body, "the payload")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html>", "is not an EODHD fundamentals payload"),
        (b"[]", "is not an EODHD fundamentals payload"),
        (b"{}", "General is not an object"),
        (b'{"General": {}, "Financials": []}', "Financials is not an object"),
        (b'{"General": {}, "Financials": {"Cash_Flow": "x"}}', "Cash_Flow is not an object"),
        (
            b'{"General": {}, "Financials": {"Cash_Flow": {"yearly": []}}}',
            "Cash_Flow.yearly is not an object",
        ),
        (
            b'{"General": {}, "Financials": {"Cash_Flow": {"yearly": {"2025-12-31": 5}}}}',
            "Cash_Flow.yearly 2025-12-31 is not an object",
        ),
        (b'{"General": {"ISIN": 5}}', "General.ISIN is not a text"),
    ],
)
def test_a_payload_of_another_shape_is_refused_with_a_message_that_names_the_place(
    body: bytes, message: str
) -> None:
    """The message says where the shape broke and names the payload."""
    with pytest.raises(ProviderError, match=message) as refused:
        read_statements(body, "US/ALPH.json.gz")
    assert "US/ALPH.json.gz" in str(refused.value)


@pytest.mark.parametrize(
    "sample", ["US_ALPH.json", "US_ALPH-PA.json", "US_BETA.json", "LSE_DLT.json", "XETRA_THT.json"]
)
def test_every_sample_payload_is_read(fundamentals_samples: Path, sample: str) -> None:
    """The checked-in samples are in the shape the reader takes."""
    read = read_statements((fundamentals_samples / sample).read_bytes(), sample)

    assert read.rows
