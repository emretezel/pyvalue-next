"""Tests for the ``provider_symbol`` table and the key it points at.

Migration 0005 creates them (ADR 0018), and migration 0006 takes the venue
label and the type out of the table (ADR 0025). The tests pin which rows the
database accepts, which it refuses and by which constraint, what happens to
symbol rows when a mapping changes, which index each lookup of the listing
rule uses, and what the two migrations do to a database that already has
rows.

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyvalue.db import migrate, packaged_migrations
from pyvalue.db.connection import connect

_CHECK = "CHECK constraint failed"
_FOREIGN_KEY = "FOREIGN KEY constraint failed"
_UNIQUE = "UNIQUE constraint failed"
_NOT_NULL = "NOT NULL constraint failed"

# The columns of the table today, in order (ADR 0018 without the two of ADR 0025).
_COLUMNS: list[str] = [
    "provider_code",
    "provider_exchange_code",
    "provider_symbol",
    "mic",
    "provider_name",
    "provider_currency",
    "isin",
]

# Valid rows, the examples of ADR 0018. EODHD's ``US`` covers two of our
# exchanges, ``KO`` one, and ``LSE`` one.
_REFERENCE: tuple[str, ...] = (
    "INSERT INTO exchange (mic, name, country) VALUES "
    "('XNYS', 'New York Stock Exchange', 'US'), ('XNAS', 'Nasdaq', 'US'), "
    "('XKRX', 'Korea Exchange', 'KR'), ('XLON', 'London Stock Exchange', 'GB'), "
    "('XKLS', 'Bursa Malaysia', 'MY')",
    "INSERT INTO provider (provider_code, name) VALUES ('eodhd', 'EODHD')",
    "INSERT INTO provider_exchange (provider_code, mic, provider_exchange_code) VALUES "
    "('eodhd', 'XNYS', 'US'), ('eodhd', 'XNAS', 'US'), ('eodhd', 'XKRX', 'KO'), "
    "('eodhd', 'XLON', 'LSE'), ('eodhd', 'XKLS', 'KLSE')",
)
_SYMBOLS: str = (
    "INSERT INTO provider_symbol (provider_code, provider_exchange_code, provider_symbol, mic, "
    "provider_name, provider_currency, isin) VALUES "
    "('eodhd', 'KO', '000660', 'XKRX', 'SK Hynix Inc', 'KRW', 'KR7000660001'), "
    "('eodhd', 'US', 'BRK-B', 'XNYS', 'Berkshire Hathaway Inc', 'USD', 'US0846707026'), "
    "('eodhd', 'LSE', 'SHEL', 'XLON', 'Shell plc', 'GBX', 'GB00BP6MXD84'), "
    "('eodhd', 'KLSE', '1155', 'XKLS', NULL, 'MYR', NULL)"
)

# The same four lines as the table took them before migration 0006, with the
# venue label and the type.
_SYMBOLS_AT_5: str = (
    "INSERT INTO provider_symbol (provider_code, provider_exchange_code, provider_symbol, mic, "
    "provider_venue, provider_name, provider_type, provider_currency, isin) VALUES "
    "('eodhd', 'KO', '000660', 'XKRX', 'KO', 'SK Hynix Inc', 'Common Stock', 'KRW', "
    "'KR7000660001'), "
    "('eodhd', 'US', 'BRK-B', 'XNYS', 'NYSE', 'Berkshire Hathaway Inc', 'Common Stock', 'USD', "
    "'US0846707026'), "
    "('eodhd', 'LSE', 'SHEL', 'XLON', 'LSE', 'Shell plc', 'Common Stock', 'GBX', "
    "'GB00BP6MXD84'), "
    "('eodhd', 'KLSE', '1155', 'XKLS', NULL, NULL, 'Preferred Stock', 'MYR', NULL)"
)


@pytest.fixture
def seeded(migrated_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Yield a migrated database holding the valid example rows."""
    for statement in (*_REFERENCE, _SYMBOLS):
        migrated_db.execute(statement)
    yield migrated_db


def _symbol(
    *,
    code: str = "'US'",
    symbol: str = "'AAPL'",
    mic: str = "'XNAS'",
    name: str = "'Apple Inc'",
    currency: str = "'USD'",
    isin: str = "'US0378331005'",
) -> str:
    """Build an insert of one symbol line; every argument is a SQL literal.

    The defaults are a valid line, so a test changes only what it is about.
    """
    return (
        "INSERT INTO provider_symbol (provider_code, provider_exchange_code, provider_symbol, "
        "mic, provider_name, provider_currency, isin) VALUES "
        f"('eodhd', {code}, {symbol}, {mic}, {name}, {currency}, {isin})"
    )


def _columns(connection: sqlite3.Connection) -> list[str]:
    """Return the names of the table's columns, in order."""
    return [str(row[1]) for row in connection.execute("PRAGMA table_info(provider_symbol)")]


def test_the_example_rows_are_accepted(seeded: sqlite3.Connection) -> None:
    """The four example lines of ADR 0018 are valid."""
    assert seeded.execute("SELECT COUNT(*) FROM provider_symbol").fetchone() == (4,)


def test_the_helper_builds_a_valid_row(seeded: sqlite3.Connection) -> None:
    """Otherwise a refusal below could be for another reason than the one tested."""
    seeded.execute(_symbol())


def test_the_table_has_the_seven_columns_of_its_record(migrated_db: sqlite3.Connection) -> None:
    """The venue label and the type are gone (ADR 0025)."""
    assert _columns(migrated_db) == _COLUMNS


# Each case: what is wrong, the statement the database must refuse, and the
# constraint that refuses it.
_REFUSED: list[tuple[str, str, str]] = [
    ("a line on an exchange its code is not mapped to", _symbol(mic="'XKRX'"), _FOREIGN_KEY),
    ("a line under a code the provider does not have", _symbol(code="'ZZ'"), _FOREIGN_KEY),
    ("a line on an exchange that does not exist", _symbol(mic="'XXXX'"), _FOREIGN_KEY),
    ("a second line with one symbol under one code", _symbol(symbol="'BRK-B'"), _UNIQUE),
    (
        "the same symbol on the other exchange of the code",
        _symbol(symbol="'BRK-B'", mic="'XNAS'"),
        _UNIQUE,
    ),
    ("an empty symbol", _symbol(symbol="''"), _CHECK),
    ("a padded symbol", _symbol(symbol="' AAPL'"), _CHECK),
    ("no symbol", _symbol(symbol="NULL"), _NOT_NULL),
    ("no exchange", _symbol(mic="NULL"), _NOT_NULL),
    ("an empty name", _symbol(name="''"), _CHECK),
    ("a padded name", _symbol(name="' Apple Inc'"), _CHECK),
    ("an empty currency", _symbol(currency="''"), _CHECK),
    ("a padded currency", _symbol(currency="'USD '"), _CHECK),
    ("no currency", _symbol(currency="NULL"), _NOT_NULL),
    ("an ISIN that is too short", _symbol(isin="'US037833100'"), _CHECK),
    ("an ISIN in lower case", _symbol(isin="'us0378331005'"), _CHECK),
    ("an ISIN that does not end in a digit", _symbol(isin="'US037833100X'"), _CHECK),
    ("an empty ISIN", _symbol(isin="''"), _CHECK),
]


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [pytest.param(statement, constraint, id=what) for what, statement, constraint in _REFUSED],
)
def test_provider_symbol_refuses_a_row_that_breaks_a_rule(
    seeded: sqlite3.Connection, statement: str, constraint: str
) -> None:
    """The schema is the last line of defence for the rules it still holds."""
    with pytest.raises(sqlite3.IntegrityError, match=constraint):
        seeded.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(_symbol(name="NULL"), id="no name"),
        pytest.param(_symbol(isin="NULL"), id="no ISIN"),
        pytest.param(_symbol(currency="'GBX'"), id="a sub-unit currency"),
        pytest.param(_symbol(currency="'Unknown'"), id="a currency code we do not know"),
        pytest.param(
            _symbol(code="'KO'", symbol="'AAPL'", mic="'XKRX'"),
            id="a symbol that another code also has",
        ),
    ],
)
def test_provider_symbol_accepts_what_a_list_really_carries(
    seeded: sqlite3.Connection, statement: str
) -> None:
    """What the provider leaves out is a valid state, and its codes are stored as given."""
    seeded.execute(statement)


def test_a_mapping_with_symbols_cannot_be_deleted(seeded: sqlite3.Connection) -> None:
    """Nothing is deleted implicitly: the symbols have to go first."""
    with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
        seeded.execute("DELETE FROM provider_exchange WHERE mic = 'XKRX'")


def test_a_mapping_can_be_deleted_once_its_symbols_are_gone(seeded: sqlite3.Connection) -> None:
    """The reference is all that kept it."""
    seeded.execute("DELETE FROM provider_symbol WHERE provider_exchange_code = 'KO'")
    seeded.execute("DELETE FROM provider_exchange WHERE mic = 'XKRX'")

    assert seeded.execute(
        "SELECT COUNT(*) FROM provider_exchange WHERE mic = 'XKRX'"
    ).fetchone() == (0,)


def test_a_corrected_market_code_follows_through(seeded: sqlite3.Connection) -> None:
    """A changed ``mic`` on ``exchange`` reaches the mapping and, through it, the symbols."""
    seeded.execute("UPDATE exchange SET mic = 'XKOR' WHERE mic = 'XKRX'")

    assert seeded.execute(
        "SELECT mic FROM provider_symbol WHERE provider_symbol = '000660'"
    ).fetchone() == ("XKOR",)


def test_a_corrected_provider_code_follows_through(seeded: sqlite3.Connection) -> None:
    """A changed ``provider_code`` reaches the symbols as well."""
    seeded.execute("UPDATE provider SET provider_code = 'eod' WHERE provider_code = 'eodhd'")

    assert seeded.execute("SELECT DISTINCT provider_code FROM provider_symbol").fetchall() == [
        ("eod",)
    ]


def test_a_changed_exchange_code_moves_the_stored_symbols(seeded: sqlite3.Connection) -> None:
    """Why no repository changes a code in place: the stored list would follow it."""
    seeded.execute(
        "UPDATE provider_exchange SET provider_exchange_code = 'KOSPI' WHERE mic = 'XKRX'"
    )

    assert seeded.execute(
        "SELECT provider_exchange_code FROM provider_symbol WHERE provider_symbol = '000660'"
    ).fetchone() == ("KOSPI",)


def test_the_new_key_adds_no_rule_to_provider_exchange(seeded: sqlite3.Connection) -> None:
    """Two exchanges may still share one code; one exchange may still have only one."""
    assert seeded.execute(
        "SELECT COUNT(*) FROM provider_exchange WHERE provider_exchange_code = 'US'"
    ).fetchone() == (2,)
    with pytest.raises(sqlite3.IntegrityError, match=_UNIQUE):
        seeded.execute(
            "INSERT INTO provider_exchange (provider_code, mic, provider_exchange_code) "
            "VALUES ('eodhd', 'XKRX', 'KQ')"
        )


def _plan(connection: sqlite3.Connection, query: str) -> str:
    """Return SQLite's plan for a query as one text."""
    return " | ".join(str(row[3]) for row in connection.execute(f"EXPLAIN QUERY PLAN {query}"))


def test_the_lines_that_carry_an_isin_are_found_through_the_index(
    seeded: sqlite3.Connection,
) -> None:
    """The first lookup of the listing rule (ADR 0019)."""
    plan = _plan(seeded, "SELECT provider_symbol FROM provider_symbol WHERE isin = 'KR7000660001'")

    assert "USING INDEX provider_symbol_isin" in plan


def test_the_lines_on_one_of_our_exchanges_are_found_through_the_index(
    seeded: sqlite3.Connection,
) -> None:
    """How the listing rule collects the lines of a country."""
    plan = _plan(seeded, "SELECT provider_symbol FROM provider_symbol WHERE mic = 'XNYS'")

    assert "provider_symbol_exchange" in plan


def test_the_list_of_one_code_is_found_through_the_primary_key(seeded: sqlite3.Connection) -> None:
    """Reading or replacing one list does not scan the table."""
    plan = _plan(
        seeded,
        "SELECT provider_symbol FROM provider_symbol "
        "WHERE provider_code = 'eodhd' AND provider_exchange_code = 'KO'",
    )

    assert "SEARCH provider_symbol" in plan


def test_migration_0005_leaves_an_existing_database_as_it_was(tmp_path: Path) -> None:
    """The reference rows stay, the new table starts empty, and no reference is broken."""
    path = tmp_path / "pyvalue.db"
    migrate(path, packaged_migrations()[:4])
    connection = connect(path)
    try:
        for statement in _REFERENCE:
            connection.execute(statement)
        before = connection.execute(
            "SELECT provider_code, mic, provider_exchange_code FROM provider_exchange ORDER BY mic"
        ).fetchall()
    finally:
        connection.close()

    report = migrate(path, packaged_migrations()[:5])

    assert [migration.label for migration in report.applied] == ["0005_provider_symbol"]
    connection = connect(path)
    try:
        after = connection.execute(
            "SELECT provider_code, mic, provider_exchange_code FROM provider_exchange ORDER BY mic"
        ).fetchall()
        assert after == before
        assert connection.execute("SELECT COUNT(*) FROM provider_symbol").fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        # The new table is usable at once on the rows that were already there.
        connection.execute(_SYMBOLS_AT_5)
    finally:
        connection.close()


def test_migration_0006_keeps_every_row_and_drops_the_two_columns(tmp_path: Path) -> None:
    """The other seven values of each line stay, and so do the keys and the indexes."""
    path = tmp_path / "pyvalue.db"
    migrate(path, packaged_migrations()[:5])
    connection = connect(path)
    try:
        for statement in (*_REFERENCE, _SYMBOLS_AT_5):
            connection.execute(statement)
        before = connection.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM provider_symbol ORDER BY provider_symbol"
        ).fetchall()
        assert len(before) == 4
    finally:
        connection.close()

    report = migrate(path, packaged_migrations()[:6])

    assert [migration.label for migration in report.applied] == [
        "0006_provider_symbol_drop_venue_and_type"
    ]
    connection = connect(path)
    try:
        assert _columns(connection) == _COLUMNS
        after = connection.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM provider_symbol ORDER BY provider_symbol"
        ).fetchall()
        assert after == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        indexes = {str(row[1]) for row in connection.execute("PRAGMA index_list(provider_symbol)")}
        assert {"provider_symbol_exchange", "provider_symbol_isin"} <= indexes
        # The rules that did not depend on the two columns still hold.
        with pytest.raises(sqlite3.IntegrityError, match=_UNIQUE):
            connection.execute(_symbol(symbol="'BRK-B'"))
        with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
            connection.execute(_symbol(mic="'XKRX'"))
        with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
            connection.execute("DELETE FROM provider_exchange WHERE mic = 'XKRX'")
        connection.execute(_symbol())
    finally:
        connection.close()
