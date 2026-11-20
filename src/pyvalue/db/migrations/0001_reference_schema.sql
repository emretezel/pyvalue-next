-- Migration 0001: the reference schema.
--
-- Creates the tables that say what pyvalue analyses and how a data provider
-- names it. Decisions and reasons are in the records under docs/adr/:
--   exchange, company                 ADR 0001
--   instrument, listing               ADR 0003
--   provider, provider_exchange,
--   provider_listing, and the view    ADR 0002
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

-- A market on which companies list, keyed by its ISO 10383 market code.
CREATE TABLE exchange (
    mic     TEXT NOT NULL PRIMARY KEY
            CHECK (mic GLOB '[A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9]'),
    name    TEXT NOT NULL CHECK (name <> '' AND name = trim(name)),
    country TEXT NOT NULL CHECK (country GLOB '[A-Z][A-Z]')
);

-- A legal entity that issues securities. The legal-entity identifier is
-- optional because many companies have none; where present it is unique.
CREATE TABLE company (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL CHECK (name <> '' AND name = trim(name)),
    lei        TEXT UNIQUE
               CHECK (length(lei) = 20 AND lei NOT GLOB '*[^A-Z0-9]*' AND substr(lei, 19) GLOB '[0-9][0-9]')
);

-- One security of a company, identified by its ISIN. It exists as soon as a
-- holdings source names it; where it trades is recorded in `listing`.
CREATE TABLE instrument (
    instrument_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL REFERENCES company (company_id) ON DELETE RESTRICT,
    isin          TEXT NOT NULL UNIQUE
                  CHECK (length(isin) = 12 AND isin NOT GLOB '*[^A-Z0-9]*' AND isin GLOB '[A-Z][A-Z]*[0-9]')
);

-- Serves "list a company's instruments" and the foreign-key check when a
-- company is deleted.
CREATE INDEX instrument_company_id ON instrument (company_id);

-- The primary exchange line of an instrument. UNIQUE on instrument_id means
-- an instrument has at most one listing; an instrument with none has no row.
CREATE TABLE listing (
    listing_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL UNIQUE REFERENCES instrument (instrument_id) ON DELETE RESTRICT,
    mic           TEXT NOT NULL REFERENCES exchange (mic) ON UPDATE CASCADE ON DELETE RESTRICT,
    ticker        TEXT NOT NULL CHECK (ticker <> '' AND ticker = trim(ticker) AND ticker = upper(ticker)),
    currency      TEXT NOT NULL CHECK (currency GLOB '[A-Z][A-Z][A-Z]'),
    UNIQUE (mic, ticker)
);

-- A data provider, keyed by pyvalue's own short code for it.
CREATE TABLE provider (
    provider_code TEXT NOT NULL PRIMARY KEY
                  CHECK (provider_code GLOB '[a-z]*' AND provider_code NOT GLOB '*[^a-z0-9_]*'),
    name          TEXT NOT NULL CHECK (name <> '' AND name = trim(name))
);

-- The code one provider uses for one of our exchanges. No row means the
-- provider does not serve that exchange.
CREATE TABLE provider_exchange (
    provider_code TEXT NOT NULL REFERENCES provider (provider_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    mic           TEXT NOT NULL REFERENCES exchange (mic) ON UPDATE CASCADE ON DELETE RESTRICT,
    provider_exchange_code TEXT NOT NULL CHECK (provider_exchange_code <> '' AND provider_exchange_code = trim(provider_exchange_code)),
    PRIMARY KEY (mic, provider_code)
);

-- The symbol one provider uses for one of our listings, without any exchange
-- part. No row means the listing is not mapped at that provider.
CREATE TABLE provider_listing (
    provider_code TEXT NOT NULL REFERENCES provider (provider_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    listing_id    INTEGER NOT NULL REFERENCES listing (listing_id) ON DELETE RESTRICT,
    provider_symbol TEXT NOT NULL CHECK (provider_symbol <> '' AND provider_symbol = trim(provider_symbol)),
    PRIMARY KEY (listing_id, provider_code)
);

-- The two parts a provider needs to address a listing. The exchange part
-- always comes from the exchange the listing trades on, so a listing on an
-- exchange the provider does not serve has no row here.
CREATE VIEW provider_listing_address AS
SELECT pl.provider_code, pl.listing_id, pl.provider_symbol, pe.provider_exchange_code
FROM provider_listing AS pl
JOIN listing AS l ON l.listing_id = pl.listing_id
JOIN provider_exchange AS pe ON pe.mic = l.mic AND pe.provider_code = pl.provider_code;
