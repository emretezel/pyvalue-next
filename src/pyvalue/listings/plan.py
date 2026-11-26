"""What one run of the listing fill does: every security sorted, every listing chosen.

``pyvalue.listings.rule`` answers for one security. This module answers for a
whole run (ADR 0026): which securities are left alone and why, what the
decisions file says about the others, which get a listing from the rule, and
which of two securities gets an exchange and ticker both want.

It is one pure function of what is stored and what is decided. Nothing here
reads or writes: ``pyvalue.listings.fill`` hands it the contents of the
database and writes what it returns. That is what lets "a second run changes
nothing" be tested without a database.

Author: Emre Tezel
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pyvalue.errors import REBUILD_STEPS
from pyvalue.listings.decisions import ListingDecision
from pyvalue.listings.errors import ListingsError
from pyvalue.listings.rule import (
    Case,
    Fill,
    Line,
    Lines,
    Reason,
    Security,
    judge,
    listing_ticker,
    shown_lines,
)

# How many securities a refusal names before it only counts the rest.
_NAMED_AT_MOST: int = 10

# What a person does when the database and the decisions file disagree. The
# fill never changes a listing (ADR 0019), so the listings are derived again.
_REBUILD: str = f"A run never changes a listing, so the database has to be rebuilt: {REBUILD_STEPS}"


@dataclass(frozen=True, slots=True)
class Markets:
    """Where the provider has exchanges, and which of its symbol lists are stored.

    Attributes:
        codes_of_country: For each country in which the provider has an
            exchange of ours, its exchange codes there. Korea has two: one
            for KOSPI and one for KOSDAQ.
        stored_codes: The exchange codes that have at least one stored line.
    """

    codes_of_country: Mapping[str, frozenset[str]]
    stored_codes: frozenset[str]

    def serves_any(self, countries: Iterable[str]) -> bool:
        """Say whether the provider has an exchange in at least one of the countries."""
        return any(country in self.codes_of_country for country in countries)

    def missing_lists(self, countries: Iterable[str]) -> tuple[str, ...]:
        """Return the exchange codes of the countries that have no stored list, in order.

        The rule asks whether a line is the only one of its kind in a
        country. It cannot know while one of the country's lists is missing.
        """
        wanted: set[str] = set()
        for country in countries:
            wanted |= self.codes_of_country.get(country, frozenset())
        return tuple(sorted(wanted - self.stored_codes))


@dataclass(frozen=True, slots=True)
class StoredListing:
    """A listing that exists, as far as a run reads it.

    Attributes:
        instrument_id: The security that has the listing.
        mic: The exchange it is on.
        ticker: Its ticker there.
        line: The provider's line the listing stands for, named by provider,
            exchange code and symbol, or ``None`` when the provider has no
            symbol for the listing.
    """

    instrument_id: int
    mic: str
    ticker: str
    line: tuple[str, str, str] | None


@dataclass(frozen=True, slots=True)
class PlannedFill:
    """A listing a run writes.

    Attributes:
        fill: The security, the line, and the listing's ticker and currency.
        decided: Whether a decision named the line. Otherwise the rule
            found it.
    """

    fill: Fill
    decided: bool


@dataclass(frozen=True, slots=True)
class Plan:
    """What a run does with every security (ADR 0026).

    Each security is in exactly one of ``fills``, ``cases``, ``decided_none``,
    ``not_held``, ``not_served`` and ``waiting``, or is counted in
    ``already_listed``.

    Attributes:
        fills: The listings to write, in the order they were chosen: the
            decided ones first, then the rule's, each in ISIN order.
        cases: The securities for the report, in ISIN order.
        already_listed: How many securities had a listing and were skipped.
        decided_none: The securities a decision gives no listing.
        not_held: The securities no fund holds.
        not_served: The securities whose home markets the provider does not
            serve.
        waiting: The securities held back because a symbol list of a home
            country is not stored.
        missing_lists: The exchange codes whose missing lists hold those
            securities back, in order.
        unknown_decisions: The ISINs the decisions file names that are not
            securities of the universe, in the order of the file.
    """

    fills: tuple[PlannedFill, ...]
    cases: tuple[Case, ...]
    already_listed: int
    decided_none: tuple[Security, ...]
    not_held: tuple[Security, ...]
    not_served: tuple[Security, ...]
    waiting: tuple[Security, ...]
    missing_lists: tuple[str, ...]
    unknown_decisions: tuple[str, ...]

    @property
    def filled_by_rule(self) -> tuple[Fill, ...]:
        """The listings the rule found, in ISIN order."""
        return tuple(each.fill for each in self.fills if not each.decided)

    @property
    def filled_by_decision(self) -> tuple[Fill, ...]:
        """The listings a decision named, in ISIN order."""
        return tuple(each.fill for each in self.fills if each.decided)


def by_country(securities: Iterable[Security]) -> dict[str, int]:
    """Count securities by home country, the country with the most first.

    A security held in two countries is counted under both, so the counts
    can add up to more than there are securities.

    Args:
        securities: The securities to count.
    """
    counts = Counter(country for security in securities for country in security.home_countries)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _named(line: tuple[str, str, str]) -> str:
    """Return a line the way a decision names it, for a message or the report."""
    return " ".join(line)


def _refuse_contradictions(
    decisions: Mapping[str, ListingDecision],
    securities: Sequence[Security],
    stored: Mapping[int, StoredListing],
) -> None:
    """Stop when a listing that exists is not what its security's decision says.

    A decision that says what the listing already is, is simply not applied
    again; that is every decided security on a second run.

    Raises:
        ListingsError: If a security has a listing and a decision of ``none``,
            or a decision that names another line. Every such security is
            counted and the first few are named.
    """
    contradicted: list[str] = []
    for security in securities:
        decision = decisions.get(security.isin)
        listing = stored.get(security.instrument_id)
        if decision is None or listing is None:
            continue
        if decision.line is None or decision.line != listing.line:
            contradicted.append(security.isin)
    if contradicted:
        named = ", ".join(contradicted[:_NAMED_AT_MOST])
        more = len(contradicted) - _NAMED_AT_MOST
        raise ListingsError(
            f"{len(contradicted)} securities have a listing that is not what the decisions "
            f"file says: {named}{f' and {more} more' if more > 0 else ''}. {_REBUILD}"
        )


def _may_name(security: Security, line: Line) -> bool:
    """Say whether a decision for this security may name this line (ADR 0026).

    A stand-in line stays out for a decision too: the line has to be in a
    home market. The one exception is a receipt read as its ordinary share,
    whose holding line names the receipt's market; there a line that carries
    the share's own ISIN is the share, wherever it trades.
    """
    if line.country in security.home_countries:
        return True
    return security.read_as_ordinary_share and line.stored.isin == security.isin


def _decided(security: Security, named: tuple[str, str, str], lines: Lines) -> Fill | Case:
    """Return the listing a decision asks for, or the case that says why it cannot be given."""
    line = lines.at(*named)
    reason: Reason
    if line is None:
        reason = Reason.DECISION_LINE_NOT_STORED
    elif not _may_name(security, line):
        reason = Reason.DECISION_LINE_NOT_ALLOWED
    elif line.currency is None:
        reason = Reason.DECISION_CURRENCY_UNREADABLE
    else:
        return Fill(security, line, listing_ticker(security, line), line.currency)
    return Case(security, reason, _named(named), shown_lines(security, lines))


def plan_listings(
    securities: Sequence[Security],
    lines: Lines,
    markets: Markets,
    decisions: Sequence[ListingDecision],
    stored: Sequence[StoredListing],
) -> Plan:
    """Work out what one run of the listing fill does.

    Args:
        securities: Every security of the universe, with its holding lines.
        lines: The provider's stored lines.
        markets: Where the provider has exchanges and which lists are stored.
        decisions: The decisions file.
        stored: The listings that exist.

    Returns:
        What to write and what to report.

    Raises:
        ListingsError: If a listing that exists contradicts a decision.
    """
    by_isin = {security.isin: security for security in securities}
    decision_of = {decision.isin: decision for decision in decisions}
    listing_of = {listing.instrument_id: listing for listing in stored}
    _refuse_contradictions(decision_of, securities, listing_of)

    # Who holds each exchange and ticker. A listing that exists keeps its pair.
    isin_of = {security.instrument_id: security.isin for security in securities}
    taken: dict[tuple[str, str], str] = {
        (listing.mic, listing.ticker): isin_of[listing.instrument_id] for listing in stored
    }

    not_held: list[Security] = []
    not_served: list[Security] = []
    waiting: list[Security] = []
    missing: set[str] = set()
    decided: list[tuple[Security, ListingDecision]] = []
    for_the_rule: list[Security] = []
    already_listed = 0
    # ISIN order throughout, so that two runs on the same data do the same.
    for security in sorted(securities, key=lambda each: each.isin):
        if security.instrument_id in listing_of:
            already_listed += 1
        elif not security.held:
            not_held.append(security)
        elif not markets.serves_any(security.home_countries):
            not_served.append(security)
        elif without_list := markets.missing_lists(security.home_countries):
            waiting.append(security)
            missing.update(without_list)
        elif security.isin in decision_of:
            decided.append((security, decision_of[security.isin]))
        else:
            for_the_rule.append(security)

    fills: list[PlannedFill] = []
    cases: list[Case] = []
    decided_none: list[Security] = []

    def settle(outcome: Fill | Case, *, was_decided: bool) -> None:
        """Keep a fill unless its exchange and ticker are taken; keep a case as it is."""
        if isinstance(outcome, Case):
            cases.append(outcome)
            return
        pair = (outcome.line.stored.mic, outcome.ticker)
        holder = taken.get(pair)
        if holder is not None:
            cases.append(
                Case(
                    outcome.security,
                    Reason.EXCHANGE_AND_TICKER_TAKEN,
                    f"{pair[0]} {pair[1]} is the listing of {holder}",
                    shown_lines(outcome.security, lines),
                )
            )
            return
        taken[pair] = outcome.security.isin
        fills.append(PlannedFill(outcome, decided=was_decided))

    # The decided securities first: a line a person or the agent chose wins
    # an exchange and ticker over a line the rule would take.
    for security, decision in decided:
        if decision.line is None:
            decided_none.append(security)
        else:
            settle(_decided(security, decision.line, lines), was_decided=True)
    for security in for_the_rule:
        settle(judge(security, lines), was_decided=False)

    return Plan(
        fills=tuple(fills),
        cases=tuple(sorted(cases, key=lambda case: case.security.isin)),
        already_listed=already_listed,
        decided_none=tuple(decided_none),
        not_held=tuple(not_held),
        not_served=tuple(not_served),
        waiting=tuple(waiting),
        missing_lists=tuple(sorted(missing)),
        unknown_decisions=tuple(
            decision.isin for decision in decisions if decision.isin not in by_isin
        ),
    )
