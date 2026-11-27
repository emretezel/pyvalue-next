# `income_statement`

One row per company, period end and length: a company's income statement for one period. Decided in ADR 0029. Created by migration `0008_statements`. Filled by `pyvalue fundamentals load`, which replaces it as a whole on every run.

## Columns

Every figure is a whole number in the main unit of the period's currency (dollars, not cents), or empty when it is not known. The figure comes from the field of EODHD's payload named under "From".

| Column | Type | Key | Required | From | Constraint | Meaning |
|---|---|---|---|---|---|---|
| `company_id` | INTEGER | PK, FK | yes | | With `period_end`, must be a row of `reporting_period` | The company |
| `period_end` | TEXT | PK, FK | yes | `date` | As above | The last day of the period |
| `months` | INTEGER | PK | yes | | 3, 6, 9 or 12 | How many months the row covers, back from `period_end`. 12 is a fiscal year |
| `revenue` | INTEGER | | no | `totalRevenue` | | Revenue |
| `cost_of_revenue` | INTEGER | | no | `costOfRevenue` | Not negative | Cost of the goods and services sold |
| `gross_profit` | INTEGER | | no | `grossProfit` | | Gross profit, as reported |
| `operating_income` | INTEGER | | no | `operatingIncome` | | Operating profit, as reported |
| `pretax_income` | INTEGER | | no | `incomeBeforeTax` | | Profit before income tax |
| `income_tax` | INTEGER | | no | `incomeTaxExpense`, else `taxProvision` | | Income tax charged to the period. Negative for a tax credit |
| `net_income` | INTEGER | | no | `netIncome` | | Net profit |
| `interest_expense` | INTEGER | | no | `interestExpense` | Not negative | Interest charged to the period |

A row must hold at least one figure. The table is `STRICT`: an amount with a fraction is refused.

## Example row

Microsoft, `2026-06-30`, 12 months, in millions here for width:

| `revenue` | `cost_of_revenue` | `gross_profit` | `operating_income` | `pretax_income` | `income_tax` | `net_income` | `interest_expense` |
|---|---|---|---|---|---|---|---|
| 331,839 | 106,374 | 225,465 | 155,237 | 165,934 | 32,185 | 133,749 | 3,051 |

## Notes

- **A row with `months` 12 is a proven fiscal year.** The load stores an income statement only for a year whose year before it was found, a year earlier. A company's oldest year in the payload has none (ADR 0029).
- **Only fiscal years are stored for now.** The lengths 3, 6 and 9 are allowed for the interim rows of the next step.
- **An empty cell is never a zero.** A figure the load empties is reported in `data/fundamentals/findings.csv` (ADR 0030), as a zero interest expense beside debt is.
- **Nothing is derived.** Gross profit is stored as reported, also where it is not revenue minus cost; the load reports the difference.

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| References | [`reporting_period`](reporting_period.md) | `company_id` and `period_end` together | A period with statements cannot be deleted |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `income_statement (company_id, period_end, months)` | The primary key | The income statements of one company, by date; the foreign-key check when a period is deleted |

## Views

None.
