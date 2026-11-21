# Sample holdings filings

Three small files in the shape of an SEC N-PORT filing, for the tests of the universe load. The series id and the holdings date of each file are those of the pinned filing it stands in for, so the load accepts it. Every company, identifier and amount is made up. The ISINs and legal-entity identifiers carry correct check digits.

The files are named by ticker. A test copies them into a temporary folder under the names the load expects.

## What each line is there for

`VTI.xml` (files categories the way Vanguard does):

| Line | Issuer | What it exercises | Outcome |
|---|---|---|---|
| 1 | ALPHA CORP | A company with a legal-entity identifier | Company 1, instrument 1 |
| 2 | ALPHA CORP | A second security with the same identifier | Joined to company 1 by identifier |
| 3 | BETA INC | A company without an identifier | Company 2 |
| 4 | Beta  Inc | The same name in other case and spacing | Joined to company 2 by name |
| 5 | GAMMA THERAPEUTICS INC | No ISIN | Not loaded: no valid ISIN |
| 6 | CHICAGO MERCANTILE EXCHANGE | A derivative | Not loaded: debt or derivative |
| 7 | SAMPLE CASH MANAGEMENT FUND | Cash, no ISIN | Not loaded: no valid ISIN |

`VXUS.xml` (files receipts as common shares, the way Vanguard does):

| Line | Issuer | What it exercises | Outcome |
|---|---|---|---|
| 1 | DELTA PLC | A company with an identifier | Company 3 |
| 2 | EPSILON SA | No identifier yet | Company 4 |
| 3 | ZETA LTD | A receipt by its title ("ADR"); the company's own share is line 4 | Not loaded: company already loaded |
| 4 | ZETA LTD | The company's own share | Company 5 |
| 5 | ETA HOLDINGS LTD | A receipt by its title; the company has no other line | Company 13, loaded after the ordinary lines |
| 6 | SAMPLE TREASURY | Debt with an ISIN | Not loaded: debt or derivative |
| 7 | SAMPLE BANK NA | A currency derivative | Not loaded: debt or derivative |
| 8 | THETA AG | A company whose identifier DFAX contradicts | Company 6 |
| 9 | IOTA KK | No identifier; DFAX supplies one that is taken | Company 7 |
| 10 | LAMBDA BHD | No identifier | Company 8 |

`DFAX.xml` (labels receipts, units and rights in the conditional category, the way Dimensional does):

| Line | Issuer | What it exercises | Outcome |
|---|---|---|---|
| 1 | Delta plc | A known ISIN with the same identifier and another spelling | Nothing |
| 2 | Epsilon S.A. | A known ISIN that brings the missing identifier | Identifier filled in on company 4 |
| 3 | Epsilon SA | A name that now belongs only to a company with an identifier | Company 9, a second "Epsilon" |
| 4 | Theta AG | A known ISIN with another identifier | Case for the agent: `different_lei` |
| 5 | Iota KK | A known ISIN with an identifier company 3 already has | Case for the agent: `lei_belongs_to_another_company` |
| 6 | Kappa Co Ltd | A receipt by label (`GDR`); same identifier as line 7 | Not loaded: company already loaded |
| 7 | Kappa Co Ltd | The company's own share | Company 10 |
| 8 | Lambda Bhd | A receipt by label; same name as company 8, no identifier | Not loaded: company already loaded |
| 9 | Mu Property Trust | Units in the conditional category | Company 11 |
| 10 | Nu Corp | Rights in the conditional category | Company 12 |
| 11 | U.S. Dollar | A currency balance, no ISIN | Not loaded: no valid ISIN |
| 12 | Zeta Ltd | The ISIN of VXUS line 3, here labelled `ADR` | Not loaded: company already loaded |
| 13 | Xi Corp | An ISIN with a wrong check digit | Not loaded: no valid ISIN |
| 14 | Omicron Ltd | A receipt by label only; the company has no other line | Company 14 |

In total: 31 lines, 14 companies, 16 instruments, 11 lines not loaded, 2 cases for the agent. The expected output files are in `expected/`.

## Sample decisions

`decisions/lei.csv` holds two decisions on legal-entity identifiers (ADR 0010) that settle the two cases above. Tests pass it to the load explicitly; the load's own decisions file concerns real securities and matches nothing here.

| Security | Decided identifier | Effect |
|---|---|---|
| `DE00000T0019` (Theta AG) | The one DFAX files | Company 6 carries it instead of the one VXUS files |
| `JP300000I006` (Iota KK) | An identifier neither fund files | Company 7, which had none, carries it |

With these decisions the load reports no case.

`decisions/name.csv` holds one decision on a company name (ADR 0012). None of the sample filings carries a vendor placeholder, so the sample decision does the next closest thing: it takes the spelling the second fund files.

| Security | Decided name | Effect |
|---|---|---|
| `JP300000I006` (Iota KK) | "Iota KK", as DFAX files it | Company 7 is called "Iota KK" instead of "IOTA KK", the spelling VXUS files |

The two spellings compare as equal, so the decision changes no join.

`decisions/excluded.csv` keeps one security out of the universe (ADR 0013).

| Security | Why | Effect |
|---|---|---|
| `US00000H0017` (Eta Holdings Ltd, VXUS line 5) | Made up: a receipt whose ordinary share is listed at home | The line is not loaded and is listed with the reason `excluded_by_decision`. Eta Holdings has no other line, so the company is not loaded: 13 companies and 15 instruments, and Omicron Ltd becomes company 13 |

A database that was loaded before the exclusion existed is refused; a rebuilt one is right.

`decisions/ordinary_share.csv` reads one receipt as its ordinary share (ADR 0015).

| Receipt | Ordinary share | Effect |
|---|---|---|
| `US00000O0018` (Omicron Ltd, DFAX line 14) | `SG00000O0017`, made up | The line is loaded as an ordinary line under the ordinary share's ISIN. Still 14 companies and 16 instruments, but Omicron is now company 13 with instrument 15, ahead of Eta Holdings, whose only line is still a receipt. One receipt fewer is recognised |

A database that already holds the receipt is refused, as for an exclusion.
