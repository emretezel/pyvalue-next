"""Tests for ``pyvalue.universe.name_decisions``: reading the names file of ADR 0012.

What the file shares with the other decisions file, such as a missing file or
an unreadable one, is checked once more here, because a reader that forgot to
use the shared reading would otherwise go unnoticed.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import NameDecision, UniverseError
from pyvalue.universe.identifiers import is_valid_isin
from pyvalue.universe.name_decisions import packaged_name_decisions, read_name_decisions

_HEADER: str = "isin,name,decided_on,evidence\n"
_GOOD_ROW: str = "DE00000T0019,Theta AG,2026-11-21,Another fund files this name\n"


def _write(tmp_path: Path, text: str) -> Path:
    """Write a names file into the temporary folder and return its path."""
    path = tmp_path / "name.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_is_read_row_by_row(nport_samples: Path) -> None:
    """The sample file that goes with the sample filings."""
    decisions = read_name_decisions(nport_samples / "decisions" / "name.csv")

    assert decisions == (
        NameDecision(
            isin="JP300000I006",
            name="Iota KK",
            decided_on=date(2026, 11, 21),
            evidence=(
                "Made up: VXUS files the name in capitals; DFAX files this spelling for "
                "the same ISIN"
            ),
        ),
    )


def test_a_file_with_only_the_header_holds_no_decision(tmp_path: Path) -> None:
    """Before the first decision, the file is its header."""
    assert read_name_decisions(_write(tmp_path, _HEADER)) == ()


def test_a_name_may_contain_commas_quotes_and_other_scripts(tmp_path: Path) -> None:
    """A name is stored as the file has it, punctuation and all."""
    path = _write(
        tmp_path,
        _HEADER + 'DE00000T0019,"Theta (Group) Co., Ltd.",2026-11-21,'
        '"The register names ""株式会社マキタ"" for this security"\n',
    )

    (decision,) = read_name_decisions(path)

    assert decision.name == "Theta (Group) Co., Ltd."
    assert decision.evidence == 'The register names "株式会社マキタ" for this security'


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "the first row must be isin,name,decided_on,evidence", id="empty"),
        pytest.param(_GOOD_ROW, "the first row must be", id="no header"),
        pytest.param(
            "isin,lei,company,decided_on,evidence\n",
            "the first row must be isin,name,decided_on,evidence",
            id="the header of the other decisions file",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,Theta AG,2026-11-21\n",
            "row 2 has 3 cells where 4 are expected",
            id="a cell missing",
        ),
        pytest.param(
            _HEADER + "DE00000T0018,Theta AG,2026-11-21,Why\n",
            "row 2: 'DE00000T0018' is not a valid ISIN",
            id="ISIN with a wrong check digit",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,,2026-11-21,Why\n",
            "row 2: the name must not be empty",
            id="no name",
        ),
        pytest.param(
            _HEADER + "DE00000T0019, Theta AG,2026-11-21,Why\n",
            "row 2: the name must not be empty and must not carry stray spaces, got ' Theta AG'",
            id="name with a leading space",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,Theta  AG,2026-11-21,Why\n",
            "row 2: the name must not be empty and must not carry stray spaces",
            id="name with two spaces between words",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,Theta AG,2026-11-21,  \n",
            "row 2: the evidence must be filled in",
            id="blank evidence",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,Theta AG,21 November 2026,Why\n",
            r"row 2: '21 November 2026' is not a date \(YYYY-MM-DD\)",
            id="unreadable date",
        ),
        pytest.param(
            _HEADER + _GOOD_ROW + "DE00000T0019,Theta SE,2026-11-22,Why\n",
            "row 3: DE00000T0019 was already decided in row 2",
            id="the same security twice",
        ),
    ],
)
def test_a_bad_file_is_refused_with_the_row_that_is_wrong(
    tmp_path: Path, content: str, message: str
) -> None:
    """A file has no constraints, so the reader is the check (ADR 0012)."""
    path = _write(tmp_path, content)

    with pytest.raises(UniverseError, match=message) as raised:
        read_name_decisions(path)

    assert str(path) in str(raised.value)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(UniverseError, match="cannot read the decisions file"):
        read_name_decisions(tmp_path / "absent.csv")


def test_the_names_shipped_with_the_package_are_valid() -> None:
    """The real file is read with the same checks on every test run."""
    decisions = packaged_name_decisions()

    assert decisions, "the shipped names file holds no decision"
    assert all(is_valid_isin(decision.isin) for decision in decisions)
    assert len({decision.isin for decision in decisions}) == len(decisions)


def test_no_shipped_name_is_itself_a_placeholder() -> None:
    """ADR 0012: the file replaces vendor placeholders, so it must not contain one."""
    assert not [
        decision.name
        for decision in packaged_name_decisions()
        if "New Issuer" in decision.name or "Company ID" in decision.name
    ]
