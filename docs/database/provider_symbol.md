# `provider_symbol`

One row per line of a provider's symbol list that is a common or preferred share on one of our exchanges. Decided in ADR 0018 and ADR 0025. Created by migration `0005_provider_symbol`; migration `0006_provider_symbol_drop_venue_and_type` removed two columns that nothing read, and migration `0007_provider_symbol_drop_isin_index` an index that nothing used (ADR 0026). Filled by `pyvalue symbols load` from the saved lists (ADR 0024).

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `provider_code` | TEXT | PK, FK | yes | With `mic` and `provider_exchange_code`, must be a row of `provider_exchange` | The provider |
| `provider_exchange_code` | TEXT | PK, FK | yes | As above | The provider's exchange code whose list the line is in |
| `provider_symbol` | TEXT | PK | yes | Not empty, no leading or trailing spaces | The symbol the provider uses, exactly as given |
| `mic` | TEXT | FK | yes | As above | Our exchange the line is on |
| `provider_name` | TEXT | | no | Not empty when present, no leading or trailing spaces | The provider's name for the security. Empty when the provider gives none |
| `provider_currency` | TEXT | | yes | Not empty, no leading or trailing spaces | The currency code as the provider gives it. It can be a sub-unit, such as `GBX` for pence |
| `isin` | TEXT | | no | 12 characters: two letters, nine letters or digits, one digit | The ISIN the provider gives for the line. Empty when it gives none or one that is not valid |

## Example rows

| `provider_code` | `provider_exchange_code` | `provider_symbol` | `mic` | `provider_name` | `provider_currency` | `isin` | Read as |
|---|---|---|---|---|---|---|---|
| `eodhd` | `KO` | `000660` | `XKRX` | SK Hynix Inc | `KRW` | `KR7000660001` | EODHD lists SK Hynix as `000660.KO` |
| `eodhd` | `US` | `BRK-B` | `XNYS` | Berkshire Hathaway Inc | `USD` | `US0846707026` | EODHD lists Berkshire's B share as `BRK-B.US`, on the New York Stock Exchange |
| `eodhd` | `LSE` | `SHEL` | `XLON` | Shell plc | `GBX` | `GB00BP6MXD84` | A London line quoted in pence |
| `eodhd` | `KLSE` | `1155` | `XKLS` | Malayan Banking Bhd | `MYR` | | A line for which EODHD gives no ISIN |

## Notes

- **The key is the provider, its exchange code and its symbol.** That is how EODHD itself identifies a line: `BRK-B.US`. Two rows cannot share it, so the same symbol cannot be stored once on New York and once on Nasdaq.
- **`mic` says which of our exchanges the line is on.** It is worked out from the code and the provider's venue label for the line, through the committed file `eodhd_exchange.csv`, when the list is stored. The label itself is not kept (ADR 0025).
- **`provider_currency` is the provider's code, not ours.** The listing rule turns a sub-unit into its currency (ADR 0019). A code we do not know, such as `Unknown`, is stored as given.
- **`isin` is the provider's claim.** It is missing on a quarter to a third of the lines and can be out of date.
- **Only shares are stored.** A fund, a warrant or a bond in the provider's list gets no row. The load decides that from the type the list gives; the type itself is not kept, so the table does not say whether a line is a common or a preferred share (ADR 0025).
- **A list is replaced as a whole.** When the list of one provider exchange code is stored again, the rows of that code are deleted and written again, in one transaction.
- **The table is as old as the last download.** It does not say when that was; the saved file under `data/eodhd/` does.

## What the schema does not enforce

| Not enforced | Consequence |
|---|---|
| That `mic` is the exchange the venue label stands for | The schema checks only that the exchange is one the code is mapped to. The load applies the file |
| That a row is a share | The table has no type to check since ADR 0025. The load stores a line only when the list gives its type as `Common Stock` or `Preferred Stock` |
| That a `provider_listing` row names a line in this table | `provider_listing` has no exchange column to join on. ADR 0019 checks it when a listing is written |
| That `provider_currency` is a code the listing rule knows | An unknown code is reported by the listing rule, and the line is not used |
| That two exchange codes do not list the same share | EODHD's KOSDAQ list has carried KOSPI lines. The listing rule sees two lines and sends the security to the agent |

## Relationships

| Direction | Table | Through | On delete | On a changed key |
|---|---|---|---|---|
| References | [`provider_exchange`](provider_exchange.md) | `mic`, `provider_code` and `provider_exchange_code` together | A mapping that still has symbols cannot be deleted | A corrected `mic`, `provider_code` or `provider_exchange_code` is copied here |

There is no direct reference to [`exchange`](exchange.md) or [`provider`](provider.md): both are reached through the mapping, so a line can only sit on an exchange its code is mapped to.

## Indexes

| Index | Created by | Query it serves |
|---|---|---|
| `provider_symbol (provider_code, provider_exchange_code, provider_symbol)` | The primary key | Find one line; read or replace the list of one provider exchange code |
| `provider_symbol (mic, provider_code, provider_exchange_code)` | `CREATE INDEX provider_symbol_exchange` | The foreign-key check when a `provider_exchange` row is deleted or corrected; the lines on one of our exchanges |

No index on `isin`: the listing rule reads the provider's lines once and looks them up in memory (ADR 0026). ADR 0018 created one, and migration 0007 dropped it.

## Normalisation

The table is in Boyce-Codd normal form with one deliberate deviation.

| Point | Reasoning |
|---|---|
| Every other column depends on the whole key | The name, currency and ISIN are what the provider says about that one line |
| The deviation: `mic` | It follows from the code and the venue label through the committed file, so it could be worked out again. It is stored because the foreign key needs it, and because the listing rule takes a line's country from it |
| Kept consistent by | The foreign key (the exchange must be one the code is mapped to) and by replacing a list as a whole |

## Views

None.
