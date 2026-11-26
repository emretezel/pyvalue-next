# ADR 0026: One command fills the listings; a security waits for a missing symbol list, and decisions come first

- Status: Accepted
- Date: 2026-11-26
- Changes: ADR 0019 in the points listed under "What changes in ADR 0019", and ADR 0018 in one index. The rule of ADR 0019, its six conditions, its terms and what it writes stand.

## Decision

ADR 0019 decided how a listing is determined. This record decides how that is run, and settles what ADR 0019 left open.

| Topic | Decision |
|---|---|
| One command | `pyvalue listings fill` reads the database and the decisions file, and writes `listing` and `provider_listing`. It cannot reach the network |
| A fifth outcome: waiting for a symbol list | A security waits when an exchange code of one of its home countries has no stored symbol list. It gets no listing and is not put on the report |
| "The same symbol" | The same text, letter for letter. The ticker comparison of ADR 0019 is for a fund's ticker against a symbol only |
| Decisions come first | The decided securities are handled first, then the rule, each in ISIN order |
| What a decision may name | A line in a home market of the security or, for a receipt read as its ordinary share, a line that carries the share's ISIN |
| A stored listing that contradicts a decision | The command stops before it writes anything. The database has to be rebuilt |
| The decisions file | One more column than ADR 0019 lists: the company's name, for the reader |
| The report | `data/listings/cases_for_agent.csv`, one row per security and line it could be |
| The ISIN index of `provider_symbol` | Dropped. Nothing reads it |

## The run

The command does this, in one transaction.

1. **It reads** the securities, their holding lines, the funds, the exchanges, the provider's exchange codes and symbol lines, and the listings that exist.
2. **It stops** if a stored listing contradicts a decision: the decision says `none`, or it names another line than the one the listing was written from.
3. **It sorts every security.** The first row of the table below that fits is the security's outcome.
4. **It applies the decisions,** in ISIN order.
5. **It applies the rule of ADR 0019** to the securities that are left, in ISIN order.
6. **It writes** a `listing` row and a `provider_listing` row for each security that was filled.
7. **It writes the report and prints the counts.**

| Outcome | When | Result |
|---|---|---|
| Has a listing | A `listing` row exists | Skipped. A run never changes a listing (ADR 0019) |
| Not held | No holding line points at the security | No listing. Counted |
| Market not served | The provider has no exchange code in any home country | No listing. Counted by country |
| Waiting for a symbol list | An exchange code of a home country has no stored line | No listing, not on the report. Counted by country, and the codes are named |
| Decided | The decisions file has a row for the security | What the row says, or the report when the row cannot be applied |
| For the rule | Anything else | Filled when the six conditions of ADR 0019 hold, otherwise on the report with a reason |

A decision is looked at only for a security that is held, served and not waiting. Until then it is neither applied nor called out of date.

### When a decision is not applied

The security goes on the report with the reason, and the lines the rule would show for it.

| Reason | When |
|---|---|
| The line is not stored | `provider_symbol` has no line with the decision's provider, exchange code and symbol |
| The line is not one the report could show | It is on an exchange outside the security's home countries, and it is not a line with the share's ISIN for a receipt read as its ordinary share |
| The line's currency cannot be read | The provider's code is neither a sub-unit in the map nor three capital letters |
| The exchange and ticker are taken | Another security already has that pair. The report names it |

The last reason also applies to a security the rule would fill.

### The report

One row per security on the report and line it could be; a security with no such line has one row with the line's cells empty.

| Column | Meaning |
|---|---|
| `isin`, `company` | The security |
| `reason` | Why it was not filled |
| `detail` | What the reason refers to: the line a decision names, or the security that holds the exchange and ticker |
| `trading_countries`, `fund_tickers`, `fund_currencies` | What the holding lines say. Several values are separated by `\|` |
| `matched_by` | Why the line is shown: `isin`, `ticker`, `isin and ticker`, or `symbol` for a line that shares the symbol of the line with the ISIN |
| `provider_code`, `provider_exchange_code`, `provider_symbol` | The line, as a decision names it |
| `mic`, `provider_name`, `provider_currency`, `provider_isin` | What the provider says about the line |

The lines shown are the ones ADR 0019 names: every line in a home market that matches by ISIN or by ticker and, for a receipt read as its ordinary share, every line that carries the share's ISIN, in any country. The rows are in the order of ISIN, exchange code and symbol, so the same database and decisions give the same bytes.

### The decisions file

`src/pyvalue/listings/decisions/listing.csv`, shipped with the package.

| Column | Meaning |
|---|---|
| `isin` | The security. No two rows are about the same one |
| `outcome` | `listing` or `none` |
| `provider_code`, `provider_exchange_code`, `provider_symbol` | The line, for `listing`. Empty for `none` |
| `company` | The company's name, for the reader. The command does not use it |
| `decided_on` | The day of the decision |
| `decided_by` | Who decided: the author or the agent |
| `evidence` | What the decision rests on |

## How ADR 0019 is read

Where its wording leaves room.

| Point | Reading |
|---|---|
| A security with several holding lines | Every ticker the lines give must equal the line's symbol, and every line must be held in the line's currency |
| The ticker that is written | The fund's ticker in capital letters, when every ticker the holding lines give equals the symbol and they are spelled alike. Otherwise the symbol in capital letters. `provider_listing.provider_symbol` is the symbol exactly as the provider gives it |
| What a currency is, for a provider's code | A sub-unit in the map, turned into its currency, or three capital letters |
| A line whose currency code cannot be read | It can never become the listing. It still counts when the rule asks whether another line carries the same ISIN or symbol. Such lines are counted by code |
| Two tickers that are equal | As ADR 0019 says, with one addition: a ticker of which nothing is left once everything but letters and digits is dropped equals nothing |
| The reason for a security that fails several conditions | The first of: a receipt read as its ordinary share; a US-coded ISIN in the non-US fund; several home markets; several lines with the ISIN; no line with the ISIN (the ticker finds one, several, or nothing); the line is in another currency; its symbol is on another line; the ticker differs |
| A decision for an ISIN that is not in the universe | Counted and named, not an error |
| A receipt read as its ordinary share whose receipt trades in a market that is not served | Market not served, by the order above |

## What changes in ADR 0019

| Point | ADR 0019 | Now |
|---|---|---|
| Outcomes | Four | Five: a security can be waiting for a symbol list |
| "No other candidate line has the same symbol" | Not said how symbols are compared. Its count of 17 was made with the ticker comparison | The same text |
| The order | "Securities are taken in ISIN order" | The decided ones first, then the others, each in ISIN order |
| A decision's line | "The line it names must be in `provider_symbol`" | It must also be a line the report could show |
| A security that has a listing and a decision | "A wrong listing is corrected by a decision and a rebuild" | The command refuses a database in which the two disagree |
| A candidate line | "A line with a code that is neither a currency nor in the map is not a candidate" | Such a line cannot become the listing, but it is still counted as another line |
| The columns of the decisions file | Eight | Nine: the company's name is added |

## What changes in ADR 0018

The index `provider_symbol_isin` is dropped. ADR 0018 named "the lines that carry a given ISIN, the first lookup of the listing rule" as its query. The rule does not make that query: it reads the provider's lines once and looks them up in memory.

## Why

- **A missing list is not an unserved market.** The exchange file was written without a subscription (ADR 0018), and ADR 0024 expects that the US list may stop on its first load. If the rule ran on a country whose list is missing, every security there would go to the agent as "nothing found", and the agent would be asked to decide what a later load settles by itself.
- **Half of a country's lines is not enough.** Korea, mainland China, Taiwan and Canada have two or three exchange codes each. The rule asks whether a line is the only one; it cannot know while a list is missing.
- **A code the provider never offers has a remedy.** The download reports it (ADR 0024). The code is taken out of the exchange file, the database is rebuilt, and the market is then "not served".
- **The ticker comparison is loose on purpose,** because a fund and a provider write the same ticker differently. Two lines of one provider are written by one hand: a duplicate is spelled the same.
- **A chosen line should win.** When two securities want one exchange and ticker, the one a person or the agent decided is written, and the automatic one is reported.
- **Stand-in lines stay out.** ADR 0019 looks only at the home market so that a company is never analysed on a foreign line, and says so "for the agent as well". Checking the decision's line is where that is enforced.
- **The database and the files agree, or the run stops.** That is the rule of the universe load (ADR 0013) and of the symbols load (ADR 0024).
- **An index needs a reader.** The whole table is some 39,000 rows and is read in a fraction of a second. A lookup per security would read the lines of a country again for every security in it, because the ticker comparison cannot be done by the database.

## Evidence

Measured on 2026-11-26 on a copy of the database that held the legacy EODHD catalogue of October 2026, loaded through the symbols load: 11,704 securities and 38,917 lines under 58 exchange codes. The catalogue has no type column, so every line in it counted as a share. The US venue label `US`, which 163 lines carry and the exchange file does not have, was left out for the trial.

| Outcome | Securities |
|---|---|
| Filled automatically | 7,898 (7,490 with ISIN and ticker agreeing, 408 by ISIN with no fund ticker) |
| Market not served | 3,110: Japan 1,306, India 645, Hong Kong 530, Turkey 175, Saudi Arabia 103, Israel 87, Italy 84, Singapore 47, United Arab Emirates 42, New Zealand 26, Kuwait 24, Qatar 21, Iceland 15, Colombia 6. The countries add up to 3,111: one security is held in two of them and is counted under both |
| Waiting for a symbol list | 0 |
| Not held | 0 |
| On the report | 696 |

| Reason | Securities |
|---|---|
| No line has the ISIN, but the ticker finds exactly one | 340 |
| Nothing found in the home market | 170, of which 107 are Thai |
| One line has the ISIN, but the ticker differs | 116 |
| Held in several markets | 22 |
| US-coded ISIN held by the non-US fund | 22 |
| Several lines carry the ISIN | 17 |
| A receipt read as its ordinary share | 7 |
| One line has the ISIN, but in another currency | 1 |
| One line has the ISIN, but its symbol is also on another line | 1 |

| Finding | Measurement |
|---|---|
| "The same symbol" by the ticker comparison | 16 securities instead of 1. The 15 others are London shares such as RS Group (`RS1`), Associated British Foods, Marks & Spencer, Next and ITV. London gives a foreign share a code that starts with a zero, and the comparison drops leading zeros: `RS1` then equals `0RS1`, the line of a German company in euros |
| Countries with several exchange codes | Canada (`TO`, `V`, `NEO`), mainland China (`SHG`, `SHE`), Korea (`KO`, `KQ`), Taiwan (`TW`, `TWO`) and Zimbabwe. 3,278 securities trade in the first four |
| Securities in a served country, on the local database, where no list is stored | 8,594. All of them wait |
| Securities with several holding lines | 28. In none do the lines give different tickers, or different currencies in one country |
| Currency codes in the catalogue | All are three capital letters. Sub-units: `GBX` on 1,386 lines, `ZAC` on 236 |
| Symbols in small letters | None |
| Time for the rule on all securities, in memory | Under a second |

## Consequences

- **Before the first download, the command fills nothing.** On the local database 8,594 securities wait and 3,110 are in a market that is not served. The report is empty.
- **A list that fails to load holds its whole country back,** and for a country with several codes, one missing list holds back the others. The command names the codes.
- **A code without a single share line would hold its country back for good.** It has to be taken out of the exchange file.
- **Running the command again changes nothing,** and writes the same report.
- **A rebuild ends with this command:** `pyvalue db migrate`, `pyvalue universe load`, `pyvalue symbols load`, `pyvalue listings fill`.
- **The agent's first pass is about 590 securities** on the legacy lists: 696 on the report, less the 107 Thai ones the author has decided (ADR 0019).
- **A decision can go out of date.** When its line leaves the provider's list, the security comes back on the report.
- **The numbers are from a stand-in,** as in ADR 0019. They are measured again on the live lists.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Count a market as served only when a list is stored for it | A list that failed to load would look like a market the provider does not have, and nobody reviews those. A country with several codes would count as served with one list of three |
| Leave ADR 0019 as it is and let the securities of a missing list go to the agent | Thousands of cases that a later load settles by itself |
| Compare symbols with the ticker comparison, as ADR 0019's count did | 15 securities go to the agent because of a zero in front of another company's code |
| One pass in ISIN order, decided or not | An automatic fill could take the exchange and ticker a decision names, only because its ISIN sorts first |
| Apply a decision's line wherever it is | The agent could bring a stand-in line back |
| Skip a security whose listing differs from its decision, without a word | The database would disagree with the file, and nobody would know |
| Keep the ISIN index for a lookup by hand | A person's query on 39,000 rows needs no index |
| Look the lines up with one query per security | More statements, slower, and the ticker comparison still has to be done in memory |
| Keep the decisions file at the eight columns of ADR 0019 | Its rows could not be reviewed without looking every ISIN up |
| A second file for the securities whose market is not served | The counts by country say it. The securities are one query away |

## Not decided here

- How the agent is run (ADR 0019).
- The `none` rows for Thailand. They are written when the rule first runs on live lists (ADR 0019).
- What makes a decision out of date beyond its line leaving the list (ADR 0019).

## Appendix: SQL

The statement of migration `0007_provider_symbol_drop_isin_index`, for SQLite.

```sql
DROP INDEX provider_symbol_isin;
```
