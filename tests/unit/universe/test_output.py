"""Tests for ``pyvalue.universe.output``: the two files a load writes.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.db import Company
from pyvalue.universe import (
    AgentCase,
    AgentCaseReason,
    HoldingLine,
    LoadResult,
    NotLoadedLine,
    NotLoadedReason,
    UniverseError,
)
from pyvalue.universe.output import CASES_FOR_AGENT_FILE, LINES_NOT_LOADED_FILE, write_output

_LEI: str = "549300THETA000000051"
_OTHER_LEI: str = "549300DELTA000000010"


def _line(
    number: int,
    *,
    issuer_name: str = "THETA AG",
    title: str = "THETA AG",
    lei: str | None = _LEI,
    isin: str | None = "DE00000T0019",
    category: str = "EC",
    category_label: str | None = None,
) -> HoldingLine:
    """Build a holdings line, a plain common share unless stated otherwise."""
    return HoldingLine(
        number=number,
        issuer_name=issuer_name,
        title=title,
        lei=lei,
        isin=isin,
        cusip=None,
        category=category,
        category_label=category_label,
        trading_country="DE",
        currency="EUR",
        ticker=None,
        sedol=None,
        sponsor_name=None,
    )


def _result(
    not_loaded: tuple[NotLoadedLine, ...] = (), agent_cases: tuple[AgentCase, ...] = ()
) -> LoadResult:
    """Build a load result that carries only what the output files show."""
    return LoadResult(
        lines_read=0,
        securities=0,
        receipts_recognised=0,
        receipts_kept=0,
        receipts_not_loaded=0,
        companies_added=0,
        instruments_added=0,
        joined_by_lei=0,
        joined_by_name=0,
        leis_filled=0,
        leis_corrected=0,
        lei_decisions_used=0,
        name_decisions_used=0,
        companies_renamed=0,
        exclusions_used=0,
        ordinary_shares_used=0,
        companies=0,
        instruments=0,
        holdings_stored=0,
        holdings_with_ticker=0,
        holdings_with_sedol=0,
        instruments_not_held=0,
        not_loaded=not_loaded,
        agent_cases=agent_cases,
    )


def test_both_files_are_written_into_the_folder(tmp_path: Path) -> None:
    """The folder is created; the paths are handed back for the command to print."""
    folder = tmp_path / "data" / "universe"

    files = write_output(_result(), folder)

    assert files.lines_not_loaded == folder / LINES_NOT_LOADED_FILE
    assert files.cases_for_agent == folder / CASES_FOR_AGENT_FILE
    assert files.lines_not_loaded.is_file()
    assert files.cases_for_agent.is_file()


def test_a_load_with_nothing_to_report_writes_the_headers_only(tmp_path: Path) -> None:
    """An empty file would look like a failed run; a header says 'nothing'."""
    files = write_output(_result(), tmp_path)

    assert files.lines_not_loaded.read_text(encoding="utf-8") == (
        "fund,line,reason,issuer_name,title,isin,lei,category,category_label\n"
    )
    assert files.cases_for_agent.read_text(encoding="utf-8") == (
        "fund,line,reason,isin,issuer_name,line_lei,company_id,company_name,company_lei,"
        "lei_owner_company_id,lei_owner_company_name\n"
    )


def test_a_line_not_loaded_is_written_as_filed(tmp_path: Path) -> None:
    """Absent values are empty cells; the filed placeholder is shown as it is."""
    not_loaded = (
        NotLoadedLine(
            "VTI",
            _line(5, issuer_name="GAMMA INC", title="GAMMA INC CVR", lei="N/A", isin=None),
            NotLoadedReason.NO_VALID_ISIN,
        ),
        NotLoadedLine(
            "DFAX",
            _line(6, category="OTHER", category_label="GDR"),
            NotLoadedReason.RECEIPT_COMPANY_ALREADY_LOADED,
        ),
        # ADR 0013: a security a decision keeps out of the universe.
        NotLoadedLine("VXUS", _line(7), NotLoadedReason.EXCLUDED_BY_DECISION),
    )

    files = write_output(_result(not_loaded=not_loaded), tmp_path)

    assert files.lines_not_loaded.read_text(encoding="utf-8").splitlines()[1:] == [
        "VTI,5,no_valid_isin,GAMMA INC,GAMMA INC CVR,,N/A,EC,",
        f"DFAX,6,receipt_company_already_loaded,THETA AG,THETA AG,DE00000T0019,{_LEI},OTHER,GDR",
        f"VXUS,7,excluded_by_decision,THETA AG,THETA AG,DE00000T0019,{_LEI},EC,",
    ]


def test_a_case_shows_the_line_and_the_companies_involved(tmp_path: Path) -> None:
    """Enough for an agent to start: the line, the company it met, and who has the identifier."""
    cases = (
        AgentCase(
            fund="DFAX",
            line=_line(4, issuer_name="Theta AG", lei=_OTHER_LEI),
            reason=AgentCaseReason.DIFFERENT_LEI,
            company=Company(6, "THETA AG", _LEI),
            lei_owner=None,
        ),
        AgentCase(
            fund="DFAX",
            line=_line(5, issuer_name="Iota KK", lei=_OTHER_LEI, isin="JP300000I006"),
            reason=AgentCaseReason.LEI_BELONGS_TO_ANOTHER_COMPANY,
            company=Company(7, "IOTA KK", None),
            lei_owner=Company(3, "DELTA PLC", _OTHER_LEI),
        ),
    )

    files = write_output(_result(agent_cases=cases), tmp_path)

    assert files.cases_for_agent.read_text(encoding="utf-8").splitlines()[1:] == [
        f"DFAX,4,different_lei,DE00000T0019,Theta AG,{_OTHER_LEI},6,THETA AG,{_LEI},,",
        f"DFAX,5,lei_belongs_to_another_company,JP300000I006,Iota KK,{_OTHER_LEI},7,IOTA KK,,3,"
        "DELTA PLC",
    ]


def test_a_name_with_a_comma_or_a_quote_stays_one_cell(tmp_path: Path) -> None:
    """Company names contain both; the file must still read back column by column."""
    not_loaded = (
        NotLoadedLine(
            "VXUS",
            _line(1, issuer_name='SAMPLE "QUOTED" CO, LTD', title="Société Générale, série A"),
            NotLoadedReason.DEBT_OR_DERIVATIVE,
        ),
    )

    files = write_output(_result(not_loaded=not_loaded), tmp_path)

    assert files.lines_not_loaded.read_text(encoding="utf-8").splitlines()[1] == (
        'VXUS,1,debt_or_derivative,"SAMPLE ""QUOTED"" CO, LTD","Société Générale, série A",'
        f"DE00000T0019,{_LEI},EC,"
    )


def test_every_line_ends_with_a_line_feed_only(tmp_path: Path) -> None:
    """The same bytes on every platform (ADR 0009)."""
    not_loaded = (NotLoadedLine("VTI", _line(1), NotLoadedReason.NO_VALID_ISIN),)

    files = write_output(_result(not_loaded=not_loaded), tmp_path)

    content = files.lines_not_loaded.read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content


def test_a_new_run_replaces_the_files_of_the_last(tmp_path: Path) -> None:
    """The files describe the latest load only; nothing of the old one stays."""
    write_output(
        _result(not_loaded=(NotLoadedLine("VTI", _line(1), NotLoadedReason.NO_VALID_ISIN),)),
        tmp_path,
    )

    files = write_output(_result(), tmp_path)

    assert len(files.lines_not_loaded.read_text(encoding="utf-8").splitlines()) == 1


def test_the_same_result_writes_the_same_bytes(tmp_path: Path) -> None:
    """Reproducibility: a file is a function of the load result and nothing else."""
    result = _result(
        not_loaded=(NotLoadedLine("VTI", _line(1), NotLoadedReason.NO_VALID_ISIN),),
        agent_cases=(
            AgentCase(
                fund="DFAX",
                line=_line(4),
                reason=AgentCaseReason.DIFFERENT_LEI,
                company=Company(6, "THETA AG", _LEI),
                lei_owner=None,
            ),
        ),
    )

    first = write_output(result, tmp_path / "first")
    second = write_output(result, tmp_path / "second")

    assert first.lines_not_loaded.read_bytes() == second.lines_not_loaded.read_bytes()
    assert first.cases_for_agent.read_bytes() == second.cases_for_agent.read_bytes()


def test_a_folder_that_cannot_be_written_is_reported(tmp_path: Path) -> None:
    """A file where the folder should be is a condition to report, not a crash."""
    blocker = tmp_path / "universe"
    blocker.write_text("a file where a folder is expected")

    with pytest.raises(UniverseError, match="cannot write"):
        write_output(_result(), blocker)
