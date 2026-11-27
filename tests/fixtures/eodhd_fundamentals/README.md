# Sample EODHD fundamentals payloads

Made-up answers in the shape EODHD gives for the fundamentals of one security, cut down to a few values. Nothing here was downloaded, and the companies do not exist. The shape was seen live on 2026-11-27 (ADR 0028): a JSON object whose `General` section names the symbol in `Code`, with the statements under `Financials`.

They go with the sample listings of [`../listings`](../listings/README.md): each file is the payload of one of the six listings the sample listing fill writes. A file is named by EODHD's exchange code and symbol, `<CODE>_<SYMBOL>.json`.

| File | Listing | What it shows |
|---|---|---|
| `US_ALPH.json` | Alpha Corp, `XNYS` | A US payload: `Exchange` is the venue label, and `ISIN` is empty, as on every US payload seen live |
| `US_ALPH-PA.json` | Alpha Corp, preferred, `XNYS` | A symbol with a hyphen |
| `US_BETA.json` | Beta Inc, `XNAS` | A second exchange under the code `US` |
| `LSE_DLT.json` | Delta PLC, `XLON` | A payload that carries its ISIN; a market quoted in pence |
| `XETRA_THT.json` | Theta AG, `XETR` | An exchange code of more than three letters |

There is no file for `MUP` under `AU`, the sixth listing: a test answers "not found" for it, as EODHD does for a symbol it has no fundamentals for.

The folder is separate from [`../eodhd`](../eodhd/README.md) because tests copy every `.json` file of that folder into a lists folder.
