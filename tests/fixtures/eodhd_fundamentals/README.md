# Sample EODHD fundamentals payloads

Made-up answers in the shape EODHD gives for the fundamentals of one security. Nothing here was downloaded, and the companies do not exist. The shape was seen live on 2026-11-27 (ADR 0028): a JSON object whose `General` section names the symbol in `Code`, with the statements under `Financials`, each with a `yearly` and a `quarterly` list keyed by date and the figures written as decimal text.

They go with the sample listings of [`../listings`](../listings/README.md): each file is the payload of one of the six listings the sample listing fill writes. A file is named by EODHD's exchange code and symbol, `<CODE>_<SYMBOL>.json`.

Each company has several fiscal years and one or two planted defects, so that the statements load (ADR 0029, ADR 0030) meets every kind of finding it reports on real payloads. The payloads were written by a one-off script; the figures are plain round numbers.

| File | Listing | Fiscal years | Planted for the statements load |
|---|---|---|---|
| `US_ALPH.json` | Alpha Corp, common, `XNYS` | 2022 to 2025, in USD; `ISIN` is empty, as on most US payloads | Zero interest expense in 2024 beside debt on the balance sheet. The oldest year, 2022, has no year before it |
| `US_ALPH-PA.json` | Alpha Corp, preferred, `XNYS` | 2023 to 2025 | Its 2025 revenue and net income disagree with the common share's payload, which is the one read |
| `US_BETA.json` | Beta Inc, `XNAS` | 2023 to 2025, plus a row on its old year end, 2024-06-30 | The old year end is off the chain of fiscal years; depreciation is negative in 2024; gross profit is not revenue minus cost in 2025 |
| `LSE_DLT.json` | Delta PLC, `XLON` | 2022 to 2025, in GBP | The 2022 rows are labelled `GBX` with amounts in pounds; total assets of 2024 are in thousands, between two years in units |
| `XETRA_THT.json` | Theta AG, `XETR` | 2020 to 2023, in EUR; nothing after 2023 | The 2021 rows carry no currency; in 2022 the income statement says EUR and the balance sheet USD; the payload names another ISIN; its latest year is stale against the others |

There is no file for `MUP` under `AU`, the sixth listing: the download tests answer "not found" for it, as EODHD does for a symbol it has no fundamentals for, and the load reports it as without a payload.

`expected/findings.csv` is the report the statements load writes for these payloads, byte for byte: 20 findings, each planted defect once, and the oldest year of each company.

The folder is separate from [`../eodhd`](../eodhd/README.md) because tests copy every `.json` file of that folder into a lists folder.
