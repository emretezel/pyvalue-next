# ADR 0023: Funds and property trusts are kept out of the universe

- Status: Accepted
- Date: 2026-11-26
- Builds on: ADR 0013, whose file and mechanism it uses unchanged. Nothing is superseded.

## Decision

The universe holds companies. A fund and a property trust are not what pyvalue analyses, and their securities are kept out of the universe, each as a row of `excluded.csv` (ADR 0013). No code changes.

| Kind of security | In the universe | How it is recognised |
|---|---|---|
| Property trust (a real-estate investment trust, REIT) | No | The open identifier mapping (OpenFIGI) gives the security the type `REIT` |
| Security with a mixed label: some of its market lines are typed `REIT`, others common stock | Checked one by one | Out when the company has trust status today, by its own filings or announcements |
| Stapled security built around a property trust | No | The group's own description: a property trust stapled to its manager or to a business trust |
| Property trust in another legal form | No | A trust whose business is owning property, whatever OpenFIGI calls its units |
| Infrastructure fund or infrastructure investment trust | No | Its legal form: a Thai infrastructure fund is a mutual fund, an Indian infrastructure investment trust (InvIT) is the twin of India's property trusts |
| Exchange-traded fund | No | Already so (ADR 0013) |
| Property company that is not a trust: a developer or a landlord in company form | Yes | |
| Company that gave up its trust status | Yes | |
| Stapled security or unit of an operating business | Yes | |
| Business trust that runs a business | Yes | |

**The test is the legal form, not the business.** A trust that owns phone masts, data centres, timber land or mortgages is out, because it is a property trust by law. A company that owns shopping centres is in.

**Upkeep.** When newer filings are pinned, the securities that are new are classified in the same way before the database is rebuilt. Today that is a one-off script, as in this review.

## Why

- **The author decided it** on 2026-11-26: "remove funds and property trusts", and confirmed the list of 420 when it was shown by kind and country.
- **pyvalue analyses companies, not funds.** The first exclusion of a fund says so (ADR 0013). A property trust is the same kind of vehicle: it holds assets and passes their income through.
- **One legal test can be repeated.** Whether a trust "is really a landlord" is a judgement that would have to be made again for every new security. Whether it is a trust is a fact with a source.
- **Kept out at the source.** A security that is not in the universe gets no listing and no downloaded fundamentals later.
- **The existing file is enough.** 420 rows in a file the load already applies, against a new rule in the load that would need a type for every security and a source for it.

## Evidence

Measured on 2026-11-26 on the local database, after the 59 exclusions of the two-fund review.

**The classification.** OpenFIGI's public mapping was asked for every ISIN in the universe, ten in a request, and its `securityType` was read for every market line of each.

| OpenFIGI type | Securities |
|---|---|
| Common stock | 11,416 |
| `REIT` | 389 |
| Foreign share (Thailand) | 104 |
| No entry | 73 |
| Preference share | 50 |
| Unit | 23 |
| American depositary receipt | 19 |
| Common stock on some lines, `REIT` on others | 18 |
| Stapled security | 14 |
| Eleven other types | 19 |
| **Total** | **12,125** |

**The 420 securities.**

| Group | Securities | How it was confirmed |
|---|---|---|
| Typed `REIT` on every market line | 391 | OpenFIGI. Two of them are also typed as stapled (Goodman Group, DigiCo Infrastructure REIT) |
| Mixed label, a trust today | 12 | One by one: Americold, Ellington Financial, Postal Realty, Janus Living, Claros Mortgage, NexPoint Diversified, Grainger, Sirius Real Estate, and four Turkish real-estate investment companies (Ziraat, Peker, Kizilbuk, Yeni Gimat) |
| Stapled around a property trust | 5 | BWP Property Group, Stoneweg Europe Stapled Trust, Far East Hospitality Trust, CDL Hospitality Trusts, CapitaLand Ascott Trust |
| Filed under a retired code | 4 | OpenFIGI has no entry for the filed ISIN. Granite Point Mortgage, Lument Finance and National Healthcare Properties are typed `REIT` under their ticker; Modiv Industrial by its own description |
| Property trust in another legal form | 2 | CapitaLand India Trust (a business trust that owns business parks), Chartwell Retirement Residences (an open-ended real-estate trust) |
| Infrastructure fund | 6 | Three Thai infrastructure funds (Digital Telecommunications, Thailand Future Fund, 3BB Internet) and three Indian infrastructure investment trusts (IndiGrid, PowerGrid, IRB) |
| **Total** | **420** | |

Each of the 420 is its company's only security, so 420 companies leave. Together they are 2.0% of the value the two funds hold.

| Country | Securities | Country | Securities |
|---|---|---|---|
| United States | 182 | South Africa | 8 |
| Japan | 52 | Belgium | 7 |
| Australia | 29 | India | 7 |
| Singapore | 29 | Hong Kong | 6 |
| United Kingdom | 18 | Korea | 5 |
| Brazil | 17 | Thailand | 5 |
| Canada | 15 | Malaysia | 4 |
| Turkey | 14 | Mexico | 3 |
| France | 9 | Israel, Philippines, Spain, Netherlands | 2 each |
| | | Saudi Arabia, New Zealand | 1 each |

The largest are Welltower, Prologis, Equinix, American Tower, Simon Property Group, Digital Realty, Realty Income and Public Storage.

**What was checked and stays.**

| Security | Why it stays |
|---|---|
| GEO Group, CoreCivic | Gave up trust status in 2021 |
| HA Sustainable Infrastructure Capital | Gave up trust status from 2024 |
| Seritage Growth Properties | Gave up trust status from 2022 |
| Uniti Group | Not a trust since its merger with Windstream in August 2025 |
| HMC Capital | A fund manager; one market line carries the trust label |
| Tera Yatirim Teknoloji Holding | The trust label belongs to an earlier name of the company |
| Transurban, APA Group, Atlas Arteria, Lendlease, Centuria Capital, Gemlife Communities | Stapled securities of operating businesses |
| Precinct Properties, Stride Property, Goodman New Zealand, Argosy Property, Kiwi Property | New Zealand property companies; none is a trust |
| NetLink NBN Trust, Hutchison Port Holdings Trust, Keppel Infrastructure Trust | Singapore business trusts that run a network, ports and utilities |
| Thirteen Brazilian and Mexican units (Klabin, BTG Pactual, Femsa, Cemex and others) | Bundles of an ordinary company's shares |
| Baskent Dogalgaz | A gas distributor in the Turkish legal form of a real-estate investment company; OpenFIGI types it as common stock |

**Rebuilding the database.** The local database was rebuilt on 2026-11-26 with the 420 rows and one more warrant the classification found (Presidio Property Trust, a position of 1,765 dollars).

| Result | Before | After |
|---|---|---|
| Companies | 11,900 | 11,479 |
| Securities | 12,125 | 11,704 |
| Holding lines | 12,155 | 11,734 |
| Lines kept out by a decision | 73 | 494 |
| Rows of `excluded.csv` | 72 | 493 |

Every other security is under a company of the same name and identifier as before.

## Consequences

- **420 companies are no longer in the universe,** among them some of the largest listed in the United States. They come back only if their rows are removed.
- **OpenFIGI's label is the test, so a few trusts may remain:** those it types as plain common stock and whose name does not say what they are. The industry label that comes with the fundamentals will show them, and each is then one more row.
- **A stale label can also keep a company out wrongly.** Seven mixed labels were found to be out of date and corrected by hand; a label that is `REIT` on every line was taken as it is.
- **A change of status is not followed by itself.** A company that becomes a trust, or stops being one, is noticed only when the securities are classified again.
- **Every new pinned filing needs the classification of what is new.** Should that become a routine, a command for it is its own decision.
- **Property companies stay,** so the universe still holds the real-estate business; it holds no trusts.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Leave them in and drop them in the screen, by industry | The author decided to remove them. Out of the universe, they also cost no listing work and no downloads |
| Recognise them by the words in their name | Counted about 180. Most trusts do not say what they are in their name |
| A rule in the load that reads a type for every security | A stored type and a source for it, for what a file of rows does today |
| Remove the whole real-estate business, companies included | The decision names trusts and funds. A company's accounts can be read like any other's |
| Keep the trusts that are not landlords: masts, data centres, timber, mortgages | A judgement on every security in place of one test with a source |

## Not decided here

- A command that repeats the classification.
- Investment holding companies, which are companies in law and stay.
