# Sample EODHD lists

Made-up answers in the shape EODHD documents for its two list requests, and a small pair of exchange files that goes with them. Nothing here was downloaded: the legacy project kept no raw answer, and no request is made to EODHD without the author asking for it (ADR 0024). The companies do not exist; every ISIN has a correct check digit unless the table says otherwise.

The shape is confirmed at the first live download. Until then these files are what the readers were written for.

## Files

| File | Stands in for |
|---|---|
| `exchanges.json` | EODHD's list of exchange codes |
| `symbols_KO.json`, `symbols_US.json`, `symbols_LSE.json` | The symbol list of one exchange code each |
| `exchange.csv` | Our exchanges file, `listings/reference/exchange.csv`, with five markets |
| `eodhd_exchange.csv` | EODHD's exchange file, `providers/eodhd_exchange.csv`, for the same markets |

## The two exchange files

| EODHD code | In `eodhd_exchange.csv` | In `exchanges.json` | Saved symbol list | What it shows |
|---|---|---|---|---|
| `KO` | One market, `XKRX` | Yes | Yes | A code on one exchange |
| `LSE` | One market, `XLON` | Yes | Yes | Lines in several currencies |
| `US` | By label: `NYSE` and `AMEX` are `XNYS`, `NASDAQ` is `XNAS`, `PINK` is left out | Yes | Yes | A code that covers several exchanges |
| `WAR` | One market, `XWAR` | No | No | A code the file maps and EODHD no longer offers; a code without a saved list |
| `F`, `CC` | Left out on purpose | Yes | No | A regional German exchange and a list that is not a stock exchange |
| `HK` | Not in the file | Yes | No | A code EODHD offers that the file lacks |

## The symbol lines

Twelve lines are stored, four per code.

| List | Symbol | What it shows | Stored |
|---|---|---|---|
| `KO` | `000100` | A common share with every value | Yes |
| `KO` | `000105` | A preferred share | Yes |
| `KO` | `000200` | No ISIN | Yes, without an ISIN |
| `KO` | `000300` | An exchange-traded fund | No: not a share |
| `KO` | `000400` | An ISIN that is cut short | Yes, without an ISIN |
| `US` | `ALFA` | A New York line | Yes, on `XNYS` |
| `US` | `BETA-B` | A Nasdaq line; a share class written with a hyphen | Yes, on `XNAS` |
| `US` | `GAMA` | A fund under a label the file does not have (`NYSE ARCA`) | No: not a share, so its label does not matter |
| `US` | `DLTA` | A second label for New York (`AMEX`); an empty ISIN | Yes, on `XNYS`, without an ISIN |
| `US` | `EPSL` | An over-the-counter line (`PINK`) | No: its label is left out on purpose |
| `US` | `ZETA-P` | A preferred share | Yes, on `XNYS` |
| `US` | (none) | A line without a symbol | No: the table cannot hold it |
| `US` | `THTA` | A mutual fund | No: not a share |
| `LSE` | `ALP` | A line quoted in pence (`GBX`) | Yes, with `GBX` as given |
| `LSE` | `0A1B` | A foreign share on London, in US dollars, without an ISIN | Yes |
| `LSE` | `GAM` | The currency `Unknown` | Yes, as given |
| `LSE` | `DEL` | No currency at all | No: the table cannot hold it |
| `LSE` | `EPS` | A line quoted in pounds | Yes |
