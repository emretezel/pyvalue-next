# ADR 0015: A depositary receipt can be read as its ordinary share by a file the load applies

- Status: Accepted
- Date: 2026-11-21

## Decision

Where a fund holds a depositary receipt and the ISIN of the company's ordinary share is known, the load reads the fund's line as a line of the ordinary share. The pair is one row in a committed file. The company stays in the universe, through the share pyvalue wants to analyse.

| Topic | Decision |
|---|---|
| What a decision says | "This security is a receipt, and that security is the ordinary share it stands for" |
| Key | The ISIN of the receipt, as the funds file it |
| Where the file is | `src/pyvalue/universe/decisions/ordinary_share.csv`, committed and shipped inside the package |
| Who applies it | The load (`pyvalue universe load`). There is no separate command |
| What it overrules | The ISIN of every line of the receipt, and whatever in the line says "receipt" |
| What it keeps | The company's name and legal-entity identifier, which come from the filing line as before |
| A database that already holds the receipt | The load stops and asks for a rebuild, as for an excluded security (ADR 0013) |

This replaces the first use of ADR 0013. The receipts that were kept out of the universe on 2026-11-21 are now read as their ordinary shares, so their companies come back. The exclusions file and its mechanism stay, for a security that should be out altogether; today the file holds no row.

## The file

One row per receipt.

| Column | Required | Content |
|---|---|---|
| `isin` | yes | The receipt. No ISIN appears twice |
| `ordinary_isin` | yes | The ordinary share its lines are read as. Not the same as `isin`. Two receipts may name the same share |
| `company` | yes | The company's name, for the reader. The load does not use it |
| `decided_on` | yes | The date of the decision, `YYYY-MM-DD` |
| `evidence` | yes | What shows that the first is a receipt and the second its ordinary share, and where that share trades |

Example row:

| `isin` | `ordinary_isin` | `company` | `decided_on` | `evidence` |
|---|---|---|---|---|
| `US48268K1016` | `KR7030200000` | KT Corp | 2026-11-21 | New York receipt (ADR per OpenFIGI), held by DFAX. The ordinary share trades in Korea (OpenFIGI: common stock). No fund holds it |

## How the load applies it

| Situation | What happens |
|---|---|
| A line of a listed receipt | Loaded as a line of the ordinary share, and as an ordinary line, whatever its title or label says |
| A fund also holds the ordinary share | Both lines are the same security: one instrument |
| Two receipts of one company | Both are read as the same ordinary share: one instrument |
| The company has other receipts in the filings | They are left out by the receipt rule (ADR 0006, ADR 0014), because the company now has a line of its own |
| A decision on the company's identifier or name | It is keyed by the ordinary share. A decision keyed by the receipt is refused |
| A receipt that is also excluded, or an ordinary share that is itself listed as a receipt or excluded | The load stops and names it: the files contradict each other |
| The database already holds a listed receipt | The load stops before it writes anything and names the securities. The database has to be rebuilt |
| A row for a receipt no filing holds | Nothing happens |

Notes:

- **A line that is debt, a derivative or without a valid ISIN keeps its own reason** and is not loaded.
- **The line is still reported as filed.** Where a line appears in the load output, it shows the ISIN the fund filed.
- **Nothing else changes.** Joining by identifier and name, the receipt rule and the other decisions stay as they are.

## Why this design

- **The author asked for it**: "swap the ordinary share if you know the ISIN", and chose to apply it to every such receipt, "including the Russian ones".
- **It is what pyvalue analyses.** The author wants the fundamentals of the ordinary share, not of the receipt. A listing is found by the instrument's ISIN (ADR 0005), so the instrument has to be the ordinary share.
- **The company should not be lost.** Keeping a receipt out (ADR 0013) removed the company whenever no fund held its ordinary share. That was 18 companies.
- **A file the load applies survives a rebuild** and records the evidence for each pair (the argument of ADR 0010).
- **The filing line still says which company it is.** Only the security is corrected. No company is entered by hand.

## Evidence

Measured on 2026-11-21.

**The 26 receipts.** Each ordinary-share ISIN has a valid check digit and is confirmed as a share of the same company in at least one source other than the filings.

| Group | Receipts | Companies | Receipt to ordinary share | Sources for the ordinary share |
|---|---|---|---|---|
| In the universe as receipts until now | 5 | 5 | KT `US48268K1016` to `KR7030200000`; Cementos Pacasmayo `US15126Q2084` to `PEP239501005`; Vista Energy `US92837L1098` to `MX01VI0C0006`; JBS `BRJBSSBDR002` to `NL0015002J37`; XP `BRXPBRBDR001` to `KYG982391099` | OpenFIGI (common stock); for JBS and XP also the EU securities register, under the company's own identifier |
| Chinese companies with a Hong Kong share | 6 | 6 | Kanzhun `US48553T1060` to `KYG5224V1032`; Qfin `US88557W1018` to `KYG8851G1001`; Tuya `US90114C1071` to `KYG913841006`; Lufax `US54975P2011` to `KYG5700Y2097`; WeRide `US9509151083` to `KYG9560F1028`; Pony AI `US7329081084` to `KYG7171B1068` | The Hong Kong exchange's list of securities; OpenFIGI |
| James Hardie | 1 | 1 | `AU000000JHX1` to `IE000R94NGM2` | The EU securities register, under the company's own identifier; OpenFIGI |
| Russian companies with a Moscow share | 14 | 13 | Gazprom to `RU0007661625`; Sberbank to `RU0009029540`; RusHydro to `RU000A0JPKH7`; Sistema to `RU000A0DQZE3`; Norilsk Nickel to `RU0007288411`; Mechel to `RU000A0DKXV5`; Novatek to `RU000A0DKVS5`; Severstal to `RU0009046510`; Surgutneftegas to `RU0008926258`; VTB to `RU000A0JP5V6`; Magnitogorsk to `RU0009084396`; PhosAgro's two receipts to `RU000A0JRKT8`; Polyus to `RU000A0JNAA8` | The Moscow Exchange's list of shares on its main board, all with trades on 2026-11-21 |

- **That each first code is a receipt** is given by OpenFIGI or the EU register for 25 of the 26. The exception is PhosAgro's line in VXUS, `US71922G4073`, which neither source knows; it is a US-coded security of a Russian company and is taken to be a receipt.
- **A fund already holds the ordinary share** of Kanzhun (DFAX) and VTB (VXUS). The other 23 ordinary shares are new to the universe.
- **One search result was discarded.** A second ISIN reported for Vista Energy, `MX01VI000003`, has an invalid check digit and is unknown to OpenFIGI.

**Rebuilding the database.** The local database was rebuilt on 2026-11-21.

| Result | Before | After |
|---|---|---|
| Instruments | 15,955 | 15,973 |
| Companies | 15,596 | 15,614 |
| Companies with an identifier | 9,507 | 9,520 |
| Lines not loaded | 402 | 374 |
| Lines kept out by decision | 28 | 0 |
| Receipts kept as the company's only line | 32 | 27 |

- **The five receipt ISINs are gone and 23 ordinary-share ISINs are new.** Every other security is under a company of the same name and identifier as before.
- **18 companies came back:** Qfin, Tuya, Lufax, WeRide, Pony AI, James Hardie and 12 Russian companies.
- **Pony AI's name decision returned** to `name.csv` (ADR 0012), now keyed by the ordinary share. The file holds 47 names.
- **The run before the rebuild** refused the old database and changed nothing.

## Consequences

- **The universe no longer equals what the funds literally hold.** For these companies it holds the share, where the fund holds the receipt.
- **The listing step will not fill these automatically.** Its rule takes the trading country from the currency in which the fund holds the line (ADR 0005), and the fund holds a receipt in US dollars or Brazilian reais. The 23 new ordinary shares go to the agent.
- **13 Russian companies are in the universe** under shares a Western investor cannot trade today. Whether the provider covers the Moscow Exchange is not known.
- **A swap needs a rebuild**, and row ids are renumbered by it, as with an exclusion.
- **That the two securities belong together is not checked by code.** The evidence column is for the reviewer.
- **A wrong pair would attach a company to another company's share.** The load cannot notice that. Each pair has to be confirmed in a source outside the filings before it is added.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep such receipts out (ADR 0013, as decided earlier the same day) | The company leaves the universe whenever no fund holds its ordinary share. |
| A file of companies and securities added by hand | It would need the company's name and identifier typed in. Here the filing line already supplies both. |
| One file for exclusions and swaps, with an optional second ISIN | The two say different things: one removes a security, the other keeps the company. |
| Leave the receipt and give it the ordinary share's listing in the listing step | A listing hangs on an instrument, and the instrument's ISIN would then be the receipt's (ADR 0003). |

## Not decided here

- The 29 receipts for which no listed ordinary share was found: 23 Chinese companies listed in New York, four Australian depositary interests, SES and Heijmans.
- The Vanguard emerging-markets fund that VXUS holds and the load took for a company.
- Adding a company that no fund holds in any form.
- Whether the Russian companies should get a listing.
