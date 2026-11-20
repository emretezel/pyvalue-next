"""Tests for ``pyvalue.universe.load``: the rules of ADR 0006, one at a time.

Each test builds a few holdings lines by hand, loads them into a temporary
database through the same unit of work the load itself uses, and reads the two
tables back. The end-to-end run on sample filings is in
``tests/integration/test_universe_load.py``.

Author: Emre Tezel
"""

from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import Company, ConstraintError, Database, DatabaseError, Instrument
from pyvalue.universe import (
    AgentCaseReason,
    FundHoldings,
    HoldingLine,
    LoadResult,
    NotLoadedReason,
    UniverseError,
    load_holdings,
)
from pyvalue.universe.load import name_key

# Made-up identifiers with correct check digits.
_ALPHA_LEI: str = "549300ALPHA000000003"
_DELTA_LEI: str = "549300DELTA000000010"
_THETA_LEI: str = "549300THETA000000051"
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
