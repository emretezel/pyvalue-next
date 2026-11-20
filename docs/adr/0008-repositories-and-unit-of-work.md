# ADR 0008: Database access goes through repositories and a unit of work

- Status: Accepted
- Date: 2026-11-20

## Decision

All reading and writing of the database goes through the `pyvalue.db` package. Inside it, each table has one class that is responsible for it, and one object owns the transaction. The design pattern is Repository with Unit of Work.

| Part | What it is | What it is responsible for |
|---|---|---|
| Repository | One class per table, in `pyvalue.db`, named after the table: `CompanyRepository` for `company` | Every statement that reads or changes that table |
| Record | One frozen dataclass per table, in `pyvalue.db` | Carrying a row out of the database as typed, immutable values |
| Unit of work | One object a component obtains from `pyvalue.db` | The connection and the transaction: everything done inside it is committed together or rolled back together |
| Component | Any package outside `pyvalue.db` | The business rules. It reaches the database only through a unit of work and its repositories |

## Who may do what

| | Component | Unit of work | Repository | Migration file |
|---|---|---|---|---|
| Import `sqlite3`, hold a connection | No | Yes | Uses the unit of work's connection | Not applicable |
| Contain SQL that reads or changes rows | No | No | Yes, for its own table | No |
| Begin, commit or roll back | No | Yes | No | No |
| Create, alter or drop a table | No | No | No | Yes |
| Decide a business rule | Yes | No | No | No |

## Rules

| Rule | What it means |
|---|---|
| One home | Only `pyvalue.db` imports `sqlite3`, holds a connection or contains SQL. No other package builds a query, not even a `SELECT`. A test enforces the import rule. |
| One repository class per table | A table has exactly one repository. Every statement that inserts, updates or deletes its rows is a method of that class and of nothing else. |
| Reads go through repositories too | A query lives in the repository of the table whose rows it returns. A query that joins several tables lives in the repository of the table it is mainly about, or reads a view. |
| Methods say what, not how | A method is named after what the caller wants (`find_by_isin`, `add`, `set_lei`). It takes and returns ids and typed values. It never takes SQL, a `WHERE` fragment or a column name from its caller, and there is no general `execute` for other packages. |
| Typed, immutable records | A repository returns records or plain values, never a tuple, a `sqlite3.Row` or a cursor. |
| A unit of work owns the transaction | All repositories of one unit of work share its connection. A repository never begins, commits or rolls back, and a component never sees a connection. |
| Components decide, repositories store | A business rule lives in the component that owns it. A repository does what its method name says and nothing more. |
| Errors are pyvalue's own | A violated constraint reaches the component as a `pyvalue.db` error, never as a raw `sqlite3` one. |
| Tests use the same door | A test of a component works through a unit of work on a temporary migrated database. Only the tests of `pyvalue.db` itself use `sqlite3` directly. |

## What a component looks like

An illustration; the class and method names are settled when the first repository is written.

```python
with database.unit_of_work() as work:
    company = work.companies.find_by_lei(lei) or work.companies.add(name=name, lei=lei)
    work.instruments.add(company_id=company.company_id, isin=isin)
# Both rows are committed here, or neither is.
```

The component decides which company the line belongs to. `CompanyRepository` and `InstrumentRepository` each know how to store their own table. The unit of work makes the two writes one.

## Why this design

- **The author's rule**: all database access goes through the database package, and classes are responsible for updating the tables.
- **One class per table gives each table one owner.** The question "what can change this table?" has a one-class answer, which matters most when a constraint or a column changes.
- **The unit of work is what keeps the rule intact.** The steps already designed write two tables at once: the load writes a company and its instrument (ADR 0006), and filling a listing writes `listing` and `provider_listing` (ADR 0005). Without a shared transaction owner, the component would have to hold a connection to keep such a pair together, and database access would leak out of the package.
- **Business rules stay where they can be tested without a database.** A repository that only stores has nothing to decide, so the deciding code can be tested on its own.

## Evidence

Measured on 2026-11-20 in the legacy project, which used repositories without a unit of work.

- **The one-home rule held there.** 12 modules import `sqlite3`, all inside the persistence package.
- **Tables did not have one owner.** 33 repository classes served 21 tables.
- **Each repository opened its own connection.** Its base class connected from a database path, so two repositories could not share a transaction. For batches it offered a method that handed the caller a raw connection.
- **The package grew large.** 15 modules, 17,975 lines, of which 9,431 were migrations (ADR 0007).

## Consequences

- **More classes than a module of functions would need.** Seven tables mean seven repositories and seven record types, written as each is first needed.
- **A query across tables needs a decision about where it lives.** The rule above gives the default; a view is the other answer.
- **A component cannot run ad-hoc SQL.** A new question to the database means a new repository method, with a test.
- **Every database operation happens inside a unit of work**, a read included. A read-only one costs a transaction that is never written to.
- **Nothing implements this yet.** `pyvalue.db` has connections and migrations. The repositories, the records and the unit of work are written with the first component that needs them, the load of ADR 0006.
- **The migration run stays outside the pattern.** It is the one place that manages a connection and a transaction directly, as ADR 0007 describes.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A module of functions per table that take a connection | The caller has to hold the connection, so components would import or pass `sqlite3` objects. |
| Repositories that each open their own connection, as in legacy | Two tables cannot be written in one transaction. |
| One repository per group of related tables (company with its instruments and listings) | Fewer classes, but a table no longer has a single obvious owner, and the groups are a matter of opinion. |
| Active Record: each record saves itself | The record would carry a connection, and storing would be mixed with the values. |
| An object-relational mapper such as SQLAlchemy | A large dependency that hides the SQL the project wants to control and review. |

## Not decided here

- The names of the classes and methods, and whether records live in one module or beside their repositories.
- How `sqlite3` errors are translated into `pyvalue.db` errors.
- Whether a read-only unit of work is a separate, cheaper kind.
- Whether the second legacy rule, a pinned list of the few places where an ISIN or ticker is turned into an id, is adopted here.
