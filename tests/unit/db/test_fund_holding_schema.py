"""Tests for the ``fund`` and ``holding`` tables.

Migration 0002 creates them (ADR 0017) and migration 0003 rebuilds ``holding``
so that it keeps only the lines that were loaded (ADR 0021). The tests pin
which rows the database accepts, which it refuses and by which constraint,
what happens to holding lines when a fund or an instrument changes, which
index the listing rule's lookup uses, and what migration 0003 does to rows
that are already there.

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

# Valid rows. Ids are assigned in insertion order:
#   company    1 SK Hynix, 2 Qfin Holdings
#   instrument 1 SK Hynix, 2 Qfin's ordinary share
#   holding    VXUS 4 a line with every sponsor value,
#              VXUS 5 a receipt read as the ordinary share (another ISIN than the instrument's),
#              VXUS 6 a line in the filer's own category, with its label,
#              VTI 4  a line of the other fund
_SEED: tuple[str, ...] = (
    "INSERT INTO company (name, lei) VALUES "
    "('SK hynix Inc', '988400XAIK6XISWQV045'), ('Qfin Holdings Inc', '836800R59NKEPDR6I240')",
    "INSERT INTO instrument (company_id, isin) VALUES (1, 'KR7000660001'), (2, 'KYG8851G1001')",
    "INSERT INTO fund (fund_code, name, scope, sec_series_id, sec_filing_number, holdings_date, "
    "sponsor_file_date) VALUES "
    "('VXUS', 'Vanguard Total International Stock Index Fund', 'NON_US', 'S000002932', "
    "'0000736054-26-000275', '2026-07-31', '2026-10-31'), "
    "('VTI', 'Vanguard Total Stock Market Index Fund', 'US', 'S000002848', "
    "'0000036405-26-000480', '2026-06-30', NULL)",
    "INSERT INTO holding (fund_code, line_number, instrument_id, isin, issuer_name, title, lei, "
    "cusip, sedol, ticker, asset_category, asset_category_label, issuer_type, trading_country, "
    "currency) VALUES "
    "('VXUS', 4, 1, 'KR7000660001', 'SK hynix Inc', 'SK HYNIX INC', '988400XAIK6XISWQV045', "
    "NULL, '6450267', '000660', 'EC', NULL, 'CORP', 'KR', 'KRW'), "
    "('VXUS', 5, 2, 'US88557W1018', 'Qfin Holdings Inc', NULL, NULL, '88557W101', NULL, NULL, "
    "'EC', NULL, 'CORP', 'US', 'USD'), "
    "('VXUS', 6, 2, 'KYG8851G1001', 'Qfin Holdings Inc', NULL, NULL, NULL, NULL, NULL, "
    "'OTHER', 'UNITS', 'RF', 'HK', 'HKD'), "
    "('VTI', 4, 1, 'KR7000660001', 'SK hynix Inc', NULL, NULL, NULL, NULL, 'BRK.B', "
    "'EP', NULL, 'CORP', 'US', 'USD')",
)


@pytest.fixture
def seeded(migrated_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Yield a migrated database holding the valid example rows."""
    for statement in _SEED:
        migrated_db.execute(statement)
    yield migrated_db


def _fund(
    code: str = "'NEW'",
    name: str = "'A fund'",
    scope: str = "'US'",
    series: str = "'S000000001'",
    filing: str = "'0000000001-26-000001'",
    holdings_date: str = "'2026-07-31'",
    sponsor_file_date: str = "NULL",
) -> str:
    """Return an insert of one fund, valid unless an argument makes it otherwise.

    Every argument is a SQL literal, so a test can also pass ``NULL``.
    """
    return (
        "INSERT INTO fund (fund_code, name, scope, sec_series_id, sec_filing_number, "
        f"holdings_date, sponsor_file_date) VALUES ({code}, {name}, {scope}, {series}, {filing}, "
        f"{holdings_date}, {sponsor_file_date})"
    )


def _holding(
    fund: str = "'VXUS'",
    line: str = "9",
    instrument: str = "1",
    isin: str = "'KR7000660001'",
    name: str = "'SK hynix Inc'",
    title: str = "NULL",
    lei: str = "NULL",
    cusip: str = "NULL",
    sedol: str = "NULL",
    ticker: str = "NULL",
    category: str = "'EC'",
    label: str = "NULL",
    issuer_type: str = "'CORP'",
    country: str = "'KR'",
    currency: str = "'KRW'",
) -> str:
    """Return an insert of one holding line, valid unless an argument makes it otherwise."""
    return (
        "INSERT INTO holding (fund_code, line_number, instrument_id, isin, issuer_name, title, "
        "lei, cusip, sedol, ticker, asset_category, asset_category_label, issuer_type, "
        f"trading_country, currency) VALUES ({fund}, {line}, {instrument}, {isin}, {name}, "
        f"{title}, {lei}, {cusip}, {sedol}, {ticker}, {category}, {label}, {issuer_type}, "
        f"{country}, {currency})"
    )


def test_the_example_rows_are_accepted(seeded: sqlite3.Connection) -> None:
    """Every kind of row ADR 0017 describes fits the schema."""
    assert seeded.execute("SELECT COUNT(*) FROM fund").fetchone() == (2,)
    assert seeded.execute("SELECT COUNT(*) FROM holding").fetchone() == (4,)


def test_the_helpers_build_valid_rows(seeded: sqlite3.Connection) -> None:
    """Guard: a refusal below is caused by the one value its test changes."""
    seeded.execute(_fund())
    seeded.execute(_holding())


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        pytest.param(_fund(code="''"), _CHECK, id="empty code"),
        pytest.param(_fund(code="'vti2'"), _CHECK, id="lower-case code"),
        pytest.param(_fund(code="'V TI'"), _CHECK, id="space in the code"),
        pytest.param(_fund(code="NULL"), _NOT_NULL, id="no code"),
        pytest.param(_fund(code="'VTI'"), _UNIQUE, id="a code that is taken"),
        pytest.param(_fund(name="''"), _CHECK, id="empty name"),
        pytest.param(_fund(name="' A fund'"), _CHECK, id="padded name"),
        pytest.param(_fund(scope="'WORLD'"), _CHECK, id="unknown scope"),
        pytest.param(_fund(scope="'us'"), _CHECK, id="lower-case scope"),
        pytest.param(_fund(series="'2848'"), _CHECK, id="series id too short"),
        pytest.param(_fund(series="'X000000001'"), _CHECK, id="series id without its S"),
        pytest.param(_fund(series="'S00000000A'"), _CHECK, id="letter in the series id"),
        pytest.param(_fund(series="'S000002848'"), _UNIQUE, id="a second fund for one series"),
        pytest.param(_fund(filing="'000000000126000001'"), _CHECK, id="filing without hyphens"),
        pytest.param(_fund(filing="'0000000001-26-00001'"), _CHECK, id="filing number too short"),
        pytest.param(
            _fund(filing="'0000036405-26-000480'"), _UNIQUE, id="one filing loaded as two funds"
        ),
        pytest.param(_fund(holdings_date="'31/07/2026'"), _CHECK, id="date in another order"),
        pytest.param(_fund(holdings_date="'2026-02-30'"), _CHECK, id="a day that does not exist"),
        pytest.param(_fund(holdings_date="'2026-07-31 00:00:00'"), _CHECK, id="date with a time"),
        pytest.param(_fund(holdings_date="NULL"), _NOT_NULL, id="no holdings date"),
        pytest.param(_fund(sponsor_file_date="'Oct 31'"), _CHECK, id="sponsor date as words"),
    ],
)
def test_fund_refuses_a_row_that_breaks_a_rule(
    seeded: sqlite3.Connection, statement: str, constraint: str
) -> None:
    """Each rule of the ``fund`` table is enforced by the database itself."""
    with pytest.raises(sqlite3.IntegrityError, match=constraint):
        seeded.execute(statement)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        pytest.param(_holding(fund="'NOPE'"), _FOREIGN_KEY, id="a fund that does not exist"),
        pytest.param(_holding(line="4"), _UNIQUE, id="the same line twice"),
        pytest.param(_holding(line="0"), _CHECK, id="line zero"),
        pytest.param(_holding(instrument="99"), _FOREIGN_KEY, id="an instrument that is not there"),
        pytest.param(_holding(instrument="NULL"), _NOT_NULL, id="a line that was not loaded"),
        pytest.param(_holding(isin="NULL"), _NOT_NULL, id="no ISIN"),
        pytest.param(_holding(isin="'N/A'"), _CHECK, id="a placeholder for the ISIN"),
        pytest.param(_holding(name="''"), _CHECK, id="empty issuer name"),
        pytest.param(_holding(title="''"), _CHECK, id="empty title"),
        pytest.param(_holding(lei="'N/A'"), _CHECK, id="a placeholder for the identifier"),
        pytest.param(_holding(cusip="'N/A'"), _CHECK, id="a placeholder for the CUSIP"),
        pytest.param(_holding(cusip="'03783310'"), _CHECK, id="CUSIP one character short"),
        pytest.param(_holding(sedol="'64502'"), _CHECK, id="SEDOL too short"),
        pytest.param(_holding(sedol="'645026-'"), _CHECK, id="punctuation in the SEDOL"),
        pytest.param(_holding(ticker="''"), _CHECK, id="empty ticker"),
        pytest.param(_holding(ticker="' 000660'"), _CHECK, id="padded ticker"),
        pytest.param(_holding(category="'DBT'"), _CHECK, id="a debt line"),
        pytest.param(_holding(category="'DE'"), _CHECK, id="a derivative line"),
        pytest.param(_holding(label="'ADR'"), _CHECK, id="a label without the OTHER category"),
        pytest.param(_holding(category="'OTHER'", label="''"), _CHECK, id="an empty label"),
        pytest.param(_holding(issuer_type="'corp'"), _CHECK, id="lower-case issuer type"),
        pytest.param(_holding(issuer_type="''"), _CHECK, id="empty issuer type"),
        pytest.param(_holding(issuer_type="NULL"), _NOT_NULL, id="no issuer type"),
        pytest.param(_holding(country="'Korea'"), _CHECK, id="country as a word"),
        pytest.param(_holding(country="NULL"), _NOT_NULL, id="no country"),
        pytest.param(_holding(currency="'won'"), _CHECK, id="currency as a word"),
        pytest.param(_holding(currency="NULL"), _NOT_NULL, id="no currency"),
    ],
)
def test_holding_refuses_a_row_that_breaks_a_rule(
    seeded: sqlite3.Connection, statement: str, constraint: str
) -> None:
    """Each rule of the ``holding`` table is enforced by the database itself."""
    with pytest.raises(sqlite3.IntegrityError, match=constraint):
        seeded.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(_holding(ticker="'NOVO B'"), id="a ticker with a space inside"),
        pytest.param(_holding(ticker="'GCC*'"), id="a ticker with an asterisk"),
        pytest.param(_holding(cusip="'38259P508'"), id="a CUSIP with letters"),
        pytest.param(_holding(cusip="'1234567*@'"), id="a CUSIP with its special characters"),
        pytest.param(_holding(sedol="'BP6MXD8'"), id="a SEDOL with letters"),
        pytest.param(_holding(category="'OTHER'"), id="the OTHER category without a label"),
        pytest.param(_holding(category="'STIV'"), id="a short-term investment vehicle"),
        pytest.param(_holding(issuer_type="'OTHER'"), id="the form's OTHER issuer type"),
    ],
)
def test_holding_accepts_what_the_documents_really_carry(
    seeded: sqlite3.Connection, statement: str
) -> None:
    """The shapes are no narrower than the filings and the sponsor's file need."""
    seeded.execute(statement)


def test_a_fund_with_holding_lines_cannot_be_deleted(seeded: sqlite3.Connection) -> None:
    """Nothing is deleted implicitly: the lines would lose their fund."""
    with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
        seeded.execute("DELETE FROM fund WHERE fund_code = 'VXUS'")


def test_an_instrument_a_line_points_at_cannot_be_deleted(seeded: sqlite3.Connection) -> None:
    """The line would point at nothing."""
    seeded.execute("DELETE FROM holding WHERE instrument_id = 2")
    with pytest.raises(sqlite3.IntegrityError, match=_FOREIGN_KEY):
        seeded.execute("DELETE FROM instrument WHERE instrument_id = 1")
    # With no line left pointing at it, the instrument can go.
    seeded.execute("DELETE FROM instrument WHERE instrument_id = 2")


def test_a_corrected_fund_code_follows_through(seeded: sqlite3.Connection) -> None:
    """The lines of a renamed fund stay its lines."""
    seeded.execute("UPDATE fund SET fund_code = 'VXUS2' WHERE fund_code = 'VXUS'")

    rows = seeded.execute(
        "SELECT fund_code, COUNT(*) FROM holding GROUP BY fund_code ORDER BY fund_code"
    ).fetchall()
    assert rows == [("VTI", 1), ("VXUS2", 3)]


def test_a_fund_can_be_deleted_once_its_lines_are_gone(seeded: sqlite3.Connection) -> None:
    """Replacing a fund's lines never needs its row to go, but it may."""
    seeded.execute("DELETE FROM holding WHERE fund_code = 'VTI'")
    seeded.execute("DELETE FROM fund WHERE fund_code = 'VTI'")

    assert seeded.execute("SELECT fund_code FROM fund").fetchall() == [("VXUS",)]


def test_the_lines_of_a_security_are_found_through_the_index(seeded: sqlite3.Connection) -> None:
    """The lookup the listing rule makes for every instrument does not scan the table."""
    plan = seeded.execute(
        "EXPLAIN QUERY PLAN SELECT fund_code, line_number FROM holding WHERE instrument_id = 1"
    ).fetchall()

    assert [row[3] for row in plan] == [
        "SEARCH holding USING INDEX holding_instrument_id (instrument_id=?)"
    ]


def test_the_lines_of_a_fund_are_found_through_the_primary_key(seeded: sqlite3.Connection) -> None:
    """Reading or replacing one fund's lines uses the key, whose first column is the fund."""
    plan = seeded.execute(
        "EXPLAIN QUERY PLAN SELECT line_number FROM holding WHERE fund_code = 'VXUS'"
    ).fetchall()

    assert len(plan) == 1
    assert plan[0][3].startswith("SEARCH holding USING")
    assert "(fund_code=?)" in plan[0][3]


# --- Migration 0003: only the lines that were loaded (ADR 0021) ---------------------------------

_HOLDING_COLUMNS: list[str] = [
    "fund_code",
    "line_number",
    "instrument_id",
    "isin",
    "issuer_name",
    "title",
    "lei",
    "cusip",
    "sedol",
    "ticker",
    "asset_category",
    "asset_category_label",
    "issuer_type",
    "trading_country",
    "currency",
]


def test_holding_has_no_column_for_a_line_that_was_not_loaded(
    migrated_db: sqlite3.Connection,
) -> None:
    """Every row is a line of a security: no reason column, and the instrument is required."""
    columns = migrated_db.execute("PRAGMA table_info(holding)").fetchall()

    assert [column[1] for column in columns] == _HOLDING_COLUMNS
    assert {column[1]: column[3] for column in columns}["instrument_id"] == 1


def test_migration_0003_keeps_loaded_lines_and_drops_the_others(tmp_path: Path) -> None:
    """A database loaded under ADR 0017 keeps every line that points at an instrument, as it is."""
    path = tmp_path / "pyvalue.db"
    migrate(path, packaged_migrations()[:2])
    connection = connect(path)
    try:
        for statement in _SEED[:3]:
            connection.execute(statement)
        # Rows as migration 0002 stored them: two loaded, one of each kind that was not.
        connection.execute(
            "INSERT INTO holding (fund_code, line_number, instrument_id, not_loaded_reason, isin, "
            "issuer_name, title, lei, cusip, sedol, ticker, asset_category, asset_category_label, "
            "issuer_type, trading_country, currency) VALUES "
            "('VXUS', 4, 1, NULL, 'KR7000660001', 'SK hynix Inc', 'SK HYNIX INC', "
            "'988400XAIK6XISWQV045', NULL, '6450267', '000660', 'EC', NULL, 'CORP', 'KR', 'KRW'), "
            "('VXUS', 5, 2, NULL, 'US88557W1018', 'Qfin Holdings Inc', NULL, NULL, NULL, NULL, "
            "NULL, 'OTHER', 'ADR', 'CORP', 'US', 'USD'), "
            "('VXUS', 6, NULL, 'excluded_by_decision', 'US9220428588', "
            "'Vanguard FTSE Emerging Markets ETF', NULL, NULL, '922042858', NULL, NULL, 'EC', "
            "NULL, 'RF', 'US', 'USD'), "
            "('VXUS', 7, NULL, 'receipt_company_already_loaded', 'US7223041028', "
            "'PDD Holdings Inc', NULL, NULL, NULL, NULL, 'PDD', 'EC', NULL, 'CORP', 'US', 'USD')"
        )
    finally:
        connection.close()

    report = migrate(path)

    assert [migration.label for migration in report.applied] == ["0003_holding_loaded_lines_only"]
    connection = connect(path)
    try:
        rows = connection.execute(
            f"SELECT {', '.join(_HOLDING_COLUMNS)} FROM holding ORDER BY fund_code, line_number"
        ).fetchall()
        objects = connection.execute(
            "SELECT type, name FROM sqlite_schema WHERE name LIKE 'holding%' ORDER BY type, name"
        ).fetchall()
        broken = connection.execute("PRAGMA foreign_key_check").fetchall()
        funds = connection.execute("SELECT COUNT(*) FROM fund").fetchone()
    finally:
        connection.close()
    assert rows == [
        (
            "VXUS",
            4,
            1,
            "KR7000660001",
            "SK hynix Inc",
            "SK HYNIX INC",
            "988400XAIK6XISWQV045",
            None,
            "6450267",
            "000660",
            "EC",
            None,
            "CORP",
            "KR",
            "KRW",
        ),
        (
            "VXUS",
            5,
            2,
            "US88557W1018",
            "Qfin Holdings Inc",
            None,
            None,
            None,
            None,
            None,
            "OTHER",
            "ADR",
            "CORP",
            "US",
            "USD",
        ),
    ]
    # The rebuilt table has its index again, and nothing else was touched.
    assert objects == [("index", "holding_instrument_id"), ("table", "holding")]
    assert broken == []
    assert funds == (2,)
