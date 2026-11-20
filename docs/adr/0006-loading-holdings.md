# ADR 0006: Holdings are loaded straight into `company` and `instrument`

- Status: Accepted
- Date: 2026-11-20

## Decision

The holdings filings of ADR 0004 are read and written straight into `company` and `instrument` (ADR 0003). There is no table for funds and none for holdings lines. Every line is loaded, with three stated exceptions.

### The load, step by step

| Step | What happens |
|---|---|
| 1. Read | The three filings are read in a fixed order: VTI, VXUS, DFAX. |
| 2. Leave out | A line the filing classifies as debt or as a derivative is not loaded. A line without a valid ISIN cannot be loaded and is listed in the load output. Nothing else is left out; a line valued at zero is loaded like any other. |
| 3. Set receipts aside | A security the receipt check below recognises as a depositary receipt waits until step 5. |
| 4. Load ordinary lines | For each line, the company is found or added, and the instrument is added if its ISIN is new. |
| 5. Load receipts | A receipt is loaded, in the same way, only when no company loaded in step 4 has its legal-entity identifier or its name. Otherwise it is not loaded: the company is already in the universe through its own shares. |

### Finding the company for a line

| The line has | The company is |
|---|---|
| A legal-entity identifier | The company with that identifier. If there is none, a new company with the line's name and identifier. |
| No legal-entity identifier | The company without an identifier that has exactly that name, ignoring upper and lower case and spacing. If there is none, a new company with that name. |

### When the ISIN is already an instrument

This happens when a second fund holds a security the first fund already brought in.

| Situation | What happens |
|---|---|
| The line's legal-entity identifier equals the company's, or the line has none | Nothing. A differently spelled name is not a conflict: the same ISIN is the same security. |
| The company has no legal-entity identifier and the line has one | The identifier is filled in. If another company already has it, the case goes to the agent. |
| The line's legal-entity identifier differs from the company's | The case goes to the agent. |

### The receipt check

It reads three things on every line of a security.

| Read | A receipt when |
|---|---|
| The filing's category label | It is `ADR`, `GDR` or `DEPOSITORY RECEIPT`. Dimensional labels its receipts this way; Vanguard does not. |
| The security title | It contains one of the words below as a whole word. |
| The issuer name | The same. |

The words: ADR, ADRS, ADS, GDR, GDRS, NVDR, BDR, CDI, SDR, EDR, SPONSORED, SPON, SPN, and "depositary" or "depository" followed by receipt, share or interest. The list lives in the code and can grow without a new record.

### What takes the place of tables

| Topic | Decision |
|---|---|
| Funds and holdings lines | Not stored in the database. The three funds and their scope (ADR 0004) are a constant in the loader. The filing files are kept under `data/`, which is never committed; they can be downloaded again from the SEC by their filing numbers. |
| Later loads | Run by hand when newer filings are wanted. A load only adds companies and instruments. Nothing is ever deleted. |
| A security no fund holds | Added by hand, straight into `company` and `instrument`. |
| Receipts that were still loaded | An agent checks the loaded instruments afterwards. The listing rule of ADR 0005 already sends it every US-coded ISIN held by a non-US fund. |

## Evidence

The load was simulated on 2026-11-20 on the three filings named in ADR 0004.

| Result | Count |
|---|---|
| Lines for shares, units, rights and receipts | 22,820 |
| Of those, without a valid ISIN: listed, not loaded | 56 |
| Lines left out as debt or derivatives | 107, of which 9 carry an ISIN (three government bonds, six equity derivatives) |
| Securities (distinct ISINs) | 16,124 |
| Recognised as receipts | 192 |
| Receipts not loaded: the company is already there | 145 |
| Receipts loaded: the company has no other line | 47 |
| **Instruments** | **15,979** |
| **Companies** | **15,619** (9,520 with a legal-entity identifier, 6,099 without) |
| Instruments joined to an existing company by legal-entity identifier | 320 |
| Instruments joined to an existing company by exact name | 40 |
| Legal-entity identifiers filled in from a later fund | 82 |
| Cases for the agent: an existing ISIN with a different identifier | 15 |

The filings also hold 40 cash lines (money-market funds and foreign-currency balances), none with an ISIN.

### Why names are matched exactly, and only exactly

| Finding | Measurement |
|---|---|
| Exact name joins are right | Every exact-name join was checked by eye: share classes, mainland and Hong Kong lines of one company, a common and a preferred share. |
| Spelling differs between sponsors | 5,547 ISINs are spelled differently by Vanguard and Dimensional ("JHSF PARTICIPACOES S.A." and "JHSF PARTICIPACOES SA"). Reporting each difference would have produced 1,683 cases. |
| Looser matching joins different companies | 28 groups of look-alike names carry different legal-entity identifiers: Pfizer Inc and Pfizer Ltd (India), Domino's Pizza Inc and Domino's Pizza Group PLC, Humana Inc and Humana AB. |

### What the receipt check finds

| Finding | Measurement |
|---|---|
| How the 192 are recognised | 124 only by Dimensional's category label, 36 by label and wording, 32 only by wording. A check on the name alone would find 68. |
| The 47 that are loaded | 23 Chinese companies listed in New York (PDD, Vipshop, TAL Education), 9 Russian companies frozen at a value of zero, 7 companies whose main listing is legally a receipt (James Hardie, Light & Wonder, SES), and 8 others. Four of the 8 are receipts of a company that is in the universe under a differently spelled name (KT, Woori Financial). |
| What it misses | 15 US-coded ISINs in the non-US funds are not recognised, about 12 of them receipts (Kanzhun, Qfin, Tuya). All 15 go to the agent under ADR 0005. |
| Receipts by fund | VTI holds none. VXUS files 64 as ordinary common shares. DFAX files 161 lines under a labelled category, 6.5% of the fund. |

## Why this design

- **The author wants a one-off exercise, with no extra tables.** The universe is set once from three files and then used. Fund and holdings tables can be added later without touching `company` or `instrument`.
- **Nothing is left behind.** The author's rule: every line is loaded unless the filing itself says it is debt or a derivative.
- **Receipts are kept out where that is safe.** A receipt whose company already has its own shares in the universe adds nothing. A receipt that is the company's only line is the company, so it is loaded and checked.
- **A filing does not say reliably what is a receipt.** The form has no field for it. One sponsor labels receipts by its own choice, the other files them as common shares, which is why the check is a keyword list backed by an agent.

## Consequences

- **The database cannot say which fund holds an instrument, or since when.** That is in the filing files only.
- **The filing files must be at hand when listings are filled.** ADR 0005 reads each line's trading currency and each fund's scope from them.
- **Loaded and hand-added instruments look the same.** That is harmless while nothing is deleted.
- **An instrument no fund holds any more stays in the universe.**
- **The stored company name is the first fund's spelling.**
- **Some companies are split.** About 150 securities without a legal-entity identifier sit in a company row of their own although a sibling line is in the universe, because the two sponsors spell the name differently. The largest group is 66 Thai local and foreign-board shares. Such a company can appear twice in a screen.
- **Rights and units are loaded.** Units are real listings. Rights will get no listing.
- **The reader must handle the filing's conditional category.** Dimensional files receipts, units and rights there; a reader that takes only "common" and "preferred" misses 190 lines of DFAX.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A `fund` table and a holdings table | Rejected by the author for a one-off exercise. They can be added later. |
| Report every differently spelled name on an existing ISIN | 1,683 cases, almost all spelling. |
| One company per security when there is no legal-entity identifier | It misses the 40 correct name joins. |
| Looser name matching | It would join different companies (28 proven cases). |
| Leave out every recognised receipt | It drops the 47 companies whose only line is a receipt. |
| Load every receipt and let the agent sort them | 145 more cases for the agent, each a company that is already in the universe. |
| Take only the "common" and "preferred" categories | It misses Dimensional's units, five of which are companies not otherwise in the universe, and hides its receipts. |

## Not decided here

- Where the load output (the lines not loaded and the cases for the agent) is written. It is a generated file, not committed.
- How a later correction to a company, such as merging two rows, is recorded.
- Whether the name comparison should also ignore punctuation. In the simulation it changes one join and two receipts ("ChipMOS Technologies Inc" and "ChipMOS TECHNOLOGIES INC." would then match).
- How a listing is found for each instrument (ADR 0005).
