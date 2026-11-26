"""The rules that turn holdings lines into companies and instruments (ADR 0006).

The load has three parts. Sorting is pure: it decides for every line whether
it is left out, is an ordinary security or is a depositary receipt, and needs
no database. Placing writes: it finds or adds the company of each line and
adds the instrument. Recording writes what the funds' documents say: one
``fund`` row per fund and one ``holding`` row per line that was loaded, each
pointing at the instrument its line was loaded as (ADR 0017, ADR 0021). Placing
and recording share
one unit of work, so a load is saved whole or not at all (ADR 0009).

Two kinds of decision overrule the filings, each for the security it names.
Where the funds disagree about a company's legal-entity identifier, a decision
says which one holds (ADR 0010, ADR 0011). Where a fund files a placeholder
instead of a company name, a decision gives the name (ADR 0012). In both cases
the decided value is what a line of that security is read as carrying, and
what its company is given.

A third kind of decision keeps a security out of the universe altogether
(ADR 0013): its lines are left out like debt, and reported with their own
reason. A fourth says that a security is a depositary receipt and names the
ordinary share it stands for (ADR 0015): its lines are read as lines of that
share, so the company stays in the universe through the share pyvalue
analyses. The load never deletes, so it refuses a database that already holds
a security of either kind.

Author: Emre Tezel
"""

import re
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, replace
from enum import StrEnum

from pyvalue.db import Company, Database, Fund, Holding, UnitOfWork
from pyvalue.identifiers import is_valid_isin, is_valid_lei
from pyvalue.universe.errors import UniverseError
from pyvalue.universe.exclusions import Exclusion
from pyvalue.universe.holdings import FundHoldings, HoldingLine
from pyvalue.universe.lei_decisions import LeiDecision
from pyvalue.universe.name_decisions import NameDecision
from pyvalue.universe.nport import CONDITIONAL_CATEGORY
from pyvalue.universe.ordinary_shares import OrdinaryShare
from pyvalue.universe.receipts import is_receipt

# The form's category codes for debt and for the six kinds of derivative. A
# line in one of them is not loaded, even when it carries an ISIN (ADR 0006).
_DEBT_OR_DERIVATIVE: frozenset[str] = frozenset({"DBT", "DCO", "DCR", "DE", "DFE", "DIR", "DO"})

# Categories whose lines are loaded when they have a valid ISIN: common and
# preferred equity, short-term investment vehicles (the funds' cash, which in
# practice has no ISIN), and whatever a filer puts in the conditional category.
_LOADABLE: frozenset[str] = frozenset({"EC", "EP", "STIV", CONDITIONAL_CATEGORY})


# A CUSIP is nine characters: letters, digits and three special signs. A SEDOL
# is seven letters or digits. The ``holding`` table accepts nothing else, so a
# value of another shape is stored as no value: it is a typing error or a
# placeholder, not an identifier.
_CUSIP_SHAPE: re.Pattern[str] = re.compile(r"[A-Z0-9*@#]{9}")
_SEDOL_SHAPE: re.Pattern[str] = re.compile(r"[A-Z0-9]{7}")

# What the load says when the database holds a security it is no longer to
# hold. Taking a row out would be the load's first delete, with rules of its
# own for a company left without securities; a rebuild does it in seconds.
_REBUILD: str = (
    "The load does not delete rows, so the database has to be rebuilt: set the file aside, "
    "run `pyvalue db migrate`, then `pyvalue universe load`"
)


class NotLoadedReason(StrEnum):
    """Why a holdings line was not loaded."""

    DEBT_OR_DERIVATIVE = "debt_or_derivative"
    NO_VALID_ISIN = "no_valid_isin"
    RECEIPT_COMPANY_ALREADY_LOADED = "receipt_company_already_loaded"
    EXCLUDED_BY_DECISION = "excluded_by_decision"


class AgentCaseReason(StrEnum):
    """Why a holdings line needs a decision the load does not take."""

    DIFFERENT_LEI = "different_lei"
    LEI_BELONGS_TO_ANOTHER_COMPANY = "lei_belongs_to_another_company"


@dataclass(frozen=True, slots=True)
class NotLoadedLine:
    """A holdings line that was not loaded, and why.

    Attributes:
        fund: The ticker of the fund whose filing holds the line.
        line: The line.
        reason: Why it was not loaded.
    """

    fund: str
    line: HoldingLine
    reason: NotLoadedReason


@dataclass(frozen=True, slots=True)
class AgentCase:
    """A holdings line that contradicts the database, for an agent to decide.

    Attributes:
        fund: The ticker of the fund whose filing holds the line.
        line: The line.
        reason: What the contradiction is.
        company: The company the line's ISIN already belongs to.
        lei_owner: The company that carries the line's legal-entity
            identifier, when there is one. It is never ``company`` itself.
    """

    fund: str
    line: HoldingLine
    reason: AgentCaseReason
    company: Company
    lei_owner: Company | None


@dataclass(frozen=True, slots=True)
class LoadResult:
    """What one load did.

    Attributes:
        lines_read: Lines in all filings, whatever their category.
        securities: Distinct valid ISINs among the lines that are not debt or
            derivatives and not kept out by a decision.
        receipts_recognised: Of those securities, the depositary receipts.
        receipts_kept: Receipts whose company has no other line, so the
            receipt stands for the company and is placed like any security.
        receipts_not_loaded: Receipts of a company that is in the universe
            through its own shares.
        companies_added: Companies this load added.
        instruments_added: Instruments this load added.
        joined_by_lei: New instruments put under an existing company because
            the legal-entity identifier matched.
        joined_by_name: New instruments put under an existing company because
            the name matched.
        leis_filled: Companies without a legal-entity identifier that got one,
            from a line of a security already loaded or from a decision.
        leis_corrected: Companies whose legal-entity identifier a decision
            replaced by another.
        lei_decisions_used: Decisions on legal-entity identifiers about a
            security that these filings hold.
        name_decisions_used: Decisions on company names about a security that
            these filings hold.
        companies_renamed: Companies that a decision gave another name.
        exclusions_used: Securities these filings hold that a decision keeps
            out of the universe.
        ordinary_shares_used: Receipts these filings hold whose lines a
            decision reads as lines of their ordinary share.
        companies: Companies in the database after the load.
        instruments: Instruments in the database after the load.
        holdings_stored: Holding lines the load wrote: every line that
            became, or met, an instrument.
        holdings_with_ticker: Of those, the lines that carry a ticker.
        holdings_with_sedol: Of those, the lines that carry a SEDOL.
        instruments_not_held: Instruments in the database that no holding
            line points at. None after a rebuild; a database loaded from more
            funds than today keeps the securities only the other funds held.
        not_loaded: Every line that was not loaded, in the order of the
            filings.
        agent_cases: Every case for the agent, in the order of the filings.
    """

    lines_read: int
    securities: int
    receipts_recognised: int
    receipts_kept: int
    receipts_not_loaded: int
    companies_added: int
    instruments_added: int
    joined_by_lei: int
    joined_by_name: int
    leis_filled: int
    leis_corrected: int
    lei_decisions_used: int
    name_decisions_used: int
    companies_renamed: int
    exclusions_used: int
    ordinary_shares_used: int
    companies: int
    instruments: int
    holdings_stored: int
    holdings_with_ticker: int
    holdings_with_sedol: int
    instruments_not_held: int
    not_loaded: tuple[NotLoadedLine, ...]
    agent_cases: tuple[AgentCase, ...]

    def not_loaded_for(self, reason: NotLoadedReason) -> int:
        """Return how many lines were not loaded for the given reason."""
        return sum(1 for entry in self.not_loaded if entry.reason is reason)


def name_key(name: str) -> str:
    """Return the form in which two company names are compared.

    Upper and lower case and spacing are ignored and nothing else is:
    punctuation counts, because looser matching joins different companies
    (ADR 0006: Pfizer Inc and Pfizer Ltd, Humana Inc and Humana AB).
    """
    return " ".join(name.casefold().split())


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A line that can be loaded: it has a valid ISIN and is not debt or a derivative.

    Attributes:
        fund: The ticker of the fund whose filing holds the line.
        line: The line as filed.
        isin: The line's ISIN, known to be valid.
        lei: The legal-entity identifier the line is read as carrying: the
            decided one when there is a decision for the security, else the
            filed one when it is valid, else ``None`` (a missing one, or a
            placeholder such as ``N/A``).
        name: The company name the line is read as carrying, as it would be
            stored: the decided one when there is a decision for the security,
            else the filed issuer name with runs of spaces reduced to one.
        key: That name as it is compared.
        named: Whether the name comes from a decision. The company such a
            line belongs to is given the name (ADR 0012).
        swapped: Whether ``isin`` is the ordinary share that a decision names
            for the receipt the fund filed (ADR 0015). Such a line is an
            ordinary line, whatever its title or label says.
    """

    fund: str
    line: HoldingLine
    isin: str
    lei: str | None
    name: str
    key: str
    named: bool
    swapped: bool


@dataclass(frozen=True, slots=True)
class _SortedLines:
    """Every line of every filing, sorted into what happens to it.

    Attributes:
        lines_read: How many lines there were.
        ordinary: The lines of securities that are not receipts, in the order
            of the filings.
        receipts: The lines of receipts, one group per ISIN, groups in the
            order their ISIN first appears.
        left_out: The lines that cannot be loaded at all.
        lei_decisions_used: How many securities with a decided identifier
            occur among the lines.
        name_decisions_used: How many securities with a decided name occur
            among the lines.
        exclusions_used: How many securities that a decision keeps out occur
            among the lines.
        ordinary_shares_used: How many receipts that a decision reads as
            their ordinary share occur among the lines.
    """

    lines_read: int
    ordinary: tuple[_Candidate, ...]
    receipts: tuple[tuple[_Candidate, ...], ...]
    left_out: tuple[NotLoadedLine, ...]
    lei_decisions_used: int
    name_decisions_used: int
    exclusions_used: int
    ordinary_shares_used: int


def _sort_lines(
    funds: Sequence[FundHoldings],
    decided: Mapping[str, str],
    named: Mapping[str, str],
    excluded: frozenset[str],
    ordinary_of: Mapping[str, str],
) -> _SortedLines:
    """Decide for every line whether it is left out, ordinary or a receipt.

    Args:
        funds: The funds, in the order of loading.
        decided: The decided legal-entity identifier of each ISIN that has one.
        named: The decided company name of each ISIN that has one.
        excluded: The ISINs that a decision keeps out of the universe.
        ordinary_of: For each receipt that a decision reads as its ordinary
            share, the ISIN of that share.

    Raises:
        UniverseError: If a line is in a category the load has no rule for,
            or a line with a valid ISIN does not say where it trades.
    """
    lines_read = 0
    candidates: list[_Candidate] = []
    left_out: list[NotLoadedLine] = []
    excluded_held: set[str] = set()
    swapped_held: set[str] = set()
    for holdings in funds:
        fund = holdings.fund.code
        for line in holdings.lines:
            lines_read += 1
            if line.category in _DEBT_OR_DERIVATIVE:
                left_out.append(NotLoadedLine(fund, line, NotLoadedReason.DEBT_OR_DERIVATIVE))
            elif line.category not in _LOADABLE:
                # Loading it would be a guess and so would leaving it out.
                # No fund files such a line today.
                raise UniverseError(
                    f"{fund} line {line.number} ({line.issuer_name}) is in category "
                    f"'{line.category}', which the load has no rule for"
                )
            elif line.isin is None or not is_valid_isin(line.isin):
                left_out.append(NotLoadedLine(fund, line, NotLoadedReason.NO_VALID_ISIN))
            elif line.trading_country is None:
                # Such a line may get a holding row, and the row says where
                # the line trades (ADR 0017). No share line of a filing lacks
                # the country; guessing one would mislead the listing rule.
                raise UniverseError(
                    f"{fund} line {line.number} ({line.issuer_name}) carries a valid ISIN and "
                    "no country, so the load cannot say where it trades"
                )
            elif line.isin in excluded:
                # Asked last, so a line that is left out anyway keeps the
                # reason the filing itself gives. Taken out here, before the
                # receipts are sorted, the line is not a line of its company
                # in the receipt rule either (ADR 0013).
                left_out.append(NotLoadedLine(fund, line, NotLoadedReason.EXCLUDED_BY_DECISION))
                excluded_held.add(line.isin)
            else:
                # A receipt with a known ordinary share is read as that share
                # (ADR 0015). From here on the line is a line of the share:
                # the other decisions are looked up by its ISIN too.
                swapped = line.isin in ordinary_of
                isin = ordinary_of.get(line.isin, line.isin)
                if swapped:
                    swapped_held.add(line.isin)
                lei = line.lei if line.lei is not None and is_valid_lei(line.lei) else None
                # A decision overrules what the fund filed, for the identifier
                # (ADR 0010) and for the name (ADR 0012).
                name = named.get(isin, " ".join(line.issuer_name.split()))
                candidates.append(
                    _Candidate(
                        fund=fund,
                        line=line,
                        isin=isin,
                        lei=decided.get(isin, lei),
                        name=name,
                        key=name_key(name),
                        named=isin in named,
                        swapped=swapped,
                    )
                )

    # A security is a receipt when any of its lines says so. One fund may label
    # a receipt that another files as plain common shares, and it is the same
    # security in both.
    # A line read as an ordinary share is not asked: its wording is the
    # receipt's. And a share a decision names as ordinary is ordinary in every
    # fund's filing.
    receipt_isins = {
        candidate.isin
        for candidate in candidates
        if not candidate.swapped and is_receipt(candidate.line)
    } - set(ordinary_of.values())
    receipt_groups: dict[str, list[_Candidate]] = {}
    ordinary: list[_Candidate] = []
    for candidate in candidates:
        if candidate.isin in receipt_isins:
            receipt_groups.setdefault(candidate.isin, []).append(candidate)
        else:
            ordinary.append(candidate)
    loadable_isins = {candidate.isin for candidate in candidates}
    return _SortedLines(
        lines_read=lines_read,
        ordinary=tuple(ordinary),
        receipts=tuple(tuple(group) for group in receipt_groups.values()),
        left_out=tuple(left_out),
        lei_decisions_used=len(decided.keys() & loadable_isins),
        name_decisions_used=len(named.keys() & loadable_isins),
        exclusions_used=len(excluded_held),
        ordinary_shares_used=len(swapped_held),
    )


class _Placer:
    """Finds or adds the company of a line and adds its instrument.

    It reads both tables once and then answers every lookup from memory. Two
    reasons: comparing names is a business rule and so cannot be a query in a
    repository (ADR 0008), and a query per line would mean tens of thousands
    of them. Every change it makes goes through the repositories of its unit
    of work, and it keeps its own picture in step with them.
    """

    def __init__(self, work: UnitOfWork) -> None:
        """Read the companies and instruments the database already holds."""
        self._work = work
        self._companies: dict[int, Company] = {}
        self._company_by_lei: dict[str, int] = {}
        # Only companies without an identifier are found by name (ADR 0006).
        self._company_by_name: dict[str, int] = {}
        for company in work.companies.all():
            self._remember(company)
        self._company_of_isin: dict[str, int] = {}
        # The id of each instrument, which is what a holding line points at.
        self._instrument_of_isin: dict[str, int] = {}
        for instrument in work.instruments.all():
            self._company_of_isin[instrument.isin] = instrument.company_id
            self._instrument_of_isin[instrument.isin] = instrument.instrument_id
        self.companies_added = 0
        self.instruments_added = 0
        self.joined_by_lei = 0
        self.joined_by_name = 0
        self.leis_filled = 0
        self.leis_corrected = 0
        self.companies_renamed = 0
        self.agent_cases: list[AgentCase] = []
        # The name each company was given by a decision in this run, with the
        # security the decision is about: what tells two decisions apart that
        # call one company by different names.
        self._decided_name: dict[int, tuple[str, str]] = {}

    @property
    def company_count(self) -> int:
        """How many companies the database holds now."""
        return len(self._companies)

    @property
    def instrument_count(self) -> int:
        """How many instruments the database holds now."""
        return len(self._company_of_isin)

    def company(self, company_id: int) -> Company:
        """Return a company as it stands now."""
        return self._companies[company_id]

    def instrument_id(self, isin: str) -> int:
        """Return the id of the instrument with this ISIN, which must be there."""
        return self._instrument_of_isin[isin]

    def held(self, isins: frozenset[str]) -> list[str]:
        """Return which of the given ISINs are instruments already, in order."""
        return sorted(isins & self._company_of_isin.keys())

    def settle(self, decisions: Sequence[LeiDecision]) -> None:
        """Give the company of every decided security its decided identifier.

        Only securities that are already instruments are touched; a decided
        security that is new is placed by its decided identifier when its
        lines are reached. This runs before any line is placed, so that a
        company's other securities are compared with the corrected
        identifier in the same run (ADR 0010).

        A company is left as it is when another company already has the
        decided identifier, or when an earlier decision of this run gave it
        a different one. Both mean that company rows would have to be merged
        or split, which the load does not do; the lines of the security
        then report a case.
        """
        settled: set[int] = set()
        for decision in decisions:
            company_id = self._company_of_isin.get(decision.isin)
            if company_id is None:
                continue
            company = self._companies[company_id]
            if company.lei != decision.lei:
                if company_id in settled or decision.lei in self._company_by_lei:
                    continue
                self._set_lei(company, decision.lei)
            settled.add(company_id)

    def settle_names(self, decisions: Sequence[NameDecision]) -> None:
        """Give the company of every security with a decided name that name.

        Only securities that are already instruments are touched; a new one
        brings its decided name with its line. This runs before any line is
        placed, so that the lines are compared with the names as decided
        (ADR 0012).

        Raises:
            UniverseError: If two decisions call one company by different
                names.
        """
        for decision in decisions:
            company_id = self._company_of_isin.get(decision.isin)
            if company_id is not None:
                self._name(company_id, decision.name, decision.isin)

    def place(self, candidate: _Candidate) -> int:
        """Put one line into the database.

        Args:
            candidate: A line that can be loaded.

        Returns:
            The id of the company the line belongs to: the one its ISIN was
            already under, one found by identifier or name, or a new one.
        """
        existing = self._company_of_isin.get(candidate.isin)
        if existing is not None:
            self._meet_again(candidate, self._companies[existing])
            if candidate.named:
                self._name(existing, candidate.name, candidate.isin)
            return existing

        if candidate.lei is not None:
            company_id = self._company_by_lei.get(candidate.lei)
            if company_id is not None:
                self.joined_by_lei += 1
        else:
            company_id = self._company_by_name.get(candidate.key)
            if company_id is not None:
                self.joined_by_name += 1
        if company_id is None:
            company_id = self._add_company(candidate)
        if candidate.named:
            # The company may have been found by its identifier under the
            # name another line gave it. A decision names the company of its
            # security, whichever line brought the company in.
            self._name(company_id, candidate.name, candidate.isin)

        instrument = self._work.instruments.add(company_id, candidate.isin)
        self._company_of_isin[candidate.isin] = company_id
        self._instrument_of_isin[candidate.isin] = instrument.instrument_id
        self.instruments_added += 1
        return company_id

    def _meet_again(self, candidate: _Candidate, company: Company) -> None:
        """Handle a line whose ISIN is already an instrument.

        The same ISIN is the same security, so a differently spelled name is
        not a conflict. Only the legal-entity identifier can add something or
        contradict.
        """
        if candidate.lei is None or candidate.lei == company.lei:
            return
        owner_id = self._company_by_lei.get(candidate.lei)
        owner = None if owner_id is None else self._companies[owner_id]
        if company.lei is not None:
            self._report(candidate, AgentCaseReason.DIFFERENT_LEI, company, owner)
        elif owner is not None:
            self._report(candidate, AgentCaseReason.LEI_BELONGS_TO_ANOTHER_COMPANY, company, owner)
        else:
            self._set_lei(company, candidate.lei)

    def _set_lei(self, company: Company, lei: str) -> None:
        """Give a company a legal-entity identifier: its first, or another one.

        The caller has made sure that no other company has the identifier.
        """
        self._work.companies.set_lei(company.company_id, lei)
        if company.lei is None:
            # The company has an identifier now, so it is no longer one of the
            # companies that are found by name.
            if self._company_by_name.get(name_key(company.name)) == company.company_id:
                del self._company_by_name[name_key(company.name)]
            self.leis_filled += 1
        else:
            # The old identifier no longer leads to this company. A line that
            # still files it for a new security starts a company of its own.
            del self._company_by_lei[company.lei]
            self.leis_corrected += 1
        self._remember(replace(company, lei=lei))

    def _name(self, company_id: int, name: str, isin: str) -> None:
        """Give a company the name a decision gives the company of a security.

        Args:
            company_id: The company the security belongs to.
            name: The decided name.
            isin: The security the decision is about.

        Raises:
            UniverseError: If a decision about another security of the same
                company gave it a different name in this run. Renaming it
                back and forth would make the result depend on the order of
                the lines, so the file has to be put right first.
        """
        earlier = self._decided_name.get(company_id)
        if earlier is not None and earlier[0] != name:
            raise UniverseError(
                f"{earlier[1]} and {isin} are securities of one company, but the name "
                f"decisions call it '{earlier[0]}' and '{name}'"
            )
        self._decided_name[company_id] = (name, isin)
        company = self._companies[company_id]
        if company.name == name:
            return
        self._work.companies.set_name(company_id, name)
        # The old name no longer leads to this company. Only a company
        # without an identifier is found by name at all.
        if self._company_by_name.get(name_key(company.name)) == company_id:
            del self._company_by_name[name_key(company.name)]
        self.companies_renamed += 1
        self._remember(replace(company, name=name))

    def _report(
        self,
        candidate: _Candidate,
        reason: AgentCaseReason,
        company: Company,
        lei_owner: Company | None,
    ) -> None:
        """Record a case for the agent; the database is left as it is."""
        self.agent_cases.append(
            AgentCase(
                fund=candidate.fund,
                line=candidate.line,
                reason=reason,
                company=company,
                lei_owner=lei_owner,
            )
        )

    def _add_company(self, candidate: _Candidate) -> int:
        """Add the company a line names and return its id."""
        company = self._work.companies.add(candidate.name, candidate.lei)
        self._remember(company)
        self.companies_added += 1
        return company.company_id

    def _remember(self, company: Company) -> None:
        """Take a company, new or changed, into the in-memory picture."""
        self._companies[company.company_id] = company
        if company.lei is not None:
            self._company_by_lei[company.lei] = company.company_id
        else:
            # Should two companies without an identifier share a name (only a
            # hand-made row can cause that), the earlier one is the one found.
            self._company_by_name.setdefault(name_key(company.name), company.company_id)


def _fitting(value: str | None, shape: re.Pattern[str]) -> str | None:
    """Return a value that has the given shape, and ``None`` for any other."""
    return value if value is not None and shape.fullmatch(value) else None


def _holding(fund: str, line: HoldingLine, instrument_id: int) -> Holding:
    """Build the ``holding`` row of one loaded line (ADR 0017, ADR 0021, ADR 0022).

    The row records what the fund's documents say, so the ISIN, the name and
    the identifier are the filed ones, not the decided ones: a receipt read as
    its ordinary share keeps the receipt's ISIN, and that difference is how
    the listing rule recognises it (ADR 0019).

    Args:
        fund: The code of the fund whose filing holds the line.
        line: A line with a valid ISIN and a trading country: one that
            ``_sort_lines`` made a candidate.
        instrument_id: The instrument the line was loaded as.
    """
    # Both are guaranteed by the sorting; the assertions say so to the reader
    # and to the type checker.
    assert line.isin is not None
    assert line.trading_country is not None
    return Holding(
        fund_code=fund,
        line_number=line.number,
        instrument_id=instrument_id,
        isin=line.isin,
        issuer_name=line.issuer_name.strip(),
        title=line.title.strip() or None,
        # A filed identifier that fails its check digits is a typing error
        # (ADR 0009); the row then says that the line gave none.
        lei=line.lei if line.lei is not None and is_valid_lei(line.lei) else None,
        cusip=_fitting(line.cusip, _CUSIP_SHAPE),
        sedol=_fitting(line.sedol, _SEDOL_SHAPE),
        ticker=None if line.ticker is None else line.ticker.strip() or None,
        asset_category=line.category,
        trading_country=line.trading_country,
        currency=line.currency,
    )


def _refuse_contradictions(
    decided_on: Set[str], excluded: frozenset[str], ordinary_of: Mapping[str, str]
) -> None:
    """Stop the load when the decisions files say two things about one security.

    Each file is checked on its own when it is read. What no single reader
    can see is a security that two files treat differently. Left in, such a
    row could never apply and would mislead whoever reads the files.

    Args:
        decided_on: The ISINs that have an identifier or a name decision.
        excluded: The ISINs that are kept out of the universe.
        ordinary_of: For each receipt read as its ordinary share, that share.

    Raises:
        UniverseError: Naming the securities and what the files say of them.
    """
    receipts = ordinary_of.keys()
    checks: tuple[tuple[Set[str], str], ...] = (
        (
            excluded & decided_on,
            "kept out of the universe by one decisions file and given an identifier or a "
            "name by another",
        ),
        (
            excluded & receipts,
            "kept out of the universe by one decisions file and read as an ordinary share "
            "by another",
        ),
        (
            receipts & decided_on,
            "read as an ordinary share, so a decision on the identifier or the name has to "
            "be keyed by that share",
        ),
        (
            set(ordinary_of.values()) & (receipts | excluded),
            "named as an ordinary share by one row and listed as a receipt or kept out of "
            "the universe by another",
        ),
    )
    for isins, what in checks:
        if isins:
            raise UniverseError(
                f"{', '.join(sorted(isins))}: {what}; the files contradict each other"
            )


def load_holdings(
    database: Database,
    funds: Sequence[FundHoldings],
    lei_decisions: Sequence[LeiDecision] = (),
    name_decisions: Sequence[NameDecision] = (),
    exclusions: Sequence[Exclusion] = (),
    ordinary_shares: Sequence[OrdinaryShare] = (),
) -> LoadResult:
    """Load the holdings of the funds into the database.

    Companies and instruments are added by the steps of ADR 0006: lines that
    are debt, derivatives or without a valid ISIN are left out; ordinary
    securities are loaded in the order of the funds; a depositary receipt is
    loaded only when no ordinary line of this run belongs to a company with
    its identifier or its name, or carries its name itself (ADR 0014).

    Decisions overrule the filings, on legal-entity identifiers (ADR 0010)
    and on company names (ADR 0012): first the company of every decided
    security already loaded is given its decided identifier or name, then the
    lines are placed, a line of a decided security being read as carrying the
    decided value.

    A security that a decision keeps out of the universe is not loaded
    (ADR 0013). A receipt that a decision pairs with its ordinary share is
    loaded as that share (ADR 0015). The load never deletes: a database that
    already holds a security of either kind is refused and has to be rebuilt.

    The funds and their lines are recorded as well (ADR 0017, ADR 0021): one
    ``fund`` row per fund, and one ``holding`` row per line that was loaded.
    A line that was not loaded gets no row; it is in the result, and in the
    output file written from it. A fund's rows are a copy of the loaded part
    of its filing, so each load replaces them as a whole.

    Everything is written in one unit of work. Loading the same holdings
    with the same decisions again changes nothing: no company or instrument
    is added, and the rows of ``fund`` and ``holding`` come out the same.

    Args:
        database: The database to load into.
        funds: The funds, in the order they are to be loaded. The first fund
            that names a company decides how its name is stored.
        lei_decisions: The decisions on legal-entity identifiers, at most
            one per ISIN. None by default.
        name_decisions: The decisions on company names, at most one per ISIN.
            None by default.
        exclusions: The securities that are kept out of the universe. None by
            default.
        ordinary_shares: The receipts that are read as their ordinary share,
            at most one decision per receipt. None by default.

    Returns:
        What the load did, including the lines it did not load and the cases
        it left for the agent.

    Raises:
        UniverseError: If a line is in a category the load has no rule for,
            a line with a valid ISIN does not say where it trades, two
            decisions of one kind are about the same ISIN, two name
            decisions call one company by different names, the decisions
            files contradict each other about a security, or the database
            already holds a security that is kept out or read as its ordinary
            share. Nothing is written.
        DatabaseError: If the database is not ready or refuses a row. Nothing
            is written.
    """
    # Sorting comes first and needs no database, so a filing the load cannot
    # handle is refused before a transaction is even opened.
    decided = {decision.isin: decision.lei for decision in lei_decisions}
    if len(decided) != len(lei_decisions):
        raise UniverseError("two decisions are about the same ISIN; a security has one issuer")
    named = {decision.isin: decision.name for decision in name_decisions}
    if len(named) != len(name_decisions):
        raise UniverseError("two name decisions are about the same ISIN; a company has one name")
    excluded = frozenset(exclusion.isin for exclusion in exclusions)
    ordinary_of = {decision.isin: decision.ordinary_isin for decision in ordinary_shares}
    if len(ordinary_of) != len(ordinary_shares):
        raise UniverseError(
            "two decisions name an ordinary share for the same receipt; a receipt stands for one"
        )
    _refuse_contradictions(decided.keys() | named.keys(), excluded, ordinary_of)
    lines = _sort_lines(funds, decided, named, excluded, ordinary_of)
    not_loaded = list(lines.left_out)
    receipts_kept = 0
    receipts_not_loaded = 0
    # Report and record in the order of the filings, whatever order the steps
    # reach the lines in.
    fund_order = {holdings.fund.code: position for position, holdings in enumerate(funds)}

    with database.unit_of_work() as work:
        placer = _Placer(work)
        # Saying so beats leaving the rows in silently (ADR 0013, ADR 0015).
        held = placer.held(excluded)
        if held:
            raise UniverseError(
                f"{database.path} holds securities that a decision keeps out of the universe: "
                f"{', '.join(held)}. {_REBUILD}"
            )
        held = placer.held(frozenset(ordinary_of))
        if held:
            raise UniverseError(
                f"{database.path} holds receipts that a decision reads as their ordinary share: "
                f"{', '.join(held)}. {_REBUILD}"
            )
        # Decisions first, so that every line below is compared with the
        # identifiers and names as they have been decided (ADR 0010, ADR 0012).
        placer.settle(lei_decisions)
        placer.settle_names(name_decisions)

        # Step 4 of ADR 0006: ordinary lines. The companies they belong to are
        # what "already in the universe through its own shares" means below.
        own_share_companies: set[int] = set()
        placed: list[_Candidate] = []
        for candidate in lines.ordinary:
            own_share_companies.add(placer.place(candidate))
            placed.append(candidate)
        own_share_leis = {
            company.lei
            for company in map(placer.company, own_share_companies)
            if company.lei is not None
        }
        own_share_names = {
            name_key(placer.company(company_id).name) for company_id in own_share_companies
        }
        # The stored name is one fund's spelling. Another fund's line for the
        # same share joined by its ISIN, and its spelling was dropped, yet
        # that fund files the very same spelling on the company's receipt. So
        # every name an ordinary line carries counts as a name of its company
        # (ADR 0014).
        own_share_names.update(candidate.key for candidate in lines.ordinary)

        # Step 5: a receipt stands in for its company only when the company
        # has no line of its own.
        for group in lines.receipts:
            if any(
                candidate.lei in own_share_leis or candidate.key in own_share_names
                for candidate in group
            ):
                receipts_not_loaded += 1
                not_loaded.extend(
                    NotLoadedLine(
                        candidate.fund,
                        candidate.line,
                        NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED,
                    )
                    for candidate in group
                )
            else:
                receipts_kept += 1
                for candidate in group:
                    placer.place(candidate)
                    placed.append(candidate)

        # Recording (ADR 0017, ADR 0021). Every instrument exists by now, so
        # each loaded line can point at the one it was loaded as: for a
        # receipt read as its ordinary share that is the share, found by the
        # candidate's ISIN, while the row keeps the ISIN the fund filed.
        rows = [
            _holding(candidate.fund, candidate.line, placer.instrument_id(candidate.isin))
            for candidate in placed
        ]
        for holdings in funds:
            definition = holdings.fund
            work.funds.save(
                Fund(
                    fund_code=definition.code,
                    name=definition.name,
                    scope=definition.scope.value,
                    sec_series_id=definition.series_id,
                    sec_filing_number=definition.filing_number,
                    holdings_date=definition.holdings_date,
                    sponsor_file_date=holdings.sponsor_file_date,
                )
            )
            # The rows of a fund are a copy of its filing: replaced as a
            # whole, so a line the filing no longer has does not linger.
            work.holdings.remove_of_fund(definition.code)
        for row in sorted(rows, key=lambda row: (fund_order[row.fund_code], row.line_number)):
            work.holdings.add(row)
        # Read back, not counted from this run's rows: the table may hold the
        # lines of a fund that an earlier version of the load knew.
        held_instruments = {row.instrument_id for row in work.holdings.all()}
        instruments_not_held = placer.instrument_count - len(held_instruments)

    return LoadResult(
        lines_read=lines.lines_read,
        securities=len({candidate.isin for candidate in lines.ordinary}) + len(lines.receipts),
        receipts_recognised=len(lines.receipts),
        receipts_kept=receipts_kept,
        receipts_not_loaded=receipts_not_loaded,
        companies_added=placer.companies_added,
        instruments_added=placer.instruments_added,
        joined_by_lei=placer.joined_by_lei,
        joined_by_name=placer.joined_by_name,
        leis_filled=placer.leis_filled,
        leis_corrected=placer.leis_corrected,
        lei_decisions_used=lines.lei_decisions_used,
        name_decisions_used=lines.name_decisions_used,
        companies_renamed=placer.companies_renamed,
        exclusions_used=lines.exclusions_used,
        ordinary_shares_used=lines.ordinary_shares_used,
        companies=placer.company_count,
        instruments=placer.instrument_count,
        holdings_stored=len(rows),
        holdings_with_ticker=sum(1 for row in rows if row.ticker is not None),
        holdings_with_sedol=sum(1 for row in rows if row.sedol is not None),
        instruments_not_held=instruments_not_held,
        not_loaded=tuple(
            sorted(not_loaded, key=lambda entry: (fund_order[entry.fund], entry.line.number))
        ),
        agent_cases=tuple(
            sorted(placer.agent_cases, key=lambda case: (fund_order[case.fund], case.line.number))
        ),
    )
