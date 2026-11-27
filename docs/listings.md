# The listings

What the listings hold on 2026-11-27, after the first download of EODHD's symbol lists and the first pass of the agent. A listing says where a security trades and what the provider calls it there (`listing`, `provider_listing`). How one is determined is decided in ADR 0019, ADR 0026 and ADR 0027.

## In short

| Figure | Count |
|---|---|
| Securities in the universe | 11,704 |
| Securities with a listing | 8,309, or 71% |
| Companies with at least one listed security | 8,210 of 11,479 |
| Exchanges with a listing | 40, in 35 countries |
| Securities whose market EODHD does not serve | 3,110 |
| Securities decided to have no listing | 115 |
| Securities left undecided, on the report | 170 |

Every security has exactly one of these outcomes.

| Outcome | Securities |
|---|---|
| Filled by the rule: one line in the home market carries the ISIN, and the fund's ticker and currency agree | 8,026, of which 315 by ISIN alone because the fund gives no ticker |
| Filled by a decision | 283 |
| Decided to have no listing | 115 |
| Market not served | 3,110 |
| Undecided | 170 |

## Where it comes from

One download on 2026-11-27, 60 requests: EODHD's exchange list and the symbol list of each of the 59 codes our exchange file gives a market. The answers are kept under `data/eodhd/` and are the source for every rebuild.

| Step | Result |
|---|---|
| The exchange list | 70 codes, the same 70 as `eodhd_exchange.csv`. Nothing to add or remove |
| Lines downloaded | 98,963 in 59 lists |
| Lines stored | 37,781: common and preferred shares on our exchanges |
| Not stored: not a share | 49,544: funds 22,241, exchange-traded funds 21,338, mutual funds 4,829, warrants 508, units 283, notes 173, and 172 others |
| Not stored: a US venue label that is left out | 11,637: over-the-counter lines, and the lines EODHD gives no venue (ADR 0027) |
| Not stored: no currency | 1 |
| Stored lines without an ISIN | 7,529 |

The load was checked for shares it should not have dropped: of the lines that carry the ISIN of a security the funds hold in that market, 9 were not stored, all in the US list. Six carry the over-the-counter label `PINK` and one the label `OTC`, one is a warrant, and one has no venue (ERock).

## Where the listings are

| Country of the exchange | Listings |
|---|---|
| United States | 3,198 |
| Mainland China | 2,070 |
| Taiwan | 525 |
| Korea | 451 |
| Australia | 269 |
| United Kingdom | 206 |
| Canada | 197 |
| Sweden | 144 |
| Germany | 144 |
| Brazil | 126 |
| France | 121 |
| Switzerland | 115 |
| 23 other countries | 743 |

## Markets EODHD does not serve

3,110 securities trade only where EODHD has no exchange. They stay in the universe without a listing and are outside every screen.

| Country | Securities |
|---|---|
| Japan | 1,306 |
| India | 645 |
| Hong Kong | 530 |
| Turkey | 175 |
| Saudi Arabia | 103 |
| Israel | 87 |
| Italy | 84 |
| Singapore | 47 |
| United Arab Emirates | 42 |
| New Zealand | 26 |
| Kuwait | 24 |
| Qatar | 21 |
| Iceland | 15 |
| Colombia | 6 |

One security is held in two of these countries and is counted under both.

## The decisions

398 rows in `src/pyvalue/listings/decisions/listing.csv`, all of 2026-11-27. The agent's rows were proposed with their evidence and approved by the author batch by batch (ADR 0027).

| Kind | Rows | Outcome | Decided by | The evidence |
|---|---|---|---|---|
| Thai foreign-board shares | 107 | None | Author | The fund's ticker ends in `-F` or OpenFIGI types the security "Foreign Sh."; EODHD lists the local share only (ADR 0019) |
| The ticker differs | 97 | Listing | Agent | The line carries the ISIN. 90 are Malaysian: the symbol is the stock code, which the ISIN contains. For 7, OpenFIGI gives the line's ticker |
| The ticker finds one line | 128 | Listing | Agent | No line carries the ISIN; OpenFIGI ties the ISIN to the same ticker on the home exchange |
| US-coded ISIN in the non-US fund | 22 | Listing | Agent | 19 New York receipts that are each company's only line, and three ordinary shares of US companies |
| Held in several markets | 17 | Listing | Agent | The line in the ISIN's own country |
| Korean shares with a duplicate line | 12 | Listing | Agent | OpenFIGI lists the share on KOSPI; the KOSDAQ line of the same code has no ISIN |
| Several lines carry the ISIN | 3 | Listing | Agent | OpenFIGI's exchange and ticker |
| Receipts read as the ordinary share | 6 | None | Agent | The share trades only in Hong Kong, which EODHD does not serve |
| A market the author chose | 4 | Listing | Author | RHI Magnesita in Vienna; Brookfield Infrastructure, AngloGold Ashanti and James Hardie in New York |
| New Zealand companies also listed in Sydney | 2 | None | Author | a2 Milk and Fletcher Building do not take their Sydney line |

A decided listing whose line carries no ISIN, or an older one, rests on the outside source: 130 listings.

## What is undecided

170 securities are on the report `data/listings/cases_for_agent.csv` with no row in the decisions file. The author decided on 2026-11-27 that a security that left its exchange or changed its ISIN since the filing waits for newer filings (ADR 0027). The filings show holdings of 30 June (VTI) and 31 July (VXUS).

| Group | Securities | Examples |
|---|---|---|
| Nothing found, and EODHD has no line under the ticker OpenFIGI gives for the home market | 136 | The company left its exchange (Roku, Kenvue, Janus Henderson), or trades under a new ISIN after a reorganisation or a reverse split (Exxon Mobil, Gates Industrial, Expro, Beyond Meat) |
| Nothing found; EODHD has a line under OpenFIGI's ticker, without an ISIN, and the fund gives no ticker | 22 | 17 recent mainland-Chinese listings, such as Hua Hong; Webjet Group; Qualco |
| Nothing found; EODHD's line under OpenFIGI's ticker carries another ISIN | 1 | SpareBank 1 Sor-Norge |
| The ticker finds a line, and no outside source ties it | 10 | A new ISIN at EODHD: ONEOK, Weatherford, Accuray. Also Coretronic, NGEx Minerals, and the old Supernus, whose line now carries Indivior's ISIN |
| The line's currency is stated wrongly | 1 | Baltic Classifieds: a London line given in euros |

By country, the 159 with nothing found are: United States 110, mainland China 18, Canada 6, Australia 5, United Kingdom 5, Korea 5, and 10 elsewhere. Which of the 136 left and which changed ISIN was not worked out one by one. Of the 110 in the United States, the ISIN of 56 is on EODHD's list of delisted symbols, which also holds the old ISIN of a company that lives on.

What clears them:

- **A newer filing** drops a company that left and brings a new ISIN. A company delisted after the filing's date stays a quarter more.
- **A later download** brings an ISIN that EODHD has added to a line, and the venue of a line that had none. The rule then fills the security.
- **The agent's next pass** takes what is left with a line on the report.

## Checks made

- **No two listings share an exchange and ticker,** and every listing has its provider symbol.
- **8,179 listings are on a line that carries the security's ISIN.** The other 130 are decided.
- **A second run changes nothing** and writes the same report, byte for byte.
- **A rebuild from the saved files gives the same listings.** Tried on a copy: `db migrate`, `universe load`, `symbols load`, `listings fill` gave the same 8,309 listings and the same report.
