# `exchange`

One row per market on which companies list. Decided in ADR 0001. Created by migration `0001_reference_schema`. The rows come from the committed file `src/pyvalue/listings/reference/exchange.csv` (ADR 0018), which lists the markets a provider serves.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `mic` | TEXT | PK | yes | Exactly four upper-case letters or digits | The market's ISO 10383 code |
| `name` | TEXT | | yes | Not empty, no leading or trailing spaces | The market's name |
| `country` | TEXT | | yes | Exactly two upper-case letters | The market's ISO 3166 country code |

## Example rows

| `mic` | `name` | `country` |
|---|---|---|
| `XNYS` | New York Stock Exchange | `US` |
| `XNAS` | Nasdaq | `US` |
| `XETR` | Xetra | `DE` |
| `XKRX` | Korea Exchange | `KR` |
| `XKOS` | KOSDAQ | `KR` |

There is no row for Tokyo (`XJPX`): no provider serves it, and a market no provider serves needs no row.

## Notes

- **`mic` is the primary key** because it is an international standard and stable.
- **Germany has one exchange, Xetra.** The regional exchanges get no row (ADR 0018). US over-the-counter trading gets none either (ADR 0024).
- **Which code a market gets.** A row uses the ISO operating code by default: AIM is stored as London (`XLON`). A segment code gets its own row only where two separate listing markets share one operating code, as KOSDAQ (`XKOS`) does under Korea Exchange.

## Relationships

| Direction | Table | Through | On delete | On a changed `mic` |
|---|---|---|---|---|
| Referenced by | [`listing`](listing.md) | `listing.mic` | Refused while listings remain | The listings follow |
| Referenced by | [`provider_exchange`](provider_exchange.md) | `provider_exchange.mic` | Refused while codes remain | The codes follow |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `exchange (mic)` | The primary key | Find an exchange by its market code |

## Views

`provider_listing_address` reads this table indirectly, through `listing.mic` and `provider_exchange.mic`. See [`provider_listing`](provider_listing.md#view-provider_listing_address).
