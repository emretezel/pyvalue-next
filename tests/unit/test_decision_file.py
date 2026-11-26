"""Tests for ``pyvalue.decision_file``: what every decisions file shares.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from pyvalue.decision_file import read_decisions, read_packaged, valid_day, valid_isin
from pyvalue.errors import PyvalueError

_HEADER: tuple[str, ...] = ("isin", "decided_on")

# Two made-up ISINs with correct check digits.
_ALPHA: str = "US0000000002"
_BETA: str = "KR7000100008"


class _FileError(PyvalueError):
    """Stands in for a component's own error."""


@dataclass(frozen=True, slots=True)
class _Sample:
    """The smallest decision: a security and a day."""

    isin: str
    decided_on: date


def _sample(row: list[str], where: str) -> _Sample:
    """Turn one row into a decision, with the two checks every reader makes."""
    isin, decided_on = row
    return _Sample(
        isin=valid_isin(isin, where, _FileError),
        decided_on=valid_day(decided_on, where, _FileError),
    )


def _write(tmp_path: Path, text: str) -> Path:
    """Write a decisions file into the temporary folder and return its path."""
    path = tmp_path / "sample.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_decisions_are_returned_in_the_order_of_the_file(tmp_path: Path) -> None:
    """Each row is handed to the reader of its kind."""
    path = _write(tmp_path, f"isin,decided_on\n{_BETA},2026-11-26\n{_ALPHA},2026-11-25\n")

    assert read_decisions(path, _HEADER, _sample, _FileError) == (
        _Sample(_BETA, date(2026, 11, 26)),
        _Sample(_ALPHA, date(2026, 11, 25)),
    )


def test_a_file_with_only_its_header_holds_no_decision(tmp_path: Path) -> None:
    """That is how a decisions file starts."""
    assert read_decisions(_write(tmp_path, "isin,decided_on\n"), _HEADER, _sample, _FileError) == ()


def test_a_security_decided_twice_is_refused_with_both_rows(tmp_path: Path) -> None:
    """Two answers for one security: the file must say which one holds."""
    path = _write(tmp_path, f"isin,decided_on\n{_ALPHA},2026-11-26\n{_ALPHA},2026-11-27\n")

    with pytest.raises(_FileError, match=f"row 3: {_ALPHA} was already decided in row 2"):
        read_decisions(path, _HEADER, _sample, _FileError)


def test_a_wrong_header_is_the_components_error(tmp_path: Path) -> None:
    """The checks of the file itself raise the same error as the rows."""
    with pytest.raises(_FileError, match="the first row must be isin,decided_on"):
        read_decisions(_write(tmp_path, "isin,day\n"), _HEADER, _sample, _FileError)


def test_a_missing_file_is_called_the_decisions_file(tmp_path: Path) -> None:
    """The message says what could not be read."""
    with pytest.raises(_FileError, match="cannot read the decisions file"):
        read_decisions(tmp_path / "absent.csv", _HEADER, _sample, _FileError)


def test_a_valid_isin_is_returned_as_it_is() -> None:
    """The check passes the cell through."""
    assert valid_isin(_ALPHA, "row 2", _FileError) == _ALPHA


@pytest.mark.parametrize("text", ["", "US0000000001", "us0000000002", " US0000000002"])
def test_a_cell_that_is_not_an_isin_is_refused_with_its_row(text: str) -> None:
    """A wrong check digit is caught as well as a wrong shape."""
    with pytest.raises(_FileError, match="row 2: '.*' is not a valid ISIN"):
        valid_isin(text, "row 2", _FileError)


def test_a_day_is_read_as_a_date() -> None:
    """Dates are written as YYYY-MM-DD."""
    assert valid_day("2026-11-26", "row 2", _FileError) == date(2026, 11, 26)


@pytest.mark.parametrize("text", ["", "26.11.2026", "2026-13-01", "today"])
def test_a_cell_that_is_not_a_date_is_refused_with_its_row(text: str) -> None:
    """The message says which form is expected."""
    with pytest.raises(_FileError, match=r"row 2: '.*' is not a date \(YYYY-MM-DD\)"):
        valid_day(text, "row 2", _FileError)


def test_a_packaged_file_is_found_in_the_decisions_folder_of_its_component() -> None:
    """The reader is handed a real path to the shipped file."""
    seen: list[Path] = []

    def read(path: Path) -> tuple[str, ...]:
        seen.append(path)
        return (path.read_text(encoding="utf-8").splitlines()[0],)

    assert read_packaged("pyvalue.universe", "excluded.csv", read) == (
        "isin,company,decided_on,evidence",
    )
    assert [path.name for path in seen] == ["excluded.csv"]
