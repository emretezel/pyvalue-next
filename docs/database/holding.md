# `holding`

One row per share line of a fund's loaded filing that carries a valid ISIN. Decided in ADR 0017. Created by migration `0002_fund_and_holding`.

A row records what the fund's documents say about the line. The only thing in it that pyvalue decided is which instrument the line was loaded as.

## Columns

"From" says which document a value comes from (ADR 0016): "SEC" is the holdings filing, "Sponsor" the fund company's own file, "Adapter" the sponsor's adapter.

| Column | Type | Key | Required | From | Constraint | Meaning |
|---|---|---|---|---|---|---|
| `fund_code` | TEXT | PK, FK → `fund.fund_code` | yes | | The fund must exist | The fund that reports the line |
| `line_number` | INTEGER | PK | yes | SEC | Greater than zero | The line's position in the filing, counted from 1 |
| `instrument_id` | INTEGER | FK → `instrument.instrument_id` | no | | The instrument must exist | The security the line was loaded as. Empty when the line was not loaded |
| `not_loaded_reason` | TEXT | | only when `instrument_id` is empty | | `excluded_by_decision` or `receipt_company_already_loaded`; present exactly when `instrument_id` is empty | Why the line was not loaded |
| `isin` | TEXT | | yes | SEC | 12 characters: two letters, nine letters or digits, one digit | The ISIN as filed |
| `issuer_name` | TEXT | | yes | SEC | Not empty, no leading or trailing spaces | The issuer's name as filed |
| `title` | TEXT | | no | SEC | Not empty when present | The security's title. Empty when the filing gives none |
| `lei` | TEXT | | no | SEC | 20 upper-case letters or digits, the last two digits | The issuer's legal-entity identifier. Empty when the filing gives none or a placeholder such as `N/A` |
| `cusip` | TEXT | | no | SEC | Nine characters | The US security number. Empty when the filing gives none or a placeholder |
| `sedol` | TEXT | | no | Sponsor | Seven letters or digits | The London Stock Exchange's security number. Empty when the join rule of ADR 0016 attaches none |
| `ticker` | TEXT | | no | Sponsor | Not empty when present, no leading or trailing spaces | The ticker as the sponsor writes it. Empty when the join rule attaches none |
| `asset_category` | TEXT | | yes | SEC | `EC`, `EP`, `STIV` or `OTHER` | The form's asset category: common share, preferred share, short-term investment vehicle, or the filer's own category |
| `asset_category_label` | TEXT | | no | SEC | Allowed only when `asset_category` is `OTHER` | The filer's own label for that category, such as `ADR` |
| `issuer_type` | TEXT | | yes | SEC | Upper-case letters only | The form's issuer type, such as `CORP` for a company or `RF` for a registered fund |
| `trading_country` | TEXT | | yes | Adapter | Two upper-case letters | The ISO 3166 code of the country the line trades in |
| `currency` | TEXT | | yes | SEC | Three upper-case letters | The ISO 4217 code of the currency the fund holds the line in |

## Example rows

Columns that are empty in all three rows are left out.

| `fund_code` | `line_number` | `instrument_id` | `not_loaded_reason` | `isin` | `issuer_name` | `lei` | `sedol` | `ticker` | `asset_category` | `issuer_type` | `trading_country` | `currency` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `VXUS` | 8803 | 5210 (SK Hynix) | | `KR7000660001` | SK hynix Inc | `988400XAIK6XISWQV045` | `6450267` | `000660` | `EC` | `CORP` | `KR` | `KRW` |
| `VXUS` | 3618 | 6034 (Qfin Holdings, ordinary share `KYG8851G1001`) | | `US88557W1018` | Qfin Holdings Inc | `836800R59NKEPDR6I240` | | | `EC` | `CORP` | `US` | `USD` |
| `VXUS` | 6798 | | `excluded_by_decision` | `US9220428588` | Vanguard FTSE Emerging Markets ETF | | | | `EC` | `RF` | `US` | `USD` |

The lines are those of the VXUS filing of 31 July 2026; the instrument ids are made up, and so is which sponsor values are empty. The second row is a depositary receipt read as its ordinary share (ADR 0015): the line keeps the receipt's ISIN, country and currency, and points at the instrument of the ordinary share.

## Which lines get a row

| Line of the filing | Row | `instrument_id` |
|---|---|---|
| A share line that the load turns into an instrument, or that names an instrument already there | Yes | The instrument |
| A share line of a security kept out by `excluded.csv` (ADR 0013) | Yes | Empty, reason `excluded_by_decision` |
| A depositary receipt whose company is already in the universe through its own shares (ADR 0006, ADR 0014) | Yes | Empty, reason `receipt_company_already_loaded` |
| A line without a valid ISIN | No. It stays in `lines_not_loaded.csv` (ADR 0009) | |
| A line the filing classifies as debt or as a derivative | No. It stays in `lines_not_loaded.csv` | |

The number of shares, the value and the share of the fund are not stored for any line.

## Notes

- **The key is the pair `fund_code` plus `line_number`.** It is the line's own identity in the filing, so no numeric id is added. Nothing refers to a holding row.
- **`isin` is what the fund filed.** It equals the instrument's ISIN except for a receipt read as its ordinary share.
- **`lei` and `issuer_name` are what the fund filed.** The company's stored identifier and name can differ, where a decision of ADR 0010 or ADR 0012 applies.
- **A placeholder is stored as empty,** never as the text `N/A`.
- **A newer filing replaces the fund's lines.** The rows of a fund are deleted and written again in one transaction. Companies and instruments are never deleted, so an instrument whose fund no longer holds it has no holding line.
- **`issuer_type` is checked for its shape only.** The list of codes is the SEC's and can grow.
- **Not enforced by the schema:** that `isin` belongs to the instrument the row points at, that `ticker` and `sedol` belong to the line, and that `lei` passes its check digits. The load guarantees all three.

## Relationships

| Direction | Table | Through | On delete | On a changed key |
|---|---|---|---|---|
| References | [`fund`](fund.md) | `holding.fund_code` | A fund with holding lines cannot be deleted | A corrected `fund_code` is copied here |
| References | [`instrument`](instrument.md) | `holding.instrument_id` | An instrument a line points at cannot be deleted | |

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `holding (fund_code, line_number)` | The primary key | Read or replace the lines of one fund; the foreign-key check when a fund is deleted |
| `holding (instrument_id)` | `holding_instrument_id` | The holding lines of a security, read by the listing rule of ADR 0019; the foreign-key check when an instrument is deleted |

No index on `isin`: nothing looks a line up by its filed ISIN.

## Views

None.
