"""Tests for ``pyvalue.universe.ordinary_shares``: reading the file of ADR 0015.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import OrdinaryShare, UniverseError
from pyvalue.universe.exclusions import packaged_exclusions
from pyvalue.universe.identifiers import is_valid_isin
from pyvalue.universe.lei_decisions import packaged_lei_decisions
from pyvalue.universe.name_decisions import packaged_name_decisions
from pyvalue.universe.ordinary_shares import packaged_ordinary_shares, read_ordinary_shares

_HEADER: str = "isin,ordinary_isin,company,decided_on,evidence\n"
_GOOD_ROW: str = (
    "US00000O0018,SG00000O0017,Omicron Ltd,2026-11-21,A receipt; the share trades at home\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    """Write a file of receipts and ordinary shares and return its path."""
    path = tmp_path / "ordinary_share.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_is_read_row_by_row(nport_samples: Path) -> None:
    """The sample file that goes with the sample filings."""
    decisions = read_ordinary_shares(nport_samples / "decisions" / "ordinary_share.csv")

    assert decisions == (
        OrdinaryShare(
            isin="US00000O0018",
            ordinary_isin="SG00000O0017",
            company="Omicron Ltd",
            decided_on=date(2026, 11, 21),
            evidence=(
                "Made up: a depositary receipt, which DFAX labels ADR; the ordinary share "
                "trades at home, where no sample fund holds it"
            ),
        ),
    )


def test_a_file_with_only_the_header_swaps_nothing(tmp_path: Path) -> None:
    """Before the first decision, the file is its header."""
    assert read_ordinary_shares(_write(tmp_path, _HEADER)) == ()


def test_two_receipts_may_name_the_same_ordinary_share(tmp_path: Path) -> None:
    """A company can have two receipt lines, and both stand for one share."""
    path = _write(
        tmp_path, _HEADER + _GOOD_ROW + "US00000H0017,SG00000O0017,Omicron Ltd,2026-11-21,Why\n"
    )

    decisions = read_ordinary_shares(path)

    assert [decision.ordinary_isin for decision in decisions] == ["SG00000O0017", "SG00000O0017"]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(
            "", "the first row must be isin,ordinary_isin,company,decided_on,evidence", id="empty"
        ),
        pytest.param(_GOOD_ROW, "the first row must be", id="no header"),
        pytest.param(
            "isin,company,decided_on,evidence\n",
            "the first row must be isin,ordinary_isin,company,decided_on,evidence",
            id="the header of the exclusions file",
        ),
        pytest.param(
            _HEADER + "US00000O0018,Omicron Ltd,2026-11-21,Why\n",
            "row 2 has 4 cells where 5 are expected",
            id="the ordinary share missing",
        ),
        pytest.param(
            _HEADER + "US00000O0019,SG00000O0017,Omicron Ltd,2026-11-21,Why\n",
            "row 2: 'US00000O0019' is not a valid ISIN",
            id="receipt with a wrong check digit",
        ),
        pytest.param(
            _HEADER + "US00000O0018,SG00000O0018,Omicron Ltd,2026-11-21,Why\n",
            "row 2: 'SG00000O0018' is not a valid ISIN",
            id="ordinary share with a wrong check digit",
        ),
        pytest.param(
            _HEADER + "US00000O0018,,Omicron Ltd,2026-11-21,Why\n",
            "row 2: '' is not a valid ISIN",
            id="no ordinary share",
        ),
        pytest.param(
            _HEADER + "US00000O0018,US00000O0018,Omicron Ltd,2026-11-21,Why\n",
            "row 2: US00000O0018 is given as its own ordinary share",
            id="a security paired with itself",
        ),
        pytest.param(
            _HEADER + "US00000O0018,SG00000O0017,,2026-11-21,Why\n",
            "row 2: the company and the evidence must both be filled in",
            id="no company name",
        ),
        pytest.param(
            _HEADER + "US00000O0018,SG00000O0017,Omicron Ltd,2026-11-21,\n",
            "row 2: the company and the evidence must both be filled in",
            id="no evidence",
        ),
        pytest.param(
            _HEADER + "US00000O0018,SG00000O0017,Omicron Ltd,yesterday,Why\n",
            "row 2: 'yesterday' is not a date",
            id="unreadable date",
        ),
        pytest.param(
            _HEADER + _GOOD_ROW + "US00000O0018,KR70000H0005,Omicron Ltd,2026-11-22,Why\n",
            "row 3: US00000O0018 was already decided in row 2",
            id="the same receipt twice",
        ),
    ],
)
def test_a_bad_file_is_refused_with_the_row_that_is_wrong(
    tmp_path: Path, content: str, message: str
) -> None:
    """A file has no constraints, so the reader is the check (ADR 0015)."""
    path = _write(tmp_path, content)

    with pytest.raises(UniverseError, match=message) as raised:
        read_ordinary_shares(path)

    assert str(path) in str(raised.value)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(UniverseError, match="cannot read the decisions file"):
        read_ordinary_shares(tmp_path / "absent.csv")


def test_the_pairs_shipped_with_the_package_are_valid() -> None:
    """The real file is read with the same checks on every test run."""
    decisions = packaged_ordinary_shares()

    assert decisions, "the shipped file of ordinary shares holds no decision"
    assert all(is_valid_isin(decision.isin) for decision in decisions)
    assert all(is_valid_isin(decision.ordinary_isin) for decision in decisions)
    assert len({decision.isin for decision in decisions}) == len(decisions)


def test_the_shipped_files_do_not_contradict_each_other() -> None:
    """ADR 0015: what the load would refuse, found before anyone runs it.

    A receipt that is read as its ordinary share is not also kept out, has
    no identifier or name decision of its own, and no ordinary share is
    itself listed as a receipt or kept out.
    """
    swaps = packaged_ordinary_shares()
    receipts = {decision.isin for decision in swaps}
    ordinary = {decision.ordinary_isin for decision in swaps}
    excluded = {exclusion.isin for exclusion in packaged_exclusions()}
    decided = {decision.isin for decision in packaged_lei_decisions()} | {
        decision.isin for decision in packaged_name_decisions()
    }

    assert not receipts & excluded
    assert not receipts & decided
    assert not ordinary & (receipts | excluded)
