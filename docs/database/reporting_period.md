# `reporting_period`

One row per company and date its financial statements are drawn up to, with the one currency they are in. Decided in ADR 0029. Created by migration `0008_statements`. Filled by `pyvalue fundamentals load`, which replaces it as a whole on every run.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `company_id` | INTEGER | PK, FK → `company.company_id` | yes | The company must exist | The company |
| `period_end` | TEXT | PK | yes | A date written as `YYYY-MM-DD` | The date the statements are drawn up to |
| `currency` | TEXT | | yes | Three upper-case letters | The ISO 4217 code of the currency the statements of that date are in. Never a sub-unit such as `GBX` |

The table is `STRICT`: a value of the wrong kind is refused, not converted.

## Example rows

| `company_id` | `period_end` | `currency` | Read as |
|---|---|---|---|
| 4120 (Microsoft) | `2026-06-30` | `USD` | Microsoft's fiscal year to June 2026 is reported in US dollars |
| 4120 (Microsoft) | `2025-06-30` | `USD` | The year before |
| 5210 (SK Hynix) | `2025-12-31` | `KRW` | SK Hynix reports in won |

The company ids are made up.

## Notes

- **A period has one currency, for all its statements.** It is stored here once, and the three statement tables reach it through their foreign key (ADR 0029). In the payloads, the statements of one year disagree on their currency for 89 fiscal years; such a year gets no row.
- **A row exists only with at least one statement.** The load writes a period together with its statements. The schema would accept a period without one.
- **Nothing is converted.** A company that changed its reporting currency has periods in two currencies.
- **The table is rebuilt by every load.** Company ids change when the database is rebuilt, and the load derives them afresh.

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| References | [`company`](company.md) | `company_id` | A company with periods cannot be deleted |
| Referenced by | [`income_statement`](income_statement.md), [`cash_flow_statement`](cash_flow_statement.md), [`balance_sheet`](balance_sheet.md) | `company_id` and `period_end` together | A period with statements cannot be deleted |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `reporting_period (company_id, period_end)` | The primary key | The periods of one company; the foreign-key checks of the three statement tables and of `company` |

## What the schema does not enforce

| Not enforced | Consequence |
|---|---|
| That a period has a statement | The load writes a period only with one |
| That `currency` exists | The schema checks the shape. The load takes the provider's code, a sub-unit turned into its currency |

## Views

None.
