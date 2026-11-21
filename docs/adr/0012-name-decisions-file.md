# ADR 0012: A company's name can be decided in a file the load applies

- Status: Accepted
- Date: 2026-11-21

## Decision

When a fund files something that is not a company name, the name is recorded as one row in a committed file, and the load gives the company that name. The mechanism is the one ADR 0010 uses for legal-entity identifiers. This settles a point ADR 0010 left open: how a company's stored name is corrected.

| Topic | Decision |
|---|---|
| What a decision says | "The company that issued this security is called this" |
| Key | The ISIN, for the reason ADR 0010 gives: database ids change on a rebuild |
| Where the file is | `src/pyvalue/universe/decisions/name.csv`, committed and shipped inside the package |
| Who applies it | The load (`pyvalue universe load`). There is no separate command |
| What it overrules | The name the funds filed for that security, and the name the database holds for its company |
| When a decision is made | When the filed name is a vendor placeholder, such as "New Issuer: BB Company ID:68830100" |
| Which name is used | The name another fund files for the same security, exactly as filed. Where no fund files one, the company's name from a public source, written like the names around it: no punctuation, short legal forms (Inc, Ltd, Co) |

**How this differs from ADR 0011.** An identifier is chosen only among those the funds filed, because it only has to be consistent between the funds. A placeholder name is consistent with nothing: no other fund will ever file it. A name is also read by people. So a name may come from outside the filings when no fund files a real one.

## The file

One row per security.

| Column | Required | Content |
|---|---|---|
| `isin` | yes | The security. No ISIN appears twice |
| `name` | yes | The name the company of this security gets. Not empty, no leading or trailing space, single spaces between words |
| `decided_on` | yes | The date of the decision, `YYYY-MM-DD` |
| `evidence` | yes | Where the name comes from, in a sentence |

Example row:

| `isin` | `name` | `decided_on` | `evidence` |
|---|---|---|---|
| `US4333131039` | Hinge Health Inc | 2026-11-21 | VTI files a vendor placeholder. SEC registrant name "Hinge Health, Inc." (ticker HNGE) |

The load checks every row before it touches the database, as it does for `lei.csv`. A bad row stops the load and is named by its number.

## How the load applies it

| Situation | What happens |
|---|---|
| The security is already an instrument | Its company is renamed, before any line is placed |
| The security is new | Its line is read as carrying the decided name, so the company is added with it |
| The security joins an existing company, by identifier or by name | That company is given the decided name |
| Two rows give securities of one company different names | The load stops with an error that names both, and writes nothing |
| A row for a security no filing holds | Nothing happens |

Notes:

- **A decided name takes part in the comparison of names.** A line of a decided security is compared under its decided name, in the rule for joining (ADR 0006) and in the receipt rule.
- **The lookup by name follows a rename.** After a rename, a line with the new name finds the company and the placeholder no longer does.
- **Nothing else changes.** Joining, filling in, the receipt rule, the identifier decisions and the report stay as ADR 0006, ADR 0009, ADR 0010 and ADR 0011 have them.

## Why this design

- **The author asked for it**: "We should fix the names now", and approved a name for each of the 47 companies on 2026-11-21.
- **A placeholder is of no use to a reader.** A screen row that reads "New Issuer: BB Company ID:71496967" does not say which company it is.
- **A placeholder cannot join.** The name is the key the load falls back on when a line has no identifier (ADR 0006). A placeholder never equals the name another fund files, so a second security of such a company would become a second company.
- **A file the load applies survives a rebuild**, carries its history and is reviewed like any change (the argument of ADR 0010). A name changed by hand would be lost.

## Evidence

Measured on 2026-11-21 on the three pinned filings.

**The placeholders.**

| Fact | Count |
|---|---|
| Companies stored under a placeholder | 47 |
| Fund that files it | VTI 17, VXUS 30. DFAX files none |
| Of the 47, companies without a legal-entity identifier | 41 |
| Securities per company | 1 each |

The load keeps the first fund's spelling (ADR 0006), and Vanguard's funds are loaded first. So the placeholder is stored even where DFAX files the real name for the same ISIN.

**Where each name comes from.**

| Source | Names | Example |
|---|---|---|
| DFAX files the name for the same ISIN | 12 | Eureka Forbes Ltd |
| The SEC's registrant name for the ticker | 18 | Hinge Health Inc |
| The legal name of the entity the public register of identifiers (GLEIF) maps the ISIN to | 5 | Intea Fastigheter AB |
| A web search for the listed company | 4 | Suzhou Centec Communications Co Ltd |
| The security name in the open identifier mapping (OpenFIGI), which agrees with the fund's security title | 8 | Premier Energies Ltd |

- **One company was renamed after the filing.** Aureus Greenway Holdings took the name Powerus Corporation on 2 October 2026 and kept its share code. The file uses the current name.
- **No decided name is already the name of another company** in the database, and none begins like one.

**Applying the file.** The load was run on the real database on 2026-11-21, with the 47 name decisions and the 14 identifier decisions.

| Result | Count |
|---|---|
| Name decisions that concern a security of the filings | 47 of 47 |
| Companies renamed | 47 |
| Companies whose name still begins with "New Issuer" | 0 |
| Companies, instruments, companies with an identifier | Unchanged: 15,619, 15,979 and 9,520 |
| Other company rows, and all instrument rows | Unchanged |
| Cases for the agent | 0 |
| Second run | Changed nothing |
| Rebuild from scratch, same filings and same files | All rows of `company` and `instrument` identical to the renamed database |

## Consequences

- **`company.name` is no longer always the first fund's spelling.** It is that, or the name a decision gives.
- **A decision is a change to the package** and goes through the quality gate.
- **Removing a decision does not undo it** in an existing database, as with identifier decisions.
- **A rebuild equals the renamed database only when no other company would have joined under the decided name.** A decided name that equals the name of a line with another ISIN and no identifier joins that line on a rebuild, while a database renamed in place keeps two companies. None of the 47 names does.
- **The scope is not checked by code.** That a decision is made only for a placeholder is for the reviewer of the file to see.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Change the 47 rows in the database by hand | Lost on a rebuild, and nothing records where a name came from. |
| A rule in the load: when the stored name is a placeholder, take another fund's name | Covers 12 of the 47, and the load would need its own definition of a placeholder. |
| Take the name from the data provider's listing | There are no listings yet, and provider values are kept out of the core tables (ADR 0002). |
| Add a name column to `lei.csv` | The two files follow different rules (ADR 0011), and a company usually needs only one of the two decisions. |

## Not decided here

- Restyling the roughly 300 names the funds' data vendor writes its own way, such as "Procter & Gamble Co/The" or "Republic Bancorp Inc/KY".
- Following a company's later change of name.
- Whether a screen shows the stored name or the provider's.
- The name of a company no filing holds.
