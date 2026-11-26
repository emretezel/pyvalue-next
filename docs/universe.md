# The stock universe

What the universe holds at the end of the universe phase, on 2026-11-26, after the review of the two-fund universe. The universe is every company and security in `company` and `instrument`. How it is built is in `docs/architecture.md` and in ADR 0006, ADR 0009 to ADR 0017 and ADR 0020 to ADR 0023.

## In short

| Figure | Count |
|---|---|
| Companies | 11,479 |
| Securities (instruments) | 11,704 |
| Companies with a legal-entity identifier | 7,603 |
| Companies with more than one security | 224 |
| Trading countries | 50 |
| Holding lines stored | 11,734 |
| Holding lines with a ticker | 11,167 |
| Holding lines with a SEDOL | 11,374 |
| Preferred-share securities | 51 |

The universe holds companies only: no fund and no property trust (ADR 0023).

## Where it comes from

Two pinned SEC holdings filings, each joined with Vanguard's own holdings file for the ticker and the SEDOL (ADR 0016), and corrected by four committed files.

| Fund | SEC filing | Holdings date | Lines | Vanguard's own file | Rows |
|---|---|---|---|---|---|
| VTI, Vanguard Total Stock Market | `0000036405-26-000480` | 2026-06-30 | 3,546 | 2026-10-31 | 3,475 |
| VXUS, Vanguard Total International Stock | `0000736054-26-000275` | 2026-07-31 | 8,868 | 2026-10-31 | 8,860 |
| **Both** | | | **12,414** | | |

| Lines not loaded | Count |
|---|---|
| Debt or derivative | 103 |
| No valid ISIN (cash, leftover claims) | 52 |
| Receipt of a company already in the universe | 31 |
| Kept out by decision | 494 |
| **Total** | **680** |

| Decisions file | Rows | What it does | Record |
|---|---|---|---|
| `lei.csv` | 0 | Chooses between two identifiers the funds file for one security. Empty while both funds have one sponsor | ADR 0010, ADR 0011 |
| `name.csv` | 47 | Names a company that a fund files under a vendor placeholder | ADR 0012 |
| `excluded.csv` | 493 | Keeps a security out | ADR 0013, ADR 0023 |
| `ordinary_share.csv` | 7 | Reads a depositary receipt as its ordinary share | ADR 0015 |

What `excluded.csv` keeps out:

| Kind | Securities |
|---|---|
| Funds and property trusts | 421 |
| Rights, warrants, claims and unlisted lines: not a listed share | 31 |
| A second form of a share that is already in the universe | 15 |
| Companies without a market | 14 |
| Russian securities blocked for foreign holders | 10 |
| Depositary receipts | 2 |
| **Total** | **493** |

## Companies by country

The country is where the company's main security trades, not where the company is incorporated. A Chinese company listed in Hong Kong counts under Hong Kong, and a company whose only line is a New York receipt counts under the United States. A company with several securities is counted once, under the security the funds hold most of.

How it was worked out: Vanguard files the trading country on every line, and the load stores it in `holding`. For a receipt read as its ordinary share (ADR 0015) it is the market of that share.

| Country | Companies | Share |
|---|---|---|
| United States | 3,297 | 28.7% |
| China (mainland) | 1,958 | 17.1% |
| Japan | 1,306 | 11.4% |
| India | 644 | 5.6% |
| Taiwan | 529 | 4.6% |
| Hong Kong | 517 | 4.5% |
| Korea | 440 | 3.8% |
| Australia | 276 | 2.4% |
| United Kingdom | 213 | 1.9% |
| Canada | 201 | 1.8% |
| Turkey | 174 | 1.5% |
| Germany | 142 | 1.2% |
| Sweden | 132 | 1.1% |
| France | 121 | 1.1% |
| Brazil | 117 | 1.0% |
| Switzerland | 111 | 1.0% |
| Thailand | 107 | 0.9% |
| Saudi Arabia | 102 | 0.9% |
| Malaysia | 93 | 0.8% |
| Israel | 87 | 0.8% |
| Italy | 82 | 0.7% |
| Indonesia | 75 | 0.7% |
| South Africa | 69 | 0.6% |
| Norway | 56 | 0.5% |
| Spain | 53 | 0.5% |
| Netherlands | 51 | 0.4% |
| Singapore | 47 | 0.4% |
| United Arab Emirates | 42 | 0.4% |
| Denmark | 39 | 0.3% |
| Mexico | 39 | 0.3% |
| Greece | 36 | 0.3% |
| Philippines | 34 | 0.3% |
| Chile | 31 | 0.3% |
| Finland | 31 | 0.3% |
| Poland | 31 | 0.3% |
| Belgium | 30 | 0.3% |
| New Zealand | 27 | 0.2% |
| Austria | 26 | 0.2% |
| Kuwait | 24 | 0.2% |
| Qatar | 21 | 0.2% |
| Iceland | 15 | 0.1% |
| Portugal | 14 | 0.1% |
| Romania | 8 | 0.1% |
| Ireland | 7 | 0.1% |
| Egypt | 6 | 0.1% |
| Hungary | 6 | 0.1% |
| Colombia | 5 | 0.0% |
| Czechia | 5 | 0.0% |
| Argentina | 1 | 0.0% |
| Vietnam | 1 | 0.0% |
| **Total** | **11,479** | |

## By fund

| Held by | Companies |
|---|---|
| VXUS only | 8,207 |
| VTI only | 3,267 |
| Both | 5 |

The five in both funds are Energy Fuels, RB Global, Sempra, Sunbelt Rentals Holdings and Waste Connections.

## How it compares with what is listed

The listed counts are exchange figures from 2025. They come from different dates and count differently, and some include the trusts and funds this universe leaves out, so the last column is rough.

| Market | In the universe | Listed | Roughly |
|---|---|---|---|
| United States | 3,297 | 3,908 domestic companies | 84% |
| China (mainland) | 1,958 | 5,141 in Shanghai and Shenzhen | 38% |
| Japan | 1,306 | 3,968 | 33% |
| Taiwan | 529 | 1,884 on both exchanges | 28% |
| Hong Kong | 517 | 2,662 | 19% |
| Korea | 440 | 2,626 | 17% |
| India | 644 | 5,521 on the Bombay exchange | 12% |
| Canada | 201 | 4,377, including the venture exchange | 5% |

Sources: [listed companies by country](https://www.theglobaleconomy.com/rankings/listed_companies/), and the World Federation of Exchanges market statistics for [October 2025](https://focus.world-exchanges.org/issue/october-2025/market-statistics) and [March 2025](https://focus.world-exchanges.org/issue/march-2025/market-statistics).

## What it covers and what it does not

- **By market value the coverage is high.** The indexes the two funds follow are built to hold nearly all of the tradable market value. This was not measured from the filings.
- **No funds and no property trusts.** 420 of them were kept out on 2026-11-26, 2.0% of the value the two funds hold (ADR 0023). Property companies that are not trusts are in.
- **Smaller companies outside the United States are thinner than they were.** The universe was first built from three funds. Leaving out Dimensional's fund (ADR 0016) took it from 15,607 companies to 11,929, before the review took it to 11,479.

| Market | Three funds, 2026-11-22 | Two funds, before the review |
|---|---|---|
| Taiwan | 1,070 | 531 |
| Japan | 1,853 | 1,358 |
| Korea | 870 | 445 |
| India | 991 | 652 |
| China (mainland) | 2,235 | 1,958 |
| Hong Kong | 735 | 523 |
| Canada | 326 | 216 |
| United States | 3,504 | 3,490 |

- **Frontier markets are missing.** There is no company from Pakistan, Bangladesh, Nigeria, Kenya, Morocco, Sri Lanka, Kazakhstan, Jordan, Bahrain or Oman, and one each from Vietnam and Argentina.
- **No Russian company is in.** The ten the funds still hold are blocked for foreign holders and were kept out.
- **Nothing listed after mid-2026 is in**, until newer filings are pinned.

## Age of the data

The filings are four and five months old. Vanguard's own file is from 2026-10-31, and setting the two side by side shows what has changed since.

| Finding | VTI | VXUS | Both |
|---|---|---|---|
| Securities of the universe that are no longer in Vanguard's October file | 126 | 186 | 312 |
| Of those: the company is still there under a new ISIN | 39 | 14 | 53 |
| Of those: gone (taken over, delisted, or renamed beyond a match) | 87 | 172 | 259 |
| Securities in the October file that are not in the filings | 120 | 296 | 416 |
| Of those: the new ISIN of a company in the universe | 40 | 14 | 54 |
| Of those: new securities | 80 | 282 | 362 |

- **Nothing was fixed for this.** Newer filings cure it, and the universe is only ever loaded from filings.
- **The next filings** are expected around 2026-11-29 for VTI (holdings of 30 September) and around 2026-12-30 for VXUS (holdings of 31 October). Neither existed on 2026-11-26.
- **The new securities are not classified yet.** Some will be property trusts, which are kept out before the rebuild (ADR 0023).
- **Vanguard's address shows only the latest month,** so the saved file is the only copy of October.

## What the review found

The rebuilt two-fund universe was reviewed on 2026-11-26. Each check read the database, the saved filings and Vanguard's saved files, and each doubtful case was confirmed outside the filings before anything was decided.

| Check | Found | Decided |
|---|---|---|
| Lines that are not a listed share | 20: seven warrants, two earn-out lines, a subscription right and a subscription receipt, two leftover claims, and seven unlisted lines and companies | Kept out |
| Funds and property trusts | 420 | Kept out (ADR 0023) |
| A second ISIN for a share already in the universe | 15 registered forms of French shares that earn a loyalty bonus | Kept out; each company stays through its ordinary share |
| Companies without a market: the fund marks the line as having no market price and values the position under 1,000 dollars | 14 | Kept out |
| Russian securities blocked for foreign holders | 10, of which 8 were receipts read as their ordinary share | Kept out; the 8 rows left `ordinary_share.csv` |
| Receipts the receipt check does not recognise | 1, a Thai non-voting receipt | Kept out |
| One company in two rows | 0. 55 groups of company rows share a name once the legal form and punctuation are set aside, and all are different companies | Nothing to do |
| Securities under the wrong company | 0 among the 25 companies that were joined by name | Nothing to do |
| A ticker or a SEDOL shared by two securities, placeholder names, securities no fund holds | 0 of each | Nothing to do |
| Securities gone from, or new in, Vanguard's October file | 312 and 416 | Recorded above |
| Lines without a ticker | 567 | Recorded below |
| Lines whose country is not the currency's | 32 | Recorded below |

In all, 480 securities were kept out in the review: 59 in its first part and 421 with the funds and property trusts.

## Carried into the listing step

Found in the universe phase and left for the listing step (ADR 0018, ADR 0019), where the data provider's lists are available.

| Point | What is known |
|---|---|
| Markets the provider does not serve | By ADR 0019 these securities get no listing and stay outside every screen: Japan 1,306, India 645, Hong Kong 531, Turkey 175, Saudi Arabia 103, and smaller markets |
| Thailand | All 107 Thai securities are foreign-board shares: 105 carry a ticker ending in `-F` and two have none. By the author's decision in ADR 0019 none gets a listing |
| Lines without a ticker | 567. For 312 the ISIN is no longer in Vanguard's October file. For 207 Vanguard gives no ticker, 199 of them in mainland China. For 48 Vanguard's file has two rows for the ISIN |
| Securities under an old ISIN | 53. The provider will know the company under its new one |
| Securities that are gone | 259. Some will have no live line at the provider |
| Receipts still in the universe | 22, each its company's only line: 19 New York receipts, nearly all of Chinese companies (PDD Holdings, Vipshop, TAL Education and others), and three Australian depositary interests (GQG Partners, Light & Wonder, Fineos). Four Dutch certificates and the receipt of SES are the listed form of their share and are not counted as receipts |
| Receipts read as their ordinary share | 7. The fund holds the receipt in another market and currency than the share trades in |
| Lines whose country is not the currency's | 32: 26 mainland Chinese shares that trade in US or Hong Kong dollars, four Singapore lines in US dollars, and two British lines filed in US dollars (Compass Group, InterContinental Hotels) |
| Preferred shares | 51 securities of 50 companies. 19 of those companies are in the universe only through a preferred share |
| Securities that are new in a later filing | Each is classified before the rebuild, and the funds and property trusts among them are kept out (ADR 0023) |

## Reproducing the numbers

`pyvalue db migrate` and `pyvalue universe load` on a new database give the companies, securities, holding lines and lines not loaded above; the load prints them.

The other figures were worked out on 2026-11-26 with one-off scripts that are not part of the repository:

- **Country and fund tables:** from `holding`, with the value of each line read from the filings in `data/sec/` to choose a company's main security.
- **Age of the data, tickers and the review's checks:** from the database, the filings and Vanguard's files in `data/vanguard/`.
- **Funds and property trusts:** from the security type the open identifier mapping (OpenFIGI) gives each ISIN, as ADR 0023 describes.

The database holds no country for a company; the trading country is on each holding line.
