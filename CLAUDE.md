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
  - `universe/`: the universe load. Downloads the three pinned SEC holdings filings, reads them, and fills `company` and `instrument` by the rules of ADR 0006 and ADR 0009.
  - `cli/`: the `pyvalue` command. Thin commands that call the components.
  - `config.py`: reads `private/config.toml`. Never puts a value from that file into a message.
  - `errors.py`: `PyvalueError`, the base of every error a person can fix. The command line prints such an error as one line.
- `tests/`: pytest suite, mirroring the source tree under `tests/unit/`, `tests/regression/`, and `tests/integration/`. Shared fixtures are in `tests/conftest.py`; checked-in sample data is under `tests/fixtures/`.
- `docs/`: substantive documentation (see the **Documentation** section); `docs/architecture.md` is the design, `docs/adr/` holds the architecture decision records, and `docs/database/` has one file per table.
- `data/`: local artifacts such as the database (gitignored).
- `private/`: local config and API keys (`private/config.toml`, gitignored).

## Build, Test, and Development Commands
- Use the `pyvalue-next` conda environment (Python 3.14) for all project commands. Never install this package into the legacy project's `pyvalue` environment.
- `conda run -n pyvalue-next sh -c 'UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv sync --locked --extra dev'`: install the editable package and its development tools at the exact versions in `uv.lock` (Python >=3.14). `UV_PROJECT_ENVIRONMENT` points uv at the conda environment; without it uv creates its own `.venv`. The sync is exact: it also removes packages that are not in the lock, and it fails if `uv.lock` is out of date with `pyproject.toml`.
- `conda run -n pyvalue-next pytest`: run the test suite.
- `conda run -n pyvalue-next pyvalue db migrate`: create `data/pyvalue.db`, or bring it up to the latest schema. Re-run the install command above first if the `pyvalue` command is missing.
- `conda run -n pyvalue-next pyvalue universe load`: fill `company` and `instrument` from the three pinned SEC filings. The first run downloads them into `data/sec/` and needs the `[sec] user_agent` line in `private/config.toml`; later runs need neither. Running it again adds nothing. The filings are pinned in `src/pyvalue/universe/filings.py`.
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
- The SEC contact string is `[sec].user_agent` in the same file. It names a person: send it only as the `User-Agent` header to `www.sec.gov`, and never print it, log it or put it in an error message.
- `data/` holds local artifacts (the database, the downloaded filings under `data/sec/`, the load output under `data/universe/`, vendor payloads, logs, screen outputs) and is never committed.
- If you import a new third-party package, add it to `pyproject.toml` under `[project].dependencies` and re-lock with `uv lock` in the same commit.
