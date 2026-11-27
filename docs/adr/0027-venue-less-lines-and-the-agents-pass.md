# ADR 0027: Lines without a venue are left out, and the agent's pass is a session the author approves batch by batch

- Status: Accepted
- Date: 2026-11-27
- Changes: ADR 0019 in one point: the agent may leave a security undecided. It settles what ADR 0019 left open on how the agent is run, and what ADR 0024 left open on a US share line without a venue. Everything else in both records stands.

## Decision

The first requests to EODHD were made on 2026-11-27. This record decides what they left to decide.

### The US list

| Venue label | Decision | Why |
|---|---|---|
| `US` | Left out: a row in `eodhd_exchange.csv` with the label and no market | EODHD gives the code itself as the label of a line whose venue it does not state. No exchange of ours can be named for such a line |
| `OTC`, `OTCPK` | Left out, the same way | Over-the-counter lines, which ADR 0024 leaves out |

### The agent's pass

| Topic | Decision |
|---|---|
| Who the agent is | Claude Code in a session of this repository, asked by the author to work through `data/listings/cases_for_agent.csv`. There is no command for it, and pyvalue itself calls no model |
| Batches | The agent takes one reason at a time and shows the author the rows it proposes, with the evidence, and the securities it leaves undecided, with why. A batch is committed only after the author approves it |
| Who is named | `decided_by` is `agent` for a row the agent proposed, and `author` for a decision the author made of their own, such as the Thai rows of ADR 0019 |
| What the agent may use | The report, the saved lists under `data/eodhd/`, OpenFIGI's keyless lookup, an exchange's own website, `docs/universe.md`, and web search. No request to EODHD |
| The agent may leave a security undecided | It stays on the report. ADR 0019 said the agent decides each one |
| The agent names only a line the report shows | As ADR 0019 has it. The fill would also accept another line in a home market (ADR 0026); the agent does not use that |

### What a row needs

| Row | What it needs |
|---|---|
| `listing`, where no line carries the ISIN | A source outside the fund and outside the provider's list that ties the ISIN to that symbol on that exchange |
| `listing`, where the line carries the ISIN and the fund's ticker differs | A source that explains the other ticker |
| `none` | A lasting reason why the security has no line: a foreign-board share (ADR 0019), or a share that trades only in a market the provider does not serve. "Not found today" is not a reason |

Three guards hold for every `listing` row. The fill checks none of them for a decided line, so the agent does.

| Guard | What it prevents |
|---|---|
| The line's currency is the currency the fund holds the security in | A listing in a currency the provider states wrongly |
| The line does not carry the ISIN of another security of the universe, and no other row names it | A wrong row taking the line from the right security: decisions are applied before the rule |
| A receipt read as its ordinary share (ADR 0015) never gets the receipt's own line | Analysing the receipt in place of the share |

### Securities that left the exchange or changed ISIN since the filing

Decided by the author on 2026-11-27. They get no listing and no `none` row, and stay on the report until newer filings are pinned. Nothing is built to follow a change of ISIN between two filings.

## Evidence

Measured on 2026-11-27 with six requests: the account, the exchange list, the symbol lists of `US`, `BK` and `LSE`, and the delisted symbols of `US`.

| Finding | Measurement |
|---|---|
| The exchange list | 70 codes, the same 70 as `eodhd_exchange.csv`: 59 with a market, 11 left out |
| The readers of ADR 0024 | Read the three live lists as they are: 50,424, 1,439 and 7,290 lines |
| US venue labels on share lines that the file lacks | `US` 306, `OTC` 6, `OTCPK` 1. With the three rows, 6,356 US lines are stored |
| Who is under those labels | Of the 306 `US` lines the funds hold one, ERock. Many of the others are funds, rights and notes typed `Common Stock`. Of the 6 `OTC` lines the funds hold one, SPAR Group |
| Thailand | 107 securities, 105 with a ticker ending in `-F`. None has a live line with its ISIN; for 104 the local share is listed under the ticker without `-F` |
| A trial fill, with the three live lists and the legacy catalogue for the other 56 codes | 8,030 filled, 3,110 market not served, 564 on the report |
| US securities with nothing found | 110. 97 have no fund ticker: Vanguard's file of 31 October no longer joins them by ISIN |
| Where those 110 are | The ISIN of 56 is on EODHD's delisted list (Roku, Kenvue). The other 54 are not: most are listed under a new ISIN, such as Exxon Mobil, filed as `US30231G1022`, whose line `XOM` now carries `US30233Q1085` |
| The delisted list as evidence | It also holds the old ISIN of a company that lives on: aTyr Pharma and Alight are on it, and both have a live line under a new ISIN |
| OpenFIGI | Asked about eight securities where the ticker finds one line: it gave the same ticker on the home exchange for each. For two Malaysian shares it gave another ticker than the provider's stock code |
| Malaysian ISINs | They contain the exchange's stock code: `MYL1155OO000` is Maybank, code 1155 |
| Receipts the non-US fund holds | `docs/universe.md` records 19 New York receipts as each company's only line |

The filings show holdings of 30 June 2026 (VTI) and 31 July 2026 (VXUS), so four to five months of delistings and reorganisations lie between them and the lists.

## Why

- **A line without a venue cannot be placed.** A listing names an exchange, and guessing one would put a share on the wrong market.
- **The smallest thing that works.** The decisions file is the lasting record of the agent's work. A command that calls a model would add a dependency and a key for a pass that runs a few times a year.
- **The author approves, because a row is hard to see once applied.** A wrong `listing` row analyses the wrong company's prices and accounts, and a `none` row removes a company from every screen.
- **An outside source is what makes a decision more than the provider confirming itself.** The report already shows what the provider says.
- **Undecided is better than guessed.** A security left on the report is looked at again; a wrong row is not.
- **A stale security heals by itself.** A newer filing drops the company that left and brings the new ISIN. A `none` row would have to be found and removed again.

## Consequences

- **The agent's first pass is about 300 securities,** once the Thai rows are in and the stale ones are set aside.
- **ERock cannot be listed** until EODHD gives its line a venue. A later download brings it, and the next fill takes it.
- **Some securities wait longer than one filing.** A company delisted after the next filing's date stays a quarter more, and so does an ISIN changed after it. A filing is two to five months old when it is pinned, so some securities are always in this state.
- **The report keeps the undecided securities.** `docs/listings.md` names them at the end of the pass.
- **A decision row for a security that leaves the universe** is counted and named by the fill (ADR 0026). Such rows are removed when the newer filings are pinned.
- **A new venue label still stops the US list** until a person adds a row for it (ADR 0024).

## Alternatives considered

| Alternative | Why not |
|---|---|
| Put the `US` lines on New York or Nasdaq | It would be a guess for 306 lines, most of them not shares the funds hold |
| A command that sends each case to a model | A dependency, a key and a prompt to maintain, for work the author wants to approve anyway |
| The agent decides and commits, the author reviews afterwards | A wrong row would already have been applied, and correcting a listing needs a rebuild (ADR 0019) |
| Let the agent name the live line of a company with a new ISIN | The stored ISIN would stay the old one, a name match can pick the wrong class of share, and the row dies at the next filing. Decided against by the author |
| `none` for a company on the delisted list | The list also holds companies that live on under a new ISIN, and the row would have to be removed after the next filing |
| Follow a change of ISIN between filings | A new mechanism. How many securities need it is measured first, at the next filing |

## Not decided here

- Whether a share type the load leaves out, such as `Unit`, hides shares the funds hold. It is checked at the first full load.
- How a change of ISIN between two filings is followed, if it is.
- A second provider for the markets EODHD does not serve.
