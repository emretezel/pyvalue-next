# ADR 0024: One command downloads the provider's symbol lists, another loads them

- Status: Accepted
- Date: 2026-11-26
- Changes: ADR 0018 in three points, listed under "What changes in ADR 0018". Its tables, its two files and its other rules stand.

## Decision

ADR 0018 decided what is stored. This record decides how it gets there.

| Topic | Decision |
|---|---|
| Two commands | `pyvalue symbols download` is the only thing that contacts the provider; it writes files and never the database. `pyvalue symbols load` reads files and writes the database; it cannot reach the network |
| The saved files | Under `data/eodhd/`: `exchanges.json` for the provider's exchange list and `symbols_<CODE>.json` for the symbol list of one exchange code, each the provider's answer as it arrived |
| The three exchange tables | The load adds what is missing in `exchange`, `provider` and `provider_exchange` and corrects a name or a country. It deletes nothing |
| A database that holds a row the files no longer have | Refused. The database has to be rebuilt, as for a security that is kept out (ADR 0013) |
| US over-the-counter lines | Left out, as Germany's regional exchanges are. Decided by the author on 2026-11-26 |
| The API key | Read from `[eodhd].api_key` in `private/config.toml`, by the download only. Sent to `eodhd.com` and to no other host, and never put into a message, a file name or a saved file |

## The download

| Rule | What it means |
|---|---|
| What is requested | The exchange list, then the symbol list of every code that has a market in `eodhd_exchange.csv`. About 60 requests |
| A file is whole or absent | An answer is written under a temporary name. It gets its final name only once it reads back as a list of the provider's shape |
| A suspiciously short answer does not replace a saved file | When the new list has at least 20 fewer lines than the saved one and fewer than half as many, the saved file stays and the code is reported. It is the test ADR 0018 has for the table |
| "Not found" | The provider answers so for an exchange that is not in the subscription. The code is reported and the other downloads go on |
| Any other failure | The run stops. What was saved before stays |
| The live exchange list is compared with the file | Reported: a code the provider offers that the file does not have, and a code the file maps to a market that the provider no longer offers. A code the file leaves out on purpose is not reported |
| The database | Not opened |

## The load

It works in this order.

1. **The two files are read and checked,** each row by row and one against the other: every market in the provider's file is one of ours, no market has two codes, and a code has either one row without a label or rows with labels.
2. **The exchange tables,** in one transaction. If the database holds an exchange or a mapping the files do not have, nothing is changed and the load stops. Otherwise missing rows are added and names and countries are corrected.
3. **Each code that has a market,** one after the other, each in a transaction of its own. A code without a saved file is reported as such.
4. **The report:** lines stored by code, lines not stored by reason, and every list that was not stored with why.

What happens to one line of a list:

| Line | Result |
|---|---|
| Its type is not `Common Stock` or `Preferred Stock` | Not stored. Counted by type in the report, so a new spelling of a type is seen |
| It has no symbol, or no currency at all | Not stored, and counted. The table cannot hold such a row |
| Its venue label has a row that leaves it out on purpose | Not stored, and counted |
| Its ISIN is missing or is not a valid ISIN | Stored without an ISIN |
| Its currency is a code we do not know, such as `Unknown` | Stored as given. The listing rule deals with it (ADR 0019) |
| Anything else | Stored, on the market its code and label give |

When a whole list is not stored. In each case the rows already stored for that code stay as they are, and the other lists are not affected.

| Case | What the report names |
|---|---|
| A share line carries a venue label the file does not know | Every such label, with the number of lines |
| A symbol appears twice among the lines to store | The symbols |
| The new list is suspiciously short against the stored one | Both counts. The test of ADR 0018 |
| The saved file is not a list of the provider's shape | The file |

A list that is stored replaces the stored rows of its code as a whole (ADR 0018). Running the load again with the same files changes nothing.

## What changes in ADR 0018

| Point | ADR 0018 | Now |
|---|---|---|
| Leaving out by venue label | Only a whole code can be left out, by a row without a market | A row with a label and no market leaves out the lines with that label. A code can mix such rows with rows that name a market |
| A line with a label the file does not know | "The download of that list stops" | The download always saves the answer. The load of that list stops, so adding a row to the file and loading again costs no request |
| A symbol twice in one list | Not decided | The list is not stored |

A line with no label at all, under a code whose rows carry labels, is treated as an unknown label. Whether EODHD sends such lines is one of the things the first live download shows (ADR 0018).

## Why

- **The author's rule is that no request goes to EODHD unless they ask for it.** The settings file holds a key, so a command that downloads whatever is missing would contact EODHD the first time it is run. With two commands, everything but one of them is safe to run at any time.
- **A subscription is bought for a month at a time.** What is downloaded in that month has to be enough to work with afterwards, so the files are the source and the database is filled from them.
- **A rebuild is cheap.** The lists are files, and loading them takes seconds. So the load does not need rules for deleting an exchange that listings may hang on; it refuses, as the universe load does.
- **A stopped load costs nothing.** The answer is already saved when a label turns out to be unknown. A stopped download would have cost a request and left nothing to look at.
- **Over-the-counter lines are not where the funds' securities trade.** The two funds hold exchange-listed shares. An over-the-counter line is a second line of a foreign share, or the line of a company that has left its exchange.

## Evidence

- **The legacy catalogue,** as stored on 2026-07-11: 71,322 lines under 70 codes. 20,578 are on Germany's six regional exchanges. The US code has 18,913.
- **US venue labels.** The legacy project did not keep the label of a symbol line. EODHD's fundamentals for the same US lines carried these: `PINK` 8,737, `NASDAQ` 3,836, `NYSE` 2,895, `OTCQB` 1,281, `OTCGREY` 539, `OTCQX` 517, `OTCCE` 484, `AMEX` 272, `US` 163, `OTCMKTS` 99, `BATS` 34, `NYSE ARCA` 28, `NYSE MKT` 25, `OTCBB` 3. About 11,700 are over-the-counter.
- **"Not found" means "not in the subscription".** The legacy client met HTTP 404 for exchanges outside the plan and treats it so.
- **A stub answer.** On 2026-07-11 EODHD answered for a dropped exchange with HTTP 200 and 30 lines (ADR 0018).
- **The key is part of the address.** EODHD takes it as the query part `api_token`. The download helper as it stood put the address into its error message, and did not catch the error Python raises for a malformed address, whose text quotes the address. Tried on 2026-11-26 without a request.
- **No raw answer exists to test against.** The legacy project stored neither endpoint's answer, so the sample files of the tests are made up in the provider's shape.

## Consequences

- **The first live download is run by the author,** in a subscription month. Until then the US labels in the file are an expectation, and the US list may stop on its first load.
- **Refreshing is the same command.** A later download replaces each saved file, unless the new answer is suspiciously short.
- **Taking an exchange or a code out of the files needs a rebuild:** set the database aside, `pyvalue db migrate`, `pyvalue universe load`, `pyvalue symbols load`. No request is made.
- **A new venue label stops one list** until a person adds a row for it, with a market or without.
- **The database does not say when a list was downloaded.** The file's date does.
- **The download helper is shared.** It moves out of the universe load, takes secret parts of an address that it sends and never shows, and tells "not found" from every other failure.

## Alternatives considered

| Alternative | Why not |
|---|---|
| One command that downloads what is missing and then loads, as `pyvalue universe load` does | It would contact EODHD when run on a folder without saved lists, which the author's rule forbids |
| A `--refresh` option on one command | The same accident, one typed word away |
| Make the tables equal to the files, deleting what left them | Deleting an exchange needs rules for the listings on it, and correcting a code in place would move its stored symbols under the new code. A rebuild does it in seconds |
| Stop the download on an unknown label, as ADR 0018 had it | The request is spent and nothing is saved to look at |
| Keep the first of two lines with one symbol | Which of the two is the right one is not something the load can know |
| Store over-the-counter lines under their own market | A delisted company would be filled on such a line, and a foreign share would get a second US candidate to rule out |

## Not decided here

- The rows of the two files. They are written with the code (ADR 0018).
- What to do with a US share line that carries no label, should EODHD send any.
- How a listing is determined from the stored lines (ADR 0019).
