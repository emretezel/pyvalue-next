# ADR 0028: Fundamentals payloads are downloaded into files, one per listing

- Status: Accepted
- Date: 2026-11-27
- Changes: ADR 0024 in one point: `pyvalue symbols download` is no longer the only thing that contacts the provider. It settles what ADR 0002 and ADR 0018 left open on raw provider payloads. Everything else in the three records stands.

## Decision

EODHD answers one request per listing with the company's whole history of financial statements. This record decides how those answers are fetched and kept. Reading them into tables is a later decision.

### Where a payload is kept

| Topic | Decision |
|---|---|
| Storage | Files, not the database: one file per provider line under `data/eodhd/fundamentals/`. No table and no migration |
| The file | `<CODE>/<SYMBOL>.json.gz`: the provider's exchange code and symbol, as the provider has them |
| Unusual characters | In a file or folder name every character outside `A-Z`, `0-9`, `-` and `_` is written as `%XX`, byte by byte: `PE&OLES` is kept as `PE%26OLES`. A small letter is written that way too |
| What is kept | The answer's bytes as they arrived, gzip-compressed. The same answer always gives the same file |
| What gets a file | Only an answer that reads as a JSON object whose `General.Code` is the symbol that was asked for |
| A file is whole or absent | It is written under a temporary name and then renamed, as for the symbol lists (ADR 0024) |
| History | One payload per line. pyvalue keeps no older copy |
| A saved payload is never overwritten | To fetch one again, a person sets its file aside; to fetch all again, the folder. The command then downloads what is missing. No refresh option is built |
| The record that a listing was downloaded | Its file. Nothing is written to the database |

### The run

`pyvalue fundamentals download` is the second command that contacts the provider.

| Topic | Decision |
|---|---|
| What is requested | The payload of every provider line that a listing is on and that has no file. Two listings on one line share one request and one file |
| The listings | Read from the database through the view `provider_listing_address` (ADR 0002). The run reads the database and never writes it |
| The key | As in ADR 0024: read from `[eodhd].api_key`, sent to `eodhd.com` only, never in a message, a file name or a saved file. It is read only when at least one line needs a request |
| Concurrency | 8 threads in one process. No second process, and no pacing between requests |
| Batches | The lines are taken in batches of 500, in the order of exchange code and symbol |
| "Not found" | The provider has nothing for the symbol. The listing is reported and is asked again on the next run |
| An answer that is not a payload for the symbol | Not kept. The listing is reported |
| A request that fails | The listing is reported and the run goes on |
| When the run stops by itself | After a batch in which more than half the requests failed. "Not found" is an answer, not a failure |
| The report | `data/fundamentals/not_downloaded.csv`, rewritten by every run: one row per listing without a saved payload, with the reason |
| Progress | Decided by the author on 2026-11-27: one progress bar on one line, redrawn in place after every request. The counts are printed once, at the end. Nothing is drawn when the output is not a terminal |

### The daily allowance

| Topic | Decision |
|---|---|
| When it is asked | Before every batch. The account request costs nothing |
| What fits | (daily limit − used today − 5,000) ÷ 10 requests, and never fewer than none. The 10 is what one fundamentals request costs |
| "Used today" | The account's counter, or 0 when the counter's date is an earlier day by GMT, which is when EODHD starts a new day |
| When nothing fits | The run ends. The lines that are left are reported, and a later run takes them |
| The extra reserve | Never counted. EODHD draws on it once a day's allowance is used up, so the run stops 5,000 short of that |
| The account answer | It names the account holder. Only the daily limit, the used count and its date are read. The answer is never saved or printed |
| The account request fails | The run stops there. What was saved stays |

## Evidence

Measured on 2026-11-27 with 21 requests through pyvalue's own client: 20 fundamentals requests and one price request.

| Finding | Measurement |
|---|---|
| Cost of a fundamentals request | 10 of the daily 100,000: the account's counter went 65, 75, 85, 95, 105 over four requests |
| Cost of the account request | Nothing: the counter did not move, and it showed each fundamentals request at once |
| All 8,309 listings | 83,090 of the allowance, so one day covers them |
| Size of a payload | 105 KB to 989 KB on 20 listings; 446 KB on average over the 16 that were not picked by name. About 3.7 GB for all |
| Compression | gzip brings a payload to about 10%: about 370 MB for all |
| One request | 0.6 to 0.9 seconds, so about two hours one after another |
| 8 threads | 16 requests in 1.9 seconds: about 500 a minute, and about 15 minutes for all |
| The limit per minute | 1,200, and a fundamentals request counts as 1 against it. Read from the answer's headers |
| The payload names its symbol | `General.Code` was the symbol asked for in 20 of 20 |
| The payload's own ISIN | Missing on all six US payloads, present on the 14 others |
| Symbols with an unusual character | One of the 8,309 (`PE&OLES`). No two differ only by upper and lower case. One stored line that no listing is on has small letters |
| Two listings on one line | None today. The schema does not prevent it (ADR 0002) |
| The extra reserve | 74,094 requests on the account |
| Prices | The price request was refused (`403`): the subscription has fundamentals only |
| The legacy project | It kept 71,258 payloads in a table of its 43.6 GB database: 169 KB at the median on a sample of 600. It downloaded on 16 threads, which needed a single writer for SQLite, and kept a table of failed requests |

## Why

- **The database is rebuilt from saved files.** A rebuild sets `data/pyvalue.db` aside and downloads nothing. Payloads inside the database would be lost with it, and they are the one thing that cannot be fetched again outside a subscription.
- **Files remove the single-writer problem.** Each thread writes its own file, so nothing has to queue for the database.
- **Threads are enough.** The work is waiting for the network. Eight of them stay at less than half the limit per minute without any pacing.
- **The smallest thing that works.** A saved file is the state. There is no table of what was fetched, no refresh option and no schedule.
- **Never overwriting keeps the choice with the author.** A folder set aside can be compared with the new one before anything is deleted, and kept for as long as it is wanted.
- **The reserve must not be spent by accident.** Asking before every batch works from the account's own counter, so it also holds when another run uses the key or a request costs more than was measured. The margin of 5,000 covers one batch at twice the cost.
- **A batch rule cannot depend on timing.** Counting failures per batch gives the same result on every run. One timeout does not stop 8,000 requests, and a refused request does not make 8,000.
- **No dependency for a progress bar.** pyvalue has no runtime dependency, and one redrawn line needs none.

## Consequences

- **`pyvalue symbols download` is no longer the only thing that contacts EODHD.** The rules for the key are the same for both commands.
- **About 370 MB under `data/eodhd/fundamentals/`,** which is never committed. It is the only copy outside a subscription, so it is worth a backup.
- **A full download costs most of a day's allowance.** Two on the same day do not fit.
- **A refresh is a person's act.** Until it has finished, the new folder is incomplete. One cut short by the allowance stays so until the next day.
- **A symbol EODHD has nothing for is asked again on every run,** ten of the allowance each time if EODHD charges for it. How many there are is measured at the first run.
- **A payload for a listing that is gone stays in the folder.** The run finds a payload by its listing's file name and ignores every other file.
- **A stale listing gets a payload like any other.** Whether a payload belongs to the security is for the step that reads it. The payload's own ISIN cannot settle it for US lines.
- **The bar shows only on a terminal.** Plain `conda run` holds output back until the end; `conda run --no-capture-output`, or an activated environment, shows it.
- **File names are safe on macOS and Linux.** Windows reserves a few names that are symbols, such as `CON`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A table that holds the payloads | Lost at every rebuild. The database would grow from megabytes to gigabytes, and every copy of it with it |
| Several processes | Nothing here needs a second processor. They would need a single writer if the payloads were in SQLite |
| A table of fetch state: failures, when to try again | A saved file already says what is done. Tried again only if the first run shows a cost |
| Replace a payload in place, or an option such as `--older-than` | More code, and the older payload is gone before the new one has been looked at |
| Keep every download | The payload carries the full history. The author may keep a folder that was set aside |
| Ask the account once, at the start | A second run, or a request that costs more than measured, would spend the reserve unseen |
| Stop after ten failures in a row | Ten neighbours that fail for a lasting reason would stop every run at the same place, and "in a row" depends on timing with eight threads |
| Pace the requests | Measured as not needed |
| Keep the payloads uncompressed | Ten times the space for one line of code saved each way |
| EODHD's bulk fundamentals request | A separate plan, and it returns four quarters and four years only (EODHD's documentation; not tried) |
| A library for the progress bar | It would be pyvalue's first runtime dependency |

## Not decided here

- How payloads are read into tables, and what is checked when they are: that a payload belongs to the security, and what it lacks.
- What to do with a listing EODHD has no fundamentals for.
- Whether a refresh needs a guard against a payload that got much shorter. The first refresh is compared with the folder it replaces.
- Prices. The subscription has none.
