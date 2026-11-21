"""Tests for ``pyvalue.universe.load``: the rules of ADR 0006, one at a time.

Each test builds a few holdings lines by hand, loads them into a temporary
database through the same unit of work the load itself uses, and reads the two
tables back. The end-to-end run on sample filings is in
``tests/integration/test_universe_load.py``.

Author: Emre Tezel
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import Company, ConstraintError, Database, DatabaseError, Instrument, migrate
from pyvalue.universe import (
    AgentCaseReason,
    Exclusion,
    FundHoldings,
    HoldingLine,
    LeiDecision,
    LoadResult,
    NameDecision,
    NotLoadedReason,
    OrdinaryShare,
    UniverseError,
    load_holdings,
)
from pyvalue.universe.load import name_key

# Made-up identifiers with correct check digits.
_ALPHA_LEI: str = "549300ALPHA000000003"
_DELTA_LEI: str = "549300DELTA000000010"
_THETA_LEI: str = "549300THETA000000051"
_KAPPA_LEI: str = "549300KAPPA000000078"
_ISIN_1: str = "US00000A0014"
_ISIN_2: str = "US00000A0022"
_ISIN_3: str = "GB00000D0016"
_ISIN_4: str = "FR00000E0013"
_ISIN_5: str = "DE00000T0019"
_RECEIPT_ISIN: str = "US00000Z0015"
_SECOND_RECEIPT_ISIN: str = "US00000H0017"


def _line(
    issuer_name: str,
    isin: str | None,
    *,
    lei: str | None = None,
    title: str | None = None,
    category: str = "EC",
    label: str | None = None,
) -> HoldingLine:
    """Build a holdings line; ``_fund`` numbers it. The title defaults to the name."""
    return HoldingLine(
        number=0,
        issuer_name=issuer_name,
        title=issuer_name if title is None else title,
        lei=lei,
        isin=isin,
        category=category,
        category_label=label,
    )


def _fund(ticker: str, *lines: HoldingLine) -> FundHoldings:
    """Build a fund from lines, numbering them from 1 as a filing does."""
    return FundHoldings(
        ticker=ticker,
        lines=tuple(replace(line, number=number) for number, line in enumerate(lines, start=1)),
    )


def _decision(isin: str, lei: str) -> LeiDecision:
    """Build a decision that the security's issuer has the given identifier."""
    return LeiDecision(
        isin=isin,
        lei=lei,
        company="Sample Co",
        decided_on=date(2026, 11, 20),
        evidence="Made up for a test",
    )


def _name_decision(isin: str, name: str) -> NameDecision:
    """Build a decision that the security's issuer is called by the given name."""
    return NameDecision(
        isin=isin, name=name, decided_on=date(2026, 11, 21), evidence="Made up for a test"
    )


def _exclusion(isin: str) -> Exclusion:
    """Build a decision that keeps the security out of the universe."""
    return Exclusion(
        isin=isin, company="Sample Co", decided_on=date(2026, 11, 21), evidence="Made up for a test"
    )


def _ordinary_share(isin: str, ordinary_isin: str) -> OrdinaryShare:
    """Build a decision that the first security is a receipt of the second."""
    return OrdinaryShare(
        isin=isin,
        ordinary_isin=ordinary_isin,
        company="Sample Co",
        decided_on=date(2026, 11, 21),
        evidence="Made up for a test",
    )


def _companies(database: Database) -> tuple[Company, ...]:
    """Read every company."""
    with database.unit_of_work() as work:
        return work.companies.all()


def _instruments(database: Database) -> tuple[Instrument, ...]:
    """Read every instrument."""
    with database.unit_of_work() as work:
        return work.instruments.all()


def _not_loaded(result: LoadResult) -> list[tuple[str, int, NotLoadedReason]]:
    """Return (fund, line number, reason) of every line that was not loaded."""
    return [(entry.fund, entry.line.number, entry.reason) for entry in result.not_loaded]


# --- Finding the company for a line ------------------------------------------------------


def test_a_line_adds_its_company_and_its_instrument(database: Database) -> None:
    """The simplest load: one line, one company, one instrument."""
    result = load_holdings(database, [_fund("VTI", _line("ALPHA CORP", _ISIN_1, lei=_ALPHA_LEI))])

    assert _companies(database) == (Company(1, "ALPHA CORP", _ALPHA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1),)
    assert (result.companies_added, result.instruments_added) == (1, 1)
    assert (result.companies, result.instruments) == (1, 1)


def test_a_second_security_joins_its_company_by_identifier(database: Database) -> None:
    """The identifier decides, however the name is spelled; the first spelling is kept."""
    result = load_holdings(
        database,
        [
            _fund(
                "VTI",
                _line("ALPHA CORP", _ISIN_1, lei=_ALPHA_LEI),
                _line("Alpha Corporation", _ISIN_2, lei=_ALPHA_LEI),
            )
        ],
    )

    assert _companies(database) == (Company(1, "ALPHA CORP", _ALPHA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1), Instrument(2, 1, _ISIN_2))
    assert (result.joined_by_lei, result.joined_by_name) == (1, 0)


def test_a_line_without_identifier_joins_the_company_of_the_same_name(database: Database) -> None:
    """Upper and lower case and spacing are ignored when names are compared."""
    result = load_holdings(
        database,
        [_fund("VTI", _line("BETA INC", _ISIN_1), _line("  Beta   Inc ", _ISIN_2))],
    )

    assert _companies(database) == (Company(1, "BETA INC", None),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1), Instrument(2, 1, _ISIN_2))
    assert (result.joined_by_lei, result.joined_by_name) == (0, 1)


def test_punctuation_keeps_two_names_apart(database: Database) -> None:
    """ADR 0009: punctuation counts, so the sponsors' spellings give two companies."""
    load_holdings(
        database,
        [
            _fund("VXUS", _line("JHSF PARTICIPACOES S.A.", _ISIN_1)),
            _fund("DFAX", _line("JHSF PARTICIPACOES SA", _ISIN_2)),
        ],
    )

    assert _companies(database) == (
        Company(1, "JHSF PARTICIPACOES S.A.", None),
        Company(2, "JHSF PARTICIPACOES SA", None),
    )


def test_a_name_is_not_matched_to_a_company_that_has_an_identifier(database: Database) -> None:
    """Only companies without an identifier are found by name (ADR 0006)."""
    load_holdings(
        database,
        [
            _fund(
                "VTI",
                _line("ALPHA CORP", _ISIN_1, lei=_ALPHA_LEI),
                _line("ALPHA CORP", _ISIN_2),
            )
        ],
    )

    assert _companies(database) == (
        Company(1, "ALPHA CORP", _ALPHA_LEI),
        Company(2, "ALPHA CORP", None),
    )


def test_a_line_with_an_identifier_does_not_join_by_name(database: Database) -> None:
    """A new identifier is a new company, even when a nameless twin exists."""
    load_holdings(
        database,
        [
            _fund(
                "VTI",
                _line("ALPHA CORP", _ISIN_1),
                _line("ALPHA CORP", _ISIN_2, lei=_ALPHA_LEI),
            )
        ],
    )

    assert _companies(database) == (
        Company(1, "ALPHA CORP", None),
        Company(2, "ALPHA CORP", _ALPHA_LEI),
    )


@pytest.mark.parametrize(
    "filed",
    [
        pytest.param("N/A", id="the placeholder"),
        pytest.param(_ALPHA_LEI[:-1] + "4", id="wrong check digits"),
        pytest.param("not an identifier", id="other text"),
    ],
)
def test_an_invalid_identifier_counts_as_none(database: Database, filed: str) -> None:
    """ADR 0009: the company is stored without it and can still be found by name."""
    result = load_holdings(
        database,
        [
            _fund(
                "VTI",
                _line("BETA INC", _ISIN_1, lei=filed),
                _line("BETA INC", _ISIN_2, lei=filed),
            )
        ],
    )

    assert _companies(database) == (Company(1, "BETA INC", None),)
    assert result.joined_by_name == 1


def test_the_first_fund_decides_how_a_name_is_stored(database: Database) -> None:
    """Funds are loaded in the order given (ADR 0006)."""
    load_holdings(
        database,
        [
            _fund("VXUS", _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI)),
            _fund("DFAX", _line("Delta plc", _ISIN_4, lei=_DELTA_LEI)),
        ],
    )

    assert _companies(database) == (Company(1, "DELTA PLC", _DELTA_LEI),)


def test_runs_of_spaces_in_a_stored_name_are_reduced_to_one(database: Database) -> None:
    """The stored name is the filing's spelling, tidied only in its spacing."""
    load_holdings(database, [_fund("VTI", _line("  ALPHA    Corp ", _ISIN_1))])

    assert _companies(database) == (Company(1, "ALPHA Corp", None),)


# --- When the ISIN is already an instrument ----------------------------------------------


def test_a_known_isin_with_the_same_identifier_changes_nothing(database: Database) -> None:
    """A differently spelled name on the same security is not a conflict."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI)),
            _fund("DFAX", _line("Delta Public Limited Co", _ISIN_3, lei=_DELTA_LEI)),
        ],
    )

    assert _companies(database) == (Company(1, "DELTA PLC", _DELTA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert result.agent_cases == ()
    assert result.not_loaded == ()


def test_a_known_isin_without_identifier_changes_nothing(database: Database) -> None:
    """A line that knows less than the database adds nothing and removes nothing."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI)),
            _fund("DFAX", _line("Delta plc", _ISIN_3, lei="N/A")),
        ],
    )

    assert _companies(database) == (Company(1, "DELTA PLC", _DELTA_LEI),)
    assert result.agent_cases == ()
    assert result.leis_filled == 0


def test_a_known_isin_fills_in_a_missing_identifier(database: Database) -> None:
    """The second fund knows the identifier the first one did not file."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("EPSILON SA", _ISIN_4)),
            _fund("DFAX", _line("Epsilon S.A.", _ISIN_4, lei=_ALPHA_LEI)),
        ],
    )

    assert _companies(database) == (Company(1, "EPSILON SA", _ALPHA_LEI),)
    assert result.leis_filled == 1
    assert result.agent_cases == ()


def test_a_company_whose_identifier_was_filled_in_is_no_longer_found_by_name(
    database: Database,
) -> None:
    """After the fill it is a company with an identifier, and those are found by identifier."""
    load_holdings(
        database,
        [
            _fund("VXUS", _line("EPSILON SA", _ISIN_4)),
            _fund(
                "DFAX",
                _line("Epsilon S.A.", _ISIN_4, lei=_ALPHA_LEI),
                _line("EPSILON SA", _ISIN_5),
                _line("Epsilon Holding", _ISIN_1, lei=_ALPHA_LEI),
            ),
        ],
    )

    assert _companies(database) == (
        Company(1, "EPSILON SA", _ALPHA_LEI),
        Company(2, "EPSILON SA", None),
    )
    assert _instruments(database) == (
        Instrument(1, 1, _ISIN_4),
        Instrument(2, 2, _ISIN_5),
        Instrument(3, 1, _ISIN_1),
    )


def test_an_identifier_that_belongs_to_another_company_goes_to_the_agent(
    database: Database,
) -> None:
    """The fill would give two companies one identifier, so it is not made."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
                _line("IOTA KK", _ISIN_5),
            ),
            _fund("DFAX", _line("Iota KK", _ISIN_5, lei=_DELTA_LEI)),
        ],
    )

    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "IOTA KK", None),
    )
    (case,) = result.agent_cases
    assert (case.fund, case.line.number) == ("DFAX", 1)
    assert case.reason is AgentCaseReason.LEI_BELONGS_TO_ANOTHER_COMPANY
    assert case.company == Company(2, "IOTA KK", None)
    assert case.lei_owner == Company(1, "DELTA PLC", _DELTA_LEI)
    assert result.leis_filled == 0


def test_a_different_identifier_on_a_known_isin_goes_to_the_agent(database: Database) -> None:
    """Two funds disagree about who issued a security; the database keeps the first answer."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("THETA AG", _ISIN_5, lei=_THETA_LEI)),
            _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI)),
        ],
    )

    assert _companies(database) == (Company(1, "THETA AG", _THETA_LEI),)
    (case,) = result.agent_cases
    assert case.reason is AgentCaseReason.DIFFERENT_LEI
    assert case.company == Company(1, "THETA AG", _THETA_LEI)
    assert case.lei_owner is None


def test_a_different_identifier_names_the_company_that_has_it(database: Database) -> None:
    """When the other identifier is a company of the universe, the case says which."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("THETA AG", _ISIN_5, lei=_THETA_LEI),
                _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            ),
            _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_DELTA_LEI)),
        ],
    )

    (case,) = result.agent_cases
    assert case.reason is AgentCaseReason.DIFFERENT_LEI
    assert case.lei_owner == Company(2, "DELTA PLC", _DELTA_LEI)


# --- Lines that are left out -------------------------------------------------------------


@pytest.mark.parametrize("category", ["DBT", "DCO", "DCR", "DE", "DFE", "DIR", "DO"])
def test_debt_and_derivatives_are_not_loaded_even_with_an_isin(
    database: Database, category: str
) -> None:
    """ADR 0006: the filing's own classification keeps these out of the universe."""
    result = load_holdings(
        database, [_fund("VXUS", _line("SAMPLE TREASURY", _ISIN_1, category=category))]
    )

    assert _companies(database) == ()
    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.DEBT_OR_DERIVATIVE)]
    assert result.securities == 0


@pytest.mark.parametrize(
    "isin",
    [
        pytest.param(None, id="no ISIN"),
        pytest.param("US00000A0015", id="wrong check digit"),
        pytest.param("US00000A001", id="too short"),
        pytest.param("N/A", id="placeholder"),
    ],
)
def test_a_line_without_a_valid_isin_is_listed_and_not_loaded(
    database: Database, isin: str | None
) -> None:
    """It cannot become an instrument, and it must not vanish silently either."""
    result = load_holdings(database, [_fund("VTI", _line("GAMMA INC", isin))])

    assert _companies(database) == ()
    assert _not_loaded(result) == [("VTI", 1, NotLoadedReason.NO_VALID_ISIN)]


@pytest.mark.parametrize(
    ("category", "label"),
    [
        pytest.param("EC", None, id="common"),
        pytest.param("EP", None, id="preferred"),
        pytest.param("STIV", None, id="short-term vehicle with an ISIN"),
        pytest.param("OTHER", "UNITS", id="units"),
        pytest.param("OTHER", "RIGHTS", id="rights"),
        pytest.param("OTHER", None, id="conditional category without a label"),
    ],
)
def test_every_other_known_category_is_loaded(
    database: Database, category: str, label: str | None
) -> None:
    """Nothing is left behind (ADR 0006): a valid ISIN outside debt and derivatives is loaded."""
    result = load_holdings(
        database, [_fund("DFAX", _line("MU TRUST", _ISIN_1, category=category, label=label))]
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_1),)
    assert result.not_loaded == ()


def test_a_category_the_load_has_no_rule_for_stops_it(database: Database) -> None:
    """ADR 0009: loading it would be a guess, so nothing at all is written."""
    funds = [
        _fund(
            "VXUS",
            _line("ALPHA CORP", _ISIN_1),
            _line("SAMPLE MORTGAGE TRUST", _ISIN_2, category="ABS-MBS"),
        )
    ]

    with pytest.raises(UniverseError, match="VXUS line 2 .*category 'ABS-MBS'"):
        load_holdings(database, funds)

    assert _companies(database) == ()


# --- Depositary receipts -----------------------------------------------------------------


def test_a_receipt_is_not_loaded_when_its_company_is_there_by_identifier(
    database: Database,
) -> None:
    """The company is already in the universe through its own shares."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("ZETA LTD", _RECEIPT_ISIN, lei=_ALPHA_LEI, title="ZETA LTD ADR"),
                _line("Zeta Limited", _ISIN_3, lei=_ALPHA_LEI),
            )
        ],
    )

    assert _companies(database) == (Company(1, "Zeta Limited", _ALPHA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        1,
        0,
        1,
    )


def test_a_receipt_is_not_loaded_when_its_company_is_there_by_name(database: Database) -> None:
    """The name of any company with a line of its own counts, with or without identifier."""
    result = load_holdings(
        database,
        [
            _fund(
                "DFAX",
                _line("Lambda Bhd", _RECEIPT_ISIN, category="OTHER", label="DEPOSITORY RECEIPT"),
                _line("LAMBDA BHD", _ISIN_3, lei=_ALPHA_LEI),
            )
        ],
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("DFAX", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def test_a_receipt_is_matched_by_the_name_its_own_fund_files_for_the_share(
    database: Database,
) -> None:
    """ADR 0014: the stored name is the first fund's spelling; the second fund's counts too.

    The case of Woori Financial. Two funds hold the home share and spell the
    company differently, the second fund files its own spelling on the
    receipt, and no line carries an identifier. Before ADR 0014 the receipt
    was loaded as a second company.
    """
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Woori Financial Group Inc", _ISIN_3)),
            _fund(
                "DFAX",
                _line("Woori Financial Group Inc.", _ISIN_3),
                _line("Woori Financial Group Inc.", _RECEIPT_ISIN, category="OTHER", label="ADR"),
            ),
        ],
    )

    # The stored name is still the first fund's spelling.
    assert _companies(database) == (Company(1, "Woori Financial Group Inc", None),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("DFAX", 2, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]
    assert (result.receipts_kept, result.receipts_not_loaded) == (0, 1)


def test_a_fund_s_own_spelling_counts_even_when_it_names_another_legal_form(
    database: Database,
) -> None:
    """ADR 0014, the case of BeOne Medicines: "Ltd" in one fund, "AG" in the other.

    The first fund's line carries the identifier, so the company is found by
    it; the second fund's lines carry none, and only its name ties the
    receipt to the share.
    """
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("BeOne Medicines Ltd", _ISIN_3, lei=_ALPHA_LEI)),
            _fund(
                "DFAX",
                _line("BeOne Medicines AG", _ISIN_3),
                _line("BeOne Medicines AG", _RECEIPT_ISIN, category="OTHER", label="ADR"),
            ),
        ],
    )

    assert _companies(database) == (Company(1, "BeOne Medicines Ltd", _ALPHA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("DFAX", 2, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def test_a_receipt_whose_name_no_ordinary_line_carries_is_still_loaded(
    database: Database,
) -> None:
    """The limit of ADR 0014: a spelling that appears on the receipt only ties it to nothing.

    Punctuation counts when names are compared (ADR 0009), so the full stop
    alone keeps the two apart when the second fund does not hold the share.
    """
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Woori Financial Group Inc", _ISIN_3)),
            _fund(
                "DFAX",
                _line("Woori Financial Group Inc.", _RECEIPT_ISIN, category="OTHER", label="ADR"),
            ),
        ],
    )

    assert _companies(database) == (
        Company(1, "Woori Financial Group Inc", None),
        Company(2, "Woori Financial Group Inc.", None),
    )
    assert (result.receipts_kept, result.receipts_not_loaded) == (1, 0)


def test_a_receipt_is_loaded_when_its_company_has_no_other_line(database: Database) -> None:
    """Then the receipt is the company, as for a Chinese company listed only in New York."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("ETA HOLDINGS LTD", _RECEIPT_ISIN, title="ETA HOLDINGS LTD SPONSORED ADR"),
                _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            )
        ],
    )

    # The receipt comes first in the filing and is still placed after the ordinary line.
    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "ETA HOLDINGS LTD", None),
    )
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3), Instrument(2, 2, _RECEIPT_ISIN))
    assert result.not_loaded == ()
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        1,
        1,
        0,
    )


def test_a_security_is_a_receipt_when_any_fund_says_so(database: Database) -> None:
    """One sponsor files the receipt as common shares; the other's label decides for both."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("ZETA LTD", _RECEIPT_ISIN, lei=_ALPHA_LEI),
                _line("ZETA LTD", _ISIN_3, lei=_ALPHA_LEI),
            ),
            _fund(
                "DFAX",
                _line("Zeta Ltd", _RECEIPT_ISIN, lei=_ALPHA_LEI, category="OTHER", label="ADR"),
            ),
        ],
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [
        ("VXUS", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED),
        ("DFAX", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED),
    ]
    assert result.receipts_recognised == 1


def test_a_receipt_waits_for_the_ordinary_lines_of_every_fund(database: Database) -> None:
    """The company's own share may be held only by the last fund."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("ZETA LTD", _RECEIPT_ISIN, lei=_ALPHA_LEI, title="ZETA LTD ADR")),
            _fund("DFAX", _line("Zeta Ltd", _ISIN_3, lei=_ALPHA_LEI)),
        ],
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def test_two_receipts_of_a_company_without_other_lines_are_both_loaded(
    database: Database,
) -> None:
    """They are judged against the ordinary lines only, and share one company."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("SIGMA PJSC", _RECEIPT_ISIN, lei=_ALPHA_LEI, title="SIGMA PJSC ADR"),
                _line("SIGMA PJSC", _SECOND_RECEIPT_ISIN, lei=_ALPHA_LEI, title="SIGMA PJSC GDR"),
            )
        ],
    )

    assert _companies(database) == (Company(1, "SIGMA PJSC", _ALPHA_LEI),)
    assert _instruments(database) == (
        Instrument(1, 1, _RECEIPT_ISIN),
        Instrument(2, 1, _SECOND_RECEIPT_ISIN),
    )
    assert (result.receipts_kept, result.receipts_not_loaded) == (2, 0)


# --- A load as a whole -------------------------------------------------------------------


def _mixed_funds() -> list[FundHoldings]:
    """Return two funds that exercise every outcome a line can have."""
    return [
        _fund(
            "VXUS",
            _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            _line("SAMPLE TREASURY", _ISIN_2, category="DBT"),
            _line("ZETA LTD", _RECEIPT_ISIN, lei=_DELTA_LEI, title="DELTA PLC ADR"),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI),
        ),
        _fund(
            "DFAX",
            _line("U.S. Dollar", None, category="OTHER", label="currency"),
            _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI),
            _line("Epsilon SA", _ISIN_4),
        ),
    ]


def test_the_result_counts_what_the_load_did(database: Database) -> None:
    """The numbers a person reads after a load."""
    result = load_holdings(database, _mixed_funds())

    assert result.lines_read == 7
    assert result.securities == 4
    assert (result.receipts_recognised, result.receipts_kept, result.receipts_not_loaded) == (
        1,
        0,
        1,
    )
    assert (result.companies_added, result.instruments_added) == (3, 3)
    assert (result.companies, result.instruments) == (3, 3)
    assert result.not_loaded_for(NotLoadedReason.DEBT_OR_DERIVATIVE) == 1
    assert result.not_loaded_for(NotLoadedReason.NO_VALID_ISIN) == 1
    assert result.not_loaded_for(NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED) == 1
    assert len(result.agent_cases) == 1


def test_the_lines_not_loaded_are_reported_in_the_order_of_the_filings(
    database: Database,
) -> None:
    """Receipts are decided last and still appear where their fund and line put them."""
    result = load_holdings(database, _mixed_funds())

    assert _not_loaded(result) == [
        ("VXUS", 2, NotLoadedReason.DEBT_OR_DERIVATIVE),
        ("VXUS", 3, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED),
        ("DFAX", 1, NotLoadedReason.NO_VALID_ISIN),
    ]


def test_every_line_is_either_loaded_or_listed(database: Database) -> None:
    """Nothing is left behind: the lines that are not listed are the instruments, or repeats."""
    result = load_holdings(database, _mixed_funds())

    listed = {(entry.fund, entry.line.number) for entry in result.not_loaded}
    loaded_isins = {
        line.isin
        for fund in _mixed_funds()
        for line in fund.lines
        if (fund.ticker, line.number) not in listed
    }
    assert result.lines_read == len(listed) + 4
    assert loaded_isins == {instrument.isin for instrument in _instruments(database)}


def test_loading_the_same_holdings_again_adds_nothing(database: Database) -> None:
    """ADR 0009: a second run finds every ISIN and reports the same open points."""
    first = load_holdings(database, _mixed_funds())
    companies = _companies(database)
    instruments = _instruments(database)

    second = load_holdings(database, _mixed_funds())

    assert _companies(database) == companies
    assert _instruments(database) == instruments
    assert (second.companies_added, second.instruments_added, second.leis_filled) == (0, 0, 0)
    assert (second.joined_by_lei, second.joined_by_name) == (0, 0)
    assert second.not_loaded == first.not_loaded
    assert second.agent_cases == first.agent_cases
    assert (second.companies, second.instruments) == (first.companies, first.instruments)


def test_a_later_load_builds_on_what_the_database_holds(database: Database) -> None:
    """New lines are placed against companies an earlier load added."""
    load_holdings(
        database,
        [_fund("VXUS", _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI), _line("BETA INC", _ISIN_1))],
    )

    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("Delta plc", _ISIN_4, lei=_DELTA_LEI),
                _line("beta inc", _ISIN_2),
                _line("Beta Inc", _ISIN_1, lei=_ALPHA_LEI),
            )
        ],
    )

    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "BETA INC", _ALPHA_LEI),
    )
    assert _instruments(database) == (
        Instrument(1, 1, _ISIN_3),
        Instrument(2, 2, _ISIN_1),
        Instrument(3, 1, _ISIN_4),
        Instrument(4, 2, _ISIN_2),
    )
    assert (result.joined_by_lei, result.joined_by_name, result.leis_filled) == (1, 1, 1)
    assert (result.companies_added, result.instruments_added) == (0, 2)


def test_a_later_load_judges_a_receipt_by_the_ordinary_lines_of_its_own_run(
    database: Database,
) -> None:
    """ADR 0009: a company met again through its own share still keeps its receipt out."""
    funds = [
        _fund(
            "VXUS",
            _line("ZETA LTD", _ISIN_3, lei=_ALPHA_LEI),
            _line("ZETA LTD", _RECEIPT_ISIN, lei=_ALPHA_LEI, title="ZETA LTD ADR"),
            _line("ETA HOLDINGS LTD", _SECOND_RECEIPT_ISIN, title="ETA HOLDINGS LTD ADR"),
        )
    ]
    first = load_holdings(database, funds)

    second = load_holdings(database, funds)

    assert _instruments(database) == (
        Instrument(1, 1, _ISIN_3),
        Instrument(2, 2, _SECOND_RECEIPT_ISIN),
    )
    assert (second.receipts_kept, second.receipts_not_loaded) == (1, 1)
    assert second.not_loaded == first.not_loaded


def test_a_row_the_database_refuses_leaves_it_untouched(database: Database) -> None:
    """One unit of work for the whole load: all of it, or nothing."""
    funds = [
        _fund(
            "VTI",
            _line("ALPHA CORP", _ISIN_1, lei=_ALPHA_LEI),
            # A name of spaces only is stored as an empty name, which the schema refuses.
            _line("   ", _ISIN_2),
        )
    ]

    with pytest.raises(ConstraintError, match="the company table refused a row"):
        load_holdings(database, funds)

    assert _companies(database) == ()
    assert _instruments(database) == ()


def test_a_database_that_is_not_ready_is_refused(database_path: Path) -> None:
    """The load does not create a database; ``pyvalue db migrate`` does."""
    with pytest.raises(DatabaseError, match="run `pyvalue db migrate`"):
        load_holdings(Database(database_path), [_fund("VTI", _line("ALPHA CORP", _ISIN_1))])

    assert not database_path.exists()


def test_no_funds_is_a_load_that_does_nothing(database: Database) -> None:
    """An empty input is not an error."""
    result = load_holdings(database, [])

    assert (result.lines_read, result.securities, result.companies, result.instruments) == (
        0,
        0,
        0,
        0,
    )


# --- Decisions on legal-entity identifiers (ADR 0010) -------------------------------------


def _disputed_funds() -> list[FundHoldings]:
    """Return two funds that file different identifiers for one security."""
    return [
        _fund("VXUS", _line("THETA AG", _ISIN_5, lei=_THETA_LEI)),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI)),
    ]


def test_without_a_decision_the_dispute_is_a_case(database: Database) -> None:
    """The starting point of every test below: the first fund's identifier, and a case."""
    result = load_holdings(database, _disputed_funds())

    assert _companies(database) == (Company(1, "THETA AG", _THETA_LEI),)
    assert len(result.agent_cases) == 1
    assert (result.lei_decisions_used, result.leis_corrected) == (0, 0)


def test_on_an_empty_database_the_decided_identifier_is_the_one_loaded(
    database: Database,
) -> None:
    """Both funds' lines are read as carrying it, so there is nothing to dispute."""
    result = load_holdings(database, _disputed_funds(), [_decision(_ISIN_5, _ALPHA_LEI)])

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    assert result.agent_cases == ()
    assert (result.lei_decisions_used, result.leis_corrected) == (1, 0)


def test_a_decision_may_side_with_the_first_fund(database: Database) -> None:
    """Then the database was right all along, and only the case goes away."""
    load_holdings(database, _disputed_funds())

    result = load_holdings(database, _disputed_funds(), [_decision(_ISIN_5, _THETA_LEI)])

    assert _companies(database) == (Company(1, "THETA AG", _THETA_LEI),)
    assert result.agent_cases == ()
    assert (result.lei_decisions_used, result.leis_corrected) == (1, 0)


def test_a_decision_may_name_an_identifier_no_fund_filed(database: Database) -> None:
    """The register can know better than both funds."""
    result = load_holdings(database, _disputed_funds(), [_decision(_ISIN_5, _KAPPA_LEI)])

    assert _companies(database) == (Company(1, "THETA AG", _KAPPA_LEI),)
    assert result.agent_cases == ()


def test_a_decision_corrects_a_company_that_is_already_loaded(database: Database) -> None:
    """Applying a decision is running the load again; the stored name is kept."""
    load_holdings(database, _disputed_funds())

    result = load_holdings(database, _disputed_funds(), [_decision(_ISIN_5, _ALPHA_LEI)])

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_5),)
    assert result.agent_cases == ()
    assert (result.leis_corrected, result.leis_filled) == (1, 0)
    assert (result.companies_added, result.instruments_added) == (0, 0)


def test_a_correction_is_made_once(database: Database) -> None:
    """A second run with the same decisions finds nothing left to correct."""
    load_holdings(database, _disputed_funds())
    decisions = [_decision(_ISIN_5, _ALPHA_LEI)]
    load_holdings(database, _disputed_funds(), decisions)

    again = load_holdings(database, _disputed_funds(), decisions)

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    assert (again.leis_corrected, again.leis_filled) == (0, 0)
    assert again.agent_cases == ()
    assert again.lei_decisions_used == 1


def test_a_decision_gives_an_identifier_to_a_company_that_has_none(database: Database) -> None:
    """That counts as filling in, not as correcting."""
    funds = [_fund("VXUS", _line("IOTA KK", _ISIN_5, lei="N/A"))]
    load_holdings(database, funds)

    result = load_holdings(database, funds, [_decision(_ISIN_5, _KAPPA_LEI)])

    assert _companies(database) == (Company(1, "IOTA KK", _KAPPA_LEI),)
    assert (result.leis_filled, result.leis_corrected) == (1, 0)


def test_a_decided_new_security_joins_the_company_that_has_the_identifier(
    database: Database,
) -> None:
    """The decision replaces the filed identifier before the company is looked for."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
                _line("Delta Holdings", _ISIN_4, lei=_THETA_LEI),
            )
        ],
        [_decision(_ISIN_4, _DELTA_LEI)],
    )

    assert _companies(database) == (Company(1, "DELTA PLC", _DELTA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3), Instrument(2, 1, _ISIN_4))
    assert result.joined_by_lei == 1


def test_a_sibling_security_with_the_old_identifier_is_reported_in_the_same_run(
    database: Database,
) -> None:
    """Decisions come first, so the sibling is compared with the corrected identifier."""
    funds = [
        _fund(
            "VXUS",
            # The sibling comes before the decided security, as the B share of
            # Guangdong Electric Power does in the real filing.
            _line("THETA AG", _ISIN_1, lei=_THETA_LEI, title="THETA AG-B"),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI, title="THETA AG-A"),
        ),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI)),
    ]
    load_holdings(database, funds)
    decisions = [_decision(_ISIN_5, _ALPHA_LEI)]

    first = load_holdings(database, funds, decisions)
    second = load_holdings(database, funds, decisions)

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    (case,) = first.agent_cases
    assert (case.fund, case.line.number, case.line.isin) == ("VXUS", 1, _ISIN_1)
    assert case.reason is AgentCaseReason.DIFFERENT_LEI
    assert second.agent_cases == first.agent_cases


def test_deciding_the_sibling_too_closes_the_case(database: Database) -> None:
    """ADR 0010: decide every security of the company that carries the wrong identifier."""
    funds = [
        _fund(
            "VXUS",
            _line("THETA AG", _ISIN_1, lei=_THETA_LEI, title="THETA AG-B"),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI, title="THETA AG-A"),
        ),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI)),
    ]
    load_holdings(database, funds)

    result = load_holdings(
        database, funds, [_decision(_ISIN_5, _ALPHA_LEI), _decision(_ISIN_1, _ALPHA_LEI)]
    )

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    assert result.agent_cases == ()
    assert (result.lei_decisions_used, result.leis_corrected) == (2, 1)


def test_a_database_corrected_in_place_equals_one_built_from_scratch(
    database: Database, tmp_path: Path
) -> None:
    """The decisions are an input of the load, so both ways give the same rows."""
    funds = [
        _fund(
            "VXUS",
            _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            _line("THETA AG", _ISIN_1, lei=_THETA_LEI, title="THETA AG-B"),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI, title="THETA AG-A"),
            _line("IOTA KK", _ISIN_4),
        ),
        _fund(
            "DFAX",
            _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI),
            _line("Iota KK", _ISIN_4, lei=_DELTA_LEI),
        ),
    ]
    decisions = [
        _decision(_ISIN_5, _ALPHA_LEI),
        _decision(_ISIN_1, _ALPHA_LEI),
        _decision(_ISIN_4, _KAPPA_LEI),
    ]
    # Corrected in place: loaded without decisions first, as the real database was.
    load_holdings(database, funds)
    corrected = load_holdings(database, funds, decisions)
    # Built from scratch: a second database that sees the decisions from the start.
    scratch_path = tmp_path / "scratch.db"
    migrate(scratch_path)
    scratch = Database(scratch_path)
    built = load_holdings(scratch, funds, decisions)

    assert _companies(database) == _companies(scratch)
    assert _instruments(database) == _instruments(scratch)
    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "THETA AG", _ALPHA_LEI),
        Company(3, "IOTA KK", _KAPPA_LEI),
    )
    assert corrected.agent_cases == built.agent_cases == ()


def test_a_decided_identifier_that_another_company_has_is_not_taken(database: Database) -> None:
    """Two rows would become one company; merging rows is not the load's to do."""
    funds = [
        _fund(
            "VXUS",
            _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI),
        )
    ]
    load_holdings(database, funds)
    decisions = [_decision(_ISIN_5, _DELTA_LEI)]

    first = load_holdings(database, funds, decisions)
    second = load_holdings(database, funds, decisions)

    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "THETA AG", _THETA_LEI),
    )
    (case,) = first.agent_cases
    assert case.reason is AgentCaseReason.DIFFERENT_LEI
    assert case.company == Company(2, "THETA AG", _THETA_LEI)
    assert case.lei_owner == Company(1, "DELTA PLC", _DELTA_LEI)
    assert first.leis_corrected == 0
    assert second.agent_cases == first.agent_cases


def test_a_decided_identifier_another_company_has_is_not_filled_in_either(
    database: Database,
) -> None:
    """The same refusal for a company that has no identifier yet."""
    funds = [
        _fund(
            "VXUS",
            _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            _line("IOTA KK", _ISIN_5),
        )
    ]
    load_holdings(database, funds)

    result = load_holdings(database, funds, [_decision(_ISIN_5, _DELTA_LEI)])

    assert _companies(database)[1] == Company(2, "IOTA KK", None)
    (case,) = result.agent_cases
    assert case.reason is AgentCaseReason.LEI_BELONGS_TO_ANOTHER_COMPANY
    assert case.lei_owner == Company(1, "DELTA PLC", _DELTA_LEI)


def test_decisions_that_contradict_each_other_apply_the_first_and_report_the_second(
    database: Database,
) -> None:
    """Two issuers for the securities of one company row: the row is not split."""
    funds = [
        _fund(
            "VXUS",
            _line("THETA AG", _ISIN_1, lei=_THETA_LEI),
            _line("THETA AG", _ISIN_5, lei=_THETA_LEI),
        )
    ]
    load_holdings(database, funds)
    decisions = [_decision(_ISIN_1, _ALPHA_LEI), _decision(_ISIN_5, _KAPPA_LEI)]

    first = load_holdings(database, funds, decisions)
    second = load_holdings(database, funds, decisions)

    assert _companies(database) == (Company(1, "THETA AG", _ALPHA_LEI),)
    (case,) = first.agent_cases
    assert (case.line.isin, case.reason) == (_ISIN_5, AgentCaseReason.DIFFERENT_LEI)
    assert first.leis_corrected == 1
    assert second.leis_corrected == 0
    assert second.agent_cases == first.agent_cases


def test_after_a_correction_the_old_identifier_starts_a_company_of_its_own(
    database: Database,
) -> None:
    """ADR 0010: a line that still files the old identifier for a new security is not joined."""
    load_holdings(database, _disputed_funds())
    funds = [
        *_disputed_funds(),
        _fund("VTI", _line("Theta Old Co", _ISIN_1, lei=_THETA_LEI)),
    ]

    load_holdings(database, funds, [_decision(_ISIN_5, _ALPHA_LEI)])

    assert _companies(database) == (
        Company(1, "THETA AG", _ALPHA_LEI),
        Company(2, "Theta Old Co", _THETA_LEI),
    )


def test_the_receipt_rule_uses_the_decided_identifier(database: Database) -> None:
    """A receipt filed with a wrong identifier is still recognised as its company's."""
    funds = [
        _fund(
            "VXUS",
            _line("ZETA LTD", _ISIN_3, lei=_ALPHA_LEI),
            _line("ZETA DEPOSITARY CO", _RECEIPT_ISIN, lei=_THETA_LEI, title="ZETA ADR"),
        )
    ]

    result = load_holdings(database, funds, [_decision(_RECEIPT_ISIN, _ALPHA_LEI)])

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("VXUS", 2, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def test_a_decision_for_a_security_no_fund_holds_changes_nothing(database: Database) -> None:
    """A fund may drop a security; its decision stays in the file and is simply unused."""
    result = load_holdings(database, _disputed_funds(), [_decision(_ISIN_1, _KAPPA_LEI)])

    assert _companies(database) == (Company(1, "THETA AG", _THETA_LEI),)
    assert result.lei_decisions_used == 0
    assert len(result.agent_cases) == 1


def test_a_decision_does_not_make_a_line_loadable(database: Database) -> None:
    """Debt stays out whatever is decided about its issuer."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line("SAMPLE TREASURY", _ISIN_1, category="DBT"))],
        [_decision(_ISIN_1, _KAPPA_LEI)],
    )

    assert _companies(database) == ()
    assert result.lei_decisions_used == 0


def test_two_decisions_for_one_security_are_refused(database: Database) -> None:
    """A security has one issuer; the load does not pick between two answers."""
    decisions = [_decision(_ISIN_5, _ALPHA_LEI), _decision(_ISIN_5, _KAPPA_LEI)]

    with pytest.raises(UniverseError, match="two decisions are about the same ISIN"):
        load_holdings(database, _disputed_funds(), decisions)

    assert _companies(database) == ()


# --- Decisions on company names (ADR 0012) -----------------------------------------------

# What a fund's data vendor files when it has not set the issuer up yet.
_PLACEHOLDER: str = "New Issuer: BB Company ID:68830100"


def _placeholder_funds() -> list[FundHoldings]:
    """Return two funds that hold one security; the first files a placeholder for its issuer."""
    return [
        _fund("VXUS", _line(_PLACEHOLDER, _ISIN_5, lei=_THETA_LEI)),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_THETA_LEI)),
    ]


def test_without_a_name_decision_the_placeholder_is_stored(database: Database) -> None:
    """The starting point of the tests below: the first fund's spelling is kept."""
    result = load_holdings(database, _placeholder_funds())

    assert _companies(database) == (Company(1, _PLACEHOLDER, _THETA_LEI),)
    assert (result.name_decisions_used, result.companies_renamed) == (0, 0)


def test_on_an_empty_database_the_decided_name_is_the_one_stored(database: Database) -> None:
    """The line is read as carrying the decided name, so the company is added under it."""
    result = load_holdings(
        database, _placeholder_funds(), name_decisions=[_name_decision(_ISIN_5, "Theta AG")]
    )

    assert _companies(database) == (Company(1, "Theta AG", _THETA_LEI),)
    # Added under the name, not renamed.
    assert (result.name_decisions_used, result.companies_renamed) == (1, 0)


def test_a_name_decision_renames_a_company_that_is_already_loaded(database: Database) -> None:
    """The real database was loaded first and given its names afterwards."""
    load_holdings(database, _placeholder_funds())

    result = load_holdings(
        database, _placeholder_funds(), name_decisions=[_name_decision(_ISIN_5, "Theta AG")]
    )

    # The identifier and the instrument are left as they were.
    assert _companies(database) == (Company(1, "Theta AG", _THETA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_5),)
    assert (result.name_decisions_used, result.companies_renamed) == (1, 1)
    assert (result.companies_added, result.instruments_added) == (0, 0)


def test_a_name_that_is_already_right_is_not_changed(database: Database) -> None:
    """A second run with the same decision finds nothing left to rename."""
    names = [_name_decision(_ISIN_5, "Theta AG")]
    load_holdings(database, _placeholder_funds(), name_decisions=names)

    again = load_holdings(database, _placeholder_funds(), name_decisions=names)

    assert _companies(database) == (Company(1, "Theta AG", _THETA_LEI),)
    assert (again.name_decisions_used, again.companies_renamed) == (1, 0)


def test_a_company_found_by_its_identifier_is_given_the_decided_name(database: Database) -> None:
    """A decision names the company of its security, whichever line brought the company in."""
    result = load_holdings(
        database,
        [
            _fund(
                "VXUS",
                _line("THETA AG", _ISIN_1, lei=_THETA_LEI, title="THETA AG-A"),
                _line(_PLACEHOLDER, _ISIN_5, lei=_THETA_LEI, title="THETA AG-B"),
            )
        ],
        name_decisions=[_name_decision(_ISIN_5, "Theta Aktiengesellschaft")],
    )

    assert _companies(database) == (Company(1, "Theta Aktiengesellschaft", _THETA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1), Instrument(2, 1, _ISIN_5))
    assert (result.joined_by_lei, result.companies_renamed) == (1, 1)


def test_a_later_line_joins_under_the_decided_name_and_not_under_the_placeholder(
    database: Database,
) -> None:
    """A renamed company without an identifier is found by its new name only."""
    load_holdings(database, [_fund("VXUS", _line(_PLACEHOLDER, _ISIN_1))])

    result = load_holdings(
        database,
        [
            _fund("VXUS", _line(_PLACEHOLDER, _ISIN_1)),
            _fund(
                "DFAX",
                # The decided name in another case: the same company.
                _line("BETA INC", _ISIN_2),
                # The placeholder again, for another security: it leads nowhere now.
                _line(_PLACEHOLDER, _ISIN_3),
            ),
        ],
        name_decisions=[_name_decision(_ISIN_1, "Beta Inc")],
    )

    assert _companies(database) == (Company(1, "Beta Inc", None), Company(2, _PLACEHOLDER, None))
    assert _instruments(database) == (
        Instrument(1, 1, _ISIN_1),
        Instrument(2, 1, _ISIN_2),
        Instrument(3, 2, _ISIN_3),
    )
    assert (result.joined_by_name, result.companies_renamed) == (1, 1)


def test_a_placeholder_hides_a_company_from_its_receipt(database: Database) -> None:
    """Without a decision nothing ties the receipt to the company, so the receipt is loaded."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line(_PLACEHOLDER, _ISIN_3)),
            _fund("DFAX", _line("Zeta Ltd", _RECEIPT_ISIN, category="OTHER", label="ADR")),
        ],
    )

    assert _companies(database) == (Company(1, _PLACEHOLDER, None), Company(2, "Zeta Ltd", None))
    assert (result.receipts_kept, result.receipts_not_loaded) == (1, 0)


def test_a_receipt_of_a_company_named_by_decision_is_not_loaded(database: Database) -> None:
    """The receipt rule compares names as decided: the company is seen to be there already."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line(_PLACEHOLDER, _ISIN_3)),
            _fund("DFAX", _line("Zeta Ltd", _RECEIPT_ISIN, category="OTHER", label="ADR")),
        ],
        name_decisions=[_name_decision(_ISIN_3, "Zeta Ltd")],
    )

    assert _companies(database) == (Company(1, "Zeta Ltd", None),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("DFAX", 1, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def _two_securities_of_one_company() -> list[FundHoldings]:
    """Return one fund that holds two securities of a company, joined by its identifier."""
    return [
        _fund(
            "VXUS",
            _line(_PLACEHOLDER, _ISIN_1, lei=_THETA_LEI, title="THETA AG-A"),
            _line(_PLACEHOLDER, _ISIN_5, lei=_THETA_LEI, title="THETA AG-B"),
        )
    ]


def test_the_same_name_for_two_securities_of_a_company_is_no_contradiction(
    database: Database,
) -> None:
    """Deciding every security of a company alike is the normal case."""
    names = [_name_decision(_ISIN_1, "Theta AG"), _name_decision(_ISIN_5, "Theta AG")]

    result = load_holdings(database, _two_securities_of_one_company(), name_decisions=names)

    assert _companies(database) == (Company(1, "Theta AG", _THETA_LEI),)
    assert (result.name_decisions_used, result.companies_renamed) == (2, 0)


def test_name_decisions_that_contradict_each_other_are_refused_on_an_empty_database(
    database: Database,
) -> None:
    """One company cannot be called two things, so the load stops and writes nothing."""
    names = [_name_decision(_ISIN_1, "Theta AG"), _name_decision(_ISIN_5, "Theta SE")]

    with pytest.raises(UniverseError) as raised:
        load_holdings(database, _two_securities_of_one_company(), name_decisions=names)

    assert str(raised.value) == (
        f"{_ISIN_1} and {_ISIN_5} are securities of one company, but the name decisions call it "
        "'Theta AG' and 'Theta SE'"
    )
    assert _companies(database) == ()
    assert _instruments(database) == ()


def test_name_decisions_that_contradict_each_other_are_refused_on_a_loaded_database(
    database: Database,
) -> None:
    """The same refusal when the company is already there; it keeps the name it had."""
    load_holdings(database, _two_securities_of_one_company())
    funds = [*_two_securities_of_one_company(), _fund("DFAX", _line("Gamma Inc", _ISIN_3))]
    names = [_name_decision(_ISIN_1, "Theta AG"), _name_decision(_ISIN_5, "Theta SE")]

    with pytest.raises(UniverseError, match="are securities of one company"):
        load_holdings(database, funds, name_decisions=names)

    # Neither the first rename nor the new line of the same run was saved.
    assert _companies(database) == (Company(1, _PLACEHOLDER, _THETA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1), Instrument(2, 1, _ISIN_5))


def test_a_name_decision_for_a_security_no_fund_holds_changes_nothing(
    database: Database,
) -> None:
    """The file may run ahead of the filings; such a row waits."""
    result = load_holdings(
        database, _placeholder_funds(), name_decisions=[_name_decision(_ISIN_1, "Alpha Corp")]
    )

    assert _companies(database) == (Company(1, _PLACEHOLDER, _THETA_LEI),)
    assert (result.name_decisions_used, result.companies_renamed) == (0, 0)


def test_a_name_decision_does_not_make_a_line_loadable(database: Database) -> None:
    """A line that is debt stays out, whatever the names file says about its ISIN."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line(_PLACEHOLDER, _ISIN_5, category="DBT"))],
        name_decisions=[_name_decision(_ISIN_5, "Theta AG")],
    )

    assert _companies(database) == ()
    assert result.name_decisions_used == 0


def test_two_name_decisions_for_one_security_are_refused(database: Database) -> None:
    """A company has one name; the load does not pick between two answers."""
    names = [_name_decision(_ISIN_5, "Theta AG"), _name_decision(_ISIN_5, "Theta SE")]

    with pytest.raises(UniverseError, match="two name decisions are about the same ISIN"):
        load_holdings(database, _placeholder_funds(), name_decisions=names)

    assert _companies(database) == ()


def test_both_kinds_of_decision_apply_to_one_company(database: Database) -> None:
    """A company can need its identifier settled and its name given in the same run."""
    funds = [
        _fund("VXUS", _line(_PLACEHOLDER, _ISIN_5, lei=_THETA_LEI)),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_ALPHA_LEI)),
    ]
    load_holdings(database, funds)

    result = load_holdings(
        database,
        funds,
        [_decision(_ISIN_5, _ALPHA_LEI)],
        [_name_decision(_ISIN_5, "Theta AG")],
    )

    assert _companies(database) == (Company(1, "Theta AG", _ALPHA_LEI),)
    assert (result.leis_corrected, result.companies_renamed) == (1, 1)
    assert result.agent_cases == ()


def test_a_database_renamed_in_place_equals_one_built_from_scratch(
    database: Database, tmp_path: Path
) -> None:
    """The names are an input of the load, so both ways give the same rows."""
    funds = [
        _fund(
            "VXUS",
            _line("DELTA PLC", _ISIN_3, lei=_DELTA_LEI),
            _line(_PLACEHOLDER, _ISIN_1, lei=_THETA_LEI, title="THETA AG-B"),
            _line(_PLACEHOLDER, _ISIN_5, lei=_THETA_LEI, title="THETA AG-A"),
            _line("New Issuer: BB Company ID:2", _ISIN_4),
        ),
        _fund("DFAX", _line("Theta AG", _ISIN_5, lei=_THETA_LEI), _line("Iota KK", _ISIN_4)),
    ]
    names = [
        _name_decision(_ISIN_1, "Theta AG"),
        _name_decision(_ISIN_5, "Theta AG"),
        _name_decision(_ISIN_4, "Iota KK"),
    ]
    # Renamed in place: loaded without the names first, as the real database was.
    load_holdings(database, funds)
    renamed = load_holdings(database, funds, name_decisions=names)
    # Built from scratch: a second database that sees the names from the start.
    scratch_path = tmp_path / "scratch.db"
    migrate(scratch_path)
    scratch = Database(scratch_path)
    built = load_holdings(scratch, funds, name_decisions=names)

    assert _companies(database) == _companies(scratch)
    assert _instruments(database) == _instruments(scratch)
    assert _companies(database) == (
        Company(1, "DELTA PLC", _DELTA_LEI),
        Company(2, "Theta AG", _THETA_LEI),
        Company(3, "Iota KK", None),
    )
    assert (renamed.companies_renamed, built.companies_renamed) == (2, 0)


# --- Securities kept out of the universe (ADR 0013) --------------------------------------


def _receipt_and_share_funds() -> list[FundHoldings]:
    """Return two funds: one files a company's receipt as a plain share, one holds its share.

    Nothing in the first line says "receipt", so without a decision the load
    takes both securities for ordinary shares of one company.
    """
    return [
        _fund(
            "VXUS",
            _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI),
            _line("Delta PLC", _ISIN_3, lei=_DELTA_LEI),
        ),
        _fund("DFAX", _line("Kappa Ltd", _ISIN_1, lei=_KAPPA_LEI)),
    ]


def test_without_an_exclusion_the_unrecognised_receipt_is_loaded(database: Database) -> None:
    """The starting point of the tests below: two instruments under one company."""
    result = load_holdings(database, _receipt_and_share_funds())

    assert _companies(database) == (
        Company(1, "Kappa Ltd", _KAPPA_LEI),
        Company(2, "Delta PLC", _DELTA_LEI),
    )
    assert _instruments(database) == (
        Instrument(1, 1, _RECEIPT_ISIN),
        Instrument(2, 2, _ISIN_3),
        Instrument(3, 1, _ISIN_1),
    )
    assert result.exclusions_used == 0


def test_an_excluded_security_is_not_loaded_and_its_company_stays_on_its_other_security(
    database: Database,
) -> None:
    """The company is loaded through the share another fund holds."""
    result = load_holdings(
        database, _receipt_and_share_funds(), exclusions=[_exclusion(_RECEIPT_ISIN)]
    )

    assert _companies(database) == (
        Company(1, "Delta PLC", _DELTA_LEI),
        Company(2, "Kappa Ltd", _KAPPA_LEI),
    )
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3), Instrument(2, 2, _ISIN_1))
    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.EXCLUDED_BY_DECISION)]
    assert result.not_loaded_for(NotLoadedReason.EXCLUDED_BY_DECISION) == 1
    # The excluded security is not one of the securities the load counts.
    assert (result.exclusions_used, result.securities) == (1, 2)


def test_a_company_whose_only_security_is_excluded_is_not_loaded(database: Database) -> None:
    """Nothing is left that could bring the company in."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI))],
        exclusions=[_exclusion(_RECEIPT_ISIN)],
    )

    assert _companies(database) == ()
    assert _instruments(database) == ()
    assert (result.companies, result.instruments, result.exclusions_used) == (0, 0, 1)


def test_every_line_of_an_excluded_security_is_left_out(database: Database) -> None:
    """A security held by two funds is one exclusion and two lines not loaded."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI)),
            _fund("DFAX", _line("KAPPA LIMITED", _RECEIPT_ISIN, category="OTHER", label="ADR")),
        ],
        exclusions=[_exclusion(_RECEIPT_ISIN)],
    )

    assert _not_loaded(result) == [
        ("VXUS", 1, NotLoadedReason.EXCLUDED_BY_DECISION),
        ("DFAX", 1, NotLoadedReason.EXCLUDED_BY_DECISION),
    ]
    # Taken out before the receipts are sorted: it is not counted as a receipt.
    assert (result.exclusions_used, result.receipts_recognised) == (1, 0)


def test_an_excluded_line_is_not_a_line_of_its_company_in_the_receipt_rule(
    database: Database,
) -> None:
    """With the plain-looking line gone, the labelled receipt is the company's only line."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Kappa Ltd", _ISIN_1, lei=_KAPPA_LEI)),
            _fund(
                "DFAX",
                _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI, category="OTHER", label="GDR"),
            ),
        ],
        exclusions=[_exclusion(_ISIN_1)],
    )

    assert _instruments(database) == (Instrument(1, 1, _RECEIPT_ISIN),)
    assert (result.receipts_kept, result.receipts_not_loaded) == (1, 0)


def test_a_line_left_out_anyway_keeps_its_own_reason(database: Database) -> None:
    """Debt stays debt in the report, whatever the exclusions say about its ISIN."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line("SAMPLE TREASURY", _ISIN_5, category="DBT"))],
        exclusions=[_exclusion(_ISIN_5)],
    )

    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.DEBT_OR_DERIVATIVE)]
    assert result.exclusions_used == 0


def test_an_exclusion_for_a_security_no_fund_holds_changes_nothing(database: Database) -> None:
    """The file may name a security the filings do not hold; such a row waits."""
    result = load_holdings(database, _receipt_and_share_funds(), exclusions=[_exclusion(_ISIN_5)])

    assert len(_instruments(database)) == 3
    assert result.exclusions_used == 0
    assert result.not_loaded == ()


def test_a_database_that_holds_an_excluded_security_is_refused(database: Database) -> None:
    """The load never deletes, so it says that the database has to be rebuilt."""
    load_holdings(database, _receipt_and_share_funds())
    before = (_companies(database), _instruments(database))
    # A new line in the same run, to show that nothing at all is written.
    funds = [*_receipt_and_share_funds(), _fund("VTI", _line("Gamma Inc", _ISIN_2))]

    with pytest.raises(UniverseError) as raised:
        load_holdings(database, funds, exclusions=[_exclusion(_RECEIPT_ISIN)])

    message = str(raised.value)
    assert f"{database.path} holds securities that a decision keeps out" in message
    assert _RECEIPT_ISIN in message
    assert "has to be rebuilt" in message
    assert (_companies(database), _instruments(database)) == before


def test_a_security_that_is_excluded_and_decided_on_is_refused(database: Database) -> None:
    """A decision about a security that is not loaded could never apply."""
    with pytest.raises(UniverseError, match="the files contradict each other") as raised:
        load_holdings(
            database,
            _receipt_and_share_funds(),
            name_decisions=[_name_decision(_RECEIPT_ISIN, "Kappa Ltd")],
            exclusions=[_exclusion(_RECEIPT_ISIN)],
        )

    assert _RECEIPT_ISIN in str(raised.value)
    assert _companies(database) == ()


def test_an_identifier_decision_about_an_excluded_security_is_refused(
    database: Database,
) -> None:
    """The same refusal for the other decisions file."""
    with pytest.raises(UniverseError, match="the files contradict each other"):
        load_holdings(
            database,
            _receipt_and_share_funds(),
            [_decision(_RECEIPT_ISIN, _KAPPA_LEI)],
            exclusions=[_exclusion(_RECEIPT_ISIN)],
        )


def test_loading_with_an_exclusion_equals_loading_filings_without_those_lines(
    database: Database, tmp_path: Path
) -> None:
    """An exclusion is exactly "as if the funds did not hold it"."""
    load_holdings(database, _receipt_and_share_funds(), exclusions=[_exclusion(_RECEIPT_ISIN)])
    other_path = tmp_path / "other.db"
    migrate(other_path)
    other = Database(other_path)
    load_holdings(
        other,
        [
            _fund("VXUS", _line("Delta PLC", _ISIN_3, lei=_DELTA_LEI)),
            _fund("DFAX", _line("Kappa Ltd", _ISIN_1, lei=_KAPPA_LEI)),
        ],
    )

    assert _companies(database) == _companies(other)
    assert _instruments(database) == _instruments(other)


def test_a_second_run_with_the_same_exclusion_changes_nothing(database: Database) -> None:
    """A database built with the exclusion never held the security, so nothing is refused."""
    exclusions = [_exclusion(_RECEIPT_ISIN)]
    load_holdings(database, _receipt_and_share_funds(), exclusions=exclusions)
    before = (_companies(database), _instruments(database))

    again = load_holdings(database, _receipt_and_share_funds(), exclusions=exclusions)

    assert (_companies(database), _instruments(database)) == before
    assert (again.companies_added, again.instruments_added, again.exclusions_used) == (0, 0, 1)


# --- A receipt read as its ordinary share (ADR 0015) -------------------------------------


def _receipt_only_funds() -> list[FundHoldings]:
    """Return one fund that holds a company through its labelled receipt only."""
    return [
        _fund(
            "DFAX",
            _line("KT CORPORATION", _RECEIPT_ISIN, lei=_KAPPA_LEI, category="OTHER", label="ADR"),
        )
    ]


def test_without_a_swap_the_receipt_is_the_company_s_only_line(database: Database) -> None:
    """The starting point of the tests below: the receipt itself is the instrument."""
    result = load_holdings(database, _receipt_only_funds())

    assert _instruments(database) == (Instrument(1, 1, _RECEIPT_ISIN),)
    assert (result.receipts_recognised, result.receipts_kept) == (1, 1)
    assert result.ordinary_shares_used == 0


def test_a_swapped_receipt_is_loaded_under_its_ordinary_share(database: Database) -> None:
    """The company and its identifier come from the filing line; the ISIN is the share's."""
    result = load_holdings(
        database,
        _receipt_only_funds(),
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )

    assert _companies(database) == (Company(1, "KT CORPORATION", _KAPPA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert result.not_loaded == ()
    assert result.ordinary_shares_used == 1
    # The line is an ordinary line now, whatever its label says.
    assert (result.receipts_recognised, result.securities) == (0, 1)


def test_a_swapped_receipt_joins_the_share_another_fund_holds(database: Database) -> None:
    """Both lines are the same security, so there is one instrument."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Kanzhun Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI)),
            _fund("DFAX", _line("Kanzhun Ltd", _ISIN_1, lei=_KAPPA_LEI)),
        ],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_1)],
    )

    assert _companies(database) == (Company(1, "Kanzhun Ltd", _KAPPA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_1),)
    assert (result.instruments_added, result.securities) == (1, 1)


def test_two_receipts_of_a_company_are_read_as_one_share(database: Database) -> None:
    """Two receipt lines under two spellings end as one company with one instrument."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("PhosAgro PJSC", _SECOND_RECEIPT_ISIN, lei=_KAPPA_LEI)),
            _fund("DFAX", _line("PHOSAGRO PJSC", _RECEIPT_ISIN)),
        ],
        ordinary_shares=[
            _ordinary_share(_RECEIPT_ISIN, _ISIN_3),
            _ordinary_share(_SECOND_RECEIPT_ISIN, _ISIN_3),
        ],
    )

    assert _companies(database) == (Company(1, "PhosAgro PJSC", _KAPPA_LEI),)
    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert result.ordinary_shares_used == 2


def test_a_swapped_line_is_a_line_of_its_company_in_the_receipt_rule(
    database: Database,
) -> None:
    """Another receipt of the company is left out: the company has a line of its own now."""
    result = load_holdings(
        database,
        [
            _fund(
                "DFAX",
                _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI, category="OTHER", label="ADR"),
                _line(
                    "Kappa Ltd", _SECOND_RECEIPT_ISIN, lei=_KAPPA_LEI, category="OTHER", label="GDR"
                ),
            )
        ],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert _not_loaded(result) == [("DFAX", 2, NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED)]


def test_a_share_named_as_ordinary_is_no_receipt_whatever_a_line_says(
    database: Database,
) -> None:
    """A fund that files the ordinary share under receipt-like wording does not undo the swap."""
    result = load_holdings(
        database,
        [
            _fund("VXUS", _line("Kappa Ltd", _ISIN_3, lei=_KAPPA_LEI, title="KAPPA LTD-CDI")),
            _fund(
                "DFAX",
                _line("Kappa Ltd", _RECEIPT_ISIN, lei=_KAPPA_LEI, category="OTHER", label="ADR"),
            ),
        ],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )

    assert _instruments(database) == (Instrument(1, 1, _ISIN_3),)
    assert result.receipts_recognised == 0


def test_decisions_for_a_swapped_company_are_keyed_by_the_ordinary_share(
    database: Database,
) -> None:
    """The line is a line of the share, so that is the ISIN the other files speak of."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line(_PLACEHOLDER, _RECEIPT_ISIN, lei=_THETA_LEI))],
        [_decision(_ISIN_3, _KAPPA_LEI)],
        [_name_decision(_ISIN_3, "Kappa Ltd")],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )

    assert _companies(database) == (Company(1, "Kappa Ltd", _KAPPA_LEI),)
    assert (result.lei_decisions_used, result.name_decisions_used) == (1, 1)


def test_a_decision_keyed_by_a_swapped_receipt_is_refused(database: Database) -> None:
    """It could never apply: no line is read under the receipt's ISIN any more."""
    with pytest.raises(UniverseError, match="has to be keyed by that share") as raised:
        load_holdings(
            database,
            _receipt_only_funds(),
            name_decisions=[_name_decision(_RECEIPT_ISIN, "KT Corp")],
            ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
        )

    assert _RECEIPT_ISIN in str(raised.value)
    assert _companies(database) == ()


def test_a_receipt_that_is_swapped_and_kept_out_is_refused(database: Database) -> None:
    """The two files say opposite things about one security."""
    with pytest.raises(UniverseError, match="read as an ordinary share by another"):
        load_holdings(
            database,
            _receipt_only_funds(),
            exclusions=[_exclusion(_RECEIPT_ISIN)],
            ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
        )


@pytest.mark.parametrize(
    "also",
    [
        pytest.param("receipt", id="the ordinary share is itself listed as a receipt"),
        pytest.param("excluded", id="the ordinary share is kept out"),
    ],
)
def test_an_ordinary_share_that_is_not_to_be_loaded_itself_is_refused(
    database: Database, also: str
) -> None:
    """A chain of swaps, or a swap into a security that is kept out, has no meaning."""
    swaps = [_ordinary_share(_RECEIPT_ISIN, _ISIN_3)]
    exclusions = []
    if also == "receipt":
        swaps.append(_ordinary_share(_ISIN_3, _ISIN_1))
    else:
        exclusions.append(_exclusion(_ISIN_3))

    with pytest.raises(UniverseError, match="named as an ordinary share by one row") as raised:
        load_holdings(database, _receipt_only_funds(), exclusions=exclusions, ordinary_shares=swaps)

    assert _ISIN_3 in str(raised.value)


def test_two_swaps_for_one_receipt_are_refused(database: Database) -> None:
    """A receipt stands for one share; the load does not pick between two answers."""
    swaps = [_ordinary_share(_RECEIPT_ISIN, _ISIN_3), _ordinary_share(_RECEIPT_ISIN, _ISIN_1)]

    with pytest.raises(UniverseError, match="two decisions name an ordinary share"):
        load_holdings(database, _receipt_only_funds(), ordinary_shares=swaps)

    assert _companies(database) == ()


def test_a_database_that_holds_a_swapped_receipt_is_refused(database: Database) -> None:
    """The load never deletes, so it says that the database has to be rebuilt."""
    load_holdings(database, _receipt_only_funds())
    before = (_companies(database), _instruments(database))

    with pytest.raises(UniverseError) as raised:
        load_holdings(
            database,
            _receipt_only_funds(),
            ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
        )

    message = str(raised.value)
    assert (
        f"{database.path} holds receipts that a decision reads as their ordinary share" in message
    )
    assert _RECEIPT_ISIN in message
    assert "has to be rebuilt" in message
    assert (_companies(database), _instruments(database)) == before


def test_a_swap_for_a_receipt_no_fund_holds_changes_nothing(database: Database) -> None:
    """The file may name a receipt the filings do not hold; such a row waits."""
    result = load_holdings(
        database, _receipt_only_funds(), ordinary_shares=[_ordinary_share(_ISIN_5, _ISIN_3)]
    )

    assert _instruments(database) == (Instrument(1, 1, _RECEIPT_ISIN),)
    assert result.ordinary_shares_used == 0


def test_a_swapped_line_that_is_debt_keeps_its_own_reason(database: Database) -> None:
    """A swap does not make a line loadable."""
    result = load_holdings(
        database,
        [_fund("VXUS", _line("SAMPLE TREASURY", _RECEIPT_ISIN, category="DBT"))],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )

    assert _not_loaded(result) == [("VXUS", 1, NotLoadedReason.DEBT_OR_DERIVATIVE)]
    assert result.ordinary_shares_used == 0


def test_loading_with_a_swap_equals_loading_filings_that_carry_the_ordinary_share(
    database: Database, tmp_path: Path
) -> None:
    """A swap is exactly "as if the fund held the share"."""
    load_holdings(
        database,
        [
            _fund("VXUS", _line("Delta PLC", _ISIN_4, lei=_DELTA_LEI)),
            *_receipt_only_funds(),
        ],
        ordinary_shares=[_ordinary_share(_RECEIPT_ISIN, _ISIN_3)],
    )
    other_path = tmp_path / "other.db"
    migrate(other_path)
    other = Database(other_path)
    load_holdings(
        other,
        [
            _fund("VXUS", _line("Delta PLC", _ISIN_4, lei=_DELTA_LEI)),
            _fund("DFAX", _line("KT CORPORATION", _ISIN_3, lei=_KAPPA_LEI)),
        ],
    )

    assert _companies(database) == _companies(other)
    assert _instruments(database) == _instruments(other)


def test_a_second_run_with_the_same_swap_changes_nothing(database: Database) -> None:
    """A database built with the swap never held the receipt, so nothing is refused."""
    swaps = [_ordinary_share(_RECEIPT_ISIN, _ISIN_3)]
    load_holdings(database, _receipt_only_funds(), ordinary_shares=swaps)
    before = (_companies(database), _instruments(database))

    again = load_holdings(database, _receipt_only_funds(), ordinary_shares=swaps)

    assert (_companies(database), _instruments(database)) == before
    assert (again.companies_added, again.instruments_added, again.ordinary_shares_used) == (
        0,
        0,
        1,
    )


# --- Comparing names ---------------------------------------------------------------------

# Names as filings write them: letters, digits, common punctuation and spaces.
_NAMES: st.SearchStrategy[str] = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,&'-/()", max_size=40
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("BETA INC", "Beta Inc"),
        ("BETA INC", "  beta   inc "),
        ("BETA INC", "Beta\tInc"),
        ("STRASSE AG", "Straße AG"),
    ],
)
def test_case_and_spacing_do_not_tell_names_apart(left: str, right: str) -> None:
    """ADR 0006: 'ignoring upper and lower case and spacing'."""
    assert name_key(left) == name_key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("JHSF PARTICIPACOES S.A.", "JHSF PARTICIPACOES SA"),
        ("ChipMOS TECHNOLOGIES INC.", "ChipMOS Technologies Inc"),
        ("PFIZER INC", "PFIZER LTD"),
        ("ALPHA CORP", "ALPHACORP"),
        ("AT&T INC", "AT & T INC"),
    ],
)
def test_everything_else_tells_names_apart(left: str, right: str) -> None:
    """ADR 0009: punctuation counts, and so does where one word ends."""
    assert name_key(left) != name_key(right)


@given(name=st.text(max_size=40))
def test_comparing_a_compared_name_changes_nothing(name: str) -> None:
    """The key of a key is the key, for any text."""
    assert name_key(name_key(name)) == name_key(name)


@given(name=_NAMES)
def test_upper_and_lower_case_give_the_same_key(name: str) -> None:
    """However a sponsor capitalises a name, it compares the same."""
    assert name_key(name.upper()) == name_key(name.lower()) == name_key(name)


@given(words=st.lists(st.from_regex(r"[A-Za-z0-9.&]{1,8}", fullmatch=True), max_size=5))
def test_any_spacing_between_the_same_words_gives_the_same_key(words: list[str]) -> None:
    """One space, several, or a tab between words makes no difference."""
    assert name_key("   ".join(words) + " ") == name_key(" ".join(words))
    assert name_key("\t".join(words)) == name_key(" ".join(words))
