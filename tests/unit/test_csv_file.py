"""Tests for ``pyvalue.csv_file``: reading a committed file with a fixed header.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.csv_file import read_csv, write_csv
from pyvalue.errors import PyvalueError

_HEADER: tuple[str, ...] = ("code", "name")


class _FileError(PyvalueError):
    """Stands in for a component's own error."""


def _write(tmp_path: Path, text: str) -> Path:
    """Write a file into the temporary folder and return its path."""
    path = tmp_path / "sample.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_rows_after_the_header_are_returned_with_where_they_are(tmp_path: Path) -> None:
    """A row is located by the file and its number, counting the header as row 1."""
    path = _write(tmp_path, 'code,name\nA,Alpha\nB,"Beta, the second"\n')

    assert read_csv(path, _HEADER, _FileError, "the sample file") == (
        (f"{path} row 2", ["A", "Alpha"]),
        (f"{path} row 3", ["B", "Beta, the second"]),
    )


def test_a_file_with_only_its_header_has_no_rows(tmp_path: Path) -> None:
    """Before the first row is written, the file is its header."""
    assert read_csv(_write(tmp_path, "code,name\n"), _HEADER, _FileError, "the sample file") == ()


def test_an_empty_cell_is_an_empty_text(tmp_path: Path) -> None:
    """What an empty cell means is for the reader of that kind of file to decide."""
    path = _write(tmp_path, "code,name\nA,\n")

    assert read_csv(path, _HEADER, _FileError, "the sample file") == ((f"{path} row 2", ["A", ""]),)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "the first row must be code,name", id="empty"),
        pytest.param("A,Alpha\n", "the first row must be code,name", id="no header"),
        pytest.param(
            "name,code\n", "the first row must be code,name", id="columns in another order"
        ),
        pytest.param(
            "code,name\nA\n", "row 2 has 1 cells where 2 are expected", id="a cell missing"
        ),
        pytest.param(
            "code,name\nA,Alpha\nB,Beta,extra\n",
            "row 3 has 3 cells where 2 are expected",
            id="a cell too many",
        ),
    ],
)
def test_a_file_of_another_shape_is_refused(tmp_path: Path, content: str, message: str) -> None:
    """The error is the caller's own and says which row."""
    with pytest.raises(_FileError, match=message):
        read_csv(_write(tmp_path, content), _HEADER, _FileError, "the sample file")


def test_a_file_that_is_not_there_is_reported_as_what_it_is(tmp_path: Path) -> None:
    """The message uses the caller's words for the file."""
    with pytest.raises(_FileError, match="cannot read the sample file"):
        read_csv(tmp_path / "missing.csv", _HEADER, _FileError, "the sample file")


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 must not escape as a raw decoding error."""
    path = tmp_path / "sample.csv"
    path.write_bytes(b"code,name\n\xff\xfe,x\n")

    with pytest.raises(_FileError, match="cannot read the sample file"):
        read_csv(path, _HEADER, _FileError, "the sample file")


def test_a_written_file_is_its_header_and_its_rows(tmp_path: Path) -> None:
    """Line ends are plain new lines on every platform, and a comma in a cell is quoted."""
    path = tmp_path / "out.csv"

    write_csv(path, _HEADER, [("A", "Alpha"), ("B", "Beta, the second")], _FileError)

    assert path.read_bytes() == b'code,name\nA,Alpha\nB,"Beta, the second"\n'


def test_a_file_written_without_rows_is_its_header(tmp_path: Path) -> None:
    """A run with nothing to report still leaves a file that says so."""
    path = tmp_path / "out.csv"

    write_csv(path, _HEADER, [], _FileError)

    assert path.read_text(encoding="utf-8") == "code,name\n"


def test_writing_creates_the_folder_and_replaces_what_was_there(tmp_path: Path) -> None:
    """The file describes the latest run only."""
    path = tmp_path / "new" / "folder" / "out.csv"

    write_csv(path, _HEADER, [("A", "Alpha")], _FileError)
    write_csv(path, _HEADER, [("B", "Beta")], _FileError)

    assert path.read_text(encoding="utf-8") == "code,name\nB,Beta\n"


def test_what_is_written_can_be_read_back(tmp_path: Path) -> None:
    """The reader and the writer agree on the shape."""
    path = tmp_path / "out.csv"
    rows = [("A", 'He said "no"'), ("B", "two\nlines")]

    write_csv(path, _HEADER, rows, _FileError)

    assert [cells for _, cells in read_csv(path, _HEADER, _FileError, "the sample file")] == [
        list(row) for row in rows
    ]


def test_a_file_that_cannot_be_written_is_the_components_error(tmp_path: Path) -> None:
    """A folder in the place of the file: the message names the path."""
    path = tmp_path / "out.csv"
    path.mkdir()

    with pytest.raises(_FileError, match="cannot write"):
        write_csv(path, _HEADER, [], _FileError)
