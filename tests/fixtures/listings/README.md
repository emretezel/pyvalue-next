# Sample symbol lists for the listing fill

Made-up symbol lists in the shape EODHD documents, written to go with the sample holdings filings of [`../nport`](../nport/README.md) and the sample Vanguard files of [`../vanguard`](../vanguard/README.md). Loaded together, they take the sixteen sample securities through every outcome of the listing fill (ADR 0019, ADR 0026). Nothing here was downloaded, and the companies do not exist.

The lists are named as `pyvalue symbols download` would save them, for exchange codes of the file shipped with pyvalue. A test copies them into a temporary `data/eodhd`.

## What each security is there for

| Security | Held as | Lines in the lists | Outcome |
|---|---|---|---|
| `US00000A0014` Alpha Corp | VTI, ticker `ALPH` | `ALPH` on New York, with the ISIN | Filled: `XNYS`, `ALPH`, USD |
| `US00000A0022` Alpha Corp, preferred | VTI, ticker `ALPH.PA` | `ALPH-PA`, a preferred share, with the ISIN | Filled. The ticker is the fund's, `ALPH.PA`; the provider's symbol stays `ALPH-PA` |
| `US00000B0013` Beta Inc | VTI, no ticker | `BETA` on Nasdaq, with the ISIN | Filled by ISIN alone: `XNAS`, `BETA` |
| `US00000B0021` Beta Inc, second security | VTI, no ticker | `BETB` and `BETB-WT`, both with the ISIN | On the report: several lines carry the ISIN |
| `GB00000D0016` Delta PLC | VXUS, two holding lines, pounds | `DLT` in pence (`GBX`), with the ISIN; and `0DLT`, a foreign share in euros | Filled: `XLON`, `DLT`, GBP. `0DLT` is not a second line of `DLT` |
| `FR00000E0013` Epsilon SA | VXUS, euros | `EPS`, with the ISIN, in US dollars | On the report: the line is in another currency |
| `FR00000E0021` Epsilon SA, second company | VXUS, ticker `EPS B` | `EPS-B`, with another ISIN | On the report: no line has the ISIN, the ticker finds one |
| `KYG0000Z0015` Zeta Ltd | VXUS, Hong Kong | None: the provider has no Hong Kong exchange | Market not served |
| `US00000H0017` Eta Holdings Ltd | VXUS, ticker `ETA` | `ETA` on New York, with the ISIN | On the report: a US-coded ISIN held by the non-US fund |
| `DE00000T0019` Theta AG | VXUS, two holding lines | `THT` on Xetra, with the ISIN | Filled: `XETR`, `THT`, EUR |
| `JP300000I006` Iota KK | VXUS, Japan | None: the provider has no Japanese exchange | Market not served |
| `MYL0000L0012` Lambda Bhd | VXUS, ticker `LAMBDA` | `5555`, with the ISIN | On the report: the ticker differs |
| `KR70000K0000` Kappa Co Ltd | VXUS, ticker `000990` | `000990` in the KOSPI list with the ISIN, and again in the KOSDAQ list without one | On the report: the symbol is also on another line |
| `AU00000M0018` Mu Property Trust | VXUS, ticker `MUP` | `MUP`, with the ISIN | Filled: `XASX`, `MUP`, AUD |
| `TW00000N0013` Nu Corp | VXUS, Taiwan | `2330` in the list of `TW`, with the ISIN. There is no list for `TWO`, Taiwan's second exchange code | Waiting for a symbol list |
| `US00000O0018` Omicron Ltd | VXUS, ticker `OMC` | `OMC` on Nasdaq, with the ISIN | On the report: a US-coded ISIN held by the non-US fund |

In total: 6 filled (3 with ISIN and ticker agreeing, 3 by ISIN with no fund ticker), 2 in a market that is not served, 1 waiting, 7 on the report. `expected/cases_for_agent.csv` is the report, byte for byte.

`OTHR` in the US list belongs to no sample security.

## Sample decisions

`decisions/listing.csv` holds two decisions (ADR 0019). Tests pass it to the fill explicitly; the decisions file shipped with pyvalue concerns real securities and matches nothing here.

| Security | Decision | Effect |
|---|---|---|
| `MYL0000L0012` Lambda Bhd | The line `5555` of `KLSE` | Filled: `XKLS`, ticker `5555`, because the fund's ticker does not equal the symbol |
| `FR00000E0021` Epsilon SA | None | No listing, and no longer on the report |

With these decisions: 7 filled, 5 on the report.
