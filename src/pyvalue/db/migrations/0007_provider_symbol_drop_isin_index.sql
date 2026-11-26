-- Migration 0007: provider_symbol loses its index on the ISIN.
--
-- ADR 0018 created the index for "the lines that carry a given ISIN, the
-- first lookup of the listing rule". The rule as it is run (ADR 0026) does
-- not make that lookup: it reads the provider's lines once and finds them in
-- memory, because the ticker comparison it also needs cannot be done by the
-- database. An index names the query it serves, and this one has none.
--
-- No row changes. The primary key, the foreign key and the index on the
-- exchange stay.
--
-- Once applied, this file is never edited (ADR 0007). A change to the schema
-- is a new migration.

DROP INDEX provider_symbol_isin;
