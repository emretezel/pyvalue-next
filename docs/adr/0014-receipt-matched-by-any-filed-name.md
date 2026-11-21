# ADR 0014: A receipt is matched to its company by any name a fund files for the company's shares

- Status: Accepted
- Date: 2026-11-21

## Decision

The receipt rule of ADR 0006 asks whether a receipt's company is already in the universe through its own shares. It now also recognises the company by the name that any fund files on a line of the company's own shares, and no longer only by the name the database stores.

| Topic | Before | Now |
|---|---|---|
| A receipt is not loaded when one of its lines carries | The legal-entity identifier or the stored name of a company that an ordinary line of this run belongs to | The same, or the name that any ordinary line of this run carries |

An ordinary line is a line of a security that is not a receipt and can be loaded. Every such line belongs to a company in the universe once step 4 of ADR 0006 is done, so its name is a name of that company, whichever spelling the database kept.

Names are compared as before: upper and lower case and spacing are ignored, punctuation counts (ADR 0009).

## Why

- **The stored name is only one fund's spelling.** The database keeps the spelling of the first fund that names a company (ADR 0006). A second fund's line for the same ISIN joins by the ISIN, and its spelling is dropped.
- **A fund is consistent with itself.** Dimensional files one name for a company's share and for its receipt. When Vanguard's spelling of the share is the stored one, the receipt's name matched nothing, and the receipt was loaded as a company of its own.
- **The proof is in the filings.** The same fund, the same name, on the share and on the receipt. No outside source is needed, and no decision per case.
- **The author asked for it** on 2026-11-21, together with the removal of the three receipts it concerns.

## Evidence

Measured on 2026-11-21 on the three pinned filings.

**The three cases.** In each, VXUS and DFAX hold the home share, DFAX holds the receipt, and no line carries a legal-entity identifier that would tie the two together.

| Company | Home share | Stored name (VXUS) | DFAX's name, on the share and on the receipt | Receipt |
|---|---|---|---|---|
| Woori Financial | `KR7316140003` | Woori Financial Group Inc | Woori Financial Group Inc. | `US9810641087` |
| ChipMOS | `TW0008150004` | ChipMOS Technologies Inc | ChipMOS TECHNOLOGIES INC. | `US16965P2020` |
| BeOne Medicines | `CH1391448177`, `CNE100005XT6` | BeOne Medicines Ltd | BeOne Medicines AG | `US07725L1026` |

The open identifier mapping (OpenFIGI) gives the three US codes as American depositary receipts and the home codes as common stock.

**How far the change reaches.** Of the 35 receipts that were kept as their company's only line, the new comparison matches exactly these three. No other receipt is affected.

**Rebuilding the database.** The local database was rebuilt on 2026-11-21.

| Result | Before | After |
|---|---|---|
| Instruments | 15,958 | 15,955 |
| Companies | 15,599 | 15,596 |
| Companies with an identifier | 9,507 | 9,507 |
| Receipts kept as the company's only line | 35 | 32 |
| Receipts not loaded: the company is already there | 145 | 148 |
| Lines not loaded | 399 | 402 |

Only the three receipts and their three company rows are gone. Every other security is under a company of the same name and identifier as before.

## Consequences

- **A company that two funds spell differently is no longer doubled by its receipt.**
- **Two different companies with the same name are still taken for one in this rule**, as before: a receipt is left out when a company of its name has a line of its own. The new comparison adds names, not a new kind of mistake.
- **An existing database keeps the receipts it loaded under the old rule.** The load never deletes (ADR 0006), so they go only with a rebuild. Unlike an excluded security (ADR 0013), the load does not refuse such a database: it reports the receipt's lines as not loaded while the instrument stays.
- **The stored name is unchanged.** It is still the first fund's spelling.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Add the three receipts to the exclusions file (ADR 0013) | It works for these three and misses the next one when newer filings are loaded. |
| Ignore punctuation when names are compared | It would catch Woori and ChipMOS and not BeOne ("Ltd" against "AG"), and it joins different companies (ADR 0009). |
| Store every spelling of a company's name | A new table for one comparison that the lines of the run already answer. |
| Also compare with the identifiers filed on ordinary lines | A line whose identifier differs from its company's is already reported as a case and settled by a decision (ADR 0010). No receipt is affected today. |

## Not decided here

- Whether the load should refuse a database that still holds a receipt it would no longer load, as it does for an excluded security.
- The receipts whose home share no fund holds (KT, Cementos Pacasmayo, Vista Energy, JBS, XP).
