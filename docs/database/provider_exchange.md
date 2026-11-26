# `provider_exchange`

One row says: this provider uses this code for this exchange of ours. Decided in ADR 0002. Created by migration `0001_reference_schema`; migration `0005_provider_symbol` added a unique key (ADR 0018). Filled by `pyvalue symbols load` from the committed file `eodhd_exchange.csv` (ADR 0024).

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `mic` | TEXT | PK, FK → `exchange.mic` | yes | The exchange must exist | Our exchange |
| `provider_code` | TEXT | PK, FK → `provider.provider_code` | yes | The provider must exist | The provider |
| `provider_exchange_code` | TEXT | | yes | Not empty, no leading or trailing spaces | The code the provider itself uses for that exchange, in its own requests and responses |

## Example rows

| `mic` | `provider_code` | `provider_exchange_code` | Read as |
|---|---|---|---|
| `XNYS` | `eodhd` | `US` | EODHD calls the New York Stock Exchange `US` |
| `XNAS` | `eodhd` | `US` | EODHD calls Nasdaq `US` as well |
| `XETR` | `eodhd` | `XETRA` | EODHD calls Xetra `XETRA` |
| `XKOS` | `eodhd` | `KQ` | EODHD calls KOSDAQ `KQ` |

There is no row for `XJPX`: EODHD does not serve Tokyo.

## Notes

- **The key is the pair `mic` plus `provider_code`**: a provider has at most one code for an exchange.
- **`provider_exchange_code` is not unique.** Several of our exchanges can share one provider code, as New York and Nasdaq do above.
- **No row means the provider does not serve that exchange.** The rule that fills listings (ADR 0019) reads this to tell a market the provider serves from one it does not.
- **A code is never changed in place.** The symbol rows stored under a code follow a changed code, so a correction would move a stored list under another code. The load adds rows; a database that holds a row the file no longer has is rebuilt (ADR 0024).

## Relationships

| Direction | Table | Through | On delete | On a changed key |
|---|---|---|---|---|
| References | [`exchange`](exchange.md) | `provider_exchange.mic` | An exchange with provider codes cannot be deleted | A corrected `mic` is copied here |
| References | [`provider`](provider.md) | `provider_exchange.provider_code` | A provider with exchange codes cannot be deleted | A corrected `provider_code` is copied here |
| Referenced by | [`provider_symbol`](provider_symbol.md) | `mic`, `provider_code` and `provider_exchange_code` together | Refused while symbols remain | The symbols follow |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `provider_exchange (mic, provider_code)` | The primary key | The provider's code for a listing's exchange; the foreign-key check when an exchange is deleted |
| `provider_exchange (mic, provider_code, provider_exchange_code)`, unique | `CREATE UNIQUE INDEX provider_exchange_code_key` | It is the key the foreign key of `provider_symbol` points at. Its leading columns repeat the primary key; it exists only for that purpose and adds no rule |

The key leads with `mic`, so the index serves lookups that start from an exchange. The table has a few dozen rows, so reading all of one provider's codes scans it.

## Views

`provider_listing_address` reads `provider_exchange_code` from this table. See [`provider_listing`](provider_listing.md#view-provider_listing_address).
