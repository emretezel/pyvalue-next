# `cash_flow_statement`

One row per company, period end and length: a company's cash-flow statement for one period. Decided in ADR 0029. Created by migration `0008_statements`. Filled by `pyvalue fundamentals load`, which replaces it as a whole on every run.

## Columns

Every figure is a whole number in the main unit of the period's currency, or empty when it is not known. An amount going out, such as capital expenditure, is written as a positive number.

| Column | Type | Key | Required | From | Constraint | Meaning |
|---|---|---|---|---|---|---|
| `company_id` | INTEGER | PK, FK | yes | | With `period_end`, must be a row of `reporting_period` | The company |
| `period_end` | TEXT | PK, FK | yes | `date` | As above | The last day of the period |
| `months` | INTEGER | PK | yes | | 3, 6, 9 or 12 | How many months the row covers. 12 is a fiscal year |
| `operating_cash_flow` | INTEGER | | no | `totalCashFromOperatingActivities` | | Cash from operations |
| `capital_expenditure` | INTEGER | | no | `capitalExpenditures` | Not negative | Cash paid for property, plant and equipment |
| `depreciation_amortization` | INTEGER | | no | `depreciation` | Not negative | Depreciation and amortisation added back |
| `dividends_paid` | INTEGER | | no | `dividendsPaid` | Not negative | Cash dividends paid |
| `net_share_sales` | INTEGER | | no | `salePurchaseOfStock` | | Shares sold minus shares bought back. Negative when the company bought back more than it sold |

A row must hold at least one figure. The table is `STRICT`.

## Example row

Microsoft, `2026-06-30`, 12 months, in millions:

| `operating_cash_flow` | `capital_expenditure` | `depreciation_amortization` | `dividends_paid` | `net_share_sales` |
|---|---|---|---|---|
| 182,935 | 115,948 | 38,534 | 26,445 | -22,271 |

## Notes

- **A row with `months` 12 is a proven fiscal year,** as for [`income_statement`](income_statement.md).
- **A zero capital expenditure in a row without operating cash flow is not stored.** It is a placeholder of the provider's, and the load reports it (ADR 0030).

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| References | [`reporting_period`](reporting_period.md) | `company_id` and `period_end` together | A period with statements cannot be deleted |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `cash_flow_statement (company_id, period_end, months)` | The primary key | The cash-flow statements of one company, by date; the foreign-key check when a period is deleted |

## Views

None.
