"""Tests for the reference schema created by migration 0001.

They pin what ADR 0001 (exchange, company), ADR 0003 (instrument, listing) and
ADR 0002 (provider tables and view) promise: which rows the database accepts,
which it refuses and by which constraint, and which index each lookup uses.

Author: Emre Tezel
"""

import sqlite3
from collections.abc import Iterator

import pytest

# Valid rows, the examples the ADRs use. Ids are assigned in insertion order:
#   company    1 Berkshire, 2 Alphabet, 3 SAP, 4 Toyota, 5 and 6 without an LEI
#   instrument 1 Berkshire B, 2 Alphabet A, 3 Alphabet C, 4 SAP, 5 Toyota, 6 unlisted
#   listing    1 BRK.B, 2 GOOGL, 3 GOOG, 4 SAP    (Toyota and instrument 6 have none)
_SEED: tuple[str, ...] = (
    "INSERT INTO exchange (mic, name, country) VALUES "
    "('XNYS', 'New York Stock Exchange', 'US'), ('XNAS', 'Nasdaq', 'US'), "
    "('XETR', 'Xetra', 'DE'), ('XJPX', 'Japan Exchange Group', 'JP')",
    "INSERT INTO company (name, lei) VALUES "
    "('Berkshire Hathaway Inc', '5493000C01ZX7D35SD85'), ('Alphabet Inc', '5493006MHB84DD0ZWV18'), "
    "('SAP SE', '529900D6BF99LW9R2E68'), ('Toyota Motor Corp', '5493006W3QUS5LMH6R84'), "
    "('No LEI Co', NULL), ('Other No LEI Co', NULL)",
    "INSERT INTO instrument (company_id, isin) VALUES "
    "(1, 'US0846707026'), (2, 'US02079K3059'), (2, 'US02079K1079'), "
    "(3, 'DE0007164600'), (4, 'JP3633400001'), (5, 'KR7000660001')",
    "INSERT INTO listing (instrument_id, mic, ticker, currency) VALUES "
    "(1, 'XNYS', 'BRK.B', 'USD'), (2, 'XNAS', 'GOOGL', 'USD'), "
    "(3, 'XNAS', 'GOOG', 'USD'), (4, 'XETR', 'SAP', 'EUR')",
    "INSERT INTO provider (provider_code, name) VALUES ('eodhd', 'EODHD')",
    "INSERT INTO provider_exchange (provider_code, mic, provider_exchange_code) VALUES "
    "('eodhd', 'XNYS', 'US'), ('eodhd', 'XNAS', 'US'), ('eodhd', 'XETR', 'XETRA')",
    "INSERT INTO provider_listing (provider_code, listing_id, provider_symbol) VALUES "
    "('eodhd', 1, 'BRK-B'), ('eodhd', 2, 'GOOGL'), ('eodhd', 4, 'SAP')",
)

_CHECK = "CHECK constraint failed"
_FOREIGN_KEY = "FOREIGN KEY constraint failed"


@pytest.fixture
def seeded(migrated_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Yield a migrated database holding the valid example rows."""
    for statement in _SEED:
        migrated_db.execute(statement)
    yield migrated_db


def test_schema_has_exactly_the_agreed_tables_and_view(migrated_db: sqlite3.Connection) -> None:
    """Migration 0001 creates what the ADRs define and nothing else."""
    rows = migrated_db.execute(
        "SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()

    assert rows == [
        ("index", "instrument_company_id"),
        ("table", "company"),
        ("table", "exchange"),
        ("table", "instrument"),
        ("table", "listing"),
        ("table", "provider"),
        ("table", "provider_exchange"),
        ("table", "provider_listing"),
        ("table", "schema_migration"),
        ("view", "provider_listing_address"),
    ]


def _exchange(values: str) -> str:
    return f"INSERT INTO exchange (mic, name, country) VALUES ({values})"


def _company(values: str) -> str:
    return f"INSERT INTO company (name, lei) VALUES ({values})"


def _instrument(values: str) -> str:
    return f"INSERT INTO instrument (company_id, isin) VALUES ({values})"


def _listing(values: str) -> str:
    return f"INSERT INTO listing (instrument_id, mic, ticker, currency) VALUES ({values})"


def _provider(values: str) -> str:
    return f"INSERT INTO provider (provider_code, name) VALUES ({values})"


def _provider_exchange(values: str) -> str:
    columns = "provider_code, mic, provider_exchange_code"
    return f"INSERT INTO provider_exchange ({columns}) VALUES ({values})"


def _provider_listing(values: str) -> str:
    columns = "provider_code, listing_id, provider_symbol"
    return f"INSERT INTO provider_listing ({columns}) VALUES ({values})"


def _unique(columns: str) -> str:
    return f"UNIQUE constraint failed: {columns}"


def _not_null(column: str) -> str:
    return f"NOT NULL constraint failed: {column}"


# Each case: what is wrong, the statement the database must refuse, and the
# constraint that refuses it. Statements before a semicolon are setup.
_REFUSED: list[tuple[str, str, str]] = [
    # exchange
    ("exchange: lower-case market code", _exchange("'xlon', 'London', 'GB'"), _CHECK),
    ("exchange: three-character market code", _exchange("'XLO', 'London', 'GB'"), _CHECK),
    ("exchange: five-character market code", _exchange("'XLONX', 'London', 'GB'"), _CHECK),
    ("exchange: three-letter country", _exchange("'XLON', 'London', 'GBR'"), _CHECK),
    ("exchange: lower-case country", _exchange("'XLON', 'London', 'gb'"), _CHECK),
    ("exchange: empty name", _exchange("'XLON', '', 'GB'"), _CHECK),
    ("exchange: padded name", _exchange("'XLON', ' London ', 'GB'"), _CHECK),
    (
        "exchange: no market code",
        "INSERT INTO exchange (name, country) VALUES ('London', 'GB')",
        _not_null("exchange.mic"),
    ),
    (
        "exchange: no country",
        "INSERT INTO exchange (mic, name) VALUES ('XLON', 'London')",
        _not_null("exchange.country"),
    ),
    ("exchange: repeated market code", _exchange("'XNYS', 'Again', 'US'"), _unique("exchange.mic")),
    # company
    (
        "company: repeated legal-entity identifier",
        _company("'Copy', '5493000C01ZX7D35SD85'"),
        _unique("company.lei"),
    ),
    ("company: identifier of 19 characters", _company("'Short', '5493000C01ZX7D35SD8'"), _CHECK),
    ("company: identifier of 21 characters", _company("'Long', '5493000C01ZX7D35SD855'"), _CHECK),
    ("company: lower-case identifier", _company("'Lower', '5493000c01zx7d35sd85'"), _CHECK),
    (
        "company: identifier not ending in two digits",
        _company("'Letters', '5493000C01ZX7D35SDAB'"),
        _CHECK,
    ),
    ("company: empty identifier in place of none", _company("'Empty', ''"), _CHECK),
    ("company: empty name", _company("'', NULL"), _CHECK),
    ("company: padded name", _company("'  Padded ', NULL"), _CHECK),
    (
        "company: no name",
        "INSERT INTO company (lei) VALUES ('529900T8BM49AURSDO55')",
        _not_null("company.name"),
    ),
    # instrument
    (
        "instrument: repeated ISIN, same company",
        _instrument("1, 'US0846707026'"),
        _unique("instrument.isin"),
    ),
    (
        "instrument: repeated ISIN, another company",
        _instrument("5, 'US0846707026'"),
        _unique("instrument.isin"),
    ),
    ("instrument: ISIN of 11 characters", _instrument("1, 'US084670108'"), _CHECK),
    ("instrument: ISIN of 13 characters", _instrument("1, 'US08467010860'"), _CHECK),
    ("instrument: ISIN starting with a digit", _instrument("1, '0S0846701086'"), _CHECK),
    ("instrument: ISIN ending in a letter", _instrument("1, 'US084670108X'"), _CHECK),
    ("instrument: lower-case ISIN", _instrument("1, 'us0846701086'"), _CHECK),
    ("instrument: ISIN with a space", _instrument("1, 'US08467 01086'"), _CHECK),
    ("instrument: unknown company", _instrument("99, 'US0846701086'"), _FOREIGN_KEY),
    (
        "instrument: no ISIN",
        "INSERT INTO instrument (company_id) VALUES (1)",
        _not_null("instrument.isin"),
    ),
    (
        "instrument: no company",
        "INSERT INTO instrument (isin) VALUES ('US0846701086')",
        _not_null("instrument.company_id"),
    ),
    (
        "instrument: moved to an unknown company",
        "UPDATE instrument SET company_id = 99 WHERE instrument_id = 1",
        _FOREIGN_KEY,
    ),
    (
        "instrument: ISIN changed to one in use",
        "UPDATE instrument SET isin = 'US02079K3059' WHERE instrument_id = 1",
        _unique("instrument.isin"),
    ),
    # listing
    (
        "listing: second listing for one instrument",
        _listing("1, 'XNAS', 'BRKB', 'USD'"),
        _unique("listing.instrument_id"),
    ),
    (
        "listing: repeated exchange and ticker",
        _listing("5, 'XNYS', 'BRK.B', 'USD'"),
        _unique("listing.mic, listing.ticker"),
    ),
    ("listing: unknown instrument", _listing("99, 'XJPX', '7203', 'JPY'"), _FOREIGN_KEY),
    (
        "listing: no instrument",
        "INSERT INTO listing (mic, ticker, currency) VALUES ('XJPX', '7203', 'JPY')",
        _not_null("listing.instrument_id"),
    ),
    ("listing: unknown exchange", _listing("5, 'XLON', '7203', 'JPY'"), _FOREIGN_KEY),
    ("listing: lower-case ticker", _listing("5, 'XJPX', 'toyota', 'JPY'"), _CHECK),
    ("listing: padded ticker", _listing("5, 'XJPX', ' 7203', 'JPY'"), _CHECK),
    ("listing: empty ticker", _listing("5, 'XJPX', '', 'JPY'"), _CHECK),
    ("listing: four-letter currency", _listing("5, 'XJPX', '7203', 'YENS'"), _CHECK),
    ("listing: lower-case currency", _listing("5, 'XJPX', '7203', 'jpy'"), _CHECK),
    (
        "listing: no currency",
        "INSERT INTO listing (instrument_id, mic, ticker) VALUES (5, 'XJPX', '7203')",
        _not_null("listing.currency"),
    ),
    # provider
    ("provider: upper-case code", _provider("'SEC', 'SEC'"), _CHECK),
    ("provider: code starting with a digit", _provider("'1sec', 'SEC'"), _CHECK),
    ("provider: code with a hyphen", _provider("'sec-edgar', 'SEC'"), _CHECK),
    ("provider: empty code", _provider("'', 'SEC'"), _CHECK),
    ("provider: empty name", _provider("'sec', ''"), _CHECK),
    ("provider: repeated code", _provider("'eodhd', 'Again'"), _unique("provider.provider_code")),
    # provider_exchange
    (
        "provider_exchange: second code for one exchange",
        _provider_exchange("'eodhd', 'XNYS', 'NYSE'"),
        _unique("provider_exchange.mic, provider_exchange.provider_code"),
    ),
    (
        "provider_exchange: unknown provider",
        _provider_exchange("'nobody', 'XJPX', 'TSE'"),
        _FOREIGN_KEY,
    ),
    (
        "provider_exchange: unknown exchange",
        _provider_exchange("'eodhd', 'XLON', 'LSE'"),
        _FOREIGN_KEY,
    ),
    ("provider_exchange: empty code", _provider_exchange("'eodhd', 'XJPX', ''"), _CHECK),
    ("provider_exchange: padded code", _provider_exchange("'eodhd', 'XJPX', ' TSE'"), _CHECK),
    # provider_listing
    (
        "provider_listing: second symbol for one listing",
        _provider_listing("'eodhd', 1, 'BRK.B'"),
        _unique("provider_listing.listing_id, provider_listing.provider_code"),
    ),
    ("provider_listing: unknown listing", _provider_listing("'eodhd', 77, 'ZZZ'"), _FOREIGN_KEY),
    ("provider_listing: unknown provider", _provider_listing("'nobody', 3, 'GOOG'"), _FOREIGN_KEY),
    ("provider_listing: empty symbol", _provider_listing("'eodhd', 3, ''"), _CHECK),
    ("provider_listing: padded symbol", _provider_listing("'eodhd', 3, 'GOOG '"), _CHECK),
    # nothing is deleted implicitly
    (
        "delete: company that still has instruments",
        "DELETE FROM company WHERE company_id = 1",
        _FOREIGN_KEY,
    ),
    (
        "delete: instrument that still has a listing",
        "DELETE FROM instrument WHERE instrument_id = 1",
        _FOREIGN_KEY,
    ),
    (
        "delete: listing that still has a provider symbol",
        "DELETE FROM listing WHERE listing_id = 1",
        _FOREIGN_KEY,
    ),
    (
        "delete: exchange that still has listings",
        "DELETE FROM exchange WHERE mic = 'XNAS'",
        _FOREIGN_KEY,
    ),
    (
        "delete: exchange that still has a provider code",
        _exchange("'XLON', 'London', 'GB'")
        + "; "
        + _provider_exchange("'eodhd', 'XLON', 'LSE'")
        + "; DELETE FROM exchange WHERE mic = 'XLON'",
        _FOREIGN_KEY,
    ),
    (
        "delete: provider that still has mappings",
        "DELETE FROM provider WHERE provider_code = 'eodhd'",
        _FOREIGN_KEY,
    ),
]


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [pytest.param(statement, constraint, id=case) for case, statement, constraint in _REFUSED],
)
def test_invalid_row_is_refused(
    seeded: sqlite3.Connection, statement: str, constraint: str
) -> None:
    """The database refuses the row, and by the constraint the ADR names."""
    *setup, last = [part.strip() for part in statement.split(";")]
    for part in setup:
        seeded.execute(part)

    with pytest.raises(sqlite3.IntegrityError, match=constraint):
        seeded.execute(last)


def test_instrument_can_exist_without_a_listing(seeded: sqlite3.Connection) -> None:
    """The point of ADR 0003: a security is stored before its listing is known."""
    rows = seeded.execute(
        "SELECT i.isin FROM instrument AS i "
        "WHERE NOT EXISTS (SELECT 1 FROM listing AS l WHERE l.instrument_id = i.instrument_id) "
        "ORDER BY i.instrument_id"
    ).fetchall()

    assert rows == [("JP3633400001",), ("KR7000660001",)]


def test_listing_can_be_filled_in_later(seeded: sqlite3.Connection) -> None:
    """A listing is added to an existing instrument without touching it."""
    seeded.execute(_listing("5, 'XJPX', '7203', 'JPY'"))

    row = seeded.execute(
        "SELECT c.name, i.isin, l.mic, l.ticker, l.currency FROM listing AS l "
        "JOIN instrument AS i ON i.instrument_id = l.instrument_id "
        "JOIN company AS c ON c.company_id = i.company_id WHERE l.ticker = '7203'"
    ).fetchone()
    assert row == ("Toyota Motor Corp", "JP3633400001", "XJPX", "7203", "JPY")


def test_company_can_have_several_instruments(seeded: sqlite3.Connection) -> None:
    """Alphabet's two share classes are two instruments of one company."""
    rows = seeded.execute(
        "SELECT isin FROM instrument WHERE company_id = 2 ORDER BY instrument_id"
    ).fetchall()

    assert rows == [("US02079K3059",), ("US02079K1079",)]


def test_several_companies_may_lack_a_legal_entity_identifier(seeded: sqlite3.Connection) -> None:
    """UNIQUE on the identifier does not stop more than one company having none."""
    (count,) = seeded.execute("SELECT count(*) FROM company WHERE lei IS NULL").fetchone()

    assert count == 2


def test_isin_can_change_in_place(seeded: sqlite3.Connection) -> None:
    """A new ISIN after a corporate action keeps the instrument's id and its listing."""
    seeded.execute("UPDATE instrument SET isin = 'US0846701086' WHERE instrument_id = 1")

    row = seeded.execute(
        "SELECT i.instrument_id, l.ticker FROM instrument AS i "
        "JOIN listing AS l ON l.instrument_id = i.instrument_id WHERE i.isin = 'US0846701086'"
    ).fetchone()
    assert row == (1, "BRK.B")


def test_instrument_without_listing_can_be_deleted(seeded: sqlite3.Connection) -> None:
    """RESTRICT guards rows that are referenced, not every row."""
    seeded.execute("DELETE FROM instrument WHERE instrument_id = 6")

    (count,) = seeded.execute("SELECT count(*) FROM instrument").fetchone()
    assert count == 5


def test_corrected_market_code_follows_through(seeded: sqlite3.Connection) -> None:
    """ON UPDATE CASCADE: fixing an exchange's code updates what points at it."""
    seeded.execute("UPDATE exchange SET mic = 'XFRA' WHERE mic = 'XETR'")

    assert seeded.execute("SELECT mic FROM listing WHERE listing_id = 4").fetchone() == ("XFRA",)
    assert seeded.execute(
        "SELECT mic FROM provider_exchange WHERE provider_exchange_code = 'XETRA'"
    ).fetchone() == ("XFRA",)


def test_corrected_provider_code_follows_through(seeded: sqlite3.Connection) -> None:
    """ON UPDATE CASCADE on both mapping tables."""
    seeded.execute("UPDATE provider SET provider_code = 'eod' WHERE provider_code = 'eodhd'")

    assert seeded.execute("SELECT DISTINCT provider_code FROM provider_exchange").fetchall() == [
        ("eod",)
    ]
    assert seeded.execute("SELECT DISTINCT provider_code FROM provider_listing").fetchall() == [
        ("eod",)
    ]


def test_ids_are_never_reused(seeded: sqlite3.Connection) -> None:
    """An id in an old output file can never come to mean a different company."""
    seeded.execute("DELETE FROM company WHERE company_id = 6")
    cursor = seeded.execute("INSERT INTO company (name) VALUES ('Newcomer')")

    assert cursor.lastrowid == 7


def test_view_gives_the_two_parts_of_a_provider_request(seeded: sqlite3.Connection) -> None:
    """One row per mapped listing: the provider's symbol and its exchange code."""
    rows = seeded.execute(
        "SELECT provider_code, listing_id, provider_symbol, provider_exchange_code "
        "FROM provider_listing_address ORDER BY listing_id"
    ).fetchall()

    assert rows == [
        ("eodhd", 1, "BRK-B", "US"),
        ("eodhd", 2, "GOOGL", "US"),
        ("eodhd", 4, "SAP", "XETRA"),
    ]


def test_view_has_no_row_for_an_exchange_the_provider_does_not_serve(
    seeded: sqlite3.Connection,
) -> None:
    """No stand-in lines: a Tokyo listing cannot be addressed through another exchange.

    A symbol is stored for Toyota, but EODHD has no code for the Tokyo exchange,
    so the view offers nothing to build a request from.
    """
    cursor = seeded.execute(_listing("5, 'XJPX', '7203', 'JPY'"))
    seeded.execute(
        "INSERT INTO provider_listing (provider_code, listing_id, provider_symbol) "
        "VALUES ('eodhd', ?, '7203')",
        (cursor.lastrowid,),
    )

    rows = seeded.execute(
        "SELECT provider_symbol FROM provider_listing_address WHERE listing_id = ?",
        (cursor.lastrowid,),
    ).fetchall()
    assert rows == []


# Each case: a lookup an ADR names as the reason for an index, and the index it must use.
_LOOKUPS: list[tuple[str, str, tuple[str | int, ...], str]] = [
    (
        "instrument by ISIN",
        "SELECT instrument_id, company_id FROM instrument WHERE isin = ?",
        ("US0846707026",),
        "sqlite_autoindex_instrument_1",
    ),
    (
        "instruments of a company",
        "SELECT instrument_id, isin FROM instrument WHERE company_id = ?",
        (2,),
        "instrument_company_id",
    ),
    (
        "listing of an instrument",
        "SELECT listing_id, mic, ticker FROM listing WHERE instrument_id = ?",
        (2,),
        "sqlite_autoindex_listing_1",
    ),
    (
        "listing by exchange and ticker",
        "SELECT listing_id FROM listing WHERE mic = ? AND ticker = ?",
        ("XNYS", "BRK.B"),
        "sqlite_autoindex_listing_2",
    ),
    (
        "listings on an exchange",
        "SELECT listing_id FROM listing WHERE mic = ?",
        ("XNAS",),
        "sqlite_autoindex_listing_2",
    ),
    (
        "company by legal-entity identifier",
        "SELECT company_id FROM company WHERE lei = ?",
        ("5493000C01ZX7D35SD85",),
        "sqlite_autoindex_company_1",
    ),
    (
        "provider code of an exchange",
        "SELECT provider_exchange_code FROM provider_exchange WHERE mic = ? AND provider_code = ?",
        ("XNYS", "eodhd"),
        "sqlite_autoindex_provider_exchange_1",
    ),
    (
        "provider symbol of a listing",
        "SELECT provider_symbol FROM provider_listing WHERE listing_id = ? AND provider_code = ?",
        (1, "eodhd"),
        "sqlite_autoindex_provider_listing_1",
    ),
]


@pytest.mark.parametrize(
    ("query", "parameters", "index"),
    [
        pytest.param(query, parameters, index, id=case)
        for case, query, parameters, index in _LOOKUPS
    ],
)
def test_lookup_uses_its_index(
    seeded: sqlite3.Connection, query: str, parameters: tuple[str | int, ...], index: str
) -> None:
    """Every index in the ADRs is justified by a query; this checks the query uses it."""
    plan = [str(row[3]) for row in seeded.execute(f"EXPLAIN QUERY PLAN {query}", parameters)]

    assert len(plan) == 1
    assert plan[0].startswith("SEARCH"), plan
    assert index in plan[0], plan


def test_view_lookup_scans_no_table(seeded: sqlite3.Connection) -> None:
    """Building one provider request touches three rows, each found by a key."""
    plan = [
        str(row[3])
        for row in seeded.execute(
            "EXPLAIN QUERY PLAN SELECT provider_symbol, provider_exchange_code "
            "FROM provider_listing_address WHERE provider_code = ? AND listing_id = ?",
            ("eodhd", 1),
        )
    ]

    assert len(plan) == 3
    assert all(step.startswith("SEARCH") for step in plan), plan


def test_instruments_without_a_listing_are_found_through_the_listing_index(
    seeded: sqlite3.Connection,
) -> None:
    """The "excluded and reported" query probes listing by instrument, never scans it."""
    plan = [
        str(row[3])
        for row in seeded.execute(
            "EXPLAIN QUERY PLAN SELECT i.instrument_id, i.isin FROM instrument AS i "
            "WHERE NOT EXISTS (SELECT 1 FROM listing AS l WHERE l.instrument_id = i.instrument_id)"
        )
    ]

    listing_steps = [step for step in plan if " l " in f" {step} "]
    assert listing_steps, plan
    assert all(step.startswith("SEARCH") for step in listing_steps), plan
