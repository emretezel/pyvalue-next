# ADR 0020: The receipt check also reads the sponsor's own name for a security

- Status: Accepted. The point left open below, the receipts that are their company's only line, was settled by the author on 2026-11-26: they stay.
- Date: 2026-11-26
- Changes: the receipt check of ADR 0006, which gains a fourth thing to read, and the common holding line of ADR 0016, which gains the sponsor's name. Everything else in both records stands.

## Decision

The receipt check of ADR 0006 decides whether a line is a depositary receipt. It now also reads the name that the fund sponsor's own holdings file gives the security.

| Topic | Before | Now |
|---|---|---|
| The receipt check reads | The filing's category label, the security title and the issuer name | The same, and the sponsor's own name for the security |

| Point | Decision |
|---|---|
| The words looked for | The same list as in ADR 0006, each as a whole word: ADR, GDR, "depositary receipt" and the rest |
| Where the name comes from | The sponsor's own holdings file. For Vanguard it is the long name of the row (ADR 0016) |
| Which lines get the name | Every line whose ISIN the sponsor's file has. A name belongs to the security, not to one market, so it does not need the one-line-to-one-row pairing that a ticker and a SEDOL need. Where the file has several rows for an ISIN, the first row's name is taken |
| Whether it is stored | No. It is read at the load and used by the receipt check only. The `holding` table of ADR 0017 is unchanged |
| What happens to a recognised receipt | What ADR 0006 and ADR 0014 already say: it is loaded only when its company has no line of its own |

## Why

- **Vanguard's filing hides the word.** It files a receipt as an ordinary common share and cuts the security title at 16 characters, which is where "ADR" would stand: `DR. REDDY'S LABO`, `GRUPO CIBEST SA-`, `LATAM AIRLINES G`.
- **Vanguard's own file says it.** The same three securities are named there "Dr Reddy's Laboratories Ltd. ADR", "Grupo Cibest SA ADR" and "Latam Airlines Group SA ADR".
- **Until ADR 0016 another sponsor did the labelling.** Dimensional filed these receipts under a label of their own, and a security is a receipt when any fund's line says so. With Dimensional gone, nothing said so any more, and the three were loaded as extra securities of companies whose home share is in the universe.
- **A rule catches the next one.** Newer filings will bring new receipts. A row per receipt in a decision file would have to be added each time someone noticed.
- **The author asked for it** on 2026-11-26, together with the removal of the three receipts it concerns.

## Evidence

Measured on 2026-11-26 on the two pinned filings and Vanguard's files of 31 October 2026.

**How far the change reaches.** Among the share lines of the two funds, the sponsor's name shows a receipt that the filing's wording does not on 11 lines, all in VXUS. VTI has none.

| Security | Filed title | Vanguard's own name | What the load does with it |
|---|---|---|---|
| Dr Reddy's Laboratories, `US2561352038` | `DR. REDDY'S LABO` | Dr Reddy's Laboratories Ltd. ADR | Was loaded as a share. Now a receipt, not loaded: VXUS holds the home share `INE089A01031` |
| Grupo Cibest, `US40090E1064` | `GRUPO CIBEST SA-` | Grupo Cibest SA ADR | The same: VXUS holds the home shares `COTK7PA00010` and `COTK7PA00028` |
| Latam Airlines, `US51817R2058` | `LATAM AIRLINES G` | Latam Airlines Group SA ADR | The same: VXUS holds the home share `CL0000000423` |
| PDD Holdings, `US7223041028` | `PDD HOLDINGS INC` | PDD Holdings Inc. ADR | Loaded as before, now as a receipt that is its company's only line |
| Gaotu Techedu, `US36257Y1091` | `GAOTU TECHEDU IN` | Gaotu Techedu Inc. ADR | The same |
| EHang Holdings, `US26853E1029` | `EHANG HOLDINGS` | EHang Holdings Ltd. ADR | The same |
| Qfin, Kanzhun, Tuya, Polyus, PhosAgro | | Each "… ADR" or "… GDR" | Unchanged: each is read as its ordinary share by a decision (ADR 0015), and such a line is not asked |

The open identifier mapping (OpenFIGI) gives the first three US codes as American depositary receipts and their home codes as common stock, and for Grupo Cibest's second home code as preference shares.

**No ordinary share is taken for a receipt.** Every one of the 11 lines is a receipt. No name in either file carries one of the words by chance.

**Rebuilding the database.** The local database was rebuilt on 2026-11-26.

| Result | Before | After |
|---|---|---|
| Instruments | 12,187 | 12,184 |
| Companies | 11,929 | 11,929 |
| Receipts recognised | 47 | 53 |
| Receipts kept as the company's only line | 19 | 22 |
| Receipts not loaded: the company is already there | 28 | 31 |
| Holding lines stored | 12,259 | 12,259 |
| Holding lines that point at an instrument | 12,218 | 12,215 |

Only the three receipts are gone. Their companies stay, each through its home share. The 12,184 instruments are exactly the ones the three-fund database of 2026-11-22 shared with Vanguard's two funds.

## Consequences

- **A receipt that only the sponsor's file names is recognised without a decision.**
- **The three receipts leave the universe;** no company does.
- **The database has to be rebuilt,** because the load never deletes (ADR 0006). As ADR 0014 notes, the load does not refuse a database that still holds a receipt it would no longer load. It reports them: the last line of its output, "Instruments no fund holds", counts them.
- **The check is as good as the sponsor's wording.** A receipt that neither the filing nor the sponsor's file names is still loaded as a share. The listing rule of ADR 0019 sends every US-coded ISIN of the non-US fund to the agent, which is the second net.
- **A company name that contains one of the words would be taken for a receipt,** as with the title and the issuer name before. None does today.
- **A sponsor without a file of its own** gives no name, and the check reads the filing alone.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Three rows in `excluded.csv` (ADR 0013) | It works for these three and misses the next one when newer filings are loaded |
| Read each receipt as its ordinary share (ADR 0015) | The home share is already held. Its line would be joined by a second line from another market, and the listing rule would send a clean security to the agent |
| Leave them for the agent of the listing rule | Three extra securities sit in the universe until then, and the agent would decide each time what a rule can decide once |
| Attach the name only where one line meets one row, like the ticker | A receipt held on two lines would go unrecognised, although its name is the same on every row |
| Store the sponsor's name in `holding` | Nothing reads it after the load. It can be added when something does |

## Not decided here

- Whether the load should refuse a database that still holds a receipt it would no longer load (open since ADR 0014).
- The receipts that are their company's only line: 22 after this change, mostly Chinese companies listed in New York. Settled on 2026-11-26: they stay in the universe, as ADR 0006 has it. No listed home share was found for them, and the listing rule of ADR 0019 sends each to the agent before a listing is written.
