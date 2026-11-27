# ADR 0030: The statements load checks every row and reports what it finds

- Status: Accepted
- Date: 2026-11-27
- Settles: the second half of the first point ADR 0028 left open, what is checked when payloads are read into tables. It goes with ADR 0029, which decides the tables.

## Decision

`pyvalue fundamentals load` (ADR 0029) checks what it reads before it stores it. Every problem it meets is a **finding**, and every finding is written to a report. The checks are plain code: the same payloads give the same report, byte for byte. No AI takes part in the load.

### Three outcomes

| Outcome | In the report | What the load does | When |
|---|---|---|---|
| Left out | `left_out` | The row, or the whole period, is not stored | The row cannot be used at all, or using it would be wrong in a way no reader could see |
| Figure left empty | `figure_left_empty` | The row is stored with that one figure empty | One figure is impossible and the rest of the row is sound |
| Warning | `warning` | The row is stored as it is | Something is odd, and whether the row is wrong is not known |

A missing value is safer than a wrong one. So a check leaves a row out or empties a figure only when its verdict is certain. A check whose verdict is not yet known to be reliable starts as a warning and can be made stricter by a later record.

### The checks

The name in the first column is what the report shows.

**Left out**

| Check | Fires when | What is left out |
|---|---|---|
| `payload_not_readable` | A saved payload is not in the shape the reader expects | That payload. A company with no other payload gets no rows |
| `off_chain` | A yearly date in the window is not one of the company's fiscal years (ADR 0029) | The rows of that date |
| `length_not_proven` | A fiscal year has no year 12 months before it, so the length of its income and cash-flow rows is not known | Its income and cash-flow rows. Its balance sheet is stored |
| `currencies_differ` | The statements of one period carry different currency labels | The period: all its rows |
| `no_currency` | No currency can be settled for a period by the rule of ADR 0029 | The period: all its rows |
| `scale_outlier` | Total assets, or revenue, is at least 50 times larger or smaller than both the year before and the year after, while those two are within 50 times of each other | That balance sheet, or that income statement |
| `no_figure` | A row has no figure, or none is left after the checks below | The row |

**Figure left empty**

| Check | Fires when | Figure |
|---|---|---|
| `impossible_negative` | A figure that cannot be negative is negative, or total assets or the share count is zero or less | That figure. The list is the schema's own list of constraints (ADR 0029) |
| `absurd_value` | A value is 10^17 or more, either way | That figure |
| `placeholder_capex` | Capital expenditure is zero in a cash-flow row that has no operating cash flow | Capital expenditure |
| `zero_interest_with_debt` | Interest expense is zero and the balance sheet of the same date shows debt | Interest expense |

**Warning**

| Check | Fires when |
|---|---|
| `gross_profit_mismatch` | Revenue minus cost of revenue differs from gross profit by more than 1% of revenue |
| `balance_sides_differ` | Total assets differ by more than 1% from the provider's own total of liabilities and equity |
| `scale_step` | Total assets, or revenue, is at least 50 times larger or smaller than the year before, and the check `scale_outlier` did not fire |
| `currency_changed` | A fiscal year is in another currency than the year before it |
| `sub_unit_label` | A row is labelled with a sub-unit such as `GBX` and was read as its currency with the amount unchanged |
| `stale_payload` | The company's latest fiscal year ended more than 18 months before the latest fiscal year of any company in the load |
| `other_isin` | The payload names another ISIN than the security it was downloaded for |
| `payloads_disagree` | A company has several payloads, and another payload gives revenue, net income or total assets of the latest shared fiscal year more than 1% away from the one that is read |
| `no_payload` | A listing has no saved payload |
| `no_fiscal_year` | A payload has no yearly row |

### Rules for the checks

| Rule | What it means |
|---|---|
| A scale check compares like with like | It compares three years only when all three are in the same currency and both neighbours are at least 1,000,000. Tiny figures of companies without revenue jump for real |
| A scale check reads what the provider reported | It runs before any figure is emptied, so one bad figure does not hide another |
| The order is fixed | The chain of fiscal years first, then a period's currency, then the length of its income and cash-flow rows, then the scale check, then the figures, then the warnings on what is stored |
| No clock | No check reads today's date. `stale_payload` measures against the data itself |
| One finding per fact | A row left out by one check is not reported again by another |
| Each check is one small function | With a test that it fires and a test that it does not |

### The report

`data/fundamentals/findings.csv`, rewritten by every load.

| Column | Holds |
|---|---|
| `isin` | The security whose payload the finding is about |
| `company` | The company's name |
| `provider_exchange_code`, `provider_symbol` | The provider's line for that security |
| `statement` | `income_statement`, `cash_flow_statement` or `balance_sheet`. Empty when the finding is about a whole period, payload or company |
| `period_end` | The period. Empty when the finding is about a whole payload or company |
| `check` | The name of the check |
| `outcome` | `left_out`, `figure_left_empty` or `warning` |
| `figure` | The column concerned. Empty when the finding is not about one figure |
| `detail` | The values that made the check fire, in words |

The rows are sorted by ISIN, statement, period end, check and figure. The report identifies a company by ISIN and by the provider's line, never by a company id: ids change when the database is rebuilt.

The command prints how many findings each check made.

## Why

- **The provider's data has defects that pass silently.** A total in thousands between two years in units, a pound amount labelled as pence, a zero where nothing was reported. The legacy project found most of them only when a wrong company passed a screen.
- **A screen is safest when a bad input gives no result.** A company that gets no result is looked at. One that passes on a wrong figure is bought.
- **Emptying one figure keeps the rest of the row.** A negative depreciation figure says nothing about that year's operating cash flow.
- **The report is the work list.** An agent or a person takes rows from it, reads the company's own filing and proposes a correction. How a correction comes back into the tables is a later decision, taken when the first report has been read.
- **The same pattern as the listings.** The listing fill writes what it cannot settle to a report, and decisions come back through a committed file (ADR 0026, ADR 0027).

## Evidence

Measured on 2026-11-27 on the 8,309 saved payloads, with a prototype of the rules. The counts of the first real load are recorded in `docs/statements.md`.

| Check | Measured |
|---|---|
| `off_chain` | 96 payloads have such a row in the window |
| `length_not_proven` | The window reaches the payload's oldest row in about 1,700 payloads, and each then has one such year. Where that row can be compared, its revenue is under 60% of the next year's in 22% of cases, against 6% for other pairs of years |
| `currencies_differ` | 89 fiscal years in 47 payloads |
| `no_currency` | About 250 rows in 41 payloads. 7,600 rows without a label take the currency of the company's other years |
| `scale_outlier` | 23 balance sheets in 21 payloads and 24 income statements in 23. KBC Ancora's total assets alternate between 3.1 billion and 3.1 million from 2016 to 2020 |
| `no_figure` | 27 rows |
| `impossible_negative` | About 4,400 figures on yearly rows since 2015: short-term investments 2,745, short-term debt 771, cost of revenue 239, depreciation about 170, non-current liabilities 155, total liabilities 110, cash 109, cash and short-term investments 78. Capital expenditure, dividends and interest expense are never negative on a yearly row |
| `absurd_value` | 3 rows of one payload carry 10^18 |
| `placeholder_capex` | 86 rows in 66 payloads |
| `zero_interest_with_debt` | 2,985 yearly rows since 2015 |
| `gross_profit_mismatch` | About 3,100 rows in 1,365 payloads |
| `balance_sides_differ` | 787 rows in 379 payloads |
| `scale_step` | 81 income statements and 63 balance sheets |
| `currency_changed` | About 150 companies |
| `sub_unit_label` | 122 rows in 15 payloads inside the window. In all 33 rows that could be compared, the amount is at pound or rand scale |
| `stale_payload` | About 60 companies |
| `other_isin` | 11 payloads |
| `payloads_disagree` | 15 of the 98 companies with several payloads |
| `no_fiscal_year` | 13 payloads |
| `no_payload` | None: every listing has a saved payload |

Total assets equal the provider's own total of liabilities and equity on 99% of the yearly rows that have both. Total liabilities plus equity equal total assets on only 79%, because minority interest is often not broken out. So `balance_sides_differ` compares with the provider's total, which is read for this check and not stored.

## Consequences

- **A row in the tables has passed every check that leaves out or empties.** A reader of the tables does not need the report to be safe.
- **The warnings are not acted on by any code.** They are for the pass over the report.
- **The report is long.** About 6,000 warnings and several thousand emptied figures. It is meant to be worked through by check and by company, starting with the companies that matter to a screen.
- **A check can be wrong.** A real jump after a reverse takeover would be left out by `scale_outlier` if the company shrank back the year after. Until corrections exist, such a row stays out.
- **These checks find figures that contradict each other or cannot exist.** A figure that is wrong but consistent with the rest passes all of them. Only a comparison with the company's own filing finds it.
- **The schema's constraints and the list of figures that cannot be negative are one list,** held together by a test. A row the schema refused would otherwise stop the whole load.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Store everything and flag bad rows | Every reader would have to know the flags. A metric that forgot one would use a bad row |
| Leave out the whole row for any bad figure | One negative depreciation figure would cost the year's cash-flow row |
| Leave out a balance sheet whose two sides differ | It fires on 787 rows, and how often the row is really wrong is not known yet |
| Read a sub-unit label as a real sub-unit and divide by 100 | Measured: the amounts are at pound and rand scale. The legacy project divides, which makes these rows 100 times too small |
| Keep a zero interest expense as zero | With debt on the balance sheet, a zero is more likely a missing figure than free borrowing, and a metric would read it as unlimited interest cover |
| A findings table in the database | Nothing reads findings but a person or an agent. A file is enough, as for the listing report |
| A check for today's date | The report would change from one day to the next without any change in the data |
| An AI review as part of the load | It could not be reproduced, and it could not be tested |

## Not decided here

- **Corrections:** the file an approved correction is kept in, and how the load applies it.
- **The agent's pass over the report:** its evidence standard and its order.
- **Checks of interim rows,** which come with the interim rows.
- **Whether a warning becomes stricter,** which the first report will show.
