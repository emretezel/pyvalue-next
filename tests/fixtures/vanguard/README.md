# Sample Vanguard holdings files

Two small files in the shape of Vanguard's own holdings file (ADR 0016), for the tests of the universe load: one for each sample filing under `tests/fixtures/nport`. Every company, ticker and identifier is made up.

A file is what the load saves after a download: the pages of one fund joined into one document, with the number of rows, the date, and the rows under `fund.entity`.

The load attaches a ticker and a SEDOL to a line of the filing only when the line's ISIN has exactly one line in the filing and exactly one row here. The rows are chosen to exercise each case.

The long name of a row is attached to every line of its ISIN, and the receipt check reads it (ADR 0020). In these samples the names say "ADR" or "GDR" only for securities that the sample filings already mark as receipts, so they change nothing; the tests of the rule change a name on the fly.

`VTI.json`:

| Row | What it exercises | Outcome for the filing's line |
|---|---|---|
| Alpha Corp. | One line, one row | Ticker `ALPH` and SEDOL attached to VTI line 1 |
| Alpha Corp. Preferred | A ticker with a dot | Ticker `ALPH.PA` and SEDOL attached to line 2 |
| Beta Inc. | An empty ticker | SEDOL attached to line 3, no ticker |
| Beta Inc. Class B, twice | Two rows for one ISIN | Nothing attached to line 4 |
| E-mini S&P 500 Future | A row without an ISIN | Belongs to no line |
| Rho Inc. | A holding the filing does not have | Belongs to no line |

`VXUS.json`:

| Row | What it exercises | Outcome for the filing's line |
|---|---|---|
| Delta, Epsilon SA, Zeta ADR, Theta, Iota | An ISIN with two lines in the filing | Nothing attached to either line |
| Zeta Ltd., Eta Holdings ADR, Lambda, Kappa GDR, Kappa, Mu | One line, one row | Ticker and SEDOL attached (lines 4, 5, 10, 16, 17, 19) |
| Epsilon SA Class B | A ticker with a space | Ticker `EPS B` attached to line 13 |
| Omicron Ltd. ADR | A SEDOL of the wrong shape | Ticker `OMC` attached to line 24, no SEDOL |

Lines of the filings with no row here get no ticker and no SEDOL: Lambda's receipt (line 18), Nu Corp (line 20) and Xi Corp (line 23).
