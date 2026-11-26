-- Migration 0006: provider_symbol loses the venue label and the type.
--
-- ADR 0025 removes two columns of the table of ADR 0018: `provider_venue`,
-- the provider's venue label for a line, and `provider_type`, which said
-- whether a line is a common or a preferred share. Nothing reads either. The
-- load still reads both values from a saved list, to place a line on an
-- exchange and to keep only shares, and no longer stores them.
--
-- Each column is named only in its own check, so SQLite can drop it in
-- place: the rows keep their other values, and the primary key, the foreign
-- key and the two indexes are untouched. With `provider_type` goes the check
-- that only shares are stored; the load is the guard for that now.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

ALTER TABLE provider_symbol DROP COLUMN provider_venue;

ALTER TABLE provider_symbol DROP COLUMN provider_type;
