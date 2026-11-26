-- Migration 0005: the provider's symbol list.
--
-- Adds the table of ADR 0018, `provider_symbol`: one row per line of a
-- provider's symbol list that is a common or preferred share on one of our
-- exchanges. The listing rule looks a security up in it (ADR 0019).
--
-- A symbol row points at the mapping its exchange code comes from, and a
-- foreign key needs a unique key on exactly the columns it names. So
-- `provider_exchange` gets one more unique key first. It adds no new rule:
-- the primary key of that table already makes the three columns unique
-- together.
--
-- On an existing database the new table starts empty, and nothing else
-- changes. `pyvalue symbols load` fills it (ADR 0024).
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

-- The key the foreign key of provider_symbol points at.
CREATE UNIQUE INDEX provider_exchange_code_key
    ON provider_exchange (mic, provider_code, provider_exchange_code);

-- One line of a provider's symbol list. The provider's own identity for a line
-- is its exchange code and its symbol (`BRK-B.US`), so that is the key. `mic`
-- says which of our exchanges the line is on; it is worked out from the code
-- and the provider's venue label when the list is stored.
CREATE TABLE provider_symbol (
    provider_code          TEXT NOT NULL,
    provider_exchange_code TEXT NOT NULL,
    provider_symbol        TEXT NOT NULL CHECK (provider_symbol <> '' AND provider_symbol = trim(provider_symbol)),
    mic                    TEXT NOT NULL,
    provider_venue         TEXT CHECK (provider_venue <> '' AND provider_venue = trim(provider_venue)),
    provider_name          TEXT CHECK (provider_name <> '' AND provider_name = trim(provider_name)),
    provider_type          TEXT NOT NULL CHECK (provider_type IN ('Common Stock', 'Preferred Stock')),
    provider_currency      TEXT NOT NULL
                           CHECK (provider_currency <> '' AND provider_currency = trim(provider_currency)),
    isin                   TEXT
                           CHECK (length(isin) = 12 AND isin NOT GLOB '*[^A-Z0-9]*' AND isin GLOB '[A-Z][A-Z]*[0-9]'),
    PRIMARY KEY (provider_code, provider_exchange_code, provider_symbol),
    FOREIGN KEY (mic, provider_code, provider_exchange_code)
        REFERENCES provider_exchange (mic, provider_code, provider_exchange_code)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Serves "the lines on one of our exchanges" and the foreign-key check when a
-- provider_exchange row is deleted or corrected.
CREATE INDEX provider_symbol_exchange ON provider_symbol (mic, provider_code, provider_exchange_code);

-- Serves "the lines that carry this ISIN". Lines without an ISIN are left out.
CREATE INDEX provider_symbol_isin ON provider_symbol (isin) WHERE isin IS NOT NULL;
