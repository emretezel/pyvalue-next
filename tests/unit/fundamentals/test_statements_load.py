"""Tests for ``pyvalue.fundamentals.load``: the saved payloads into the statement tables.

The payloads are made up in EODHD's shape and written into a temporary
folder as the download would have saved them. What each company gets is
worked out by ``company_statements`` and tested there; these tests are about
the run: which payloads it reads, what it reports, that it replaces the
tables as a whole, and when it refuses to run.

Author: Emre Tezel
"""

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from pyvalue.db import (
    Database,
    Exchange,
    Fund,
    Holding,
    Provider,
    ProviderExchange,
    ProviderListing,
)
from pyvalue.fundamentals import Check, FundamentalsError, load_statements
from pyvalue.fundamentals.findings import FINDINGS_FILE
from pyvalue.fundamentals.load import balance_sheet_record, cash_flow_record, income_record
from pyvalue.fundamentals.saved_payloads import pack, payload_file
from pyvalue.fundamentals.statements import BalanceSheetRow, FlowRow
from pyvalue.providers.statements import FIGURES, Statement

_HEADER: str = (
    "isin,company,provider_exchange_code,provider_symbol,statement,period_end,check,outcome,"
    "figure,detail"
)


def _year(
    day: str, revenue: int = 1_000_000_000, total_assets: int = 5_000_000_000
) -> dict[str, dict[str, object]]:
    """Return one fiscal year of the three statements, as EODHD writes its entries."""
    common = {"date": day, "filing_date": day, "currency_symbol": "USD"}
    return {
        "Income_Statement": {**common, "totalRevenue": f"{revenue}.00", "netIncome": "100.00"},
        "Cash_Flow": {**common, "totalCashFromOperatingActivities": "200.00"},
        "Balance_Sheet": {**common, "totalAssets": f"{total_assets}.00"},
    }


def _body(symbol: str, *years: dict[str, dict[str, object]], isin: str | None = None) -> bytes:
    """Return a payload holding the given fiscal years."""
    financials: dict[str, dict[str, object]] = {
        name: {"currency_symbol": "USD", "quarterly": {}, "yearly": {}}
        for name in ("Income_Statement", "Cash_Flow", "Balance_Sheet")
    }
    for year in years:
        for name, entry in year.items():
            yearly = financials[name]["yearly"]
            assert isinstance(yearly, dict)
            yearly[str(entry["date"])] = entry
    document = {"General": {"Code": symbol, "ISIN": isin}, "Financials": financials}
    return json.dumps(document).encode()


@pytest.fixture
def market(database: Database) -> Database:
    """Return a database with New York, EODHD's code for it, and a fund."""
    with database.unit_of_work() as work:
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        work.exchanges.save(Exchange(mic="XNYS", name="New York Stock Exchange", country="US"))
        work.provider_exchanges.add(
            ProviderExchange(provider_code="eodhd", mic="XNYS", provider_exchange_code="US")
        )
        work.funds.save(
            Fund(
                fund_code="VTI",
                name="Vanguard Total Stock Market Index Fund",
                scope="US",
                sec_series_id="S000002848",
                sec_filing_number="0000036405-26-000480",
                holdings_date=date(2026, 6, 30),
                sponsor_file_date=None,
            )
        )
    return database


def _company(database: Database, name: str, *securities: tuple[str, str, str]) -> None:
    """Add a company with its listed securities: ISIN, symbol and asset category each."""
    with database.unit_of_work() as work:
        company = work.companies.add(name, None)
        lines = len(work.holdings.all())
        for number, (isin, symbol, category) in enumerate(securities, start=lines + 1):
            instrument = work.instruments.add(company.company_id, isin)
            listing = work.listings.add(instrument.instrument_id, "XNYS", symbol, "USD")
            work.provider_listings.add(
                ProviderListing(
                    provider_code="eodhd", listing_id=listing.listing_id, provider_symbol=symbol
                )
            )
            work.holdings.add(
                Holding(
                    fund_code="VTI",
                    line_number=number,
                    instrument_id=instrument.instrument_id,
                    isin=isin,
                    issuer_name=name,
                    title=None,
                    lei=None,
                    cusip=None,
                    sedol=None,
                    ticker=symbol,
                    asset_category=category,
                    trading_country="US",
                    currency="USD",
                )
            )


def _save(folder: Path, symbol: str, body: bytes) -> None:
    """Save a payload where the download would have kept it."""
    path = folder / payload_file("US", symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack(body))


@pytest.fixture
def payloads(tmp_path: Path) -> Path:
    """Return an empty payload folder."""
    folder = tmp_path / "payloads"
    folder.mkdir()
    return folder


def _report(folder: Path) -> list[str]:
    """Return the rows of the report after its header, which is checked too."""
    header, *rows = (folder / FINDINGS_FILE).read_text(encoding="utf-8").splitlines()
    assert header == _HEADER
    return rows


def _two_companies(market: Database, payloads: Path) -> None:
    """Add Alpha, with three clean years, and Beta, with one year and an old one."""
    _company(market, "Alpha Corp", ("US00000A0014", "ALPH", "EC"))
    _company(market, "Beta Inc", ("US00000B0013", "BETA", "EC"))
    _save(
        payloads,
        "ALPH",
        _body("ALPH", _year("2023-12-31"), _year("2024-12-31"), _year("2025-12-31")),
    )
    _save(payloads, "BETA", _body("BETA", _year("2023-06-30")))


def test_the_load_stores_each_companys_years_and_counts_them(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """Alpha has two proven years; Beta's one year has a balance sheet only, and is old."""
    _two_companies(market, payloads)

    outcome = load_statements(market, payloads, tmp_path / "report")

    assert (outcome.companies, outcome.companies_stored, outcome.periods) == (2, 2, 4)
    assert dict(outcome.rows) == {
        Statement.INCOME: 2,
        Statement.CASH_FLOW: 2,
        Statement.BALANCE_SHEET: 4,
    }
    assert dict(outcome.findings) == {Check.LENGTH_NOT_PROVEN: 4, Check.STALE_PAYLOAD: 1}
    assert outcome.report == tmp_path / "report" / FINDINGS_FILE


def test_the_report_names_each_finding_by_isin_and_line_sorted(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """Never by company id, which changes when the database is rebuilt."""
    _two_companies(market, payloads)

    load_statements(market, payloads, tmp_path)

    assert _report(tmp_path) == [
        "US00000A0014,Alpha Corp,US,ALPH,cash_flow_statement,2023-12-31,length_not_proven,"
        "left_out,,no fiscal year ends 350 to 380 days before it",
        "US00000A0014,Alpha Corp,US,ALPH,income_statement,2023-12-31,length_not_proven,"
        "left_out,,no fiscal year ends 350 to 380 days before it",
        "US00000B0013,Beta Inc,US,BETA,,2023-06-30,stale_payload,warning,,the latest fiscal "
        "year ends 2023-06-30; the newest in the load ends 2025-12-31",
        "US00000B0013,Beta Inc,US,BETA,cash_flow_statement,2023-06-30,length_not_proven,"
        "left_out,,no fiscal year ends 350 to 380 days before it",
        "US00000B0013,Beta Inc,US,BETA,income_statement,2023-06-30,length_not_proven,"
        "left_out,,no fiscal year ends 350 to 380 days before it",
    ]


def test_a_second_load_replaces_the_tables_and_writes_the_same_report(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """Rows added twice would break the tables' keys: the second load replaces them."""
    _two_companies(market, payloads)
    first = load_statements(market, payloads, tmp_path)
    report = (tmp_path / FINDINGS_FILE).read_bytes()

    second = load_statements(market, payloads, tmp_path)

    assert second == first
    assert (tmp_path / FINDINGS_FILE).read_bytes() == report


def test_a_listing_without_a_payload_and_an_unreadable_payload_are_reported_and_the_run_goes_on(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """Three of four payloads present: enough to load, and the rest is on the report."""
    _company(market, "Alpha Corp", ("US00000A0014", "ALPH", "EC"))
    _company(market, "Beta Inc", ("US00000B0013", "BETA", "EC"))
    _company(market, "Gamma Inc", ("US00000C0012", "GAMA", "EC"))
    _company(market, "Mu Corp", ("US00000M0016", "MUC", "EC"))
    _save(payloads, "ALPH", _body("ALPH", _year("2024-12-31"), _year("2025-12-31")))
    _save(payloads, "BETA", b"<html>")
    (payloads / payload_file("US", "GAMA")).write_bytes(b"not packed")

    outcome = load_statements(market, payloads, tmp_path)

    assert outcome.companies_stored == 1
    assert outcome.findings[Check.NO_PAYLOAD] == 1
    assert outcome.findings[Check.PAYLOAD_NOT_READABLE] == 2
    rows = _report(tmp_path)
    assert any(row.startswith("US00000M0016,Mu Corp,US,MUC,,,no_payload,warning,,") for row in rows)
    assert any(
        row.startswith("US00000B0013,Beta Inc,US,BETA,,,payload_not_readable,left_out,,")
        and "is not an EODHD fundamentals payload" in row
        for row in rows
    )
    assert any(
        row.startswith(
            "US00000C0012,Gamma Inc,US,GAMA,,,payload_not_readable,left_out,,cannot read"
        )
        for row in rows
    )


def test_a_folder_with_fewer_than_half_of_the_payloads_stops_the_load_and_changes_nothing(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """The refresh routine sets the folder aside; a load then must not empty the tables."""
    _two_companies(market, payloads)
    load_statements(market, payloads, tmp_path)
    before = market.path.read_bytes()
    _company(market, "Gamma Inc", ("US00000C0012", "GAMA", "EC"))
    _company(market, "Delta Inc", ("US00000D0011", "DLTA", "EC"))
    _company(market, "Eta Inc", ("US00000H0017", "ETA", "EC"))
    after_listing = market.path.read_bytes()
    report = (tmp_path / FINDINGS_FILE).read_bytes()

    with pytest.raises(FundamentalsError, match="only 2 of 5 listings have a saved payload"):
        load_statements(market, payloads, tmp_path)

    assert market.path.read_bytes() == after_listing != before
    assert (tmp_path / FINDINGS_FILE).read_bytes() == report


def test_half_of_the_payloads_is_enough_to_load(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """The guard is for a folder set aside, not for a few listings without a payload."""
    _company(market, "Alpha Corp", ("US00000A0014", "ALPH", "EC"))
    _company(market, "Beta Inc", ("US00000B0013", "BETA", "EC"))
    _save(payloads, "ALPH", _body("ALPH", _year("2025-12-31")))

    assert load_statements(market, payloads, tmp_path).companies_stored == 1


def test_a_report_that_cannot_be_written_leaves_the_tables_as_they_were(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """The tables and the report are never out of step."""
    _two_companies(market, payloads)
    before = market.path.read_bytes()
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(FundamentalsError, match="cannot write"):
        load_statements(market, payloads, blocked)

    assert market.path.read_bytes() == before


def test_of_a_companys_two_securities_the_common_share_is_read_and_the_other_compared(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """The preferred share's payload has more years but is only compared."""
    _company(
        market,
        "Alpha Corp",
        ("US00000A0022", "ALPH-PA", "EP"),
        ("US00000A0014", "ALPH", "EC"),
    )
    _save(payloads, "ALPH", _body("ALPH", _year("2025-12-31")))
    _save(
        payloads,
        "ALPH-PA",
        _body("ALPH-PA", _year("2024-12-31"), _year("2025-12-31", revenue=1_300_000_000)),
    )

    outcome = load_statements(market, payloads, tmp_path)

    assert outcome.periods == 1
    assert outcome.findings[Check.PAYLOADS_DISAGREE] == 1
    assert any(
        row.startswith("US00000A0022,Alpha Corp,US,ALPH-PA,income_statement,2025-12-31,")
        for row in _report(tmp_path)
    )


def test_the_load_says_how_far_it_is_after_each_company(
    market: Database, payloads: Path, tmp_path: Path
) -> None:
    """What moves the progress bar."""
    _two_companies(market, payloads)
    told: list[tuple[int, int]] = []

    load_statements(
        market, payloads, tmp_path, progress=lambda done, total: told.append((done, total))
    )

    assert told == [(1, 2), (2, 2)]


def test_a_database_without_listings_loads_nothing_and_writes_an_empty_report(
    database: Database, payloads: Path, tmp_path: Path
) -> None:
    """Before the first listing fill there is nothing to read."""
    outcome = load_statements(database, payloads, tmp_path)

    assert (outcome.companies, outcome.periods, dict(outcome.findings)) == (0, 0, {})
    assert _report(tmp_path) == []


@pytest.mark.parametrize("statement", [Statement.INCOME, Statement.CASH_FLOW])
def test_each_figure_of_a_flow_goes_to_the_column_of_its_name(statement: Statement) -> None:
    """A figure the load forgot would be an empty column; each gets its own value."""
    figures = {figure: number for number, figure in enumerate(FIGURES[statement], start=1)}
    row = FlowRow(statement=statement, period_end=date(2025, 12, 31), months=12, figures=figures)

    record = (income_record if statement is Statement.INCOME else cash_flow_record)(7, row)

    assert (record.company_id, record.period_end, record.months) == (7, date(2025, 12, 31), 12)
    assert {figure: getattr(record, figure.value) for figure in figures} == figures


def test_each_figure_of_a_balance_sheet_goes_to_the_column_of_its_name() -> None:
    """The same for the fifteen figures of the balance sheet."""
    figures = {
        figure: number for number, figure in enumerate(FIGURES[Statement.BALANCE_SHEET], start=1)
    }

    record = balance_sheet_record(
        7, BalanceSheetRow(period_end=date(2025, 12, 31), figures=figures)
    )

    assert (record.company_id, record.period_end) == (7, date(2025, 12, 31))
    assert {figure: getattr(record, figure.value) for figure in figures} == figures


def test_a_figure_not_reported_is_an_empty_column() -> None:
    """Never a zero."""
    row = FlowRow(statement=Statement.INCOME, period_end=date(2025, 12, 31), months=12, figures={})

    assert income_record(1, row).revenue is None


def test_the_sample_payload_of_a_listing_is_read_where_the_download_saved_it(
    market: Database, payloads: Path, tmp_path: Path, fundamentals_samples: Path
) -> None:
    """The load finds a payload under the name ``payload_file`` gives it."""
    _company(market, "Beta Inc", ("US00000B0013", "BETA", "EC"))
    path = payloads / payload_file("US", "BETA")
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress((fundamentals_samples / "US_BETA.json").read_bytes()))

    assert load_statements(market, payloads, tmp_path).periods == 3
