# ADR 0005: A listing is filled by one narrow rule; every other case is decided by an agent

- Status: Accepted
- Date: 2026-11-20

## Decision

For every instrument (ADR 0003), the listings the data provider has for the instrument's ISIN are looked up. EODHD is the first provider. The lookup does not ask the provider about one instrument at a time: the provider's list of symbols is downloaded for each exchange it serves, and the instruments are matched against those lists by ISIN. "The provider returns" below means what that match finds. What happens next depends on it.

| Case | When | Result |
|---|---|---|
| 1. Filled automatically | All three hold: the provider returns exactly one listing; that listing's exchange is in a trading country of the instrument; and the ISIN is not a US-coded one held by a non-US fund | The listing is written |
| 2. Home market not served | The provider returns nothing, and it serves no exchange in any trading country of the instrument | No listing. The instrument is reported as "home market not served". Nobody reviews it |
| 3. On the report | Anything else | No listing yet. The instrument goes on a report, and an AI agent decides each one individually |

Terms used above:

| Term | Meaning |
|---|---|
| Trading country | The country of the currency in which a fund holds the security: HKD is Hong Kong, KRW is Korea, USD is the United States. For a line held in euros it is the country in the first two letters of the ISIN, when that is a euro-area country; otherwise it is unknown. A security held in two currencies has two trading countries. It is never the country where the fund itself is listed. |
| The provider serves an exchange | The exchange has a `provider_exchange` row for that provider (ADR 0002). |
| US-coded ISIN | An ISIN that starts with `US`. |
| Non-US fund | A fund whose scope in ADR 0004 is "Non-US": VXUS and DFAX. |
| The report | The instruments in case 3, each with what the provider returned and why case 1 did not apply. |

What the agent does:

| Rule | What it means |
|---|---|
| One decision per instrument | For each instrument on the report, the agent picks one of the listings the provider returned, or none. It never supplies an exchange or a ticker of its own. |
| It may search the web | The agent may use web searches to decide, for example to find a company's home exchange. |
| Decisions are kept in a file | Each decision is one row in a file under version control: the ISIN, the outcome (a listing, or no listing), the chosen exchange and ticker, the reason, who decided, and the date. The file is keyed by ISIN because database ids change when the database is rebuilt. |
| Decisions are reused | A decided instrument is not put on the report again. A later load of the funds puts only new instruments on it. |
| The report is generated | It is a file under `data/`, not committed: the instruments in case 3 that have no row in the decisions file. |
| What is not in the file | Listings filled by case 1 and instruments in case 2. Both are recomputed on every run. |
| The first pass tests a wider rule | The agent's choices for instruments with several listings are compared with the choice "the listing in the trading country". If they agree, a later record can widen case 1. |

## Worked examples

What the legacy EODHD catalogue holds for eight real securities, and the case each falls into.

| Security | Held in | Lines at the provider | Case | Why |
|---|---|---|---|---|
| Realtek, `TW0002379005` | TWD | 1: Taiwan | 1 | One line, in Taiwan. Filled |
| SK Hynix, `KR7000660001` | KRW | 1: Korea | 1 | One line, in Korea. Filled |
| State Bank of India, `INE062A01020` | INR | none | 2 | Nothing returned, and EODHD has no Indian exchange |
| Apple, `US0378331005` | USD | 11: US, seven German exchanges, London, Mexico, Buenos Aires | 3 | Several lines |
| Toyota, `JP3633400001` | JPY | 8: six German exchanges, London, US | 3 | Several lines, none of them in Japan |
| Orix JREIT, `JP3040880001` | JPY | 1: Frankfurt | 3 | One line, but not in Japan |
| Qfin Holdings, `US88557W1018`, held by VXUS | USD | 1: US | 3 | A US-coded ISIN in a non-US fund. It is a depositary receipt, and nothing in the filing says so |
| Waste Connections, `CA94106B1013` | USD and CAD | 4: Toronto, US, two German exchanges | 3 | Several lines |

Orix JREIT and Qfin show what the count of lines alone would get wrong: each returns exactly one line. For Orix JREIT that line is a foreign stand-in. For Qfin it is the line of a receipt, which an agent should look at before it is accepted.

## Evidence

Measured on 2026-11-20 on the 15,979 instruments that the load of ADR 0006 produces from the three funds. The legacy EODHD catalogue, refreshed 2026-07-11, stands in for the provider's answer. It was built from the same per-exchange symbol lists this record chooses.

Nothing here could be checked against the live provider. On 2026-11-20 five test calls were made with the expired key. The account call answered and showed a daily limit of 20 calls. The exchange list, a symbol list, the search by ISIN and the identifier mapping each returned HTTP 401. EODHD's documentation lists all four as available on its free plan.

### What the rule does

| Case | Instruments |
|---|---|
| 1. Filled automatically | 6,002 |
| 2. Home market not served | 3,222 |
| 3. On the report | 6,755 |

Why instruments land on the report:

| Reason | Instruments |
|---|---|
| Several listings returned | 5,247 |
| One listing returned, outside the trading country | 782 |
| Nothing returned, although the trading country is served | 654 |
| US-coded ISIN held by a non-US fund | 59 |
| Trading country unknown (a line held in euros whose ISIN is not from a euro-area country) | 13 |

Case 2 by trading country: Japan 1,250, India 992, Turkey 213, Hong Kong 212, Saudi Arabia 150, Israel 149, United Arab Emirates 65, Singapore 56, Kuwait 47, Qatar 37, others 51.

### Why each condition of case 1 is there

| Condition | What happens without it |
|---|---|
| Exactly one listing returned | A choice among several lines is made by rule. The author wants an agent to see every such case first. 44% of the securities found in the catalogue have two or more lines. |
| The listing is in a trading country | 782 instruments are filled with the only line the provider has, which is a foreign one. 340 of them are held in yen and 222 in Hong Kong dollars, and their single line is Frankfurt. |
| Not a US-coded ISIN in a non-US fund | A depositary receipt with one clean US line is filled without anyone looking at it. |

### The US-coded ISINs in the non-US funds

An American depositary receipt always carries a US-coded ISIN, so in a fund of non-US companies the code finds every one of them, whatever the filing says. The load of ADR 0006 has already kept out 145 receipts whose company is in the universe on its own shares. 59 US-coded ISINs remain:

| What it is | Count | Example | What the agent has to decide |
|---|---|---|---|
| Receipt the load recognised and kept, because the company has no other line | 38 | PDD, Vipshop, Sberbank | Whether the US line is the company's main listing (the Chinese companies listed in New York) or the receipt gets no listing (the frozen Russian ones) |
| Not recognised by the load's receipt check | 15 | Kanzhun, Qfin, Tuya, Yum China | Whether it is a receipt at all, and if so whether the home share is in the universe |
| US company that a non-US fund holds on a second line abroad | 6 | International Paper in London | Nothing new: the US line; VTI holds it too |

VTI was checked separately: no VTI company with a legal-entity identifier appears in the non-US funds under a different ISIN, apart from one contingent value right.

### Why other shortcuts were not used

| Shortcut | Measurement |
|---|---|
| The provider's own "primary" flag | On 10,179 securities with exactly one line in the trading country, the flag was missing, doubled or on another line for 469 (4.6%). |
| The wording of the title or the filing's label | Used at load (ADR 0006), but not relied on here: Vanguard's titles name only 52 of its 64 receipts, and the load's check leaves 15 US-coded ISINs unrecognised. |
| The country in the ISIN | About 940 securities are incorporated in one country and listed in another: 340 Cayman, 221 mainland China and 84 Bermuda companies listed in Hong Kong. |
| The country field of the filing | Vanguard writes where the security trades, Dimensional where the company is incorporated (ADR 0004). |

## Why this design

- **The filing does not name an exchange.** It gives the ISIN and the trading currency. The exchange and ticker have to come from a lookup.
- **One ISIN usually trades in several places**, so "does this ISIN have another listing" is the wrong question. ADR 0003 already allows only one listing per instrument. The question is which line is the home line.
- **That cannot be known for certain from any single source.** "Primary listing" is not a registered fact worldwide. So the automatic rule is kept to the case where the evidence agrees from two sides: the provider has one line, and it is where the fund holds the security.
- **A wrong line for the right ISIN is a small mistake.** It is the same share of the same company. The costly mistake is analysing a depositary receipt in place of the share, and a receipt always has its own ISIN, which is why the receipt condition exists.
- **The author's method**: fill when the lookup returns one listing, otherwise report, and let an AI agent decide each reported case. The two further conditions were added after the measurement above and agreed on 2026-11-20.

## Consequences

- **The first pass is large.** About 6,750 instruments go to the agent. Later loads bring only new instruments.
- **About a fifth of the universe gets no listing at EODHD without review**, and more will follow from the agent's "no listing" decisions. They stay in the universe as instruments and are outside every screen until a provider serves their market.
- **The rule needs data from the holdings filings** when listings are filled: the trading currency of each line and the scope of each fund. Nothing of that is in the database (ADR 0006), so the filing files have to be at hand.
- **The rule depends on reference data being right**: the country of each exchange (ADR 0001), which exchanges the provider serves (ADR 0002), and which country a currency belongs to.
- **The agent's decisions are data.** They cannot be recomputed by code. Kept in a committed file, they survive a rebuild of the database, can be reviewed like any change, and carry their history. Together with the three filings they rebuild the whole universe.
- **A file has no constraints.** The code that applies the decisions checks every row, and a test checks the file's format.
- **Receipts that do not carry a US code are not caught by the receipt condition.** The load keeps out the ones Dimensional labels. A Thai or Swedish receipt that Vanguard files as a common share, with one line in its own trading country, is filled automatically. Known exposure: 87 Thai companies appear under two ISINs, a local and a foreign-board share, and both could get a listing.
- **The agent cannot add a listing the lookup did not find.** 654 instruments return nothing although their trading country is served, either because the provider's list has no ISIN for the line or because it does not have the security. For those the agent can only decide "no listing", even where a web search shows the provider has the stock.
- **Listings can only be filled while a subscription is active.** The lookup endpoints refuse an expired key.
- **The evidence is from a stand-in.** The numbers above have to be re-measured against the live provider at the first load.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Fill whenever exactly one listing is returned | 782 foreign stand-in lines and some receipts would be filled, and nothing would flag them. It breaks the earlier decision that a company is never analysed on a stand-in line. |
| Fill the one listing in the trading country even when several are returned | It fills about 10,200 automatically and leaves about 1,200 for review. Not adopted yet: the author wants the agent to see every case with several listings. The first pass will show whether it is safe. |
| Trust the provider's "primary" flag | Wrong or missing for 4.6% of the clear cases. |
| A person reviews the report | The author chose an agent. Nothing stops a person from correcting a decision. |
| One query to the provider per instrument | The author's first method. About 16,000 requests for a full pass, against about 65 for the symbol lists, for the same information. |
| Let the agent name an exchange and ticker itself | It could then write a listing the provider never offered. The author limits it to the returned listings. |
| Add official sources to the rule (the EU regulator's register of most relevant markets) | Not needed for a rule this narrow. The agent may use them. |

## Not decided here

- The path of the decisions file. It must be a place an installed copy of pyvalue can find.
- How the agent is run, and which tools it is given besides web search.
- Whether the agent may also pick a line from the provider's symbol list that carries no ISIN. It would recover some of the 654 instruments that return nothing.
- How a provider's exchange code and symbol are turned into the `mic` and `ticker` of a listing. EODHD's `US` code covers several exchanges. This needs the live symbol lists.
- Where the currency-to-country reference is kept.
- What makes a stored decision stale, such as a listing that disappears at the provider.
