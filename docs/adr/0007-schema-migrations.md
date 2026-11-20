# ADR 0007: Schema changes are numbered SQL files, recorded in a history table

- Status: Accepted
- Date: 2026-11-20

## Decision

Every change to the database schema is a migration: one numbered SQL file shipped inside the package. The database keeps a history table with one row per migration it has received. One command brings a database from whatever version it is at to the latest.

| Topic | Decision |
|---|---|
| What a migration is | One plain SQL file, `NNNN_lower_snake_name.sql`, for example `0001_reference_schema.sql` |
| Where migrations live | `src/pyvalue/db/migrations/`, shipped with the package so an installed copy can migrate |
| How they are numbered | From 1 upwards with no gaps and no repeats |
| How applied migrations are tracked | The `schema_migration` table: one row per applied migration |
| Direction | Forward only. There are no "down" migrations; a mistake is fixed by a new migration |
| Where the database is | `data/pyvalue.db` in the working folder by default; the command takes `--db PATH` to point elsewhere |
| How it is run | `pyvalue db migrate` |

## The history table

### `schema_migration`

One row per migration that has been applied to this database.

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `version` | INTEGER | PK | yes | Greater than zero | The migration's number |
| `name` | TEXT | UNIQUE | yes | Not empty; lower-case letters, digits and underscores only | The name part of the file name |
| `checksum` | TEXT | | yes | Exactly 64 lower-case hexadecimal characters | The SHA-256 fingerprint of the file as it was applied |
| `applied_at` | TEXT | | yes | The form `YYYY-MM-DDTHH:MM:SSZ` | When the migration was applied, in UTC |

Example row:

| `version` | `name` | `checksum` | `applied_at` |
|---|---|---|---|
| 1 | `reference_schema` | `9f2c…` (64 characters) | `2026-11-20T18:30:00Z` |

Notes:

- **`version` is the primary key** because the number is the migration's identity and never changes.
- **The table is created by the migration code itself**, not by a migration file: it has to exist before migration 1 can be recorded.
- **The current schema version is the highest `version`.** A database with no rows is at version 0.

## How a migration run behaves

| Rule | What it means |
|---|---|
| An applied migration is never edited | Before anything is applied, every recorded row is compared with its file. A different name or a different checksum stops the run. Any change to the file counts, a comment included. |
| A database newer than the code is refused | If the table records a migration the code does not have, the run stops. |
| One transaction per migration | A migration and its history row are committed together. If any statement fails, the whole migration is rolled back and the database is as it was before it. |
| Foreign keys are checked, not enforced, during a run | SQLite cannot rebuild a table that others reference while enforcement is on. Enforcement is switched off for the run, `PRAGMA foreign_key_check` must report nothing before each commit, and enforcement is switched back on afterwards. |
| A database that already has broken references is refused | The check is also made before the first migration, so an old fault is not blamed on a new migration. |
| A file controls no transaction | A file that contains `BEGIN`, `COMMIT`, `END`, `ROLLBACK`, `SAVEPOINT`, `RELEASE` or `PRAGMA foreign_keys` as a statement is rejected. |
| Running again is harmless | With nothing pending, a run changes nothing. |

## Why this design

- **The schema will change.** Six records already describe it and more tables are coming, so the first table is created through the same mechanism every later change will use.
- **The author chose a history table** over a bare version number: it shows what ran and when, and its checksum catches the classic mistake of editing a migration that has already been applied.
- **The author chose one SQL file per migration.** The legacy project kept 91 migrations as Python functions in a single module of 9,431 lines, which was hard to read and review.
- **The database will later hold data that cannot be fetched again for free**, so a migration must either succeed completely or leave the database untouched.

## Evidence

- **Legacy.** 91 migrations in one file, `migrations.py`, 9,431 lines. The version was one number in a one-row table, so the database could not say which migrations it had received or when.
- **SQLite.** Schema statements take part in transactions, so a failed migration can be rolled back as a whole. `PRAGMA foreign_keys` has no effect inside a transaction, which is why enforcement is switched outside it and the check is run before the commit.

## Consequences

- **The schema is the sum of the migration files.** The ADRs record decisions; the files under `src/pyvalue/db/migrations/` are what the database is built from.
- **A change needs a new file, never an edit.** That includes fixing a typo in a comment of an applied migration.
- **Line endings matter to the checksum.** `.gitattributes` keeps SQL files with LF endings on every platform.
- **A migration cannot switch foreign keys itself, or manage its own transaction.** A change that needs either is not supported until this record is revisited.
- **A migration that needs Python logic is not supported yet.** Support is added when the first one is needed.
- **The foreign-key check reads the whole database** before each commit. That is instant today and will take longer once large tables exist.
- **There is no way back.** Undoing a migration means restoring a backup or writing a new migration.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A version number only (SQLite's `user_version`) | The smallest option, but it keeps no record of when a migration ran and cannot detect an edited file. |
| A one-row table holding the version, as in legacy | The same information as the version number. |
| Python functions as migrations, as in legacy | Harder to read than SQL for schema changes. |
| A migration library (Alembic, yoyo) | A dependency and its conventions, for something about a hundred lines cover. |
| "Down" migrations | They double the work of every migration and are rarely trustworthy for data. |

## Not decided here

- How a database is backed up before a migration runs.
- How code that reads the database checks that it is at the latest version. It is added with the first component that reads it.

## Appendix: SQL

The exact statement the migration code runs to create the history table, for SQLite.

```sql
CREATE TABLE IF NOT EXISTS schema_migration (
    version    INTEGER NOT NULL PRIMARY KEY CHECK (version > 0),
    name       TEXT NOT NULL UNIQUE CHECK (name <> '' AND name NOT GLOB '*[^a-z0-9_]*'),
    checksum   TEXT NOT NULL CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    applied_at TEXT NOT NULL CHECK (
      applied_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'
    )
);
```
