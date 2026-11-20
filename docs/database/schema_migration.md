# `schema_migration`

One row per migration that has been applied to this database. Decided in ADR 0007. Created by the migration code itself (`pyvalue.db.migrate`), not by a migration file: it has to exist before migration 1 can be recorded.

This table describes the database, not the data in it. No other table refers to it.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `version` | INTEGER | PK | yes | Greater than zero | The migration's number |
| `name` | TEXT | UNIQUE | yes | Not empty; lower-case letters, digits and underscores only | The name part of the file name |
| `checksum` | TEXT | | yes | Exactly 64 lower-case hexadecimal characters | The SHA-256 fingerprint of the file as it was applied |
| `applied_at` | TEXT | | yes | The form `YYYY-MM-DDTHH:MM:SSZ` | When the migration was applied, in UTC |

## Example row

| `version` | `name` | `checksum` | `applied_at` |
|---|---|---|---|
| 1 | `reference_schema` | `4adba757…` (64 characters) | `2026-11-20T19:49:24Z` |

The file for this row is `src/pyvalue/db/migrations/0001_reference_schema.sql`.

## Notes

- **`version` is the primary key** because the number is the migration's identity and never changes.
- **The current schema version is the highest `version`.** A database with no rows is at version 0.
- **Rows are written only by `pyvalue db migrate`**, in the same transaction as the migration they record.
- **The checksum is compared on every run.** If the file of an applied migration has changed in any way, `pyvalue db migrate` stops. An applied migration is never edited.
- **Versions run 1, 2, 3 without a hole.** A history with a hole means the table was edited by hand, and `pyvalue db migrate` refuses the database.

## Relationships

None.

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `schema_migration (version)` | The primary key | Read the history in order |
| `schema_migration (name)` | The `UNIQUE` constraint | None; it exists to enforce that no two migrations share a name |

## Views

None.
