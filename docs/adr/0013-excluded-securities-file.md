# ADR 0013: A security can be kept out of the universe by a file the load applies

- Status: Accepted. Its first use is replaced by ADR 0015: the receipts kept out here are now read as their ordinary shares, so their companies are back in the universe. The file and the mechanism stay; the file holds no row.
- Date: 2026-11-21

## Decision

A security the author decides is not part of the universe is recorded as one row in a committed file, and the load does not load it. The mechanism is the one ADR 0010 and ADR 0012 use for identifiers and names.

| Topic | Decision |
|---|---|
| What a decision says | "This security is not part of the universe" |
| Key | The ISIN |
| Where the file is | `src/pyvalue/universe/decisions/excluded.csv`, committed and shipped inside the package |
| Who applies it | The load (`pyvalue universe load`). There is no separate command |
| What it overrules | The filings: every line of the security is left out, in whichever fund it appears |
| A database that already holds the security | The load stops and asks for a rebuild. It still never deletes (ADR 0006) |

The first use, decided by the author on 2026-11-21: six American depositary receipts of companies whose ordinary share is listed in Hong Kong. A receipt is not what pyvalue analyses; the home share is. For five of the six no fund holds the home share, and the author chose that those companies leave the universe.

## The file

One row per security.

| Column | Required | Content |
|---|---|---|
| `isin` | yes | The security that is not part of the universe. No ISIN appears twice |
| `company` | yes | The company's name, for the reader. The load does not use it |
| `decided_on` | yes | The date of the decision, `YYYY-MM-DD` |
| `evidence` | yes | Why, in a sentence or two |

Example row:

| `isin` | `company` | `decided_on` | `evidence` |
|---|---|---|---|
| `US88557W1018` | Qfin Holdings Inc | 2026-11-21 | Depositary receipt (ADR), which VXUS files as common stock. The ordinary share is listed in Hong Kong as 03660 QFIN-S, ISIN KYG8851G1001. No fund holds it |

The load checks every row before it touches the database, as for the other two files.

## How the load applies it

| Situation | What happens |
|---|---|
| A line of an excluded security | Not loaded. Listed in `lines_not_loaded.csv` with the reason `excluded_by_decision` |
| The company has another security in the filings | It is loaded through that security |
| The company has no other security | It is not loaded |
| The database already holds an excluded security | The load stops before it writes anything and names the securities. The database has to be rebuilt |
| A security is excluded and also has an identifier or name decision | The load stops and names it: the files contradict each other |
| A row for a security no filing holds | Nothing happens |

Notes:

- **A line that is debt, a derivative or without a valid ISIN keeps its own reason.** The exclusion only applies to a line that would otherwise be loaded.
- **An excluded line is taken out before anything else is decided.** It is not a line of its company in the receipt rule, and it is not counted among the securities or the receipts.
- **Nothing else changes.** Joining, the receipt rule and the other decisions stay as ADR 0006 and ADR 0009 to ADR 0012 have them.

## Why this design

- **The author asked for it**: "Remove the 6 receipts, that has an HK share from universe because they are ADR", and chose that the five companies without a held home share are removed.
- **A deleted row would come back.** The filings still hold the line, so the next load would add it again. The decision has to be an input of the load.
- **A file the load applies survives a rebuild** and records why each security is out (the argument of ADR 0010).
- **Refusing is safer than deleting.** The load has never deleted a row, and ADR 0006 says it does not. Deleting would need its own rules for a company left without securities and, later, for listings that hang on an instrument. Today a rebuild costs seconds and loses nothing, because the two tables are built from the filings and the decisions.
- **A refusal is better than silence.** Without it, an exclusion added to the file would have no effect on an existing database, and nothing would say so.

## Evidence

Measured on 2026-11-21.

**The six securities.** All are held by VXUS only, in US dollars.

| Receipt | Company | Hong Kong share | Does a fund hold the Hong Kong share |
|---|---|---|---|
| `US48553T1060` | Kanzhun Ltd | 02076 BOSS ZHIPIN-W, `KYG5224V1032` | Yes, DFAX |
| `US88557W1018` | Qfin Holdings Inc | 03660 QFIN-S, `KYG8851G1001` | No |
| `US90114C1071` | Tuya Inc | 02391 TUYA-W, `KYG913841006` | No |
| `US54975P2011` | Lufax Holding Ltd | 06623 LUFAX, `KYG5700Y2097` | No |
| `US9509151083` | WeRide Inc | 00800 WERIDE-W, `KYG9560F1028` | No |
| `US7329081084` | Pony AI Inc | 02026 PONY-W, `KYG7171B1068` | No |

- **The Hong Kong shares** are from the Hong Kong exchange's list of securities of 2026-11-21. The open identifier mapping (OpenFIGI) gives each of the six ISINs as common stock of the same company, and the US ISINs it was asked about as receipts.
- **Why the load kept them.** Lufax and WeRide are recognised as receipts and were kept because their company has no other line. The other four are filed by Vanguard as plain common shares, without a word that says "receipt", so the load took them for ordinary shares (ADR 0006).
- **How they were found.** Of 29 Chinese companies in the universe through a New York receipt, a search by name in the Hong Kong list found these six. The other 23 were not found by name, which is not proof that they have no Hong Kong share: the list uses short names, and Kanzhun appears as "BOSS ZHIPIN-W".

**Rebuilding the database.** The local database was rebuilt on 2026-11-21 with the six exclusions.

| Result | Before | After |
|---|---|---|
| Instruments | 15,979 | 15,973 |
| Companies | 15,619 | 15,614 |
| Companies with an identifier | 9,520 | 9,516 |
| Lines not loaded | 371 | 377 |
| Securities recognised as receipts | 192 | 190 |
| Receipts kept as the company's only line | 47 | 45 |

- **Kanzhun** has one instrument, its Hong Kong share.
- **Every other security** is under a company of the same name and identifier as before.
- **The run before the rebuild** refused the old database and changed nothing.
- **One name decision was withdrawn.** Pony AI's row in `name.csv` (ADR 0012) names a security that is no longer loaded, so it was removed. The file holds 46 names.

## Consequences

- **Five companies are no longer in the universe**, although they are listed and traded. They come back only when a fund holds their home share or a security is added by hand, which is not built.
- **An exclusion needs a rebuild.** Row ids are renumbered by it. Nothing refers to an id yet, and the decisions files are keyed by ISIN.
- **Once listings hang on instruments, a rebuild will cost more.** Removing a security in place will then need its own decision.
- **`lines_not_loaded.csv` has a fourth reason**, and the count of lines not loaded includes the excluded ones.
- **Removing an exclusion brings the security back** on the next load.
- **Why a security is out is not checked by code.** The file takes any ISIN; the evidence column is for the reviewer.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Delete the six rows by hand | The next load adds them again. |
| Let the load delete an excluded security from an existing database | More rules and the first delete in the load, for something a rebuild does in seconds today. |
| Read a receipt's line as its home share, so the five companies stay under their Hong Kong ISIN | The author chose to remove them. It is also more to build, and it is the same need as adding a security no fund holds. |
| Give these receipts no listing in the listing step and leave them in the universe | The author wants them out of the universe now, and the listing step does not exist yet. |
| Teach the receipt check that these four are receipts | It would not remove them: a recognised receipt is kept when its company has no other line (ADR 0006), which is the case for three of the four. |

## Not decided here

- The other receipts in the universe: those whose home share no fund holds (KT, Cementos Pacasmayo, Vista Energy, JBS, XP), the frozen Russian ones, and those whose company is in the universe twice (BeOne Medicines, ChipMOS, Woori Financial).
- The Vanguard emerging-markets fund that VXUS holds and the load took for a company.
- Adding a security that no fund holds.
- Removing a security from a database in place.
