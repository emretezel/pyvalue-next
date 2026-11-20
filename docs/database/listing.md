# `listing`

One row per instrument that has a known primary exchange line. Decided in ADR 0003. Created by migration `0001_reference_schema`.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `listing_id` | INTEGER | PK | yes | Assigned by the database, never reused | pyvalue's own id for the listing |
| `instrument_id` | INTEGER | UNIQUE, FK → `instrument.instrument_id` | yes | The instrument must exist; no two listings share an instrument | The security that trades on this line |
| `mic` | TEXT | FK → `exchange.mic` | yes | The exchange must exist | The exchange the security trades on |
| `ticker` | TEXT | UNIQUE together with `mic` | yes | Not empty, no leading or trailing spaces, upper case | The exchange's own ticker for the security |
| `currency` | TEXT | | yes | Exactly three upper-case letters | The ISO 4217 currency the security trades in |

## Example rows

| `listing_id` | `instrument_id` | `mic` | `ticker` | `currency` |
|---|---|---|---|---|
| 1 | 1 (Berkshire B, `US0846707026`) | `XNYS` | `BRK.B` | `USD` |
| 2 | 2 (Alphabet A, `US02079K3059`) | `XNAS` | `GOOGL` | `USD` |
| 3 | 3 (Alphabet C, `US02079K1079`) | `XNAS` | `GOOG` | `USD` |
| 4 | 4 (SAP, `DE0007164600`) | `XETR` | `SAP` | `EUR` |

## Notes

- **Primary listing only.** A row is the line on the market where the instrument has its primary listing. Because `instrument_id` is unique here, an instrument has at most one listing, so there is no primary/secondary status column.
- **No listing is a missing row.** An instrument whose exchange and ticker are unknown has no row here. No column is left empty to say so.
- **The company of a listing is reached through its instrument.** This table has no `company_id`.
- **`ticker` is the exchange's ticker**, written as the exchange writes it. It is not a provider's symbol; that is in [`provider_listing`](provider_listing.md).
- **`currency` is not a quote unit.** A London line is `GBP` even though its prices are quoted in pence.
- **How a listing is filled** is set out in ADR 0005.

## Relationships

| Direction | Table | Through | On delete | On a changed key |
|---|---|---|---|---|
| References | [`instrument`](instrument.md) | `listing.instrument_id` | An instrument with a listing cannot be deleted | |
| References | [`exchange`](exchange.md) | `listing.mic` | An exchange with listings cannot be deleted | A corrected `mic` is copied here |
| Referenced by | [`provider_listing`](provider_listing.md) | `provider_listing.listing_id` | Refused while provider symbols remain | |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `listing (listing_id)` | The primary key | Find a listing by id |
| `listing (instrument_id)` | The `UNIQUE` constraint | Find the listing of an instrument; list the instruments that have none; check the foreign key when an instrument is deleted |
| `listing (mic, ticker)` | The `UNIQUE` constraint | Resolve an exchange and ticker typed by a person; list the listings on an exchange |

There is no separate index on `mic`: it is the leading column of the (`mic`, `ticker`) index.

## Views

`provider_listing_address` reads `listing_id` and `mic` from this table. See [`provider_listing`](provider_listing.md#view-provider_listing_address).
