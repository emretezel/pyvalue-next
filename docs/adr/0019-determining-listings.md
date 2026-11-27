# ADR 0019: A listing is the provider's line in the security's home market, found by ISIN and confirmed by ticker

- Status: Accepted. ADR 0026 decides how the rule is run and changes seven points: a fifth outcome, waiting for a symbol list; "the same symbol" means the same text; the decided securities are handled first; a decision may only name a line the report could show; a database whose listing contradicts a decision is refused; a line whose currency code cannot be read still counts as another line; and the decisions file has one more column, the company's name. Its count of 17 securities whose symbol is also on another line was made with the ticker comparison; with the same text it is 1. ADR 0027 decides how the agent is run, lets it leave a security undecided, and says what a decision row needs.
- Date: 2026-11-26
- Supersedes: ADR 0005. Its measurements on why other shortcuts fail (the provider's "primary" flag, the country in the ISIN, the wording of a title) still stand and are not repeated here.

## Decision

For every instrument (ADR 0003) that has no listing and no stored decision, one of four things happens. Securities are taken in ISIN order, so two runs on the same data do the same.

| Outcome | When | Result |
|---|---|---|
| 1. Filled automatically | All six conditions below hold | The listing is written |
| 2. Market not served | The provider has no exchange in any home market of the security | No listing. Reported; nobody reviews it |
| 3. Not held | No fund holds the security: it was added by hand, or a newer filing dropped it | No listing. Reported; nobody reviews it |
| 4. On the report | Anything else | No listing yet. An AI agent decides each one |

Outcome 3 is tested first, then 2, then 1.

### The six conditions for filling automatically

| Condition | What it guards against |
|---|---|
| The security has one home market | A share held in Toronto and in New York: which line is the home one is a choice |
| Exactly one candidate line carries its ISIN | Several lines of one country under one ISIN, as when the provider gives a preferred series the common share's ISIN |
| That line trades in the currency the fund holds the security in | A second line of the same share in another currency, such as a US-dollar line in Toronto |
| No other candidate line has the same symbol | A duplicate line that carries no ISIN, as when the provider's KOSDAQ list repeats a KOSPI share |
| The fund gives no ticker, or its ticker equals the line's symbol | A provider line that carries the right ISIN on the wrong security |
| It is not a receipt case | A depositary receipt filled in place of the share: the ISIN is US-coded and a non-US fund holds it, or a holding line was filed under another ISIN than the instrument's (a receipt read as its ordinary share, ADR 0015) |

### Two markets decided on their own

Decided by the author on 2026-11-26.

| Market | Decision | How it is done |
|---|---|---|
| Germany | A German share is listed on Xetra | Only Xetra is an exchange of ours (ADR 0018), so a German share has one candidate line and the conditions above apply to it as to any other |
| Thailand | A foreign-board share does not take the line of the local share. It gets no listing | Each such security gets a `none` row in the decisions file, with the author as the one who decided, when the rule first runs on live lists |

### Terms

| Term | Meaning |
|---|---|
| Holding lines | The rows of `holding` that point at the instrument (ADR 0017) |
| Home market | A country one of the security's holding lines trades in (`holding.trading_country`). Most securities have one; a few are held in two |
| The provider serves a market | `provider_exchange` has a row for an exchange in that country (ADR 0002, ADR 0018) |
| Candidate line | A row of `provider_symbol` on an exchange in a home market. A line anywhere else is never a candidate |
| The line's currency | `provider_symbol.provider_currency`, with a sub-unit turned into its currency: `GBX` is `GBP`, `ZAC` is `ZAR`, `ILA` is `ILS`. The map is kept in the provider's client code. A line with a code that is neither a currency nor in the map is not a candidate, and is reported |
| The fund's ticker | `holding.ticker`, where the join rule of ADR 0016 attached one |
| Two tickers are equal | They are the same once both are put in upper case, everything but letters and digits is dropped, and leading zeros are dropped. `NOVO B` equals `NOVO-B`, `BRK.B` equals `BRK-B`, `700` equals `0700` |
| US-coded ISIN | An ISIN that starts with `US` |
| Non-US fund | A fund whose `scope` is `NON_US` |

### What the agent does

| Rule | What it means |
|---|---|
| One decision per security | For each security on the report, the agent picks one of the lines the report lists, or none. It never supplies an exchange or a symbol of its own |
| What the report lists | Every candidate line that matches by ISIN or by ticker, with the reason the security was not filled. For a receipt read as its ordinary share it lists every line that carries the instrument's ISIN, in any country: that security's holding line shows the receipt's market, not the share's |
| Names are evidence only | The report shows the provider's name for each line beside the company's name. A name never fills a listing by itself |
| It may search the web | For example to confirm that a ticker still belongs to the company |
| Decisions are kept in a file | `src/pyvalue/listings/decisions/listing.csv`, under version control and shipped with the package. One row per security: ISIN, outcome (`listing` or `none`), provider, provider exchange code, provider symbol, date, who decided, evidence. Keyed by the instrument's ISIN, because database ids change when the database is rebuilt |
| A decision is checked when it is applied | The line it names must be in `provider_symbol`. If it is not, the decision is not applied and the security is reported |
| Decisions are reused | A decided security is not put on the report again |
| The report is generated | A file under `data/`, not committed |

### What is written

| Row | Column | Value |
|---|---|---|
| `listing` | `mic` | The line's exchange (`provider_symbol.mic`) |
| `listing` | `ticker` | The fund's ticker, in upper case, when it equals the line's symbol. Otherwise the line's symbol |
| `listing` | `currency` | The line's currency, a sub-unit turned into its currency |
| `provider_listing` | `provider_symbol` | The line's symbol, exactly as the provider gives it |

| Rule | What it means |
|---|---|
| A run never changes a listing | A security that has a listing is skipped. A wrong listing is corrected by a decision and a rebuild |
| A clash does not stop the run | Two securities that would get the same exchange and ticker cannot both be written. The second is reported instead |

## Worked examples

What the legacy EODHD catalogue of October 2026 holds, and the outcome.

| Security | Holding line | Lines at the provider in the home market | Outcome | Why |
|---|---|---|---|---|
| SK Hynix, `KR7000660001` | Korea, KRW, ticker `000660` | `000660.KO`, with the ISIN | 1 | One line, ISIN and ticker agree |
| Novo Nordisk B, `DK0062498333` | Denmark, DKK, ticker `NOVO B` | `NOVO-B.CO`, with the ISIN | 1 | `NOVO B` equals `NOVO-B` |
| Toyota, `JP3633400001` | Japan, JPY | None: the provider has no Japanese exchange | 2 | Its Frankfurt, London and US lines are not candidates |
| SAP, `DE0007164600` | Germany, EUR, ticker `SAP` | `SAP.XETRA`, with the ISIN. Its Frankfurt and other regional lines are not stored | 1 | One line, ISIN and ticker agree |
| Bank of America, `US0605051046` | United States, USD, ticker `BAC` | `BAC.US` and `BAC-PS.US`, both with the ISIN | 4 | Several lines carry the ISIN: the provider gives a preferred series the common share's ISIN |
| Delta Electronics (Thailand), `TH0528A10Z14` | Thailand, THB, ticker `DELTA-F` | `DELTA.BK`, the local share, with another ISIN | 4, then none | Nothing found for the foreign-board share. The author's decision gives it a `none` row |
| Maybank, `MYL1155OO000` | Malaysia, MYR, ticker `MAYBANK` | `1155.KLSE`, with the ISIN | 4 | The ticker differs: the fund gives a letter code, the provider a number |
| Naspers, `ZAE000351946` | South Africa, ZAR, ticker `NPN` | `NPN.JSE`, with an older ISIN | 4 | No line has the ISIN; the ticker finds one, and the agent confirms it |
| Qfin Holdings, `KYG8851G1001` | United States, USD, filed under the receipt's ISIN `US88557W1018` | Not looked at | 4 | A receipt read as its ordinary share. The report lists every line with the ordinary share's ISIN |
| Barrick, `CA06849F1080` | Canada, the United Kingdom and the United States | Lines in several countries | 4 | Held in several markets |

## Evidence

Measured on 2026-11-26 on the 12,184 securities of today's database that VTI or VXUS hold. The legacy EODHD catalogue of October 2026 stands in for the provider's lists, without Germany's regional exchanges, and Vanguard's file of 31 October 2026 gives the tickers. The catalogue has no type column, so every line in it counted as a share.

### What the rule does

| Outcome | Securities |
|---|---|
| 1. Filled automatically | 8,147 (7,728 with ISIN and ticker agreeing, 419 by ISIN with no fund ticker) |
| 2. Market not served | 3,228 |
| 3. Not held | 0 |
| 4. On the report | 809 |

Why securities land on the report:

| Reason | Securities | Note |
|---|---|---|
| No line has the ISIN, but the ticker finds exactly one | 352 | The provider's line has no ISIN, or an older one |
| Nothing found in the home market | 233 | 114 are Thai and are settled by the author's decision above. The rest: United States 45, Brazil 18, mainland China 16, France 15, others 25 |
| One line has the ISIN but the ticker differs | 122 | 94 are Malaysian |
| Several lines carry the ISIN | 25 | Mostly US preferred series that carry the common share's ISIN |
| Held in several markets | 22 | |
| US-coded ISIN held by the non-US fund | 22 | |
| One line has the ISIN, but its symbol is also on another line | 17 | |
| A receipt read as its ordinary share | 15 | |
| One line has the ISIN, but in another currency | 1 | |

### The two markets decided on their own

| Finding | Measurement |
|---|---|
| German securities the two funds hold | 147. 146 have a Xetra line; 138 of those also have lines on regional exchanges with the same ISIN. One, Covestro, has only Frankfurt and Stuttgart lines |
| What Xetra-only changes | With the regional exchanges as candidates the rule fills 8,002 and sends 954 to the agent. Without them it fills 8,147 and sends 809 |
| Thai securities VXUS holds | 114, and none has a provider line with its ISIN. 110 carry a foreign-board ticker ending in `-F`, one a ticker ending in `-R`, three have no ticker |
| The local share at the provider | For 106 of the 110, the provider has a line under the same ticker without `-F`: the local share, with another ISIN |

### Against the rule of ADR 0005

On the same 12,184 securities the rule of ADR 0005 fills 4,373 automatically, finds 2,042 with no served market and sends 5,769 to the agent. Most of those 5,769 are securities with lines on several exchanges around the world, or with only a foreign line. Looking only at the home market settles them: the first kind is filled, the second is "market not served".

### How far a ticker can be trusted

| Finding | Measurement |
|---|---|
| Where the ISIN already identifies one line, Vanguard's ticker alone finds | The same line 7,298 times, a different line 13 times, several lines 21 times, nothing 124 times |
| Where no line has the ISIN and the ticker finds one | 267 such securities in the three-fund universe of ADR 0004: 119 of the lines carry no ISIN, 148 carry another one. Of 14 of those read one by one, most are the same company after a reverse split or a reorganisation (Wheels Up, `UP`); three have an ISIN that looks unrelated |

That is why a ticker confirms an ISIN match but never fills a listing alone: a reused ticker looks the same as a changed ISIN.

### What each new condition costs

| Condition | Securities it sends to the agent |
|---|---|
| No other candidate has the same symbol | 17 |
| One home market | 22 |
| Same currency | 1 |

## Why this design

- **The fund says where a security trades.** The filing gives the country (ADR 0016), so "which of the provider's many lines is the home line" is mostly answered before the provider is asked.
- **A stand-in line is never a candidate.** The author decided that a company whose home market the provider does not serve is left out, not analysed on a Frankfurt or US line. Looking only at the home market enforces that for the agent as well.
- **Two keys are safer than one.** The ISIN identifies the security and the ticker identifies the line. A listing is filled without review only where they do not contradict each other.
- **A missing ISIN at the provider is common,** so "exactly one line carries the ISIN" alone would not see a second line that lacks it. The conditions on the symbol, the currency and the single home market cover that.
- **The author's method:** fill when the ISIN gives one match; where it gives none, try the ticker, then the name; where there are several, report for an agent. This record adds the home market, lets the ticker propose but not fill, and keeps the name as evidence.

## Consequences

- **The first pass for the agent is about 700 securities:** 809 on the report, less the 114 Thai ones the author has decided. Under ADR 0005 it would be about 5,770 for the same securities.
- **Thailand leaves the screens.** Every Thai security VXUS holds is a foreign-board share, so none gets a listing. For 106 of them the provider has the local share; taking that line later would need a new decision.
- **About a quarter of the universe gets no listing at EODHD** because its market is not served: Japan 1,358, India 653, Hong Kong 536, Turkey 189, Saudi Arabia 104, and smaller markets. Those securities stay in the universe as instruments and are outside every screen until a provider serves their market.
- **The rule reads only the database:** `holding`, `fund`, `provider_symbol`, `provider_exchange` and `exchange`. The filing files are no longer needed when listings are filled.
- **A listing is as good as the filed country.** If a sponsor's adapter says the wrong country, the right line is never a candidate. The guard of ADR 0016 is the protection.
- **A security filled without a ticker rests on the provider's ISIN alone:** 419 today.
- **Receipts that are not US-coded are still not caught by the receipt condition.** The load keeps out the ones it recognises (ADR 0006, ADR 0014). A Thai or Swedish receipt filed as a common share, with one line in its own country, is filled.
- **An incremental run and a rebuild can differ.** A run never changes a listing, so a listing written from an older symbol list stays. A rebuild derives every listing again from the lists and the decisions.
- **The agent's decisions are data.** Kept in a committed file, they survive a rebuild and can be reviewed like any change.
- **The numbers are from a stand-in.** They have to be measured again on the live lists at the first run.

## Alternatives considered

| Alternative | Why not |
|---|---|
| The rule of ADR 0005: fill when the provider has exactly one line anywhere | It sends every security with lines abroad to the agent, 5,769 of these securities, and needs the trading currency from the filing files |
| Fill on a ticker match when no line has the ISIN | 148 of 267 such lines carry another ISIN. Most are the same company, but a reused ticker would be filled without anyone looking |
| Fill by company name | Name matching joins different companies: Pfizer Inc and Pfizer Ltd of India (ADR 0006) |
| Require a ticker for every automatic fill | 419 more securities for the agent, each with one ISIN match in its home market. The author's method fills those |
| Pick the provider's line with the highest trading volume | It needs prices, which a clean database does not have |
| Trust the provider's "primary" flag | Wrong or missing for 4.6% of the clear cases (ADR 0005) |
| Let the agent pick a line outside the home market | It would bring back stand-in lines |
| Take the fund's ticker as the listing's ticker in every case | A fund's ticker does not say which market it is for. Vanguard gives `ABX` for Barrick, which is its Toronto ticker; the provider's New York line is `B` |

## Not decided here

- How the agent is run, and which tools it is given besides web search.
- What makes a stored decision stale, beyond its line leaving the provider's list.
- A second provider for the markets EODHD does not serve.
