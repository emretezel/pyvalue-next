"""Tests for ``pyvalue.saved_file``: a downloaded file is whole or absent.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.errors import PyvalueError
from pyvalue.saved_file import save_whole


class _FileError(PyvalueError):
    """Stands in for a component's own error."""


def test_the_bytes_are_kept_under_the_final_name(tmp_path: Path) -> None:
    """What was given is what is read back, byte for byte."""
    destination = tmp_path / "answer.json"

    save_whole(b'{"Code": "ALFA"}', destination, _FileError)

    assert destination.read_bytes() == b'{"Code": "ALFA"}'


def test_the_folder_is_created_when_it_is_missing(tmp_path: Path) -> None:
    """A first download has no folder to write into yet."""
    destination = tmp_path / "eodhd" / "fundamentals" / "US" / "ALFA.json.gz"

    save_whole(b"payload", destination, _FileError)

    assert destination.read_bytes() == b"payload"


def test_a_file_that_is_there_is_replaced(tmp_path: Path) -> None:
    """Whether an answer may replace a saved one is the caller's decision, made before."""
    destination = tmp_path / "answer.json"
    destination.write_bytes(b"old")

    save_whole(b"new", destination, _FileError)

    assert destination.read_bytes() == b"new"


def test_no_temporary_file_stays_behind(tmp_path: Path) -> None:
    """The temporary name exists only while the bytes are written."""
    save_whole(b"payload", tmp_path / "answer.json", _FileError)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["answer.json"]


def test_a_file_that_cannot_be_written_is_the_callers_own_error(tmp_path: Path) -> None:
    """The message names the file; the error is of the class the caller gave."""
    blocker = tmp_path / "eodhd"
    blocker.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(_FileError, match=r"cannot save .*answer\.json"):
        save_whole(b"payload", blocker / "answer.json", _FileError)


def test_a_failed_save_keeps_the_file_that_was_there(tmp_path: Path) -> None:
    """The final name is touched only by the rename, which did not happen."""
    destination = tmp_path / "answer.json"
    destination.write_bytes(b"old")
    # A folder under the temporary name makes the write fail before the rename.
    (tmp_path / "answer.json.part").mkdir()

    with pytest.raises(_FileError, match="cannot save"):
        save_whole(b"new", destination, _FileError)

    assert destination.read_bytes() == b"old"
