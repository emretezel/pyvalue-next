# `company`

One row per legal entity that issues securities. Decided in ADR 0001. Created by migration `0001_reference_schema`.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `company_id` | INTEGER | PK | yes | Assigned by the database, never reused | pyvalue's own id for the company |
| `name` | TEXT | | yes | Not empty, no leading or trailing spaces | The company's name |
| `lei` | TEXT | UNIQUE | no | 20 upper-case letters or digits, the last two being digits | The company's ISO 17442 legal-entity identifier, where it has one |

## Example rows

| `company_id` | `name` | `lei` |
|---|---|---|
| 1 | Berkshire Hathaway Inc | `5493000C01ZX7D35SD85` |
| 2 | Alphabet Inc | `5493006MHB84DD0ZWV18` |
| 3 | SAP SE | `529900D6BF99LW9R2E68` |
| 4 | Toyota Motor Corp | `5493006W3QUS5LMH6R84` |

## Notes

- **`company_id` is a surrogate key** because no identifier covers every company.
- **`lei` is optional** because many companies have none. Any number of companies may have an empty `lei`; two companies can never share one.
- **`name` is not unique**: different companies can share a name.
- **Where `name` comes from**: the spelling of the first fund that names the company (ADR 0006), or, when that fund files a vendor placeholder, the name a decision gives (ADR 0012).
- **How a company is matched when holdings are loaded** is set out in ADR 0006: by `lei` when the holdings line has one, otherwise by exact name.

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| Referenced by | [`instrument`](instrument.md) | `instrument.company_id` | Refused while instruments remain |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `company (company_id)` | The primary key | Find a company by id |
| `company (lei)` | The `UNIQUE` constraint | Find a company by its legal-entity identifier when holdings are loaded |

There is no index on `name`. The load of ADR 0006 looks companies up by name; an index is added with that code if the lookup needs one.

## Views

None.
