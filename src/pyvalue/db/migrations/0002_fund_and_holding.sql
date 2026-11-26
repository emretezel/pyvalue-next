-- Migration 0002: funds and their holding lines.
--
-- Adds the two tables of ADR 0017: `fund`, one row per fund whose holdings
-- are loaded, and `holding`, one row per share line of that fund's loaded
-- filing. A holding row records what the fund's documents say; the only thing
-- in it that pyvalue decided is which instrument the line was loaded as.
--
-- On a database that already holds companies and instruments both tables
-- start empty. `pyvalue universe load` fills them.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

-- A fund whose holdings are loaded, keyed by pyvalue's own code for it (its
-- ticker). The filing number and the dates say which documents the rows of
-- `holding` come from.
CREATE TABLE fund (
    fund_code         TEXT NOT NULL PRIMARY KEY
                      CHECK (fund_code <> '' AND fund_code NOT GLOB '*[^A-Z0-9]*'),
    name              TEXT NOT NULL CHECK (name <> '' AND name = trim(name)),
    scope             TEXT NOT NULL CHECK (scope IN ('US', 'NON_US')),
    sec_series_id     TEXT NOT NULL UNIQUE
                      CHECK (length(sec_series_id) = 10 AND sec_series_id GLOB 'S[0-9]*'
                             AND substr(sec_series_id, 2) NOT GLOB '*[^0-9]*'),
    sec_filing_number TEXT NOT NULL UNIQUE
                      CHECK (sec_filing_number GLOB
                             '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    -- IS, not =: date() of a malformed text is NULL, and a comparison with
    -- NULL does not fail a CHECK.
    holdings_date     TEXT NOT NULL CHECK (holdings_date IS date(holdings_date)),
    sponsor_file_date TEXT CHECK (sponsor_file_date IS NULL OR sponsor_file_date IS date(sponsor_file_date))
);

-- One share line of a fund's loaded filing. The line's own identity is the
-- fund and its position in the filing. `instrument_id` is empty exactly when
-- the line was not loaded, and then `not_loaded_reason` says why.
CREATE TABLE holding (
    fund_code            TEXT NOT NULL REFERENCES fund (fund_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    line_number          INTEGER NOT NULL CHECK (line_number > 0),
    instrument_id        INTEGER REFERENCES instrument (instrument_id) ON DELETE RESTRICT,
    not_loaded_reason    TEXT CHECK (not_loaded_reason IN ('excluded_by_decision', 'receipt_company_already_loaded')),
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
    CHECK ((instrument_id IS NULL) = (not_loaded_reason IS NOT NULL)),
    CHECK (asset_category_label IS NULL OR asset_category = 'OTHER')
);

-- Serves "the holding lines of a security" and the foreign-key check when an
-- instrument is deleted.
CREATE INDEX holding_instrument_id ON holding (instrument_id);
