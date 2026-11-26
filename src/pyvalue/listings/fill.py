"""The listing fill: give every security the listing the rule or a decision names.

``pyvalue listings fill`` reads what the database holds, hands it to the plan
of ``pyvalue.listings.plan``, writes the listings the plan chose and the
report of the securities it could not fill (ADR 0019, ADR 0026).

It reads the database and the decisions file, and writes the database and one
file. It cannot reach the network. Everything it writes to the database is
one transaction: a run that stops halfway leaves no listing behind.

Author: Emre Tezel
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pyvalue.db import Database, ProviderListing, UnitOfWork
from pyvalue.listings.decisions import ListingDecision, packaged_listing_decisions
from pyvalue.listings.plan import Markets, Plan, StoredListing, plan_listings
from pyvalue.listings.report import DEFAULT_REPORT_DIR, write_cases
from pyvalue.listings.rule import HeldLine, Line, Lines, Security
from pyvalue.providers.eodhd import PROVIDER_CODE, currency_of

# The scope of a fund that is not expected to hold US-coded ISINs (ADR 0017).
_NON_US: str = "NON_US"


@dataclass(frozen=True, slots=True)
class ListingsFill:
    """What a run of the listing fill did.

    Attributes:
        securities: How many securities the universe has.
        plan: What became of each of them. Its fills have been written.
        unreadable_currencies: The provider's currency codes that could not
            be read, with the number of stored lines that carry each. Such a
            line can never become a listing (ADR 0026).
        report: The file the securities for the agent were written to.
    """

    securities: int
    plan: Plan
    unreadable_currencies: Mapping[str, int]
    report: Path


def _securities(work: UnitOfWork) -> tuple[Security, ...]:
    """Return every security with what the funds say about it."""
    non_us = {fund.fund_code for fund in work.funds.all() if fund.scope == _NON_US}
    held: dict[int, list[HeldLine]] = defaultdict(list)
    # The holding lines come by fund and then in the order of the filing, and
    # stay in that order: it decides which ticker is named first on the report.
    for holding in work.holdings.all():
        held[holding.instrument_id].append(
            HeldLine(
                non_us_fund=holding.fund_code in non_us,
                country=holding.trading_country,
                currency=holding.currency,
                ticker=holding.ticker,
                filed_isin=holding.isin,
            )
        )
    name_of = {company.company_id: company.name for company in work.companies.all()}
    return tuple(
        Security(
            instrument_id=instrument.instrument_id,
            isin=instrument.isin,
            company=name_of[instrument.company_id],
            held=tuple(held.get(instrument.instrument_id, ())),
        )
        for instrument in work.instruments.all()
    )


def _lines(work: UnitOfWork, country_of: Mapping[str, str]) -> tuple[Line, ...]:
    """Return the provider's stored lines, each with its country and its currency."""
    return tuple(
        Line(
            stored=stored,
            country=country_of[stored.mic],
            currency=currency_of(stored.provider_currency),
        )
        for stored in work.provider_symbols.of_provider(PROVIDER_CODE)
    )


def _stored_listings(work: UnitOfWork, code_of: Mapping[str, str]) -> tuple[StoredListing, ...]:
    """Return the listings that exist, each with the provider's line it stands for."""
    symbol_of = {
        each.listing_id: each.provider_symbol
        for each in work.provider_listings.of_provider(PROVIDER_CODE)
    }
    stored: list[StoredListing] = []
    for listing in work.listings.all():
        symbol = symbol_of.get(listing.listing_id)
        code = code_of.get(listing.mic)
        stored.append(
            StoredListing(
                instrument_id=listing.instrument_id,
                mic=listing.mic,
                ticker=listing.ticker,
                line=(None if symbol is None or code is None else (PROVIDER_CODE, code, symbol)),
            )
        )
    return tuple(stored)


def fill_listings(
    database: Database,
    decisions: Sequence[ListingDecision] | None = None,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> ListingsFill:
    """Fill the listings of the securities that have none, and report the rest.

    Running it again changes nothing: a security that has a listing is
    skipped, and the same database and decisions give the same report.

    Args:
        database: The database to read and to write.
        decisions: The decisions on listings. Defaults to the file shipped
            with pyvalue.
        report_dir: The folder the report is written to; created when
            missing.

    Returns:
        What the run did.

    Raises:
        ListingsError: If the decisions file is invalid, a listing that
            exists contradicts a decision, or the report cannot be written.
        DatabaseError: If the database cannot be used.
    """
    chosen = packaged_listing_decisions() if decisions is None else decisions
    with database.unit_of_work() as work:
        country_of = {exchange.mic: exchange.country for exchange in work.exchanges.all()}
        mappings = work.provider_exchanges.of_provider(PROVIDER_CODE)
        codes_of_country: dict[str, set[str]] = defaultdict(set)
        for mapping in mappings:
            codes_of_country[country_of[mapping.mic]].add(mapping.provider_exchange_code)
        lines = _lines(work, country_of)
        securities = _securities(work)
        plan = plan_listings(
            securities,
            Lines(lines),
            Markets(
                codes_of_country={
                    country: frozenset(codes) for country, codes in codes_of_country.items()
                },
                stored_codes=frozenset(line.stored.provider_exchange_code for line in lines),
            ),
            chosen,
            _stored_listings(
                work, {mapping.mic: mapping.provider_exchange_code for mapping in mappings}
            ),
        )
        for planned in plan.fills:
            fill = planned.fill
            listing = work.listings.add(
                fill.security.instrument_id, fill.line.stored.mic, fill.ticker, fill.currency
            )
            # The symbol exactly as the provider gives it: it can differ from
            # the listing's ticker, and it is what a request is made with.
            work.provider_listings.add(
                ProviderListing(
                    provider_code=PROVIDER_CODE,
                    listing_id=listing.listing_id,
                    provider_symbol=fill.line.symbol,
                )
            )
    # After the transaction: a report of listings that were not saved would
    # describe a run that did not happen.
    report = write_cases(plan.cases, report_dir)
    unreadable = Counter(line.stored.provider_currency for line in lines if line.currency is None)
    return ListingsFill(
        securities=len(securities),
        plan=plan,
        unreadable_currencies=MappingProxyType(dict(sorted(unreadable.items()))),
        report=report,
    )
