# ADR 0021: `holding` stores only the lines that were loaded

- Status: Accepted
- Date: 2026-11-26
- Supersedes: the part of ADR 0017 that stores a line that was not loaded, with an empty `instrument_id` and a `not_loaded_reason`. Everything else in ADR 0017 stands.

## Decision

A line of a filing gets a row in `holding` only when the load turned it into an instrument, or it named an instrument already there. A line that was not loaded gets no row.

| Topic | ADR 0017 | Now |
|---|---|---|
| A share line kept out by `excluded.csv` (ADR 0013) | A row with an empty `instrument_id` and the reason `excluded_by_decision` | No row |
| A receipt whose company is already in the universe (ADR 0006, ADR 0014, ADR 0020) | A row with an empty `instrument_id` and the reason `receipt_company_already_loaded` | No row |
| Column `not_loaded_reason` | Present, filled exactly when `instrument_id` is empty | Removed |
| Column `instrument_id` | Optional | Required |

Every line that was not loaded is still listed in `data/universe/lines_not_loaded.csv` with its reason, as ADR 0009 has it. That file is written by every load.

## The table after the change

Only the two changed columns are shown; the other fourteen are as in ADR 0017.

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `instrument_id` | INTEGER | FK → `instrument.instrument_id` | yes | The instrument must exist | The security the line was loaded as |
| `not_loaded_reason` | | | | | Removed |

Which lines get a row:

| Line of the filing | Row in `holding` |
|---|---|
| A share line that the load turns into an instrument, or that names an instrument already there | Yes |
| A depositary receipt read as its ordinary share (ADR 0015) | Yes. It points at the ordinary share and keeps the ISIN the fund filed |
| A share line kept out by a decision | No |
| A receipt whose company is already in the universe | No |
| A line without a valid ISIN, or one the filing classifies as debt or as a derivative | No, as before |

## Why

- **Nothing read those rows.** The listing rule of ADR 0019 reads the lines of a security, and a line that was not loaded belongs to no security.
- **The reasons are already written down.** `lines_not_loaded.csv` lists every such line with its reason at every load.
- **The table says one thing.** Every row is now a line of a security in the universe. No column is empty to say "this one does not count", and no second column is needed to say why.
- **The author asked for it** on 2026-11-26, after asking what each column of `holding` is for.

## Evidence

Measured on 2026-11-26 on the local database, rebuilt the same day from the two pinned filings.

| Finding | Measurement |
|---|---|
| Rows of `holding` | 12,259 |
| Rows without an instrument | 44: 13 kept out by a decision, 31 receipts of a company already loaded |
| Rows that stay | 12,215 |
| Code that reads the 44 rows or the reason | None |

The migration was tried on a copy of that database: it removed the 44 rows, left the other 12,215 exactly as they were, and left no broken reference. The lookup of a security's lines still uses the index `holding_instrument_id`.

## Consequences

- **The database alone no longer shows that a fund holds a security that was kept out.** That is read from `lines_not_loaded.csv`.
- **A migration rebuilds the table.** SQLite cannot drop a column that a check names, nor make an existing column required, so the table is created again and the rows that point at an instrument are copied over. An existing database loses its rows without an instrument and keeps every other row; it needs no rebuild.
- **`HoldingRepository` and the load lose the notion of a line that was recorded but not loaded.**
- **The count the command prints,** "Holding lines stored", is now the number of lines that point at a security.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep the rows and the reason, as in ADR 0017 | A column and 44 rows that nothing reads, kept in step with a file that already says the same |
| Keep the rows without the reason | An empty `instrument_id` would not say why |
| A table of its own for the lines that were not loaded | More structure for the same unread rows |

## Appendix: SQL

The statements of migration `0003_holding_loaded_lines_only`, for SQLite.

```sql
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

DROP TABLE holding;

ALTER TABLE holding_new RENAME TO holding;

CREATE INDEX holding_instrument_id ON holding (instrument_id);
```
