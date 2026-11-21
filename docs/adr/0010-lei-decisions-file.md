# ADR 0010: Decisions on a company's legal-entity identifier are a file the load applies

- Status: Accepted. ADR 0011 narrows which identifier a decision may name, and closes the first two points under "Not decided here". ADR 0012 settles how a company's stored name is corrected.
- Date: 2026-11-20

## Decision

When the filings are wrong or disagree about which legal entity issued a security, the answer is recorded as one row in a committed file. The load reads the file together with the filings and applies it. This settles the point ADR 0009 left open: how an agent's answer to a case reaches the database.

| Topic | Decision |
|---|---|
| What a decision says | "The company that issued this security has this legal-entity identifier" |
| Key | The ISIN, because database ids change when the database is rebuilt (the reason ADR 0005 gives for its own file) |
| Where the file is | `src/pyvalue/universe/decisions/lei.csv`, committed and shipped inside the package |
| Who applies it | The load (`pyvalue universe load`). There is no separate command |
| What it overrules | Whatever the funds filed for that security, and whatever the database holds for its company |

## The file

One row per security.

| Column | Required | Content |
|---|---|---|
| `isin` | yes | The security. No ISIN appears twice |
| `lei` | yes | The legal-entity identifier of the company that issued it |
| `company` | yes | The company's name, for the reader. The load does not use it |
| `decided_on` | yes | The date of the decision, `YYYY-MM-DD` |
| `evidence` | yes | Why, in a sentence: what the register or another source says |

Example row:

| `isin` | `lei` | `company` | `decided_on` | `evidence` |
|---|---|---|---|---|
| `CA0213611001` | `2549008X5V70MOS4HM10` | AltaGas Ltd | 2026-11-20 | GLEIF: 549300D7A8QA85Z2MH11 (filed by VXUS) is retired and names this identifier as its successor |

The load checks every row before it touches the database: the header, a valid ISIN, a valid identifier (both with check digits, ADR 0009), a real date, no empty cell and no repeated ISIN. A bad row stops the load and is named by its number.

## How the load applies it

| Step | What happens |
|---|---|
| 1. Decisions first | For each decided security that is already an instrument, its company is given the decided identifier |
| 2. Lines | As in ADR 0006, with one change: a line of a decided security is read as carrying the decided identifier, whatever the fund filed |

Step 1 leaves a company as it is in two situations, and the lines of step 2 then report a case as they do today:

| Situation | Why the load does not act |
|---|---|
| Another company already has the decided identifier | Two rows would then be one company. Merging rows is not something the load does |
| Two decisions name different identifiers for securities of one company | The decisions say the securities have different issuers. Splitting a row is not something the load does either |

Notes:

- **Decisions come first** so that a company's other securities are compared with the corrected identifier in the same run. A run and its repeat then report the same cases.
- **A decided security that is not loaded yet** is placed by its decided identifier: it joins the company that has it, or a new company is added with it.
- **A decision for a security no filing holds** changes nothing.
- **Nothing else changes.** Joining, filling in, the receipt rule and the report stay as ADR 0006 and ADR 0009 have them.

## Why this design

- **The author asked for a file that is applied**, and chose to keep it inside the package.
- **A decision is data that code cannot recompute.** In a committed file it survives a rebuild of the database, is reviewed like any change, and carries its history (the argument of ADR 0005).
- **The file is an input of the load, like the filings.** So a database built from scratch and a database corrected in place end up with the same rows.
- **The ISIN is the right key.** A decision answers "who issued this security". It does not claim that one identifier always stands for another: for Logo Yazilim, one fund filed the identifier of an unrelated company, and that company must not be turned into Logo wherever it appears.
- **Inside the package, an installed copy rebuilds the same universe.** The pinned filings are in the package too (ADR 0009); the decisions are the other half of what defines the universe.

## Evidence

Measured on 2026-11-20.

**The cases.** The first load reported 15 lines, which are 13 securities: DFAX lists Cenovus and Whitecap twice, once held in Canadian and once in US dollars. In every case VXUS and DFAX file different identifiers for the same ISIN.

**The register.** Both identifiers of each case were looked up in the public register of legal-entity identifiers (GLEIF), and the register was asked which identifier it maps the ISIN to.

| Finding | Securities |
|---|---|
| DFAX files the right identifier | 11 |
| VXUS files the right identifier | 2 (Paramount Resources, ID Logistics Group) |

| Why the other identifier is wrong | Securities |
|---|---|
| Outdated: the register shows it as retired, as a duplicate, or as lapsed under an earlier name, and another record has taken its place | 9 (Peyto, Whitecap, AltaGas, Northland Power, Cenovus, Secure Waste Infrastructure, Beijing Enterprises Water, UIE, Paramount) |
| It is a subsidiary's | 2 (ID Logistics, IONOS) |
| It is another company's altogether | 2 (Logo Yazilim, Guangdong Electric Power) |

| How firm the answer is | Securities |
|---|---|
| The register names the successor, or maps the ISIN to one of the two | 9 |
| One identifier is retired and the other active; the register names no successor | 2 (Cenovus, Paramount) |
| Decided by the legal name | 2 (Secure, whose entity was created on the day its merger closed; Guangdong, whose listed name was confirmed by a web search) |

**The fourteenth decision.** Guangdong Electric Power has a second security in the universe, its B share `CNE000000HW5`. Only VXUS holds it, with the same wrong identifier, so no fund contradicted it and it was never reported. It is the only other line in the three filings that carries one of the 26 identifiers involved. Without a decision for it, a rebuild from scratch would split the company into two rows.

**The database before the decisions.** It held the VXUS identifier for all 13 companies, because VXUS is loaded first. So 11 companies carried a wrong one.

**Applying the file.** The load was run again on the real database on 2026-11-20, with the 14 decisions.

| Result | Count |
|---|---|
| Decisions that concern a security of the filings | 14 of 14 |
| Companies whose identifier was replaced | 11 (Guangdong Electric Power is one company with two decided securities) |
| Companies and instruments | Unchanged: 15,619 and 15,979; still 9,520 companies with an identifier |
| Cases for the agent after the run | 0 |
| Second run | Changed nothing; both output files came out byte for byte the same |
| Rebuild from scratch, same filings and same file | All 31,598 rows of `company` and `instrument` identical to the corrected database |

## Consequences

- **A decision is a change to the package.** It goes through the same quality gate as code.
- **Applying a decision is running the load again.** It corrects the database in place.
- **A rebuild equals the corrected database only when no case is open.** While a sibling security still carries the old identifier undecided, a database corrected in place keeps one company and reports a case, and a rebuild from scratch makes two companies.
- **A wrong identifier that only one fund files is not found by the load.** The Guangdong B share was found by hand. Checking every identifier against the register is separate work.
- **Removing a decision does not undo it.** The database keeps the corrected identifier, and the lines that disagree are reported again.
- **The company name is not corrected.** A company whose identifier was replaced keeps the first fund's spelling, including an old name such as "Secure Energy Services Inc".
- **The file has no constraints of its own.** The reader checks every row, and a test checks the shipped file.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Correct the 11 rows in the database by hand | The corrections would be lost on a rebuild, and nothing would record why they were made. |
| A committed folder at the repository root, outside the package | Keeps data out of `src/`, but a copy installed without the repository could not rebuild the universe. The author chose the package. |
| A file that maps an old identifier to a new one | Right for the nine outdated identifiers, wrong for the two that belong to other companies. |
| A separate command that applies decisions | A second thing to run and to keep in step with the load's rules. |
| A decisions table in the database | The database is rebuilt from files; the decisions have to live outside it. |
| Merge and split company rows automatically | No case needs it today, and it is the kind of change that should be looked at one by one. |

## Not decided here

- Checking all identifiers in the database against the register, and filling in the ones the funds did not file.
- A decision that says a company has no identifier at all.
- How company rows are merged or split.
- How a company's stored name is corrected.
- The file for the listing decisions of ADR 0005. It is expected to sit in the same folder.
