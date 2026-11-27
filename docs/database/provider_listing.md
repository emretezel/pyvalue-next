# `provider_listing`

One row says: this provider uses this symbol for this listing of ours. Decided in ADR 0002. Created by migration `0001_reference_schema`. Filled by `pyvalue listings fill`, together with the listing (ADR 0019, ADR 0026).

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `listing_id` | INTEGER | PK, FK → `listing.listing_id` | yes | The listing must exist | Our listing |
| `provider_code` | TEXT | PK, FK → `provider.provider_code` | yes | The provider must exist | The provider |
| `provider_symbol` | TEXT | | yes | Not empty, no leading or trailing spaces | The symbol the provider itself uses for that listing, without any exchange part |

## Example rows

| `listing_id` | `provider_code` | `provider_symbol` | Read as |
|---|---|---|---|
| 1 (Berkshire B, ticker `BRK B`) | `eodhd` | `BRK-B` | EODHD calls Berkshire's B share `BRK-B` |
| 2 (Alphabet A, ticker `GOOGL`) | `eodhd` | `GOOGL` | EODHD calls Alphabet's A share `GOOGL` |
| 4 (SAP, ticker `SAP`) | `eodhd` | `SAP` | EODHD calls SAP `SAP` |

## Notes

- **The key is the pair `listing_id` plus `provider_code`**: a provider has at most one symbol for a listing.
- **`provider_symbol` is stored exactly as the provider gives it.** It is never derived from `listing.ticker`, because the two can differ, as for Berkshire above.
- **No row means the listing is not mapped at that provider.**
- **The row is the line the listing was written from.** With the provider's exchange code for the listing's exchange, it names a row of [`provider_symbol`](provider_symbol.md) as it stood when the listing was filled. Nothing ties the two afterwards: a stored list is replaced as a whole and can lose the line (ADR 0018).

## Relationships

| Direction | Table | Through | On delete | On a changed key |
|---|---|---|---|---|
| References | [`listing`](listing.md) | `provider_listing.listing_id` | A listing with provider symbols cannot be deleted | |
| References | [`provider`](provider.md) | `provider_listing.provider_code` | A provider with symbols cannot be deleted | A corrected `provider_code` is copied here |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `provider_listing (listing_id, provider_code)` | The primary key | The provider's symbol for a listing; the foreign-key check when a listing is deleted |

The key leads with `listing_id`, so the index serves lookups that start from a listing. Reading every mapping of one provider scans the table, which is the whole table while there is one provider.

## View: `provider_listing_address`

One row gives the two parts a provider needs to address one listing. It stores nothing; it joins this table to `listing` and `provider_exchange`.

| Column | Comes from | Meaning |
|---|---|---|
| `provider_code` | `provider_listing` | The provider |
| `listing_id` | `provider_listing` | Our listing |
| `provider_symbol` | `provider_listing` | The provider's symbol for the listing |
| `provider_exchange_code` | `provider_exchange`, for the exchange the listing trades on | The provider's code for the listing's exchange |

Worked example, for EODHD, whose requests take the form `SYMBOL.EXCHANGE`:

| Listing | Trades on | `provider_symbol` | `provider_exchange_code` | Request sent to EODHD |
|---|---|---|---|---|
| Berkshire B | `XNYS` | `BRK-B` | `US` | `BRK-B.US` |
| Alphabet A | `XNAS` | `GOOGL` | `US` | `GOOGL.US` |
| SAP | `XETR` | `SAP` | `XETRA` | `SAP.XETRA` |
| Toyota | `XJPX` | (none) | (none) | No row in the view, so no request |

- **The provider's client code formats the two parts.** The dot between them is EODHD's convention, not part of the schema.
- **No stand-in lines.** The exchange part always comes from the exchange the listing trades on. A listing on an exchange the provider does not serve has no row in the view, even if a symbol was stored for it.
