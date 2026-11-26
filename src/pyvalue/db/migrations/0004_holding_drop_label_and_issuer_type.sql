-- Migration 0004: `holding` loses `asset_category_label` and `issuer_type`.
--
-- ADR 0022. Neither column carried information: on the two pinned filings
-- the label is empty on every row and the issuer type is `CORP` on every
-- row. Nothing reads either.
--
-- SQLite cannot drop a column that a table CHECK names, and the label is
-- named in one, so the table is built again as in migration 0003: a new
-- table, every row copied over without the two columns, the old table
-- dropped, the new one given its name. Nothing refers to `holding`, so no
-- other table is touched.
--
-- On a database that already holds holding lines, every row is kept; only
-- the two columns go.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

-- One share line of a fund's loaded filing that became, or met, a security.
-- The line's own identity is the fund and its position in the filing.
CREATE TABLE holding_new (
    fund_code       TEXT NOT NULL REFERENCES fund (fund_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    line_number     INTEGER NOT NULL CHECK (line_number > 0),
    instrument_id   INTEGER NOT NULL REFERENCES instrument (instrument_id) ON DELETE RESTRICT,
    isin            TEXT NOT NULL
                    CHECK (length(isin) = 12 AND isin NOT GLOB '*[^A-Z0-9]*' AND isin GLOB '[A-Z][A-Z]*[0-9]'),
    issuer_name     TEXT NOT NULL CHECK (issuer_name <> '' AND issuer_name = trim(issuer_name)),
    title           TEXT CHECK (title <> '' AND title = trim(title)),
    lei             TEXT
                    CHECK (length(lei) = 20 AND lei NOT GLOB '*[^A-Z0-9]*' AND substr(lei, 19) GLOB '[0-9][0-9]'),
    cusip           TEXT CHECK (length(cusip) = 9 AND cusip NOT GLOB '*[^A-Z0-9*@#]*'),
    sedol           TEXT CHECK (length(sedol) = 7 AND sedol NOT GLOB '*[^A-Z0-9]*'),
    ticker          TEXT CHECK (ticker <> '' AND ticker = trim(ticker)),
    asset_category  TEXT NOT NULL CHECK (asset_category IN ('EC', 'EP', 'STIV', 'OTHER')),
    trading_country TEXT NOT NULL CHECK (trading_country GLOB '[A-Z][A-Z]'),
    currency        TEXT NOT NULL CHECK (currency GLOB '[A-Z][A-Z][A-Z]'),
    PRIMARY KEY (fund_code, line_number)
);

INSERT INTO holding_new (
    fund_code, line_number, instrument_id, isin, issuer_name, title, lei, cusip, sedol, ticker,
    asset_category, trading_country, currency
)
SELECT
    fund_code, line_number, instrument_id, isin, issuer_name, title, lei, cusip, sedol, ticker,
    asset_category, trading_country, currency
FROM holding;

-- Dropping the table drops its index with it.
DROP TABLE holding;

ALTER TABLE holding_new RENAME TO holding;

-- Serves "the holding lines of a security" and the foreign-key check when an
-- instrument is deleted.
CREATE INDEX holding_instrument_id ON holding (instrument_id);
