# ADR 0004: The universe comes from the SEC holdings filings of three funds

- Status: Accepted
- Date: 2026-11-20

## Decision

pyvalue's stock universe is the set of securities held by three US-registered funds. Each fund's holdings are read from its public quarterly holdings filing at the US Securities and Exchange Commission (form N-PORT).

| Fund | Ticker | SEC series id | What it covers | Scope |
|---|---|---|---|---|
| Vanguard Total Stock Market Index Fund | VTI | `S000002848` | All US companies, micro-caps included | US |
| Vanguard Total International Stock Index Fund | VXUS | `S000002932` | The non-US index, large to small companies | Non-US |
| Dimensional World ex U.S. Core Equity 2 ETF | DFAX | `S000070905` | Non-US companies, reaching below the index floor | Non-US |

| Rule | What it means |
|---|---|
| What is taken from a filing | Every line that carries a valid ISIN, except lines the filing classifies as debt or derivatives. Depositary receipts follow the rule of ADR 0006. |
| What a line becomes | One instrument per ISIN, under ADR 0003, loaded as ADR 0006 describes. A security held by two funds is one instrument. |
| What does not decide membership | A data provider's catalogue of listings. A provider is asked about a security only after a fund has put it in the universe (ADR 0005). |
| What "Scope" is for | It says whether the fund is expected to hold US-coded ISINs. ADR 0005 uses it to find depositary receipts. |

## What a holdings line carries

The same for all three funds, except where noted. Example: Tencent as reported by VXUS.

| Field | Example | Filled (VTI / VXUS / DFAX) |
|---|---|---|
| Issuer name | Tencent Holdings Ltd | 100% |
| Security title | TENCENT | 100% |
| ISIN | `KYG875721634` | 99.2% / 99.8% / 99.9% |
| Issuer's legal-entity identifier | `254900N4SLUMW4XUYY11` | 72% / 65% / 59% |
| Trading currency | HKD | 100% |
| Country | HK | 100% |
| Shares held, value in US dollars, share of the fund | 91,841,140; USD 5.6bn; 0.87% | 100% |
| Category | common | 100% |
| SEDOL | `BMMV2K8` | DFAX only: 98.8% |

Not in the filing: the exchange, the ticker (one line has one), a field that says a security is a depositary receipt, the sector, and the size of the company.

Three fields need care:

- **Category depends on the sponsor.** Vanguard files every share line as "common" or "preferred", receipts included. Dimensional files receipts, units and rights under a separate "other" category with a label such as `ADR`: 190 lines of DFAX. The fill rates above are for the common and preferred lines.
- **Country means different things per sponsor.** For Tencent, Vanguard writes `HK`, where it trades. Dimensional writes `KY`, the Cayman Islands, where it is incorporated.
- **Trading currency is consistent.** Both sponsors report Tencent in HKD. The funds are listed in the US but hold foreign shares in local currency: only 106 of VXUS's 8,776 equity lines and 126 of DFAX's 10,321 are held in US dollars.

## Evidence

Measured on 2026-11-20 on the latest public filing of 29 candidate funds. To compare funds on one footing, a "security" in this section is a line in the "common" or "preferred" category with a valid ISIN and a value above zero, counted once per ISIN. The load itself takes more lines than that (ADR 0006) and gives 15,979 instruments.

### The three funds

| Fund | Holdings date | Filed | SEC filing number | Common and preferred lines | Of those, without a valid ISIN | Securities |
|---|---|---|---|---|---|---|
| VTI | 2026-06-30 | 2026-08-28 | `0000036405-26-000480` | 3,531 | 29 | 3,502 |
| VXUS | 2026-07-31 | 2026-09-28 | `0000736054-26-000275` | 8,776 | 19 | 8,729 |
| DFAX | 2026-07-31 | 2026-09-24 | `0001004726-26-009205` | 10,321 | 6 | 10,178 |
| All three together | | | | 22,628 | 54 | 15,961 |

The 54 lines without a valid ISIN are contingent value rights and delisted or untradeable leftovers. The filing numbers identify the exact files; the SEC keeps them at a permanent address.

### Why three, and why these

How many securities each combination holds, and how much of five dedicated small-company funds it already contains. The five are used only as a yardstick.

| Combination | Securities | US micro-caps (IWC) | Developed small (SCZ) | Developed small, second index (GWX) | Emerging small (EEMS) | Emerging small, second index (EWX) |
|---|---|---|---|---|---|---|
| VT alone (Vanguard Total World) | 10,048 | 0% | 89% | 72% | 89% | 49% |
| VTI + VXUS | 12,226 | 92% | 89% | 72% | 89% | 52% |
| **VTI + VXUS + DFAX** | **15,961** | **92%** | **94%** | **84%** | **95%** | **78%** |
| + DFEM + DFIS + FSKAX (six funds) | 16,963 | 96% | 96% | 87% | 95% | 81% |
| All 29 funds measured | just over 19,500 | | | | | |

What each of the three contributes:

| Finding | Measurement |
|---|---|
| A US total-market fund already reaches the micro-caps | VTI holds 92% of the dedicated micro-cap fund IWC (1,372 securities) and 93% of the Russell 2000 fund IWM |
| One world fund does not | VT holds 1 of IWC's 1,372 |
| DFAX adds what the index funds lack | 3,735 securities that VTI and VXUS do not hold: Taiwan 539, Japan 495, Korea 424, India 339, China 275, Hong Kong 214, Thailand 178, others 1,271 |
| DFAX cannot replace VXUS | VXUS holds about 2,290 securities that VTI and DFAX lack |
| A fourth fund adds little | DFEM and DFIS together add 670. FSKAX adds 333 US securities. |

### The author's watchlist

All 22 listings on the legacy project's watchlist are in the three funds, matched by ISIN, each on its home line: the 17 US names in VTI, and SK Hynix, LVMH, Novo Nordisk, Realtek and Grupo México in both VXUS and DFAX.

### Depositary receipts by fund

A fund that holds receipts in place of home shares is a poor source. All three funds were checked line by line.

| Fund | Receipts | How they appear in the filing |
|---|---|---|
| VTI | None | |
| VXUS | 64 securities | Filed as ordinary common shares. The title says "ADR" or "GDR" for 52 of them. |
| DFAX | 161 lines, 6.5% of the fund | Filed under a separate category, labelled `ADR`, `GDR` or `DEPOSITORY RECEIPT`. |

DFAX's receipts do not displace home shares in the universe. Of its 161 receipt lines, 115 belong to a company that the three funds also hold on its own shares, 32 are the same receipts VXUS holds, and 14 belong to a company not otherwise held. The 3,735 securities DFAX adds are ordinary local lines.

Earlier work (2026-11-15) found that the US-listed SPDR global fund SPGM holds receipts for 57 companies, 3.6% of that fund.

### What the three funds leave out

| Gap | Measurement |
|---|---|
| The smallest companies | In Korea and Taiwan the three funds hold 81% to 90% of companies worth USD 300m to 1bn, 56% to 75% of those worth USD 100m to 300m, about a third of those worth USD 50m to 100m, and 2% to 3% of those worth USD 10m to 50m. Company sizes are from the legacy database. |
| Small mainland China companies | No combination measured, up to 13 funds, holds one worth less than about USD 300m. |
| UK small companies | 232 UK securities in the three funds; DFEM and DFIS would raise that to 323. |
| Markets the first provider does not serve | 4,588 of the 15,961 (29%) trade in a country where the legacy EODHD catalogue has no exchange. For 3,651 of them EODHD documents no exchange either: Japan 1,853, India 992, Turkey 213, Saudi Arabia 150, Singapore 120, Italy 107, others 216. The other 937 trade in Hong Kong, Israel and Iceland, which EODHD's documentation lists but the catalogue lacked. |

The legacy catalogue could not be used to measure coverage in the US, Canada or the UK: its lines there include depositary receipts and investment trusts that no equity fund holds.

## Why this design

The author's requirement is a few funds that together cover the majority of the world's actively traded stocks, micro-caps included, holding companies on their home listing. The universe is not to come from a provider's catalogue: the legacy project stored every line its vendor listed (75,680 listings), most of them companies it would never analyse, and could not reliably tell the home line from the others.

Funds were compared on the same footing, the SEC filing, because every US-registered fund files it in one format, with an ISIN on practically every line.

## Consequences

- **The universe is about 16,000 securities** (15,979 instruments under ADR 0006), against 75,680 listings in the legacy catalogue.
- **Membership is as old as the filings.** Each fund's filing becomes public about 60 days after the quarter it describes, so the list is two to five months old.
- **A security enters only when a fund holds it.** A newly listed company appears after an index adds it. A stock the author follows that no fund holds is not in the universe; all 22 watchlist stocks are held today.
- **Companies below roughly USD 50m are mostly absent.**
- **DFAX is not an index fund.** Its manager decides what it holds, so its coverage can change without notice. The count of securities per fund should be watched at each load.
- **The SEC asks automated clients to identify themselves.** The contact string is configuration, kept in `private/config.toml` and never committed.
- **Adding a fund later does not change the schema** of ADR 0003.

## Alternatives considered

| Alternative | Why not |
|---|---|
| One world fund (VT) | 10,048 securities and no US micro-caps. |
| VTI and VXUS only | 12,226 securities. Non-US coverage stops at the index floor: 52% of one emerging-markets small-company fund. |
| Six funds (add DFEM, DFIS and FSKAX) | 1,002 more securities, a 6% gain, for twice the number of funds. It can be added later without a schema change. |
| A separate US micro-cap fund (IWC) | VTI already holds 92% of it. |
| The two Dimensional mutual funds (emerging and international core equity) | They add 1,619 securities, a 10% gain, for two more funds. They can be added later without a schema change. |
| The sponsors' own daily holdings files | Each sponsor has its own format and address, and the addresses move. Whether the Vanguard and Dimensional files carry ISINs was not checked. |
| The SPDR all-cap UCITS file | 6,064 securities; large, mid and small companies only. |
| The provider's catalogue of listings as the universe | Rejected by the author. |

## Not decided here

- How the filings are loaded: which lines are left out, how companies are matched, how receipts are treated, and that nothing is stored about funds or holdings lines (ADR 0006).
- How a listing is found for each instrument (ADR 0005).
