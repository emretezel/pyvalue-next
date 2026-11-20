"""Tests for ``pyvalue.db.connection``.

Author: Emre Tezel
"""

import sqlite3
from pathlib import Path

import pytest

from pyvalue.db import DEFAULT_DATABASE_PATH, DatabaseError
from pyvalue.db.connection import connect


def test_default_path_is_relative_to_the_working_folder() -> None:
    """The default database belongs to the folder pyvalue is run from."""
    assert Path("data") / "pyvalue.db" == DEFAULT_DATABASE_PATH
    assert not DEFAULT_DATABASE_PATH.is_absolute()


def test_connect_creates_the_file_and_its_parent_folder(tmp_path: Path) -> None:
    """A first run needs no manual setup: the folder and the file are created."""
    path = tmp_path / "nested" / "folder" / "pyvalue.db"

    connection = connect(path)
    try:
        # SQLite writes the file on first access to its content.
        connection.execute("CREATE TABLE probe (probe_id INTEGER PRIMARY KEY)")
    finally:
        connection.close()

    assert path.is_file()


def test_connect_switches_foreign_keys_on(database_path: Path) -> None:
    """SQLite defaults to foreign keys off; every pyvalue connection has them on."""
    connection = connect(database_path)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        connection.close()


def test_connect_enforces_foreign_keys(database_path: Path) -> None:
    """The pragma is not just set: a row pointing at a missing parent is refused."""
    connection = connect(database_path)
    try:
        connection.execute("CREATE TABLE parent (parent_id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child (child_id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parent (parent_id))"
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            connection.execute("INSERT INTO child (parent_id) VALUES (1)")
    finally:
        connection.close()


def test_connect_opens_no_implicit_transaction(database_path: Path) -> None:
    """A write outside a transaction is committed at once and leaves none open."""
    connection = connect(database_path)
    try:
        connection.execute("CREATE TABLE probe (probe_id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO probe (probe_id) VALUES (1)")
        assert not connection.in_transaction
    finally:
        connection.close()

    # A second connection sees the row, so it was committed without a commit().
    second = connect(database_path)
    try:
        assert second.execute("SELECT probe_id FROM probe").fetchall() == [(1,)]
    finally:
        second.close()


def test_connect_rejects_a_file_that_is_not_a_database(tmp_path: Path) -> None:
    """A wrong path fails with pyvalue's own error, naming the file."""
    path = tmp_path / "notes.db"
    path.write_text("this is not a SQLite database, just some text " * 20)

    with pytest.raises(DatabaseError, match="cannot open database"):
        connect(path)


def test_connect_rejects_a_path_whose_parent_is_a_file(tmp_path: Path) -> None:
    """A folder that cannot be created is reported, not left as a raw OS error."""
    blocker = tmp_path / "data"
    blocker.write_text("a file where a folder is expected")

    with pytest.raises(DatabaseError, match="cannot open database"):
        connect(blocker / "pyvalue.db")
