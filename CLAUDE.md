# Repository Guidelines

## Project Description
pyvalue is a Python toolkit for value investing: a curated global stock universe, data-quality checks on fundamental data, and quality-at-a-reasonable-price (QARP) screening.

This repository is the ground-up successor to the original pyvalue (version 0.1.0). It is developed under the name `pyvalue-next` and takes over the `pyvalue` name on GitHub at cut-over. The package, import and command name is `pyvalue` throughout, so the cut-over needs no code change.

## Architecture

If this repository does not yet contain a `docs/architecture.md` file, **do not write any implementation code until you have done the following**:

1. Start a conversation with the author to understand the goals, constraints, and non-goals.
2. Propose a high-level architecture: identify the key components and how they communicate.
3. Get the author's sign-off on the high-level design.
4. Break each component down into a more detailed design before touching code.
5. Implement one component at a time, in dependency order (foundations first).
6. Write `docs/architecture.md` once the design is agreed, and keep it up to date as the project evolves.

When the architecture file already exists, read it at the start of every session before making any structural decisions.

Design decisions are recorded as architecture decision records under `docs/adr/`, one decision per file. A decision is agreed with the author before its record is written, and the record is written before the code that implements it.

## Legacy Project

The original pyvalue is kept as a read-only reference, checked out beside this repository (`../pyvalue`; `pyvalue-legacy` on GitHub after cut-over).

- Read it for domain knowledge: metric definitions, known vendor data defects, regression cases, and research notes.
- Never modify it from a session in this repository, and never import from it.
- Do not copy code wholesale. When something is worth carrying over (a regression case, a self-contained module), port it deliberately together with its tests, and say so in the commit message.
- Both projects install a package and a command called `pyvalue`, so each has its own conda environment: `pyvalue-next` here, `pyvalue` there.

## Agent Operating Rules

### Workflow
- Enter plan mode for any non-trivial task. Use plan mode for verification and review work, not only for building.
- Don't create feature branches. Always work on `main` unless the user explicitly instructs otherwise.

### Design & Elegance
- **Pick the right pattern up front.** Before implementing, identify the most appropriate design pattern and apply sound object-oriented (or functional, where idiomatic) principles.
- **Simplest correct solution wins.** Prefer the simplest solution that is correct and maintainable. Do not over-engineer straightforward tasks; skip the elegance pass for simple fixes.
- **Refactoring is part of every feature, not optional.** When adding or changing code, check whether the surrounding design is still the most elegant solution. If not, refactor it before moving on. If the current fix looks hacky, replace it with the elegant solution you would choose knowing everything you know now.
- **File length.** If a Python module grows too long and is becoming hard to maintain, refactor it into multiple modules along its natural responsibility seams. There is no fixed line-count rule — use judgement based on how many distinct responsibilities the file has accumulated and whether readers can still navigate it comfortably.
- **Ongoing design review.** As the project grows, whenever you are working on a part of the code, review whether that part should be refactored to better adhere to established design patterns and object-oriented principles. Long-term maintainability, ease of change, readability, and the ability to add new features without friction are paramount. Do not defer this review — if a structural improvement is warranted, propose it to the author before moving on.
- **Revisit tool and library choices.** As the project grows, periodically reassess the libraries, frameworks, and tools in use. If a better-fit alternative exists, propose the migration to the author with a concrete rationale (what it improves, what it costs, what it breaks) before switching.

## Database and SQL Design

### Schema Design Principles
- **Single source of truth.** Every fact lives in exactly one place. Never replicate a value across tables to avoid a join.
- **One table, one thing.** A table models exactly one entity, event, or relationship. Mixing concerns is a design smell.
- **Normalise to at least 3NF by default.** Deviate only when a clear, justified performance need exists — and document the deviation explicitly.
- **Primary keys: meaningful and minimal.** Prefer natural keys when they are genuinely stable and unique; use surrogate keys only when no natural key exists or the natural key is composite and unwieldy.
- **Always declare foreign keys.** Referential integrity is enforced at the schema level, not in application code. Ensure SQLite is opened with `PRAGMA foreign_keys = ON` so the constraints are actually enforced.
- **Always declare UNIQUE constraints** on every column or combination that is semantically unique, regardless of whether it is also the primary key.
- **Default to NOT NULL.** A column is nullable only when the absence of a value is a meaningful, valid state.
- **Use the most precise data type that correctly represents the domain** (`DATE` / ISO-8601 `TEXT` for dates, integer minor units or `NUMERIC` affinity for money and prices — never `REAL`/floating point for monetary or price values, since floating-point error is unacceptable in a value-investing/trading context).
- **No magic values.** Never use sentinel values (`0`, `-1`, `"N/A"`) to represent absence or special states — use `NULL` or a proper status column with a `CHECK` constraint.
- **CHECK constraints encode invariants.** Domain rules (e.g. `quantity > 0`, `side IN ('BUY','SELL')`, valid enum values, currency code length) must be `CHECK` constraints so the database enforces them.

### Indexes
- Add indexes after the schema is correct. Never let a performance desire drive a denormalisation decision.
- Justify each index: name the query pattern it serves.
- Avoid redundant indexes (e.g. an index whose leading columns are already covered by another).
- Use views to pre-compose common joins or projections without duplicating data.

### Schema Evolution
Whenever features are added or code is refactored, re-evaluate the schema. If the design can be improved, plan and apply the necessary migrations — do not silently preserve a bad design because it already exists.

Migrations live in `src/pyvalue/db/migrations/`, one numbered SQL file each (ADR 0007). To change the schema, add the next numbered file, update the table's file under `docs/database/` in the same commit, and call out any impact on the local database. Never edit a migration that has been applied: its checksum is recorded, and `pyvalue db migrate` refuses a database whose applied migrations no longer match their files.

### Database Access
All reading and writing of the database goes through the `pyvalue.db` package. The design pattern is **Repository with Unit of Work**: one repository class per table holds every statement for that table, and a unit of work owns the connection and the transaction. The decision and its reasons are in ADR 0008.

- **One home.** Only `pyvalue.db` imports `sqlite3`, holds a connection, or contains SQL. No other package builds a query, not even a `SELECT`. A test enforces the import rule (`tests/unit/test_architecture_rules.py`).
- **One repository class per table.** Each table has exactly one class in `pyvalue.db` that owns it, named after the table: `CompanyRepository` for `company`. Every statement that inserts, updates or deletes rows of a table is a method of its repository and of nothing else, so the answer to "what can change this table?" is one class.
- **Reads go through repositories too.** A query lives in the repository of the table whose rows it returns. A query that joins several tables lives in the repository of the table it is mainly about, or reads a view.
- **Methods say what, not how.** Name a method after what the caller wants (`find_by_isin`, `add`, `set_lei`). It takes and returns ids and typed values. It never takes SQL, a `WHERE` fragment or a column name from its caller, and there is no general `execute` for other packages to use.
- **Typed, immutable records.** A repository returns frozen dataclasses defined in `pyvalue.db`, one per table, or plain values. It never returns a tuple, a `sqlite3.Row` or a cursor.
- **A unit of work owns the transaction.** A component asks `pyvalue.db` for a unit of work, reaches the repositories through it, and leaves it. Everything done inside is committed together, or rolled back together if an exception escapes. All repositories of one unit of work share its connection. A repository never begins, commits or rolls back, and a component never sees a connection.
- **Components decide, repositories store.** A business rule (which company a holdings line belongs to, whether a listing may be filled) lives in the component that owns it. A repository does what its method name says and nothing more. The schema's constraints remain the last line of defence, and a violated constraint reaches the component as a `pyvalue.db` error, never as a raw `sqlite3` one.
- **Schema statements belong to migrations.** No repository creates, alters or drops anything.
- **Tests use the same door.** A test of a component works through a unit of work on a temporary migrated database. Only the tests of `pyvalue.db` itself use `sqlite3` directly.

- **One door.** Other packages import from `pyvalue.db` itself, never from a module inside it. They get `Database`, the records and the errors; `connect` is not exported. A test enforces it.
- **Only methods that are called.** A repository gets a method, with its test, when a component first needs it. Do not add `find_by_...` methods in advance.

What a component looks like under this rule:

```python
database = Database(path)
with database.unit_of_work() as work:
    company = work.companies.add(name=name, lei=lei)
    work.instruments.add(company_id=company.company_id, isin=isin)
# Both rows are committed here, or neither is.
```

`unit_of_work()` refuses a missing database and one that is not at the latest schema version. One module per table holds the record and its repository (`db/company.py`: `Company`, `CompanyRepository`), and the `Repository` base class turns every `sqlite3` error into a `pyvalue.db` one.

When adding or changing database access, flag — and correct — any of these:
- SQL, a connection or a `sqlite3` import outside `pyvalue.db`
- A second class that writes a table which already has a repository
- A repository method that commits, or a component that manages a transaction by hand
- A repository method that returns raw rows, or accepts SQL from its caller
- A business decision made inside a repository

### SQL Style
- Write correct SQL first; optimise second.
- Never use `SELECT *` in production code — name every column explicitly.
- Do not repeat logic that belongs in the schema (e.g. filtering soft-deleted rows in every query instead of defining a view).
- Check whether each important query can use an index efficiently; use `EXPLAIN QUERY PLAN` for non-trivial queries.

### Review Expectations
Flag — and propose corrections for — any schema that:
- Duplicates a fact or violates normal form without justification
- Uses an imprecise data type (especially `REAL`/floating point for money or prices)
- Omits a constraint that should exist (NOT NULL, UNIQUE, FOREIGN KEY, CHECK)
- Conflates multiple entities in one table
- Uses magic values instead of proper nullability or `CHECK` constraints

When proposing schema changes, always include:
1. Recommended schema with all constraints stated explicitly
2. Normalisation rationale (target normal form and why)
3. Index recommendations with the query patterns they serve
4. Justification for any deliberate deviation from normal form

## Project Structure & Module Organization

### Layout Principles
- Choose the folder layout that best matches the project type and language conventions. For Python, default to a `src/`-layout package with `tests/` alongside — pyvalue follows this convention.
- Re-evaluate the structure after significant changes. If a better layout has become clear, reorganise — a clean structure is worth the churn.

### Current Layout
Update this list in the same commit as any structural change. `docs/architecture.md` describes the components and the rules between them.

- `src/pyvalue/`: the package.
  - `db/`: the database. `Database` and the unit of work, one module per table with its record and repository, connections, the migration run, and the migration files under `db/migrations/`. The only package that imports `sqlite3` or contains SQL; its repository classes and unit of work are the only way in (see **Database Access**).
  - `universe/`: the universe load. Downloads the pinned SEC holdings filings of the two funds of ADR 0016 (VTI and VXUS), reads them, fills `company` and `instrument` by the rules of ADR 0006 and ADR 0009, and records the funds and the share lines that were loaded in `fund` and `holding` (ADR 0017, ADR 0021, ADR 0022). A line that was not loaded is not stored; it is listed in `data/universe/lines_not_loaded.csv`. The funds and their pinned filings are in `universe/funds.py`. Each fund is read through its sponsor's adapter (`universe/holdings.py` defines the interface and the common holding line): `universe/vanguard.py` joins the filing's lines with Vanguard's own holdings file, which adds a ticker, a SEDOL and Vanguard's own name for the security, and checks that the filed country is still the trading country. `universe/receipts.py` decides what is a depositary receipt from the filing's label and wording and from that name (ADR 0006, ADR 0020). `universe/decisions/lei.csv` holds the decisions that settle which legal-entity identifier a company gets when the funds disagree (ADR 0010, ADR 0011); it holds its header only while both funds have one sponsor. `universe/decisions/name.csv` holds the names of companies whose filed name is a vendor placeholder (ADR 0012). `universe/decisions/excluded.csv` lists securities that are kept out of the universe (ADR 0013), among them every fund and property trust (ADR 0023). `universe/decisions/ordinary_share.csv` pairs a depositary receipt with the ordinary share its lines are read as (ADR 0015).
  - `listings/`: where a security trades and what a provider calls it there (ADR 0018, ADR 0019, ADR 0024, ADR 0026, ADR 0027). `listings/reference/exchange.csv` is our list of exchanges (ISO 10383 market code, name, country), and `listings/exchanges.py` reads it. `listings/symbols.py` is the symbols load: it adds and corrects `exchange`, `provider` and `provider_exchange` from the two committed files, and stores each saved symbol list in `provider_symbol` as a whole, keeping only common and preferred shares on our exchanges. It reads a line's type and venue label to decide that and does not store them (ADR 0025). It reads files only and cannot reach the network. `listings/download.py` is the symbols download, which contacts the provider. It keeps the exchange list and one symbol list per mapped code as files under `data/eodhd/` and never opens the database. `listings/saved_lists.py` names the folder and the files and holds the test for a list that is suspiciously short, which both apply. `listings/rule.py` is the listing rule of ADR 0019 for one security, with no database in it: given the security's holding lines and the provider's lines, it answers "fill with this line" or "on the report, for this reason" (ADR 0026). `listings/decisions/listing.csv` holds the decisions on listings, one row per security: the provider's line it is listed on, or that it gets none (ADR 0019); `listings/decisions.py` reads it. `listings/plan.py` works out what one run does with every security, as one pure function: which are left alone (not held, market not served, waiting for a symbol list), what the decisions say, what the rule fills, and which of two securities gets an exchange and ticker both want. `listings/fill.py` is the listing fill: it reads the database, writes the listings the plan chose in one transaction, and `listings/report.py` writes the securities that were not filled to `data/listings/cases_for_agent.csv` (ADR 0026). It reads the database and the decisions file only and cannot reach the network.
  - `fundamentals/`: the provider's fundamentals for the listings, kept as files (ADR 0028). `fundamentals/download.py` is the fundamentals download, the second piece of code that contacts the provider: it reads the listings from the database through the view `provider_listing_address`, requests the payload of every provider line that has no saved file, and keeps each answer. It works in batches of 500 requests on 8 threads, asks the account what is left of the day's allowance before each batch, and stops 5,000 short of the limit, so the account's extra reserve is never touched. It never writes the database and never overwrites a saved payload. `fundamentals/saved_payloads.py` names the folder and a line's file (`<CODE>/<SYMBOL>.json.gz`, every character outside `A-Z`, `0-9`, `-` and `_` written as `%XX`) and packs a payload with gzip. `fundamentals/report.py` writes the listings without a payload to `data/fundamentals/not_downloaded.csv`. Three pure modules hold the rules for reading the payloads into tables (ADR 0029, ADR 0030): `fundamentals/fiscal_years.py` works out which yearly dates are a company's fiscal years, and which of those are proven to be twelve months long; `fundamentals/checks.py` holds each check of ADR 0030 as a small function, the outcome of each, and the record of a finding; `fundamentals/statements.py` turns one company's payloads into the periods and rows to store and the findings, choosing the payload, the fiscal years and each year's currency. They read no file, no database and no clock. `fundamentals/load.py` is the statements load, `pyvalue fundamentals load`: it reads every saved payload of the listings, runs those rules company by company, replaces the four statement tables as a whole in one transaction, and writes what it found with `fundamentals/findings.py` to `data/fundamentals/findings.csv`. It never contacts the provider and refuses to run when fewer than half of the listings have a saved payload.
  - `providers/`: the data providers. `providers/eodhd_exchange.csv` maps EODHD's exchange codes, and for `US` its venue labels, to our exchanges; a row without a market leaves a code or a label out on purpose. `providers/exchange_codes.py` reads it. `providers/eodhd.py` is the EODHD client: the requests for the exchange list, for the symbol list of one code, for the fundamentals of one security and for the account's daily allowance (ADR 0028); strict readers of the two lists; the check that an answer is the fundamentals payload of the symbol that was asked for; the reader of the allowance, which takes three values from an answer that names the account holder and nothing else; and the map that turns EODHD's sub-unit currency codes into currencies (`GBX` is `GBP`). It is handed the API key and never reads the settings file. `providers/statements.py` is what pyvalue asks of any provider's financial statements: the 28 figures under pyvalue's names (ADR 0029) and the shape a provider's reader hands them over in. `providers/eodhd_statements.py` reads the yearly rows of a saved EODHD payload into that shape; it alone knows EODHD's field names, reports what the payload says and decides nothing. This package writes no table.
  - `cli/`: the `pyvalue` command. Thin commands that call the components. `cli/progress.py` is the progress bar: one line redrawn in place, and nothing when the output is not a terminal. **A command that runs for more than a few seconds shows this bar and prints its counts once at the end; it never prints a line per step** (the author's rule, ADR 0028).
  - `config.py`: reads `private/config.toml`. Never puts a value from that file into a message.
  - `http.py`: the one place a download is made from: one named host, HTTPS only, no redirects. A secret part of an address, such as a provider's API key, is sent and never put into a message.
  - `identifiers.py`: whether a text is a valid ISIN or legal-entity identifier, check digits included.
  - `csv_file.py`: reads a committed comma-separated file with a fixed header, and writes a generated one. The decision files and the exchange files start with it; the files a run leaves under `data/` for a person or an agent are written with it.
  - `saved_file.py`: keeps downloaded bytes under their final name, whole or not at all: written under a temporary name, then renamed. The two EODHD downloads save with it.
  - `decision_file.py`: what every decisions file shares: one row per security, keyed by its ISIN, with the day of the decision. The reader of each kind of decision is built on it and names its own error.
  - `errors.py`: `PyvalueError`, the base of every error a person can fix. The command line prints such an error as one line. It also holds the steps of a rebuild, which every message that asks for one gives in the same words.
- `tests/`: pytest suite, mirroring the source tree under `tests/unit/`, `tests/regression/`, and `tests/integration/`. Shared fixtures are in `tests/conftest.py`; checked-in sample data is under `tests/fixtures/` (the sample EODHD lists and fundamentals payloads there are made up in the provider's shape; none was downloaded).
- `docs/`: substantive documentation (see the **Documentation** section); `docs/architecture.md` is the design, `docs/adr/` holds the architecture decision records, `docs/database/` has one file per table, `docs/universe.md` records what the universe held at the end of the universe phase, `docs/listings.md` what the listings held after the first live lists and the agent's first pass, `docs/fundamentals.md` what the first fundamentals download saved, and `docs/statements.md` what the first statements load stored and found.
- `data/`: local artifacts such as the database (gitignored).
- `private/`: local config and API keys (`private/config.toml`, gitignored).

## Build, Test, and Development Commands
- Use the `pyvalue-next` conda environment (Python 3.14) for all project commands. Never install this package into the legacy project's `pyvalue` environment.
- `conda run -n pyvalue-next sh -c 'UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv sync --locked --extra dev'`: install the editable package and its development tools at the exact versions in `uv.lock` (Python >=3.14). `UV_PROJECT_ENVIRONMENT` points uv at the conda environment; without it uv creates its own `.venv`. The sync is exact: it also removes packages that are not in the lock, and it fails if `uv.lock` is out of date with `pyproject.toml`.
- `conda run -n pyvalue-next pytest`: run the test suite.
- `conda run -n pyvalue-next pyvalue db migrate`: create `data/pyvalue.db`, or bring it up to the latest schema. Re-run the install command above first if the `pyvalue` command is missing.
- `conda run -n pyvalue-next pyvalue universe load`: fill `company`, `instrument`, `fund` and `holding` from the pinned SEC filings of VTI and VXUS. The first run downloads them into `data/sec/` and needs the `[sec] user_agent` line in `private/config.toml`; it also downloads Vanguard's own holdings files into `data/vanguard/`, which needs no setting. Later runs download nothing. Running it again adds nothing: a fund's holding lines are replaced by the same lines. The last line of output, "Instruments no fund holds", is 0 on a rebuilt database; on one loaded from other funds before, it counts the securities that are left over, and the database should be rebuilt. Vanguard's address shows only the latest month, so the saved file is the only copy of its month: do not delete it unless a newer one is wanted. The funds and their filings are pinned in `src/pyvalue/universe/funds.py`.
- `conda run -n pyvalue-next pyvalue symbols download`: **contacts EODHD. Claude Code may run it when the work needs it, without asking the author first** (see **Configuration & Data Notes**). It needs an active subscription and `[eodhd].api_key` in `private/config.toml`, and makes about 60 requests: the exchange list, then the symbol list of every code the exchange file gives a market. Each answer is kept under `data/eodhd/`; a saved list is replaced unless the new one is suspiciously short. It reports a code EODHD offers that the exchange file lacks, a code the file maps that EODHD no longer offers, and a code that is not in the subscription. It never touches the database (ADR 0024).
- `conda run -n pyvalue-next pyvalue symbols load`: add our exchanges and EODHD's exchange codes to `exchange`, `provider` and `provider_exchange` from the two committed files, and store the symbol lists saved under `data/eodhd/` in `provider_symbol` (ADR 0018, ADR 0024). It reads files only and never reaches the network, so it is safe to run at any time; before the first download it fills the three exchange tables and reports every code as without a saved list. A list is replaced as a whole. A list that cannot be stored is reported with the reason and leaves the stored rows as they were. Running it again changes nothing.
- **When the symbols load reports a venue label the exchange file does not have**, add a row for it to `src/pyvalue/providers/eodhd_exchange.csv` (code, label, market) and run the load again; no request is needed, because the list is already saved. Give the label the exchange's operating market code (ADR 0001), or leave the market empty to keep lines with that label out on purpose, as the US over-the-counter labels are, and as the label `US` is, which EODHD gives a line whose venue it does not state (ADR 0027). A new exchange also needs a row in `src/pyvalue/listings/reference/exchange.csv`.
- **To take an exchange or a provider code out of the two files**, rebuild the database afterwards (see **Rebuilding the database** below). The symbols load deletes nothing and refuses a database that holds a row the files no longer have. Never change a provider's code in place in the database: the stored list would follow it.
- `conda run -n pyvalue-next pyvalue listings fill`: give every security that has no listing the provider's line in its home market (ADR 0019, ADR 0026). It reads the database and the decisions file only and never reaches the network, so it is safe to run at any time. Each security gets one outcome, which the command counts: filled by the rule, filled by a decision, decided to have no listing, not held, market not served, waiting for a symbol list, or on the report for the agent. The report is `data/listings/cases_for_agent.csv`, one row per security and line it could be, with the reason. A run never changes a listing, and running it again changes nothing. Before the first download it fills nothing: every security in a served market waits.
- **A security waits when an exchange code of its home country has no stored symbol list** (ADR 0026). The command names the codes. Load the missing list, or, when EODHD does not offer the code at all, take the code out of `src/pyvalue/providers/eodhd_exchange.csv` and rebuild; the market is then "not served". One missing list holds back its whole country: Korea, mainland China, Taiwan and Canada have two or three codes each.
- **To decide a security on the listing report**, add a row to `src/pyvalue/listings/decisions/listing.csv` (ISIN, `listing` or `none`, provider, exchange code and symbol for `listing`, company name, date, who decided, evidence) and run `pyvalue listings fill` again. Take the provider, the exchange code and the symbol from the report's row, exactly as written. A decision may only name a line in a home market of the security, or, for a receipt read as its ordinary share, a line that carries the share's ISIN: a company is never analysed on a stand-in line. Never write or change a listing in the database by hand: a rebuild would lose it.
- **The agent's pass over the listing report** (ADR 0027) is done in a session, when the author asks for it; there is no command for it. Take one reason at a time. Show the author the rows you propose, each with its evidence, and the securities you leave undecided, with why; commit a batch only after the author approves it. Use `agent` as `decided_by` for such a row, and `author` for a decision the author made of their own.
  - **Evidence.** A `listing` row needs a source outside the fund and outside EODHD's list that ties the ISIN to that symbol on that exchange: OpenFIGI, or the exchange's own website. Where the line already carries the ISIN and only the ticker differs, it needs a source that explains the other ticker. A `none` row needs a lasting reason, such as a share that trades only in a market EODHD does not serve; "not found today" is not one, and EODHD's delisted list is not evidence.
  - **Three guards the fill does not check for a decided line.** The line's currency is the currency the fund holds the security in; this one does not hold for a receipt read as its ordinary share, whose holding line shows the receipt's currency. The line does not carry the ISIN of another security of the universe, and no other row names it. A receipt read as its ordinary share never gets the receipt's own line.
  - **Leave a security undecided** when no line on the report is right or the evidence does not settle it. A company that left the exchange or changed its ISIN since the filing gets no row: it stays on the report until newer filings are pinned. Never name a line the report does not show, and make no request to EODHD for the pass.
- **To correct a listing that exists**, add or change its decision and rebuild the database. A run never changes a listing, so the fill stops when a stored listing is not what the decisions file says.
- `conda run --no-capture-output -n pyvalue-next pyvalue fundamentals download`: **contacts EODHD. Claude Code may run it when the work needs it, without asking the author first.** It needs an active subscription and `[eodhd].api_key` in `private/config.toml`. It requests the fundamentals of every provider line that a listing is on and that has no saved payload, and keeps each answer as `data/eodhd/fundamentals/<CODE>/<SYMBOL>.json.gz` (ADR 0028). One request costs 10 of the daily allowance, so all 8,309 listings cost 83,090 of 100,000. Before every batch of 500 it asks the account what is left, which is free, and it stops 5,000 short of the daily limit: the account's extra reserve is never touched, and a later run takes the rest. It reads the database and never writes it. A symbol EODHD has nothing for, an answer that is not a payload for the symbol and a request that failed are counted and written to `data/fundamentals/not_downloaded.csv`; the run stops, with status 1, after a batch in which more than half the requests failed. `--no-capture-output` is what shows the progress bar: plain `conda run` holds the output back until the end.
- **To fetch a payload again**, set its file aside and run `pyvalue fundamentals download`; to fetch every payload again, set the folder `data/eodhd/fundamentals/` aside. The command never overwrites a saved payload, and there is no refresh option. Set aside, do not delete: outside a subscription a saved payload is the only copy, and the old folder is what a refresh is compared with. A full download needs most of a day's allowance. Run `pyvalue fundamentals load` after the download, not while the folder is set aside: the load refuses a folder with fewer than half of the payloads, so it never empties the tables by accident.
- `conda run --no-capture-output -n pyvalue-next pyvalue fundamentals load`: read the fiscal years of the saved payloads into the statement tables `reporting_period`, `income_statement`, `cash_flow_statement` and `balance_sheet` (ADR 0029). It reads files and the database only and never reaches the network, so it is safe to run at any time; it takes about a minute. The tables are replaced as a whole, and running it again gives the same rows and the same report. Every row is checked (ADR 0030): a row that cannot be used is left out, an impossible figure is left empty, and an odd one is stored with a warning; everything found is written to `data/fundamentals/findings.csv`, one row per finding, named by ISIN and the provider's line. Amounts are whole units of the currency the company reported in; nothing is converted. An income or cash-flow row is stored only for a fiscal year whose length is proven, so a company's oldest year in its payload has a balance sheet only. It refuses to run, and changes nothing, when fewer than half of the listings have a saved payload. There is no corrections file yet: a finding is read, not fixed.
- **Rebuilding the database**: set `data/pyvalue.db` aside, then run `pyvalue db migrate`, `pyvalue universe load`, `pyvalue symbols load`, `pyvalue listings fill` and `pyvalue fundamentals load`, in that order. Nothing is downloaded: the filings, the lists and the fundamentals payloads are saved files. Every message that asks for a rebuild gives these steps. The statements are loaded last because a rebuilt database gives the companies new ids (ADR 0029).
- **When the load reports that two funds file different legal-entity identifiers for a security**, add a row to `src/pyvalue/universe/decisions/lei.csv` (ISIN, identifier, company name, date, evidence) and run the load again. Never change the identifier in the database by hand: a rebuild would lose it. Decide every security of the company that carries the identifier that lost, not only the one that was reported (ADR 0010).
- **When a fund files a placeholder instead of a company name** (such as "New Issuer: BB Company ID:68830100"), add a row to `src/pyvalue/universe/decisions/name.csv` (ISIN, name, date, where the name comes from) and run the load again. Use the name another fund files for the same ISIN, exactly as filed; where no fund files one, use the company's name from a public source, written like the names around it. Never rename a company in the database by hand. The file is not for restyling names or for following a rename (ADR 0012).
- **When a fund holds a depositary receipt and the company's ordinary share is listed**, add a row to `src/pyvalue/universe/decisions/ordinary_share.csv` (the receipt's ISIN, the ordinary share's ISIN, company name, date, evidence) and rebuild the database as for an exclusion. The load then reads the receipt's lines as lines of the ordinary share, so the company stays and the right share is analysed. Confirm both things in a source outside the filings before adding the row: that the first security is a receipt, and that the second is the same company's ordinary share. An exchange's own list of securities or OpenFIGI will do; a company name alone will not. Key any identifier or name decision for the company by the ordinary share (ADR 0015).
- **To keep a security out of the universe**, add a row to `src/pyvalue/universe/decisions/excluded.csv` (ISIN, company name, date, why) and rebuild the database (see **Rebuilding the database** above). The load never deletes, so it refuses a database that still holds an excluded security. Never delete a row by hand: the next load would add it again. Remove any row for the same ISIN from `lei.csv` and `name.csv`. Excluding a security is the author's decision, not something to do on a finding alone (ADR 0013).
- **Funds and property trusts are not part of the universe** (ADR 0023). A security goes out when OpenFIGI gives it the type `REIT`, when it is a stapled security built around a property trust, or when it is a fund in law, such as an infrastructure fund. The test is the legal form, not the business: a trust that owns phone masts is out, a company that owns shopping centres is in. A mixed label is checked against the company's own filings before a row is added. When newer filings are pinned, classify the securities that are new in the same way and add their rows to `excluded.csv` before the rebuild.
- **A decision chooses only among the identifiers the funds filed** (ADR 0011). An outside register is evidence for the choice, never the source of the identifier. Do not replace an identifier the funds agree on, even when a register shows it as retired, and do not check the stored identifiers against a register as a routine: the identifier only has to join the funds' lines, and nothing after the load reads it.
- **Dependency versions are locked.** `pyproject.toml` declares the version ranges pyvalue is compatible with; `uv.lock` records the exact version and hashes of every direct and transitive dependency the project is tested with. Never pin with `==` in `pyproject.toml`, and never edit `uv.lock` by hand.
  - After changing any dependency in `pyproject.toml`, run `conda run -n pyvalue-next uv lock` and commit `uv.lock` in the same change.
  - `conda run -n pyvalue-next uv lock --upgrade` (or `--upgrade-package <name>`) moves to newer versions. An upgrade is a deliberate change with its own commit: re-run the install command above, then the full quality gate, before committing.
- **Packaging is a first-class concern.** `pyproject.toml` must always be sufficient on its own to: (a) build a distributable package, (b) carry the project version, (c) install pyvalue for end users (`pip install .`), and (d) install it in development mode for contributors (`pip install -e .[dev]`). Do not introduce setup steps that live outside the project metadata file. `uv.lock` is derived from `pyproject.toml` and adds reproducibility on top of it; a plain `pip install` must keep working without the lock.

## Coding Style & Naming Conventions

### Naming
- Use 4-space indentation and standard Python conventions: `snake_case` for modules/functions, `CapWords` for classes, and `UPPER_SNAKE_CASE` for constants.

### Comments & Documentation in Code
- **Heavily commented — explain the why, not the what.** New code must include comments around non-obvious logic, business rules, sign/unit conventions, currency invariants, and design decisions. Aim at the *motivation*; the line-by-line behaviour should already be clear from the code.
- **Module headers.** Every new module/file must open with a triple-quoted docstring (`""" ... """`) that briefly describes the module's purpose and names the author.
- **Type annotations everywhere.** Every function signature, method, attribute, and module-level constant carries type hints. Full coverage is the standard, and `mypy src/ tests/` enforces it.
- **Public docstrings.** Every public function, method, and class must have a docstring covering its purpose, inputs, outputs, and any non-obvious behaviour.

### Formatting
- Format with `ruff format`; import order is enforced by `ruff` — do not reorder manually.
- Keep diffs consistent with surrounding code.

## Testing Guidelines

### General
- **No change lands without tests.** New functionality → new unit tests. Changed behaviour → updated tests. Bug fix → a regression test that *fails on the buggy code and passes on the fix*.
- The test suite covers both **unit tests** (pure functions, isolated logic) and **regression tests** (one per fixed bug).
- Run the full suite before every commit: `conda run -n pyvalue-next pytest`. A green suite is a prerequisite for pushing, opening a PR, or declaring a task done.
- The canonical test directory layout is documented in `docs/architecture.md` once that file exists. If the layout needs to change, confirm with the author and update `docs/architecture.md` in the same commit.

### Test Structure (Python / pytest)
- Framework: `pytest` (configured in `pyproject.toml`).
- Mirror the source tree under `tests/` with `tests/unit/`, `tests/regression/`, and `tests/integration/` subdirectories. File naming `test_*.py`, function naming `test_*`.
- Tag slow, integration, and regression tests with `pytest.mark` so they can be run selectively during development and run fully in CI. The markers are registered in `pyproject.toml`, and an unregistered marker is an error.
- Prefer fixtures in `tests/conftest.py` over setup/teardown boilerplate — keep tests readable.
- Measure coverage with `pytest-cov`; aim for high coverage on business logic (metrics, normalisation, screening, currency handling, data-quality checks).

### Mandatory Test Categories
Pyvalue computes numerical metrics over a screened universe; the same disciplines a trading system needs apply here:
- **Unit tests for every pure function** — metric calculations, normalisation routines, currency/FX/sign/unit guards, screen evaluators, data-quality checks.
- **Property-based tests** (e.g. via [Hypothesis](https://hypothesis.readthedocs.io/)) for numerical and invariant-bearing code: metric formulas, FX/currency invariants, normalisation idempotence, monotonicity properties of screens.
- **Reproducibility tests** — a fixed input universe plus fixed metric inputs must produce a bit-identical screen output (CSV byte-equal) across runs.
- **Integration tests against a small, checked-in fixture dataset** — exercise the pipeline end-to-end without hitting external APIs.

## Quality Gate

Every commit must pass all five quality-gate checks with **zero errors** before being pushed, opening a PR, or marking work done. Run them in the `pyvalue-next` conda env:

| Tool | Command |
|---|---|
| Format | `conda run -n pyvalue-next ruff format .` |
| Lint | `conda run -n pyvalue-next ruff check .` |
| Type check | `conda run -n pyvalue-next mypy src/ tests/` |
| Tests | `conda run -n pyvalue-next pytest` |
| Lock | `conda run -n pyvalue-next uv lock --check` |

### Universal rule
The whole codebase must be clean — "the file I touched is clean" is not enough. Pre-existing errors are not an excuse to introduce new ones; if you find them, fix them.

### mypy (non-negotiable)
- `mypy src/ tests/` must report zero errors at the end of every change. It runs in `strict` mode.
- Fix mypy errors by correcting the design — **no `# type: ignore`, no `Any` / `object` widening to silence the checker, no removing or loosening annotations**. If mypy is unhappy, the type model is telling you something — fix it.

### ruff
- All code must pass `ruff format` and `ruff check` with no suppressions, except where a suppression has an explicit, documented reason in the surrounding comment.
- Import order is enforced by ruff — do not reorder manually.
- The lint rule set is pinned in `pyproject.toml`. Widening or narrowing it is a deliberate decision, not a side effect of a tool upgrade.

### Lock
- `uv lock --check` fails when `uv.lock` no longer matches the requirements in `pyproject.toml`. Fix it by running `conda run -n pyvalue-next uv lock` and committing the regenerated lock with the change that caused it.

## Commit & Pull Request Guidelines
- Commit messages are concise, imperative, and often scoped (e.g., `universe: add holdings import`, `docs: add ADR 0001`). Keep subjects short and omit trailing periods.
- PRs should include a clear description and relevant command output (e.g., `pytest`).
- If you touch schema or persistence, call out the migration and any impact on the local database.

## Documentation
- **`README.md` stays short.** The repo-root `README.md` covers project purpose, installation instructions, and the two or three most common usage examples — nothing else. Promote longer material to `docs/` rather than letting `README.md` grow. Update `README.md` when the project's purpose, install steps, or headline examples change.
- **Substantive documentation lives under `docs/`.** Keep the tree organised; create a subdirectory whenever a topic area grows beyond two or three files.
- **Architecture: `docs/architecture.md`.** High-level design, component map, and the canonical test layout.
- **Architecture decisions: `docs/adr/`.** One decision per file. An accepted record is not edited in substance; a new record supersedes it.
- **Database documentation: `docs/database/`.** One Markdown file per table, showing all fields, types, constraints (PK, FK, UNIQUE, CHECK, NOT NULL), indexes, and any views that reference the table.
- **Keep documentation in sync with the code.** When you change behaviour, update the relevant doc file in the same commit (and the per-table file under `docs/database/` for any schema change). For each change, explicitly decide whether docs need an update and locate the canonical file in `docs/` to edit.

## Configuration & Data Notes
- Store credentials in `private/config.toml` (for example `[eodhd].api_key`); never commit secrets.
- The EODHD key is `[eodhd].api_key` in the same file. EODHD takes it as part of the address, so every request goes through `pyvalue.http` with the key as a secret part: it is sent only to `eodhd.com`, and never printed, logged, put into an error message, a file name or a saved file.
- **Claude Code may make requests to EODHD, and the author's permission is not required** (decided by the author on 2026-11-27; until then no request was made unless the author asked for it, ADR 0024). That covers `pyvalue symbols download`, `pyvalue fundamentals download` and any other request the work needs. The rules for the key above stand. A request works only while a subscription is active and counts against its daily limit, so make the requests the work needs and say in the report which were made.
- **EODHD's account answer (`/api/user`) names the account holder.** Read the daily limit, the used count and its date from it and nothing else; never print it, save it or put a value of it into a message. The account also has an extra reserve of requests, which EODHD draws on once a day's allowance is used up: nothing may be built that spends it.
- The SEC contact string is `[sec].user_agent` in the same file. It names a person: send it only as the `User-Agent` header to `www.sec.gov` (never to a fund sponsor's site), and never print it, log it or put it in an error message.
- `data/` holds local artifacts (the database, the downloaded filings under `data/sec/`, Vanguard's holdings files under `data/vanguard/`, the provider's lists under `data/eodhd/`, its fundamentals payloads under `data/eodhd/fundamentals/`, the load output under `data/universe/`, the listing report under `data/listings/`, the fundamentals download's report and the statements load's findings under `data/fundamentals/`, vendor payloads, logs, screen outputs) and is never committed.
- If you import a new third-party package, add it to `pyproject.toml` under `[project].dependencies` and re-lock with `uv lock` in the same commit.
