# `instrument`

One row per security of a company, identified by its ISIN. Decided in ADR 0003. Created by migration `0001_reference_schema`.

An instrument exists as soon as a holdings source names it. Where it trades is recorded separately, in [`listing`](listing.md), and may not be known.

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `instrument_id` | INTEGER | PK | yes | Assigned by the database, never reused | pyvalue's own id for the security |
| `company_id` | INTEGER | FK → `company.company_id` | yes | The company must exist | The company that issued the security |
| `isin` | TEXT | UNIQUE | yes | 12 characters: two letters, nine letters or digits, one digit | The security's ISO 6166 identifier |

## Example rows

| `instrument_id` | `company_id` | `isin` |
|---|---|---|
| 1 | 1 (Berkshire Hathaway) | `US0846707026` |
| 2 | 2 (Alphabet) | `US02079K3059` |
| 3 | 2 (Alphabet) | `US02079K1079` |
| 4 | 3 (SAP) | `DE0007164600` |
| 5 | 4 (Toyota) | `JP3633400001` |

## Notes

- **Several instruments per company.** A company has one row per security: Alphabet's two share classes above, a common and a preferred share, or a Chinese company's mainland and Hong Kong shares.
- **`instrument_id` is a surrogate key.** The ISIN is unique but can change after a corporate action. When it changes, the row is updated and `instrument_id` stays the same.
- **`isin` is unique**, so the same security can never be entered twice, however many exchanges it trades on.
- **An instrument without a listing** is a normal state: its listing has not been found, its home market is not served by any provider, or it was decided that it gets none (ADR 0005).

## Relationships

| Direction | Table | Through | On delete |
|---|---|---|---|
| References | [`company`](company.md) | `instrument.company_id` | A company with instruments cannot be deleted |
| Referenced by | [`listing`](listing.md) | `listing.instrument_id` | Refused while the instrument has a listing |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `instrument (instrument_id)` | The primary key | Find an instrument by id |
| `instrument (isin)` | The `UNIQUE` constraint | Find an instrument by ISIN when holdings are loaded |
| `instrument (company_id)` | `instrument_company_id` | List a company's instruments; check the foreign key when a company is deleted |

## Views

None.
