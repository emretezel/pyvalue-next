# ADR 0022: `holding` drops the filer's label and the issuer type

- Status: Accepted
- Date: 2026-11-26
- Supersedes: the two columns `asset_category_label` and `issuer_type` of ADR 0017, and the issuer type on the common holding line of ADR 0016. Everything else in both records stands.

## Decision

`holding` loses two columns, and the load stops reading the issuer type from the filing.

| Topic | Before | Now |
|---|---|---|
| Column `asset_category_label` | The filer's own label for a line in the `OTHER` category, such as `ADR` | Removed |
| Column `issuer_type` | The form's issuer type, such as `CORP` | Removed |
| The issuer type in the load | Read from every line of the filing and carried to the table | Not read |
| The filer's label in the load | Read from the filing; the receipt check of ADR 0006 looks at it; it is written to `lines_not_loaded.csv` | Unchanged |
| Column `asset_category` | Common share, preferred share, short-term investment vehicle, or the filer's own category | Unchanged |

## The table after the change

`holding` has thirteen columns: `fund_code`, `line_number`, `instrument_id`, `isin`, `issuer_name`, `title`, `lei`, `cusip`, `sedol`, `ticker`, `asset_category`, `trading_country` and `currency`. Each is as ADR 0017 and ADR 0021 describe it.

The table-level rule that a label is allowed only with the `OTHER` category goes with the label.

## Why

- **Neither column carries information.** The label is empty on every row, and the issuer type is the same on every row.
- **Nothing reads either,** and no accepted record plans to: the listing rule of ADR 0019 reads `instrument_id`, `isin`, `ticker`, `trading_country` and `currency`.
- **`asset_category` stays because it does carry information.** It is the only place the database says that a security is a preferred share.
- **The author asked for it** on 2026-11-26, while going over the columns of every table.

## Evidence

Measured on 2026-11-26 on the two pinned filings and the local database.

| Finding | Measurement |
|---|---|
| Rows of `holding` | 12,215 |
| Rows with a label | 0 |
| Rows with an issuer type other than `CORP` | 0 |
| Lines of the two filings that carry a label | 0 of 12,414 |
| Lines of the two filings with an issuer type other than `CORP` | 104 of 12,414, none of them stored |
| Of those 104 | 103 debt or derivative lines, which are never loaded; 1 share line, Vanguard FTSE Emerging Markets ETF (`RF`, a registered fund), which is kept out by a decision (ADR 0013) |
| Rows whose `asset_category` is a preferred share | 53, of 52 companies; 32 of those companies also have a common share in the universe, and 20 companies are in the universe only through a preferred share |

The migration was tried on a copy of the local database: all 12,215 rows were kept, the other thirteen columns were unchanged, and no reference was broken.

## Consequences

- **A migration rebuilds the table.** SQLite cannot drop a column that a table-level check names, and the label is named in one. An existing database keeps every row and needs no rebuild.
- **The reader of the SEC form no longer reads the issuer type,** and a line that states none is no longer refused. Nothing used the value, so a strictness about it guarded nothing.
- **The one share line that is a fund is still kept out by its decision,** not by its issuer type. Should a rule one day keep registered funds out by their type, it reads the type from the filing again.
- **A sponsor that uses the label is not affected in what the load does.** The receipt check still reads the label from the filing. Only the stored copy is gone; the label of a line that was not loaded is still in `lines_not_loaded.csv`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep both columns, in case they become useful | A column that says nothing today can be added again, with its values, by loading the filings again |
| Drop `asset_category` as well | It is the only record of which securities are preferred shares, and 32 companies have both kinds |
| Drop the columns and keep reading the issuer type | A value read, checked and carried that nothing uses |

## Appendix: SQL

The statements of migration `0004_holding_drop_label_and_issuer_type`, for SQLite.

```sql
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

DROP TABLE holding;

ALTER TABLE holding_new RENAME TO holding;

CREATE INDEX holding_instrument_id ON holding (instrument_id);
```
