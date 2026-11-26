# The stock universe

> **These figures are for three funds.** They record the universe as it stood on 2026-11-22, loaded from VTI, VXUS and DFAX. Since ADR 0016 (2026-11-26) the universe comes from VTI and VXUS only, which is about 12,200 securities of about 11,900 companies. A new record of the two-fund universe follows after the rebuilt database has been reviewed.

What the universe holds at the end of the universe phase, on 2026-11-22. The universe is every company and security in `company` and `instrument`. How it is built is in `docs/architecture.md` and in ADR 0004, ADR 0006 and ADR 0009 to ADR 0015.

## In short

| Figure | Count |
|---|---|
| Companies | 15,607 |
| Securities (instruments) | 15,955 |
| Companies with a legal-entity identifier | 9,518 |
| Companies with more than one security | 334 |
| Countries | 54 |
| Open cases between the funds | 0 |

## Where it comes from

Three pinned SEC holdings filings (ADR 0004, ADR 0009), corrected by four committed files.

| Source | Holdings date | Lines |
|---|---|---|
| VTI, Vanguard Total Stock Market | 2026-06-30 | 3,546 |
| VXUS, Vanguard Total International Stock | 2026-07-31 | 8,868 |
| DFAX, Dimensional World ex U.S. Core Equity 2 | 2026-07-31 | 10,553 |
| **All three** | | **22,967** |

| Lines not loaded | Count |
|---|---|
| Debt or derivative | 107 |
| No valid ISIN (cash, leftover claims) | 96 |
| Receipt of a company already in the universe | 171 |
| Kept out by decision | 19 |
| **Total** | **393** |

| Decisions file | Rows | What it does | Record |
|---|---|---|---|
| `lei.csv` | 14 | Chooses between two identifiers the funds file for one security | ADR 0010, ADR 0011 |
| `name.csv` | 47 | Names a company that a fund files under a vendor placeholder | ADR 0012 |
| `excluded.csv` | 18 | Keeps a security out: one exchange-traded fund, 10 subscription rights, 4 rights to a later payment, 1 escrow claim, 2 warrants | ADR 0013 |
| `ordinary_share.csv` | 26 | Reads a depositary receipt as its ordinary share | ADR 0015 |

## Companies by country

The country is where the company's main security trades, not where the company is incorporated. A Chinese company listed in Hong Kong counts under Hong Kong, and a company whose only line is a New York receipt counts under the United States. A company with several securities is counted once, under the security the funds hold most of.

How it was worked out: Vanguard files the trading country on every line. For a security only Dimensional holds, the country is taken from the currency the line is held in, and for a line held in euros from the first two letters of the ISIN. For a receipt read as its ordinary share (ADR 0015) it is the market of that share.

| Country | Companies | Share |
|---|---|---|
| United States | 3,504 | 22.5% |
| China (mainland) | 2,235 | 14.3% |
| Japan | 1,853 | 11.9% |
| Taiwan | 1,070 | 6.9% |
| India | 991 | 6.3% |
| Korea | 870 | 5.6% |
| Hong Kong | 735 | 4.7% |
| Australia | 370 | 2.4% |
| Canada | 326 | 2.1% |
| United Kingdom | 237 | 1.5% |
| Thailand | 235 | 1.5% |
| Sweden | 224 | 1.4% |
| Turkey | 211 | 1.4% |
| Germany | 193 | 1.2% |
| Malaysia | 190 | 1.2% |
| Brazil | 186 | 1.2% |
| France | 170 | 1.1% |
| Israel | 163 | 1.0% |
| Indonesia | 161 | 1.0% |
| Switzerland | 152 | 1.0% |
| Saudi Arabia | 150 | 1.0% |
| Singapore | 130 | 0.8% |
| Italy | 116 | 0.7% |
| Norway | 105 | 0.7% |
| South Africa | 105 | 0.7% |
| Poland | 84 | 0.5% |
| Spain | 71 | 0.5% |
| Philippines | 68 | 0.4% |
| United Arab Emirates | 66 | 0.4% |
| Mexico | 62 | 0.4% |
| Netherlands | 61 | 0.4% |
| Denmark | 60 | 0.4% |
| Finland | 58 | 0.4% |
| Belgium | 52 | 0.3% |
| Kuwait | 47 | 0.3% |
| New Zealand | 42 | 0.3% |
| Chile | 41 | 0.3% |
| Greece | 40 | 0.3% |
| Qatar | 36 | 0.2% |
| Austria | 33 | 0.2% |
| Iceland | 15 | 0.1% |
| Portugal | 15 | 0.1% |
| Colombia | 15 | 0.1% |
| Russia | 14 | 0.1% |
| Ireland | 11 | 0.1% |
| Romania | 8 | 0.1% |
| Hungary | 7 | 0.0% |
| Egypt | 6 | 0.0% |
| Czechia | 6 | 0.0% |
| Luxembourg | 3 | 0.0% |
| Vietnam | 1 | 0.0% |
| Argentina | 1 | 0.0% |
| Peru | 1 | 0.0% |
| Monaco | 1 | 0.0% |
| **Total** | **15,607** | |

## By fund

| Held by | Companies |
|---|---|
| VXUS and DFAX | 6,496 |
| DFAX only | 3,678 |
| VTI only | 3,453 |
| VXUS only | 1,970 |
| Another combination | 10 |

The smaller names outside the United States come mostly from DFAX.

## How it compares with what is listed

The listed counts are exchange figures from 2025. They come from different dates and count differently, so the last column is rough.

| Market | In the universe | Listed | Roughly |
|---|---|---|---|
| United States | 3,504 | 3,908 domestic companies | 90% |
| Taiwan | 1,070 | 1,884 on both exchanges | 57% |
| Japan | 1,853 | 3,968 | 47% |
| China (mainland) | 2,235 | 5,141 in Shanghai and Shenzhen | 43% |
| Korea | 870 | 2,626 | 33% |
| Hong Kong | 735 | 2,662 | 28% |
| India | 991 | 5,521 on the Bombay exchange | 18% |
| Canada | 326 | 4,377, including the venture exchange | 7% |

Sources: [listed companies by country](https://www.theglobaleconomy.com/rankings/listed_companies/), and the World Federation of Exchanges market statistics for [October 2025](https://focus.world-exchanges.org/issue/october-2025/market-statistics) and [March 2025](https://focus.world-exchanges.org/issue/march-2025/market-statistics).

## What it covers and what it does not

- **By market value the coverage is high.** The indexes the three funds follow are built to hold nearly all of the tradable market value. This was not measured from the filings.
- **Large, mid and small companies are in.** The very small end is thin outside the United States: the companies missing from the table above are mostly small or rarely traded.
- **Frontier markets are missing.** There is no company from Pakistan, Bangladesh, Nigeria, Kenya, Morocco, Sri Lanka, Kazakhstan, Jordan, Bahrain or Oman, and one each from Vietnam and Argentina.
- **Nothing listed after mid-2026 is in**, until newer filings are pinned.

## Carried into the listing step

These were found during the universe phase and left for the listing step, where the data provider's lists are available.

| Point | What is known |
|---|---|
| Provider coverage | The provider's catalogue of October 2026 has no Hong Kong and no Moscow exchange, and 29% of its listings carry no ISIN. Of the 25 ordinary shares of ADR 0015, three have a home line that carries the ISIN |
| Age of the filings | ONEOK, Expro and Banpu changed their ISIN after the holdings dates and sit under the old one. Webster Financial, RE/MAX Holdings and National Storage Affiliates were taken over |
| Receipts still in the universe | 29, for which no listed ordinary share was found: 23 Chinese companies listed in New York, four Australian depositary interests, SES and Heijmans |
| Receipts read as their ordinary share | The fund holds the receipt in another currency than the share trades in, so the automatic rule of ADR 0005 will not fill these. The listing step should also refuse a provider line that carries a receipt's ISIN |
| One company in two rows | 58 groups of company rows share a name once the legal form and punctuation are set aside. Energisa is a near-certain case |
| Two unclear securities | `US029CNT0290` (ReElement Technologies) and `US725ESC0166` (Pivotal Software) carry in-house codes and nothing says what they are |

## Reproducing the numbers

`pyvalue db migrate` and `pyvalue universe load` on a new database give the companies and securities above. The country table was worked out on 2026-11-22 with a one-off script from the filings in `data/sec/`; the database holds no country for a company.
