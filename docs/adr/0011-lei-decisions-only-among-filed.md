# ADR 0011: A decision on a legal-entity identifier chooses only among the identifiers the funds filed

- Status: Accepted
- Date: 2026-11-21

## Decision

A row in the decisions file of ADR 0010 may name only an identifier that a fund filed for the company. The file settles a disagreement between the funds. It does not replace an identifier the funds agree on with one from an outside register.

| Topic | Decision |
|---|---|
| When a decision is made | When the load reports a case: two funds file different identifiers for the same security |
| What a decision may name | An identifier a fund filed for that security, or for another security of the same company |
| What an outside source is for | Evidence for choosing between the filed identifiers. It is never the source of the identifier |
| A filed identifier that a register shows as retired, lapsed or replaced | Stays as filed |
| Checking the stored identifiers against a register | Not done as a routine |
| A decision that says a company has no identifier | Not introduced |

This narrows ADR 0010 and closes two points it left open: checking all identifiers against the register, and a decision that says a company has no identifier.

## Why

- **The identifier has one job.** The load uses it to tell whether two filing lines are the same company: it groups a company's securities and keeps a receipt out when its company is already loaded (ADR 0006). The listing step works by ISIN and does not read it (ADR 0005).
- **For that job it has to be consistent, not current.** A retired identifier that every fund files joins exactly as well as the current one.
- **The funds keep filing old identifiers.** A new security of a company is therefore more likely to arrive with the old identifier. A corrected one would not match it, and the load would add a second company without reporting anything.
- **The author decided it** on 2026-11-21: "We should only decide on LEIs among the funds filed."

## Evidence

Measured on 2026-11-20 and 2026-11-21 on the three pinned filings and the public register of legal-entity identifiers (GLEIF).

**How often the funds disagree.** 6,496 securities are held by more than one fund.

| How the identifiers compare | Securities |
|---|---|
| Both funds file the same one | 4,302 |
| Neither fund files one | 2,071 |
| One fund files it, the other does not | 110 |
| The funds file different ones | 13 |

The 13 are the cases ADR 0010 decided. Every one of its 14 rows names an identifier a fund filed.

**What correcting against the register changed.** On 20 and 21 November, 12 further rows were added for 11 companies. Each named an identifier that no fund files anywhere, taken from the register.

| Result | Count |
|---|---|
| Companies and instruments before and after the 12 rows | Unchanged: 15,619 and 15,979 |
| Joins that changed | 0 |
| Rows that needed a second row to avoid a wrong load | 1 (Banpu) |

- **Banpu.** DFAX holds Banpu's depositary receipt with the same old identifier as the share. The receipt stays out of the universe because that identifier matches the company. Once the share was corrected, the receipt no longer matched and would have been loaded as a company of its own, so it needed a decision too.
- **How old a filed identifier can be.** VTI files, for SLM, the identifier of an entity that ended in 2014, and for Big Sky Industrial the identifier of its predecessor, which ended in 2022.

**Removing the 12 rows.** The rows were removed and the local database was rebuilt from scratch on 2026-11-21.

| Result | Count |
|---|---|
| Decisions used | 14 |
| Companies, instruments, companies with an identifier | 15,619, 15,979 and 9,520, as before |
| Instrument rows compared with the database before | All identical |
| Company rows that differ | 11, each back to the identifier its funds filed |
| Cases for the agent | 0 |
| Second run | Changed nothing |

## Consequences

- **A stored identifier can be out of date.** It may be retired or belong to a predecessor. Known examples: ONEOK, Banpu, SLM, Big Sky Industrial. Nabors Industries carries the identifier of Tesco Corporation, which it bought in 2017, because that is what the fund files.
- **The identifier is not a statement about the company's current legal entity.** Nothing downstream may treat it as one.
- **An out-of-date identifier is still a useful sign.** A retired identifier often marks a reorganisation, and a reorganisation can change the ISIN. That is how the dead ISINs of ONEOK, Expro and Banpu were found. A dead ISIN is handled by pinning newer filings and by the listing step's report, not by changing the identifier.
- **The rule is not checked by code.** A reviewer of the decisions file checks it.
- **Removing a decision does not undo it in an existing database** (ADR 0010). The local database was rebuilt.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep the 12 rows | They are right according to the register, but they move the stored identifier away from what the funds file and change no join. |
| Replace every retired identifier with its successor | The same objection. Also, of the 23 retired or replaced identifiers found, 16 name no successor, and one names the company's acquirer. |
| A decision that removes an identifier | It needs a new file format and code. No join depends on it. |
| Take the identifier from the register's ISIN mapping | For 41 companies the mapping names a different identifier than the funds, and the fund is right in about 33 of them. The mapping often points at a subsidiary or a predecessor. |

## Not decided here

- Whether the load should refuse a decision whose identifier appears on no line of the filings.
- How company rows are merged or split, and how a company's stored name is corrected (as in ADR 0010).
