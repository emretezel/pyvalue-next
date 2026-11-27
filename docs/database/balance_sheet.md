# `balance_sheet`

One row per company and date: a company's balance sheet. Decided in ADR 0029. Created by migration `0008_statements`. Filled by `pyvalue fundamentals load`, which replaces it as a whole on every run.

## Columns

Every figure is a whole number in the main unit of the period's currency, or empty when it is not known. The share count is a number of shares.

| Column | Type | Key | Required | From | Constraint | Meaning |
|---|---|---|---|---|---|---|
| `company_id` | INTEGER | PK, FK | yes | | With `period_end`, must be a row of `reporting_period` | The company |
| `period_end` | TEXT | PK, FK | yes | `date` | As above | The day of the snapshot |
| `total_assets` | INTEGER | | no | `totalAssets` | Above zero | Total assets |
| `total_liabilities` | INTEGER | | no | `totalLiab` | Not negative | Total liabilities |
| `equity` | INTEGER | | no | `totalStockholderEquity` | | Equity of the company's own shareholders. Can be negative |
| `minority_interest` | INTEGER | | no | `noncontrollingInterestInConsolidatedEntity` | | Equity that belongs to outside shareholders of subsidiaries |
| `cash` | INTEGER | | no | `cash` | Not negative | Cash |
| `short_term_investments` | INTEGER | | no | `shortTermInvestments` | Not negative | Short-term investments |
| `cash_and_short_term_investments` | INTEGER | | no | `cashAndShortTermInvestments` | Not negative | The provider's own total of the two |
| `short_term_debt` | INTEGER | | no | `shortTermDebt` | Not negative | Borrowings due within a year |
| `long_term_debt` | INTEGER | | no | `longTermDebt` | Not negative | Borrowings due later |
| `total_debt_stated` | INTEGER | | no | `shortLongTermDebtTotal` | Not negative | The provider's own total of debt. It is not the sum of the two columns before it |
| `lease_obligations` | INTEGER | | no | `capitalLeaseObligations` | Not negative | Lease liabilities |
| `current_assets` | INTEGER | | no | `totalCurrentAssets` | Not negative | Current assets |
| `current_liabilities` | INTEGER | | no | `totalCurrentLiabilities` | Not negative | Current liabilities |
| `noncurrent_liabilities` | INTEGER | | no | `nonCurrentLiabilitiesTotal` | Not negative | Liabilities due after a year |
| `shares_outstanding` | INTEGER | | no | `commonStockSharesOutstanding` | Above zero | The number of shares outstanding |

A row must hold at least one figure. The table is `STRICT`.

## Example row

Microsoft, `2026-06-30`, in millions (shares in millions of shares). Minority interest is empty:

| `total_assets` | `total_liabilities` | `equity` | `cash` | `short_term_investments` | `cash_and_short_term_investments` | `short_term_debt` | `long_term_debt` | `total_debt_stated` | `lease_obligations` | `current_assets` | `current_liabilities` | `noncurrent_liabilities` | `shares_outstanding` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 758,376 | 315,989 | 442,387 | 20,935 | 55,908 | 76,843 | 18,905 | 31,067 | 128,808 | 16,532 | 207,710 | 168,825 | 147,164 | 7,453 |

## Notes

- **A balance sheet is a snapshot, so it has no length.** It is stored for every fiscal year, also for one whose income statement is not, such as a company's oldest year (ADR 0029).
- **Debt is stored twice, as the provider states it.** Its two parts and its own total agree on about a third of the rows that have the total. A metric chooses.
- **The provider's total of liabilities and equity is not stored.** The load compares it with total assets and reports a difference (ADR 0030).

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| References | [`reporting_period`](reporting_period.md) | `company_id` and `period_end` together | A period with a balance sheet cannot be deleted |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `balance_sheet (company_id, period_end)` | The primary key | The balance sheets of one company, by date; the foreign-key check when a period is deleted |

## Normalisation

All four statement tables are in Boyce-Codd normal form: every figure is a fact about one company and one date, and for a flow, one length. The two totals stored beside their parts, `cash_and_short_term_investments` and `total_debt_stated`, are figures the provider reports on their own, not sums of the columns beside them (ADR 0029).

## Views

None.
