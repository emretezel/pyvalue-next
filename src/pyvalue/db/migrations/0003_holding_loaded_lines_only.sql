-- Migration 0003: `holding` keeps only the lines that were loaded.
--
-- ADR 0021. Migration 0002 also stored the lines that did not become a
-- security, with an empty `instrument_id` and a reason. Nothing read them,
-- and the load already lists them in `lines_not_loaded.csv`. This migration
-- drops the `not_loaded_reason` column and makes `instrument_id` required.
--
-- SQLite cannot drop a column that a CHECK names, nor add NOT NULL to an
-- existing column, so the table is built again: a new table, the rows that
-- point at an instrument copied over, the old table dropped, the new one
-- given its name. Nothing refers to `holding`, so no other table is touched.
--
-- On a database that already holds holding lines, the rows without an
-- instrument are removed. Every other row is kept as it is.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

-- One share line of a fund's loaded filing that became, or met, a security.
-- The line's own identity is the fund and its position in the filing.
CREATE TABLE holding_new (
    fund_code            TEXT NOT NULL REFERENCES fund (fund_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    line_number          INTEGER NOT NULL CHECK (line_number > 0),
    instrument_id        INTEGER NOT NULL REFERENCES instrument (instrument_id) ON DELETE RESTRICT,
    isin                 TEXT NOT NULL
                         CHECK (length(isin) = 12 AND isin NOT GLOB '*[^A-Z0-9]*' AND isin GLOB '[A-Z][A-Z]*[0-9]'),
    issuer_name          TEXT NOT NULL CHECK (issuer_name <> '' AND issuer_name = trim(issuer_name)),
    title                TEXT CHECK (title <> '' AND title = trim(title)),
    lei                  TEXT
                         CHECK (length(lei) = 20 AND lei NOT GLOB '*[^A-Z0-9]*' AND substr(lei, 19) GLOB '[0-9][0-9]'),
    cusip                TEXT CHECK (length(cusip) = 9 AND cusip NOT GLOB '*[^A-Z0-9*@#]*'),
    sedol                TEXT CHECK (length(sedol) = 7 AND sedol NOT GLOB '*[^A-Z0-9]*'),
    ticker               TEXT CHECK (ticker <> '' AND ticker = trim(ticker)),
    asset_category       TEXT NOT NULL CHECK (asset_category IN ('EC', 'EP', 'STIV', 'OTHER')),
    asset_category_label TEXT CHECK (asset_category_label <> '' AND asset_category_label = trim(asset_category_label)),
    issuer_type          TEXT NOT NULL CHECK (issuer_type <> '' AND issuer_type NOT GLOB '*[^A-Z]*'),
    trading_country      TEXT NOT NULL CHECK (trading_country GLOB '[A-Z][A-Z]'),
    currency             TEXT NOT NULL CHECK (currency GLOB '[A-Z][A-Z][A-Z]'),
    PRIMARY KEY (fund_code, line_number),
    CHECK (asset_category_label IS NULL OR asset_category = 'OTHER')
);

INSERT INTO holding_new (
    fund_code, line_number, instrument_id, isin, issuer_name, title, lei, cusip, sedol, ticker,
    asset_category, asset_category_label, issuer_type, trading_country, currency
)
SELECT
    fund_code, line_number, instrument_id, isin, issuer_name, title, lei, cusip, sedol, ticker,
    asset_category, asset_category_label, issuer_type, trading_country, currency
FROM holding
WHERE instrument_id IS NOT NULL;

-- Dropping the table drops its index with it.
DROP TABLE holding;

ALTER TABLE holding_new RENAME TO holding;

-- Serves "the holding lines of a security" and the foreign-key check when an
-- instrument is deleted.
CREATE INDEX holding_instrument_id ON holding (instrument_id);
