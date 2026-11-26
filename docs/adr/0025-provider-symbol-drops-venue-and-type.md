# ADR 0025: `provider_symbol` drops the venue label and the type

- Status: Accepted
- Date: 2026-11-26
- Supersedes: the two columns `provider_venue` and `provider_type` of ADR 0018. Everything else in that record, and all of ADR 0024, stands.

## Decision

`provider_symbol` loses two columns. The load still reads both values from a saved list, because it needs them to decide what to store; it no longer keeps them.

| Topic | Before | Now |
|---|---|---|
| Column `provider_venue` | The provider's venue label for the line, such as `NYSE` | Removed |
| Column `provider_type` | `Common Stock` or `Preferred Stock` | Removed |
| The venue label in the load | Read from the saved list; with the exchange code it decides which of our exchanges the line is on, and a label the exchange file does not have stops the list | Unchanged |
| The type in the load | Read from the saved list; only common and preferred shares are stored | Unchanged |
| The column `provider_venue` of `eodhd_exchange.csv` | The label a row of the file is about | Unchanged. It is a column of the file, not of the table |

## The table after the change

`provider_symbol` has seven columns: `provider_code`, `provider_exchange_code`, `provider_symbol`, `mic`, `provider_name`, `provider_currency` and `isin`. Each is as ADR 0018 describes it. The key, the foreign key and the two indexes are unchanged.

## Why

- **The author asked for it** on 2026-11-26, after asking what each column of the table is for.
- **Nothing reads either column,** and no accepted record plans to. The listing rule of ADR 0019 reads `mic`, `isin`, `provider_symbol` and `provider_currency`, and shows `provider_name` on the agent's report.
- **`provider_venue` only repeats how `mic` was worked out.** `mic` is the result, and it is stored.
- **Nothing is lost for good.** The saved lists under `data/eodhd/` keep both values on every line. A column can come back with a migration and one more `pyvalue symbols load`, without a request.

## Evidence

Measured on 2026-11-26.

| Finding | Measurement |
|---|---|
| Rows of `provider_symbol` in the local database | 0. No list has been downloaded |
| The migration tried on a copy of the database that held the legacy catalogue | All 38,917 rows were kept, and their other seven values were identical before and after; the primary key, the foreign key and both indexes were still there; no reference was broken |
| The load on that copy afterwards | 58 lists and 38,917 lines stored, as before the change |
| Statements needed | Two `ALTER TABLE ... DROP COLUMN`. Each column is named only in its own check, so SQLite can drop it without rebuilding the table |
| Readers of the two columns in the code | None. The load writes them and nothing reads them back |

## Consequences

- **The schema no longer makes sure that only shares are stored.** That rule was the check on `provider_type`. The load is now its only guard: it stores a line only when the list gives its type as `Common Stock` or `Preferred Stock`.
- **The database no longer says which lines are preferred shares.** Where the provider gives a preferred series the common share's ISIN, the rule of ADR 0019 sees two lines with one ISIN and sends the security to the agent. The agent's report can tell them apart by name and symbol, not by type.
- **The database no longer says which label put a US line on its exchange.** The saved list does.
- **A migration drops the two columns in place.** An existing database keeps every row and needs no rebuild.
- **What the load reports does not change:** lines that are not shares are still counted by type, and a venue label the exchange file does not have still stops its list and is named.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep both until the first live lists show whether they are useful | The author decided to drop them now. They can be added again from the saved lists |
| Keep `provider_type` so that the schema still refuses a line that is not a share | A column kept only for its check, which nothing reads |
| Stop reading the two values from the list as well | The load needs the type to keep only shares and the label to place a line on an exchange |

## Appendix: SQL

The statements of migration `0006_provider_symbol_drop_venue_and_type`, for SQLite.

```sql
ALTER TABLE provider_symbol DROP COLUMN provider_venue;

ALTER TABLE provider_symbol DROP COLUMN provider_type;
```
