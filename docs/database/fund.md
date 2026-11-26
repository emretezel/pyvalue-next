# `fund`

One row per fund whose holdings are loaded. Decided in ADR 0017. Created by migration `0002_fund_and_holding`.

The funds themselves are chosen in ADR 0016. The row says which of a fund's documents the rows of [`holding`](holding.md) come from.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `fund_code` | TEXT | PK | yes | Upper-case letters and digits only | pyvalue's own code for the fund: its ticker |
| `name` | TEXT | | yes | Not empty, no leading or trailing spaces | The fund's name |
| `scope` | TEXT | | yes | `US` or `NON_US` | Whether the fund is expected to hold US-coded ISINs |
| `sec_series_id` | TEXT | UNIQUE | yes | `S` followed by nine digits | The SEC's id for the fund |
| `sec_filing_number` | TEXT | UNIQUE | yes | Ten digits, two digits, six digits, joined by hyphens | The filing whose lines are in `holding` now |
| `holdings_date` | TEXT | | yes | A date written as `YYYY-MM-DD` | The day that filing states the holdings for |
| `sponsor_file_date` | TEXT | | no | A date written as `YYYY-MM-DD` | The day the sponsor's own file states the holdings for. Empty for a sponsor that has no such file |

## Example rows

| `fund_code` | `name` | `scope` | `sec_series_id` | `sec_filing_number` | `holdings_date` | `sponsor_file_date` |
|---|---|---|---|---|---|---|
| `VTI` | Vanguard Total Stock Market Index Fund | `US` | `S000002848` | `0000036405-26-000480` | `2026-06-30` | `2026-10-31` |
| `VXUS` | Vanguard Total International Stock Index Fund | `NON_US` | `S000002932` | `0000736054-26-000275` | `2026-07-31` | `2026-10-31` |

## Notes

- **`fund_code` is the primary key.** pyvalue assigns it, so it is stable and meaningful and no numeric id is needed.
- **One filing per fund.** The table says which filing is loaded now, not which were loaded before.
- **A fund keeps its row from load to load.** When a newer filing is loaded the row is updated in place; its holding lines are replaced.
- **`scope` is read by the listing rule** (ADR 0019) to find depositary receipts: a US-coded ISIN held by a `NON_US` fund.

## Relationships

| Direction | Table | Through | On delete | On a changed `fund_code` |
|---|---|---|---|---|
| Referenced by | [`holding`](holding.md) | `holding.fund_code` | Refused while the fund has holding lines | The lines follow |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `fund (fund_code)` | The primary key | Find a fund by its code |
| `fund (sec_series_id)` | The `UNIQUE` constraint | Refuse a second fund for one SEC series |
| `fund (sec_filing_number)` | The `UNIQUE` constraint | Refuse one filing loaded as two funds |

## Views

None.
