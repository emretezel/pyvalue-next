"""The statements load: the saved payloads into the statement tables (ADR 0029, ADR 0030).

``pyvalue fundamentals load`` reads every saved fundamentals payload of the
listings, works out each company's fiscal years and checks every row, and
replaces the four statement tables as a whole. Everything it found is
written to ``data/fundamentals/findings.csv``.

The load reads files and the database only: it never contacts the provider.
It is plain code with no clock in it, so the same payloads give the same
rows and the same report. It runs on one process and takes about a minute
for all listings: the tables are replaced whole on every run, so nothing
keeps track of what changed.

Author: Emre Tezel
"""

import gzip
import zlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

from pyvalue.db import (
    BalanceSheet,
    CashFlowStatement,
    Database,
    IncomeStatement,
    ReportingPeriod,
    UnitOfWork,
)
from pyvalue.fundamentals.checks import Check, Finding, is_stale
from pyvalue.fundamentals.errors import FundamentalsError
from pyvalue.fundamentals.findings import Security, write_findings
from pyvalue.fundamentals.report import DEFAULT_REPORT_DIR
from pyvalue.fundamentals.saved_payloads import DEFAULT_PAYLOADS_DIR, payload_file
from pyvalue.fundamentals.statements import (
    BalanceSheetRow,
    CompanyStatements,
    FlowRow,
    Payload,
    company_statements,
)
from pyvalue.providers import ProviderError
from pyvalue.providers.eodhd import PROVIDER_CODE
from pyvalue.providers.eodhd_statements import read_statements
from pyvalue.providers.statements import Figure, Statement

# Told how many companies are done out of how many, after each company.
type Progress = Callable[[int, int], None]

# The asset category of a preferred share on a holding line (ADR 0017).
_PREFERRED: str = "EP"


@dataclass(frozen=True, slots=True)
class _Listed:
    """One listed security of a company, with where its payload is."""

    security: Security
    preferred: bool
    payload: Path


@dataclass(frozen=True, slots=True)
class StatementsLoad:
    """What a load stored and found.

    Attributes:
        companies: The companies with a listing at the provider.
        companies_stored: Those that have at least one statement stored.
        periods: The reporting periods stored.
        rows: The statements stored, by statement.
        findings: The findings, by check, in the order of ``Check``. A check
            that found nothing is left out.
        report: Where the findings were written.
    """

    companies: int
    companies_stored: int
    periods: int
    rows: Mapping[Statement, int]
    findings: Mapping[Check, int]
    report: Path


def income_record(company_id: int, row: FlowRow) -> IncomeStatement:
    """Return the row of ``income_statement`` for an income statement to store.

    Each figure goes to the column of its name (ADR 0029).
    """
    figures = row.figures
    return IncomeStatement(
        company_id=company_id,
        period_end=row.period_end,
        months=row.months,
        revenue=figures.get(Figure.REVENUE),
        cost_of_revenue=figures.get(Figure.COST_OF_REVENUE),
        gross_profit=figures.get(Figure.GROSS_PROFIT),
        operating_income=figures.get(Figure.OPERATING_INCOME),
        pretax_income=figures.get(Figure.PRETAX_INCOME),
        income_tax=figures.get(Figure.INCOME_TAX),
        net_income=figures.get(Figure.NET_INCOME),
        interest_expense=figures.get(Figure.INTEREST_EXPENSE),
    )


def cash_flow_record(company_id: int, row: FlowRow) -> CashFlowStatement:
    """Return the row of ``cash_flow_statement`` for a cash-flow statement to store."""
    figures = row.figures
    return CashFlowStatement(
        company_id=company_id,
        period_end=row.period_end,
        months=row.months,
        operating_cash_flow=figures.get(Figure.OPERATING_CASH_FLOW),
        capital_expenditure=figures.get(Figure.CAPITAL_EXPENDITURE),
        depreciation_amortization=figures.get(Figure.DEPRECIATION_AMORTIZATION),
        dividends_paid=figures.get(Figure.DIVIDENDS_PAID),
        net_share_sales=figures.get(Figure.NET_SHARE_SALES),
    )


def balance_sheet_record(company_id: int, row: BalanceSheetRow) -> BalanceSheet:
    """Return the row of ``balance_sheet`` for a balance sheet to store."""
    figures = row.figures
    return BalanceSheet(
        company_id=company_id,
        period_end=row.period_end,
        total_assets=figures.get(Figure.TOTAL_ASSETS),
        total_liabilities=figures.get(Figure.TOTAL_LIABILITIES),
        equity=figures.get(Figure.EQUITY),
        minority_interest=figures.get(Figure.MINORITY_INTEREST),
        cash=figures.get(Figure.CASH),
        short_term_investments=figures.get(Figure.SHORT_TERM_INVESTMENTS),
        cash_and_short_term_investments=figures.get(Figure.CASH_AND_SHORT_TERM_INVESTMENTS),
        short_term_debt=figures.get(Figure.SHORT_TERM_DEBT),
        long_term_debt=figures.get(Figure.LONG_TERM_DEBT),
        total_debt_stated=figures.get(Figure.TOTAL_DEBT_STATED),
        lease_obligations=figures.get(Figure.LEASE_OBLIGATIONS),
        current_assets=figures.get(Figure.CURRENT_ASSETS),
        current_liabilities=figures.get(Figure.CURRENT_LIABILITIES),
        noncurrent_liabilities=figures.get(Figure.NONCURRENT_LIABILITIES),
        shares_outstanding=figures.get(Figure.SHARES_OUTSTANDING),
    )


def _companies(database: Database, payloads_dir: Path) -> dict[int, tuple[_Listed, ...]]:
    """Return every company with a listing at the provider, with its listed securities.

    The listings come from the view ``provider_listing_address`` (ADR 0002),
    as for the download. A security is a preferred share when every holding
    line it was loaded from says so.
    """
    with database.unit_of_work() as work:
        instrument_of = {each.listing_id: each.instrument_id for each in work.listings.all()}
        instruments = {each.instrument_id: each for each in work.instruments.all()}
        name_of = {each.company_id: each.name for each in work.companies.all()}
        categories: dict[int, set[str]] = {}
        for holding in work.holdings.all():
            categories.setdefault(holding.instrument_id, set()).add(holding.asset_category)
        addresses = work.provider_listings.addresses_of_provider(PROVIDER_CODE)
    companies: dict[int, list[_Listed]] = {}
    for address in addresses:
        instrument = instruments[instrument_of[address.listing_id]]
        companies.setdefault(instrument.company_id, []).append(
            _Listed(
                security=Security(
                    isin=instrument.isin,
                    company=name_of[instrument.company_id],
                    provider_exchange_code=address.provider_exchange_code,
                    provider_symbol=address.provider_symbol,
                ),
                preferred=categories.get(instrument.instrument_id) == {_PREFERRED},
                payload=payloads_dir
                / payload_file(address.provider_exchange_code, address.provider_symbol),
            )
        )
    return {company: tuple(listed) for company, listed in sorted(companies.items())}


def _require_payloads(companies: Mapping[int, Sequence[_Listed]], payloads_dir: Path) -> None:
    """Refuse a load from a folder that holds fewer than half of the payloads.

    The tables are replaced as a whole, so a load from a folder that was set
    aside for a refresh would empty them (ADR 0029). A few missing payloads
    are reported instead; the run goes on.
    """
    listed = [each for securities in companies.values() for each in securities]
    present = sum(1 for each in listed if each.payload.is_file())
    if present * 2 < len(listed):
        raise FundamentalsError(
            f"only {present:,} of {len(listed):,} listings have a saved payload in "
            f"{payloads_dir}, so the load would empty most of the statement tables; it changed "
            "nothing. Put the payload folder back, or run `pyvalue fundamentals download`"
        )


def _read(listed: _Listed) -> Payload | Finding:
    """Read one listed security's payload, or say why it cannot be."""
    isin = listed.security.isin
    if not listed.payload.is_file():
        return Finding(isin=isin, check=Check.NO_PAYLOAD, detail=f"{listed.payload} is not there")
    try:
        body = gzip.decompress(listed.payload.read_bytes())
        reported = read_statements(body, str(listed.payload))
    except (OSError, EOFError, zlib.error) as error:
        return Finding(
            isin=isin,
            check=Check.PAYLOAD_NOT_READABLE,
            detail=f"cannot read {listed.payload}: {error}",
        )
    except ProviderError as error:
        return Finding(isin=isin, check=Check.PAYLOAD_NOT_READABLE, detail=str(error))
    return Payload(isin=isin, preferred=listed.preferred, reported=reported)


def _store(work: UnitOfWork, company_id: int, statements: CompanyStatements) -> Counter[Statement]:
    """Add one company's periods and statements, and count the statements."""
    stored: Counter[Statement] = Counter()
    for period in statements.periods:
        work.reporting_periods.add(
            ReportingPeriod(
                company_id=company_id, period_end=period.period_end, currency=period.currency
            )
        )
    for row in statements.rows:
        if isinstance(row, BalanceSheetRow):
            work.balance_sheets.add(balance_sheet_record(company_id, row))
        elif row.statement is Statement.INCOME:
            work.income_statements.add(income_record(company_id, row))
        else:
            work.cash_flow_statements.add(cash_flow_record(company_id, row))
        stored[row.statement] += 1
    return stored


def load_statements(
    database: Database,
    payloads_dir: Path = DEFAULT_PAYLOADS_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    progress: Progress | None = None,
) -> StatementsLoad:
    """Replace the statement tables with what the saved payloads hold.

    Args:
        database: The database, at the latest schema version.
        payloads_dir: Where the payloads are saved (ADR 0028).
        report_dir: Where the findings are written.
        progress: Told after each company how many are done out of how many.

    Returns:
        What was stored and found.

    Raises:
        FundamentalsError: If fewer than half of the listings have a saved
            payload, or the report cannot be written. The tables are then as
            they were.
        DatabaseError: If the database is missing or not at the latest
            schema version, or refuses a row.
    """
    companies = _companies(database, payloads_dir)
    _require_payloads(companies, payloads_dir)
    securities = {
        each.security.isin: each.security for listed in companies.values() for each in listed
    }
    findings: list[Finding] = []
    stored: Counter[Statement] = Counter()
    # The end of each stored company's latest year, by the ISIN whose payload was read.
    ends: dict[str, date] = {}
    periods = 0
    with database.unit_of_work() as work:
        # Statements first: a period that a statement points at cannot go.
        work.income_statements.remove_all()
        work.cash_flow_statements.remove_all()
        work.balance_sheets.remove_all()
        work.reporting_periods.remove_all()
        for done, (company_id, listed) in enumerate(companies.items(), start=1):
            payloads: list[Payload] = []
            for each in listed:
                read = _read(each)
                if isinstance(read, Finding):
                    findings.append(read)
                else:
                    payloads.append(read)
            statements = company_statements(payloads)
            findings.extend(statements.findings)
            stored.update(_store(work, company_id, statements))
            periods += len(statements.periods)
            if statements.isin is not None and statements.latest is not None:
                ends[statements.isin] = statements.latest
            if progress is not None:
                progress(done, len(companies))
        findings.extend(_stale(ends))
        # Written inside the transaction: if the report cannot be written, the
        # tables are not replaced either, and the two never disagree.
        report = write_findings(findings, securities, report_dir)
    counts = Counter(finding.check for finding in findings)
    return StatementsLoad(
        companies=len(companies),
        companies_stored=len(ends),
        periods=periods,
        rows=MappingProxyType({statement: stored[statement] for statement in Statement}),
        findings=MappingProxyType({check: counts[check] for check in Check if counts[check]}),
        report=report,
    )


def _stale(ends: Mapping[str, date]) -> list[Finding]:
    """Report the companies whose latest year is old against the newest in the load.

    Measured against the data, never against today, so the same payloads
    always give the same report (ADR 0030).

    Args:
        ends: The end of each stored company's latest year, by the ISIN whose
            payload was read.
    """
    if not ends:
        return []
    reference = max(ends.values())
    return [
        Finding(
            isin=isin,
            check=Check.STALE_PAYLOAD,
            period_end=end,
            detail=f"the latest fiscal year ends {end.isoformat()}; the newest in the load "
            f"ends {reference.isoformat()}",
        )
        for isin, end in sorted(ends.items())
        if is_stale(end, reference)
    ]
