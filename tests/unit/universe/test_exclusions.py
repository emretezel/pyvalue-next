"""Tests for ``pyvalue.universe.exclusions``: reading the file of ADR 0013.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import Exclusion, UniverseError
from pyvalue.universe.exclusions import packaged_exclusions, read_exclusions
from pyvalue.universe.identifiers import is_valid_isin
from pyvalue.universe.lei_decisions import packaged_lei_decisions
from pyvalue.universe.name_decisions import packaged_name_decisions

_HEADER: str = "isin,company,decided_on,evidence\n"
_GOOD_ROW: str = "US00000H0017,Eta Holdings Ltd,2026-11-21,A receipt; the share is listed at home\n"


def _write(tmp_path: Path, text: str) -> Path:
    """Write an exclusions file into the temporary folder and return its path."""
    path = tmp_path / "excluded.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_is_read_row_by_row(nport_samples: Path) -> None:
    """The sample file that goes with the sample filings."""
    exclusions = read_exclusions(nport_samples / "decisions" / "excluded.csv")

    assert exclusions == (
        Exclusion(
            isin="US00000H0017",
            company="Eta Holdings Ltd",
            decided_on=date(2026, 11, 21),
            evidence=(
                "Made up: a depositary receipt whose ordinary share is listed at home, "
                "where no sample fund holds it"
            ),
        ),
    )


def test_a_file_with_only_the_header_excludes_nothing(tmp_path: Path) -> None:
    """Before the first decision, the file is its header."""
    assert read_exclusions(_write(tmp_path, _HEADER)) == ()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "the first row must be isin,company,decided_on,evidence", id="empty"),
        pytest.param(_GOOD_ROW, "the first row must be", id="no header"),
        pytest.param(
            "isin,name,decided_on,evidence\n",
            "the first row must be isin,company,decided_on,evidence",
            id="the header of the names file",
        ),
        pytest.param(
            _HEADER + "US00000H0017,Eta Holdings Ltd,2026-11-21\n",
            "row 2 has 3 cells where 4 are expected",
            id="a cell missing",
        ),
        pytest.param(
            _HEADER + "US00000H0018,Eta Holdings Ltd,2026-11-21,Why\n",
            "row 2: 'US00000H0018' is not a valid ISIN",
            id="ISIN with a wrong check digit",
        ),
        pytest.param(
            _HEADER + "US00000H0017,,2026-11-21,Why\n",
            "row 2: the company and the evidence must both be filled in",
            id="no company name",
        ),
        pytest.param(
            _HEADER + "US00000H0017,Eta Holdings Ltd,2026-11-21, \n",
            "row 2: the company and the evidence must both be filled in",
            id="blank evidence",
        ),
        pytest.param(
            _HEADER + "US00000H0017,Eta Holdings Ltd,2026-13-01,Why\n",
            "row 2: '2026-13-01' is not a date",
            id="a month that does not exist",
        ),
        pytest.param(
            _HEADER + _GOOD_ROW + "US00000H0017,Eta Holdings Ltd,2026-11-22,Why\n",
            "row 3: US00000H0017 was already decided in row 2",
            id="the same security twice",
        ),
    ],
)
def test_a_bad_file_is_refused_with_the_row_that_is_wrong(
    tmp_path: Path, content: str, message: str
) -> None:
    """A file has no constraints, so the reader is the check (ADR 0013)."""
    path = _write(tmp_path, content)

    with pytest.raises(UniverseError, match=message) as raised:
        read_exclusions(path)

    assert str(path) in str(raised.value)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(UniverseError, match="cannot read the decisions file"):
        read_exclusions(tmp_path / "absent.csv")


def test_the_exclusions_shipped_with_the_package_are_valid() -> None:
    """The real file is read with the same checks on every test run.

    It may hold no row: since ADR 0015 the receipts that were kept out are
    read as their ordinary shares instead.
    """
    exclusions = packaged_exclusions()

    assert all(is_valid_isin(exclusion.isin) for exclusion in exclusions)
    assert len({exclusion.isin for exclusion in exclusions}) == len(exclusions)


def test_no_shipped_decision_is_about_an_excluded_security() -> None:
    """ADR 0013: a security that is kept out has no identifier or name to decide.

    The load refuses such files; this says so before anyone runs it.
    """
    excluded = {exclusion.isin for exclusion in packaged_exclusions()}
    decided = {decision.isin for decision in packaged_lei_decisions()} | {
        decision.isin for decision in packaged_name_decisions()
    }

    assert not excluded & decided
