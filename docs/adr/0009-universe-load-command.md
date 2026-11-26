# ADR 0009: The universe load is a command that reads pinned filings

- Status: Accepted. The open point on how an agent's answer reaches the database is settled by ADR 0010. ADR 0013 adds a fourth reason to `lines_not_loaded.csv`: `excluded_by_decision`. ADR 0014 widens what "a company loaded in step 4" is recognised by in the receipt rule. ADR 0015 adds a fourth decisions file, which reads a receipt as its ordinary share. ADR 0016 changes the funds to VTI and VXUS and adds the sponsor's own holdings file to what is downloaded; ADR 0017 adds the `fund` and `holding` rows to what the load writes.
- Date: 2026-11-20

## Decision

The load of ADR 0006 is code in this repository, the `pyvalue.universe` component, and is run with one command. It reads three filings that are named by their SEC filing numbers. This record also settles the points ADR 0006 left open.

| Topic | Decision |
|---|---|
| Where the code lives | In the repository, with tests. It is not a throwaway script |
| How it is run | `pyvalue universe load`. `--db PATH` points it at another database |
| Which filings | The three of ADR 0004, pinned by filing number in a constant in the code |
| Where the filings are kept | `data/sec/<TICKER>_<filing number>.xml`. A filing is downloaded once; a file that is already there is used as it is |
| How pyvalue identifies itself to the SEC | The line `user_agent` in the section `[sec]` of `private/config.toml`. It is sent only as the `User-Agent` header to `www.sec.gov` |
| How much is saved at once | The whole load is one unit of work (ADR 0008): all three funds, or nothing |
| Where the load output goes | Two files under `data/universe/`, written after the load is saved and overwritten by every run |
| Name comparison | Ignores upper and lower case and spacing, and nothing else. Punctuation counts |

## The files

| File | Content | Committed |
|---|---|---|
| `data/sec/VTI_0000036405-26-000480.xml` and the two others | The filings as the SEC serves them | No |
| `data/universe/lines_not_loaded.csv` | One row per filing line that was not loaded, with the reason | No |
| `data/universe/cases_for_agent.csv` | One row per case ADR 0006 sends to the agent | No |

Reasons in `lines_not_loaded.csv`:

| Reason | Meaning |
|---|---|
| `debt_or_derivative` | The filing classifies the line as debt or as a derivative |
| `no_valid_isin` | The line has no ISIN, or one that fails the check below. Cash lines are here |
| `receipt_company_already_loaded` | A depositary receipt of a company that is in the universe through its own shares |

Reasons in `cases_for_agent.csv`:

| Reason | Meaning |
|---|---|
| `different_lei` | The ISIN is already an instrument, and the line names another legal-entity identifier than its company has |
| `lei_belongs_to_another_company` | The company of the ISIN has no identifier, the line supplies one, and another company already has it |

Every line of a filing is either loaded or listed in `lines_not_loaded.csv`.

## Rules the code needed that ADR 0006 does not spell out

| Topic | Rule |
|---|---|
| A valid ISIN | Twelve characters of the right shape, and a correct check digit |
| A valid legal-entity identifier | Twenty characters of the right shape, and correct check digits, which the standard only ever sets between 02 and 98. Any other value counts as none; the filings write `N/A` |
| Debt and derivatives | The filing categories `DBT`, `DCO`, `DCR`, `DE`, `DFE`, `DIR` and `DO` |
| Categories that are loaded | `EC`, `EP`, `STIV`, and everything filed under the conditional category `OTHER` |
| Any other category | The load stops and names the line. None occurs in the three filings |
| A filing file | Its series id and holdings date must equal the pinned ones, or it is refused |
| The stored company name | The first fund's spelling, with runs of spaces reduced to one |
| "A company loaded in step 4" (the receipt rule) | A company that an ordinary line of this run belongs to, whether the run added it or found it in the database |

## Running it again

- **With the same filings**, a run adds nothing and writes the same two files. Every ISIN is already an instrument.
- **With newer filings**, the pinned constant is changed in a commit, and the run adds what is new. Nothing is deleted (ADR 0006).
- **Open cases stay open.** A case for the agent is reported by every run until the database is corrected.

## Why this design

- **The load will run again.** ADR 0006 foresees later loads, and the database is not committed, so the code is the only way to rebuild it.
- **The database rule applies to it.** ADR 0008 allows no SQL outside `pyvalue.db`. A script that respects the rule needs the repositories and the unit of work anyway, which is most of the work.
- **Reading a filing is easy to get wrong.** The first reader written for the measurements missed 190 lines of DFAX (ADR 0006). Tests on sample filings pin the reading.
- **Pinned filings make the universe reproducible.** The database cannot say which filings it was built from (ADR 0006); the commit history of the constant can.
- **The listing step needs the same filings again** (ADR 0005), so they are kept and not fetched twice.
- **The author asked for the smallest mechanism**: generated files, not tables, for the load output.

## Evidence

Measured on 2026-11-20 on the three filings.

| Finding | Measurement |
|---|---|
| Lines in the three filings | 22,967: VTI 3,546, VXUS 8,868, DFAX 10,553 |
| Categories that occur | `EC`, `EP`, `DBT`, `DE`, `DFE`, `STIV`, and the conditional `OTHER` with the labels `ADR`, `GDR`, `DEPOSITORY RECEIPT`, `UNITS`, `RIGHTS` and `currency` |
| Legal-entity identifier field | Either twenty characters of the right shape or the text `N/A` |
| Issuer names | None empty; none with leading, trailing or repeated spaces |
| File sizes | 3.2, 8.3 and 10.4 megabytes |

The first run of the command, on 2026-11-20 on an empty database:

| Result | Count |
|---|---|
| Filings downloaded | 3, byte for byte the files the measurements of ADR 0004 and ADR 0006 used |
| Companies added | 15,619: 9,520 with a legal-entity identifier, 6,099 without |
| Instruments added | 15,979 |
| Lines that reached an instrument | 22,596: 15,979 new ones and 6,617 repeats of a security another line had brought in |
| Lines not loaded | 371: 107 debt or derivative, 96 without a valid ISIN (56 share-like lines and the 40 cash lines), 168 receipt lines of the 145 receipts whose company is already loaded |
| Cases for the agent | 15, all `different_lei` |
| Second run | Added nothing; both output files came out byte for byte the same |

Every figure that ADR 0006 predicted from the simulation was reproduced exactly.

## Consequences

- **A later load is a code change.** Newer filings mean new filing numbers in the constant, in a commit.
- **The first run needs the network and the contact line.** A missing line stops the command with a message that names it. Later runs need neither.
- **A failure leaves the database as it was**, but files already downloaded stay.
- **The two output files describe the latest run only.** They are not history.
- **A receipt can be loaded by a later run although its company is in the universe**, when no fund holds the company's own shares any more. The database does not record which instrument is a receipt.
- **The fund's scope and each line's trading currency are not read yet.** ADR 0005 needs them; they are added with the listing step.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A one-off script outside the repository | The universe could not be rebuilt, and the script would bypass the database rule or duplicate it. |
| Always load the newest filing of each fund | A run on another day would give another universe, with nothing recording which. |
| A separate download command | One more step to remember, for three files. |
| The contact string in an environment variable | The EODHD key already lives in `private/config.toml`; settings would be in two places. |
| One transaction per fund | A failure in the third fund would leave a universe that looks complete and is not. |
| Tables for the load output | Rejected by the author for a one-off exercise (ADR 0006). |

## Not decided here

- How the agent's answer to a case is applied to the database.
- How a later correction to a company, such as merging two rows, is recorded.
- A command that adds a single security by hand.
