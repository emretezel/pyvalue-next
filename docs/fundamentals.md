# The fundamentals payloads

What the first download of EODHD's fundamentals saved, on 2026-11-27. A payload is EODHD's whole answer for one listing: the company's details and its financial statements, yearly and quarterly, as far back as EODHD has them. How payloads are fetched and kept is decided in ADR 0028. Nothing here has been read into tables yet.

## In short

| Figure | Count |
|---|---|
| Listings at EODHD | 8,309 |
| Listings with a saved payload | 8,309 |
| Listings EODHD had nothing for | 0 |
| Size on disk | 403 MB, in 8,309 files under 38 folders |
| Size unpacked | 3.91 GB |
| Daily allowance used on the day | 83,355 of 100,000 |
| The account's extra reserve | 74,094 before and after |

## How it went

| Step | Requests | Result |
|---|---|---|
| Trials while the design was agreed | 20, and one price request that was refused | Kept outside the project. They gave the measurements of ADR 0028 |
| A pilot: one listing for each of the 38 exchange codes, and `PE&OLES` | 39 | 39 saved, through the same functions as the command |
| `pyvalue fundamentals download` | 8,270 | 8,269 saved. One request failed on a network name lookup and was not charged |
| The command again | 1 | The one that had failed, saved |
| The command a third time | 0 | Nothing to download: no request, and a report with its header only |

The run took about 18 minutes, at about 450 requests a minute. EODHD allows 1,200.

## What was checked

- **Every listing has a file,** and the report `data/fundamentals/not_downloaded.csv` has no row.
- **Every file unpacks to JSON whose `General.Code` is the listing's symbol.** No temporary file was left behind.
- **Each request cost 10 of the allowance,** as measured: the account's count went from 655 to 83,345 over the 8,269 that reached EODHD.
- **The reserve was not touched,** and the run ended 11,645 short of its own stopping point.

## What the payloads hold

Counted once after the download, without reading the statements themselves.

| Size of a payload, unpacked | |
|---|---|
| Smallest | 2 KB |
| Median | 448 KB |
| Mean | 470 KB |
| Largest | 1.3 MB |

Compression brings the whole set to 10.3% of its size.

| The latest yearly income statement is for | Payloads |
|---|---|
| 2026 | 1,005 |
| 2025 | 7,226 |
| 2024 | 63 |
| No yearly income statement | 15 |

## What the next step has to deal with

These are findings, not decisions.

| Finding | Payloads | Detail |
|---|---|---|
| No financial statements at all | 13 | All six Egyptian listings, and seven others that look like recent listings, which was not checked: `NIQ` and `SEV` in the US, `0120G0` and `457190` on KOSPI, `445680` on KOSDAQ, `VGC` in Toronto, `MYNLD` in Manila |
| EODHD's own update date is old | 36 | All 34 Philippine payloads: 26 dated August 2023, one 2020, six 2024, one April 2026. Two of the six Hungarian payloads are dated September 2026. Every other payload is dated November 2026, six have no date |
| The payload gives no ISIN | 3,221 | 3,109 of the 3,198 US payloads, and 112 elsewhere. A US payload cannot confirm that it belongs to the security |
| The payload gives another ISIN than ours | 11 | DL Holdings, SGH, Brookfield Renewable, Brookfield Business, RB Global, Spartan Delta, Strathcona Resources, Luzerner Kantonalbank, Cencosud Shopping, NEPI Rockcastle, Hafnia. The names agree in all eleven, so these look like companies whose ISIN changed, which was not checked one by one |
| The payload gives our ISIN | 5,077 | 4,988 outside the US, 89 in the US |
| Listings that look stale or moved | About 36 | From a check of the listings against OpenFIGI and the SEC's ticker list on 2026-11-27, which is not written up. Their payloads were downloaded like any other |

## What this subscription does not give

- **Prices.** A price request was refused: the plan has fundamentals only.

## Fetching the payloads again

The command never overwrites a payload. For a refresh, set the folder `data/eodhd/fundamentals/` aside and run `pyvalue fundamentals download`. It needs most of a day's allowance. The subscription runs to about 27 December 2026.
