"""The rules that turn holdings lines into companies and instruments (ADR 0006).

The load has two parts. Sorting is pure: it decides for every line whether it
is left out, is an ordinary security or is a depositary receipt, and needs no
database. Placing writes: it finds or adds the company of each line and adds
the instrument, all inside one unit of work, so a load is saved whole or not
at all (ADR 0009).

Author: Emre Tezel
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from pyvalue.db import Company, Database, UnitOfWork
from pyvalue.universe.errors import UniverseError
from pyvalue.universe.identifiers import is_valid_isin, is_valid_lei
from pyvalue.universe.nport import CONDITIONAL_CATEGORY, HoldingLine
from pyvalue.universe.receipts import is_receipt

# The form's category codes for debt and for the six kinds of derivative. A
# line in one of them is not loaded, even when it carries an ISIN (ADR 0006).
_DEBT_OR_DERIVATIVE: frozenset[str] = frozenset({"DBT", "DCO", "DCR", "DE", "DFE", "DIR", "DO"})

# Categories whose lines are loaded when they have a valid ISIN: common and
# preferred equity, short-term investment vehicles (the funds' cash, which in
# practice has no ISIN), and whatever a filer puts in the conditional category.
_LOADABLE: frozenset[str] = frozenset({"EC", "EP", "STIV", CONDITIONAL_CATEGORY})


class NotLoadedReason(StrEnum):
    """Why a holdings line was not loaded."""

    DEBT_OR_DERIVATIVE = "debt_or_derivative"
    NO_VALID_ISIN = "no_valid_isin"
    RECEIPT_COMPANY_ALREADY_LOADED = "receipt_company_already_loaded"


class AgentCaseReason(StrEnum):
    """Why a holdings line needs a decision the load does not take."""

    DIFFERENT_LEI = "different_lei"
    LEI_BELONGS_TO_ANOTHER_COMPANY = "lei_belongs_to_another_company"


@dataclass(frozen=True, slots=True)
class FundHoldings:
    """The lines of one fund's filing.

    Attributes:
        ticker: The fund's ticker, which names the fund in the load output.
        lines: Every line of the filing, in its order.
    """

    ticker: str
    lines: tuple[HoldingLine, ...]


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
            derivatives.
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
        leis_filled: Companies that got their legal-entity identifier from a
            line of a security already loaded.
        companies: Companies in the database after the load.
        instruments: Instruments in the database after the load.
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
    companies: int
    instruments: int
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
        lei: The line's legal-entity identifier when it is a valid one;
            ``None`` for a missing one and for a placeholder such as ``N/A``.
        name: The issuer name as it would be stored: runs of spaces reduced
            to one.
        key: The issuer name as it is compared.
    """

    fund: str
    line: HoldingLine
    isin: str
    lei: str | None
    name: str
    key: str


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
    """

    lines_read: int
    ordinary: tuple[_Candidate, ...]
    receipts: tuple[tuple[_Candidate, ...], ...]
    left_out: tuple[NotLoadedLine, ...]


def _sort_lines(funds: Sequence[FundHoldings]) -> _SortedLines:
    """Decide for every line whether it is left out, ordinary or a receipt.

    Raises:
        UniverseError: If a line is in a category the load has no rule for.
    """
    lines_read = 0
    candidates: list[_Candidate] = []
    left_out: list[NotLoadedLine] = []
    for fund in funds:
        for line in fund.lines:
            lines_read += 1
            if line.category in _DEBT_OR_DERIVATIVE:
                left_out.append(
                    NotLoadedLine(fund.ticker, line, NotLoadedReason.DEBT_OR_DERIVATIVE)
                )
            elif line.category not in _LOADABLE:
                # Loading it would be a guess and so would leaving it out.
                # None of the three funds files such a line today.
                raise UniverseError(
                    f"{fund.ticker} line {line.number} ({line.issuer_name}) is in category "
                    f"'{line.category}', which the load has no rule for"
                )
            elif line.isin is None or not is_valid_isin(line.isin):
                left_out.append(NotLoadedLine(fund.ticker, line, NotLoadedReason.NO_VALID_ISIN))
            else:
                lei = line.lei if line.lei is not None and is_valid_lei(line.lei) else None
                candidates.append(
                    _Candidate(
                        fund=fund.ticker,
                        line=line,
                        isin=line.isin,
                        lei=lei,
                        name=" ".join(line.issuer_name.split()),
                        key=name_key(line.issuer_name),
                    )
                )

    # A security is a receipt when any of its lines says so. One fund may label
    # a receipt that another files as plain common shares, and it is the same
    # security in both.
    receipt_isins = {candidate.isin for candidate in candidates if is_receipt(candidate.line)}
    receipt_groups: dict[str, list[_Candidate]] = {}
    ordinary: list[_Candidate] = []
    for candidate in candidates:
        if candidate.isin in receipt_isins:
            receipt_groups.setdefault(candidate.isin, []).append(candidate)
        else:
            ordinary.append(candidate)
    return _SortedLines(
        lines_read=lines_read,
        ordinary=tuple(ordinary),
        receipts=tuple(tuple(group) for group in receipt_groups.values()),
        left_out=tuple(left_out),
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
        self._company_of_isin: dict[str, int] = {
            instrument.isin: instrument.company_id for instrument in work.instruments.all()
        }
        self.companies_added = 0
        self.instruments_added = 0
        self.joined_by_lei = 0
        self.joined_by_name = 0
        self.leis_filled = 0
        self.agent_cases: list[AgentCase] = []

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

        self._work.instruments.add(company_id, candidate.isin)
        self._company_of_isin[candidate.isin] = company_id
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
            self._work.companies.set_lei(company.company_id, candidate.lei)
            # The company has an identifier now, so it is no longer one of the
            # companies that are found by name.
            if self._company_by_name.get(name_key(company.name)) == company.company_id:
                del self._company_by_name[name_key(company.name)]
            self._remember(replace(company, lei=candidate.lei))
            self.leis_filled += 1

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


def load_holdings(database: Database, funds: Sequence[FundHoldings]) -> LoadResult:
    """Load the holdings of the funds into ``company`` and ``instrument``.

    The steps are those of ADR 0006: lines that are debt, derivatives or
    without a valid ISIN are left out; ordinary securities are loaded in the
    order of the funds; a depositary receipt is loaded only when no ordinary
    line of this run belongs to a company with its identifier or its name.

    Everything is written in one unit of work. Loading the same holdings
    again adds nothing.

    Args:
        database: The database to load into.
        funds: The funds, in the order they are to be loaded. The first fund
            that names a company decides how its name is stored.

    Returns:
        What the load did, including the lines it did not load and the cases
        it left for the agent.

    Raises:
        UniverseError: If a line is in a category the load has no rule for.
            Nothing is written.
        DatabaseError: If the database is not ready or refuses a row. Nothing
            is written.
    """
    # Sorting comes first and needs no database, so a filing the load cannot
    # handle is refused before a transaction is even opened.
    lines = _sort_lines(funds)
    not_loaded = list(lines.left_out)
    receipts_kept = 0
    receipts_not_loaded = 0

    with database.unit_of_work() as work:
        placer = _Placer(work)

        # Step 4 of ADR 0006: ordinary lines. The companies they belong to are
        # what "already in the universe through its own shares" means below.
        own_share_companies: set[int] = set()
        for candidate in lines.ordinary:
            own_share_companies.add(placer.place(candidate))
        own_share_leis = {
            company.lei
            for company in map(placer.company, own_share_companies)
            if company.lei is not None
        }
        own_share_names = {
            name_key(placer.company(company_id).name) for company_id in own_share_companies
        }

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

    # Report in the order of the filings, whatever order the steps found them in.
    fund_order = {fund.ticker: position for position, fund in enumerate(funds)}
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
        companies=placer.company_count,
        instruments=placer.instrument_count,
        not_loaded=tuple(
            sorted(not_loaded, key=lambda entry: (fund_order[entry.fund], entry.line.number))
        ),
        agent_cases=tuple(
            sorted(placer.agent_cases, key=lambda case: (fund_order[case.fund], case.line.number))
        ),
    )
