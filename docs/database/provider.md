# `provider`

One row per data provider. Decided in ADR 0002. Created by migration `0001_reference_schema`.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `provider_code` | TEXT | PK | yes | Starts with a lower-case letter; lower-case letters, digits and underscores only | pyvalue's own short code for the provider |
| `name` | TEXT | | yes | Not empty, no leading or trailing spaces | The provider's name |

## Example row

| `provider_code` | `name` |
|---|---|
| `eodhd` | EODHD |

## Notes

- **`provider_code` is the primary key.** pyvalue assigns it, so it is stable and meaningful and no numeric id is needed.
- **Nothing that belongs to a provider is stored in the core tables.** A provider's own codes and symbols live in the two mapping tables below.

## Relationships

| Direction | Table | Through | On delete | On a changed `provider_code` |
|---|---|---|---|---|
| Referenced by | [`provider_exchange`](provider_exchange.md) | `provider_exchange.provider_code` | Refused while exchange codes remain | The codes follow |
| Referenced by | [`provider_listing`](provider_listing.md) | `provider_listing.provider_code` | Refused while symbols remain | The symbols follow |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `provider (provider_code)` | The primary key | Find a provider by its code |

## Views

`provider_listing_address` carries `provider_code` from the mapping tables. See [`provider_listing`](provider_listing.md#view-provider_listing_address).
