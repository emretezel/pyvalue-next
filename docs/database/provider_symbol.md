# `provider_symbol`

One row per line of a provider's symbol list that is a common or preferred share on one of our exchanges. Decided in ADR 0018. Created by migration `0005_provider_symbol`. Filled by `pyvalue symbols load` from the saved lists (ADR 0024).

## Columns

| Column | Type | Key | Required | Constraint | Meaning |
|---|---|---|---|---|---|
| `provider_code` | TEXT | PK, FK | yes | With `mic` and `provider_exchange_code`, must be a row of `provider_exchange` | The provider |
| `provider_exchange_code` | TEXT | PK, FK | yes | As above | The provider's exchange code whose list the line is in |
| `provider_symbol` | TEXT | PK | yes | Not empty, no leading or trailing spaces | The symbol the provider uses, exactly as given |
| `mic` | TEXT | FK | yes | As above | Our exchange the line is on |
| `provider_venue` | TEXT | | no | Not empty when present, no leading or trailing spaces | The provider's venue label for the line, as given. Empty when the provider gives none |
| `provider_name` | TEXT | | no | Not empty when present, no leading or trailing spaces | The provider's name for the security. Empty when the provider gives none |
| `provider_type` | TEXT | | yes | `Common Stock` or `Preferred Stock` | The provider's type for the line |
| `provider_currency` | TEXT | | yes | Not empty, no leading or trailing spaces | The currency code as the provider gives it. It can be a sub-unit, such as `GBX` for pence |
| `isin` | TEXT | | no | 12 characters: two letters, nine letters or digits, one digit | The ISIN the provider gives for the line. Empty when it gives none or one that is not valid |

## Example rows

| `provider_code` | `provider_exchange_code` | `provider_symbol` | `mic` | `provider_venue` | `provider_name` | `provider_type` | `provider_currency` | `isin` | Read as |
|---|---|---|---|---|---|---|---|---|---|
| `eodhd` | `KO` | `000660` | `XKRX` | `KO` | SK Hynix Inc | `Common Stock` | `KRW` | `KR7000660001` | EODHD lists SK Hynix as `000660.KO` |
| `eodhd` | `US` | `BRK-B` | `XNYS` | `NYSE` | Berkshire Hathaway Inc | `Common Stock` | `USD` | `US0846707026` | EODHD lists Berkshire's B share as `BRK-B.US`, on the New York Stock Exchange |
| `eodhd` | `LSE` | `SHEL` | `XLON` | `LSE` | Shell plc | `Common Stock` | `GBX` | `GB00BP6MXD84` | A London line quoted in pence |
| `eodhd` | `KLSE` | `1155` | `XKLS` | | Malayan Banking Bhd | `Common Stock` | `MYR` | | A line for which EODHD gives no venue label and no ISIN |

The venue labels shown are what EODHD's documentation leads one to expect; they have not been seen live.

## Notes

- **The key is the provider, its exchange code and its symbol.** That is how EODHD itself identifies a line: `BRK-B.US`. Two rows cannot share it, so the same symbol cannot be stored once on New York and once on Nasdaq.
- **`mic` says which of our exchanges the line is on.** It is worked out from the code and the venue label, through the committed file `eodhd_exchange.csv`, when the list is stored.
- **`provider_currency` is the provider's code, not ours.** The listing rule turns a sub-unit into its currency (ADR 0019). A code we do not know, such as `Unknown`, is stored as given.
- **`isin` is the provider's claim.** It is missing on a quarter to a third of the lines and can be out of date.
- **Only shares are stored.** A fund, a warrant or a bond in the provider's list gets no row.
- **A list is replaced as a whole.** When the list of one provider exchange code is stored again, the rows of that code are deleted and written again, in one transaction.
- **The table is as old as the last download.** It does not say when that was; the saved file under `data/eodhd/` does.

## What the schema does not enforce

| Not enforced | Consequence |
|---|---|
| That `mic` is the exchange the venue label stands for | The schema checks only that the exchange is one the code is mapped to. The load applies the file |
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
| `provider_symbol (mic, provider_code, provider_exchange_code)` | `CREATE INDEX provider_symbol_exchange` | The lines on one of our exchanges, which is how the listing rule collects the lines of a country; the foreign-key check when a `provider_exchange` row is deleted or corrected |
| `provider_symbol (isin)`, rows with an ISIN only | `CREATE INDEX provider_symbol_isin` | The lines that carry a given ISIN, the first lookup of the listing rule |

## Normalisation

The table is in Boyce-Codd normal form with one deliberate deviation.

| Point | Reasoning |
|---|---|
| Every other column depends on the whole key | The name, type, currency, ISIN and venue label are what the provider says about that one line |
| The deviation: `mic` | It follows from the code and the venue label through the committed file, so it could be worked out again. It is stored because the foreign key needs it, and because the listing rule reads the lines of a country through it for every security |
| Kept consistent by | The foreign key (the exchange must be one the code is mapped to) and by replacing a list as a whole |

## Views

None.
