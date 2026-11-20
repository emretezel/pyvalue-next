"""Property-based tests for the identifier shapes the schema enforces.

The ADRs state each shape in words ("12 characters: two letters, nine letters
or digits, one digit"). The schema states it as a ``CHECK`` built from ``GLOB``
and ``length``, which is easy to get subtly wrong. These tests say each shape a
third time, as a regular expression, and let Hypothesis look for any string on
which the database and the expression disagree.

Author: Emre Tezel
"""

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import connect, migrate

# The documented shapes, written independently of the SQL.
_MIC: re.Pattern[str] = re.compile(r"[A-Z0-9]{4}")
_COUNTRY: re.Pattern[str] = re.compile(r"[A-Z]{2}")
_CURRENCY: re.Pattern[str] = re.compile(r"[A-Z]{3}")
_ISIN: re.Pattern[str] = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_LEI: re.Pattern[str] = re.compile(r"[A-Z0-9]{18}[0-9]{2}")

# Characters that look right and characters that must be refused: lower case,
# spaces and punctuation, and letters and digits from outside ASCII.
_NOISE: str = "ABCXYZ0189abcz .-_*?[]%É１"


def _candidates(shape: re.Pattern[str], length: int) -> st.SearchStrategy[str]:
    """Strings that fit ``shape``, near misses of the right length, and noise.

    Random text almost never fits a shape, and a constraint that refused
    everything would pass a test fed only random text. So about a third of the
    candidates fit, and another third have the right length.
    """
    return st.one_of(
        st.from_regex(shape, fullmatch=True),
        st.text(alphabet=_NOISE, min_size=length, max_size=length),
        st.text(alphabet=_NOISE, max_size=length + 3),
    )


@pytest.fixture(scope="module")
def shapes_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[sqlite3.Connection]:
    """Yield one migrated database for all examples of this module.

    Every example runs inside a transaction that is rolled back, so the rows an
    example inserts never meet the rows of another.
    """
    path: Path = tmp_path_factory.mktemp("shapes") / "pyvalue.db"
    migrate(path)
    connection = connect(path)
    # Parents for the rows the examples try to insert.
    connection.execute("INSERT INTO exchange (mic, name, country) VALUES ('XNYS', 'NYSE', 'US')")
    connection.execute("INSERT INTO company (company_id, name) VALUES (1, 'Parent Co')")
    connection.execute(
        "INSERT INTO instrument (instrument_id, company_id, isin) VALUES (1, 1, 'US0846707026')"
    )
    try:
        yield connection
    finally:
        connection.close()


def _accepted(connection: sqlite3.Connection, statement: str, value: str) -> bool:
    """Say whether the database accepts ``value``, leaving no row behind."""
    connection.execute("BEGIN")
    try:
        connection.execute(statement, (value,))
    except sqlite3.IntegrityError:
        return False
    else:
        return True
    finally:
        connection.execute("ROLLBACK")


@given(value=_candidates(_MIC, 4))
def test_market_code_shape(shapes_db: sqlite3.Connection, value: str) -> None:
    """Exactly four upper-case letters or digits (ADR 0001)."""
    statement = "INSERT INTO exchange (mic, name, country) VALUES (?, 'Probe', 'US')"

    # 'XNYS' is taken by the fixture row, so it is refused for being a repeat.
    expected = bool(_MIC.fullmatch(value)) and value != "XNYS"
    assert _accepted(shapes_db, statement, value) == expected


@given(value=_candidates(_COUNTRY, 2))
def test_country_shape(shapes_db: sqlite3.Connection, value: str) -> None:
    """Exactly two upper-case letters (ADR 0001)."""
    statement = "INSERT INTO exchange (mic, name, country) VALUES ('XPRB', 'Probe', ?)"

    assert _accepted(shapes_db, statement, value) == bool(_COUNTRY.fullmatch(value))


@given(value=_candidates(_CURRENCY, 3))
def test_currency_shape(shapes_db: sqlite3.Connection, value: str) -> None:
    """Exactly three upper-case letters (ADR 0003)."""
    statement = (
        "INSERT INTO listing (instrument_id, mic, ticker, currency) VALUES (1, 'XNYS', 'PROBE', ?)"
    )

    assert _accepted(shapes_db, statement, value) == bool(_CURRENCY.fullmatch(value))


@given(value=_candidates(_ISIN, 12))
def test_isin_shape(shapes_db: sqlite3.Connection, value: str) -> None:
    """Two letters, nine letters or digits, one digit (ADR 0003)."""
    statement = "INSERT INTO instrument (company_id, isin) VALUES (1, ?)"

    # The fixture's own ISIN is refused for being a repeat.
    expected = bool(_ISIN.fullmatch(value)) and value != "US0846707026"
    assert _accepted(shapes_db, statement, value) == expected


@given(value=_candidates(_LEI, 20))
def test_legal_entity_identifier_shape(shapes_db: sqlite3.Connection, value: str) -> None:
    """Twenty upper-case letters or digits, the last two being digits (ADR 0001)."""
    statement = "INSERT INTO company (name, lei) VALUES ('Probe', ?)"

    assert _accepted(shapes_db, statement, value) == bool(_LEI.fullmatch(value))
