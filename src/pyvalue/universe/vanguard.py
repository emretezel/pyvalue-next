"""The adapter for Vanguard's funds.

It joins the lines of a fund's SEC filing with Vanguard's own holdings file,
which adds a ticker, a SEDOL and Vanguard's own name for the security, and it
carries what is particular to
Vanguard's documents: where the file is found, and that the country in a
Vanguard filing is the country the security trades in (ADR 0016).

Author: Emre Tezel
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyvalue.universe.errors import SponsorFileError, UniverseError
from pyvalue.universe.funds import FundDefinition
from pyvalue.universe.holdings import FundHoldings, HoldingLine
from pyvalue.universe.nport import FiledLine
from pyvalue.universe.vanguard_file import (
    FetchPage,
    VanguardRow,
    download_vanguard_file,
    fetch_from_vanguard,
    read_vanguard_file,
)

# Relative on purpose, like the folder of the filings: it belongs to the
# folder pyvalue is run from, under `data/`, which is never committed.
DEFAULT_VANGUARD_DIR: Path = Path("data") / "vanguard"

# Vanguard's own id of each fund, which is part of the file's address. It is
# knowledge of Vanguard's documents, so it lives here and not with the funds.
_FUND_IDS: Mapping[str, str] = {"VTI": "0970", "VXUS": "3369"}

# How many lines in a hundred may give a country other than that of their
# currency before the adapter stops trusting the country (ADR 0016). Real
# exceptions exist and are trading places too: a Shanghai B share is quoted in
# US dollars and trades in China. In the filings of 2026 they are 0.5%.
_MAX_DISAGREEMENT_PERCENT: int = 2

# The euro belongs to no one country, so a line held in euros cannot be
# checked this way.
_EURO: str = "EUR"


def join(filed: Sequence[FiledLine], rows: Sequence[VanguardRow]) -> tuple[HoldingLine, ...]:
    """Turn the lines of a filing into common lines, with what Vanguard's file adds.

    Neither document says which row of the file belongs to which line of the
    filing; the ISIN is all they share. A security held on two markets has
    two lines and two rows, each row with the SEDOL, and possibly the ticker,
    of one market. So a ticker and a SEDOL are attached only where the pairing
    is certain: the ISIN has exactly one line in the filing and exactly one
    row in the file.

    Vanguard's name for the security is another matter. It belongs to the
    security, not to one market, so every line of an ISIN gets it, whatever
    the number of lines and rows (ADR 0020).

    Args:
        filed: The lines of the fund's SEC filing, in order.
        rows: The rows of Vanguard's file for the same fund.

    Returns:
        One common line per filed line, in the same order. The trading
        country is the country the filing gives: Vanguard files where the
        security trades.
    """
    # The first row of an ISIN that gives a name names the security; further
    # rows of the same ISIN are the same security on another market.
    name_of_isin: dict[str, str] = {}
    for named in rows:
        if named.isin is not None and named.name is not None:
            name_of_isin.setdefault(named.isin, named.name)
    lines_per_isin = Counter(line.isin for line in filed if line.isin is not None)
    rows_per_isin = Counter(row.isin for row in rows if row.isin is not None)
    row_of_isin = {
        row.isin: row for row in rows if row.isin is not None and rows_per_isin[row.isin] == 1
    }
    lines: list[HoldingLine] = []
    for line in filed:
        row = (
            row_of_isin.get(line.isin)
            if line.isin is not None and lines_per_isin[line.isin] == 1
            else None
        )
        lines.append(
            HoldingLine(
                number=line.number,
                issuer_name=line.issuer_name,
                title=line.title,
                lei=line.lei,
                isin=line.isin,
                cusip=line.cusip,
                category=line.category,
                category_label=line.category_label,
                issuer_type=line.issuer_type,
                trading_country=line.country,
                currency=line.currency,
                ticker=None if row is None else row.ticker,
                sedol=None if row is None else row.sedol,
                sponsor_name=None if line.isin is None else name_of_isin.get(line.isin),
            )
        )
    return tuple(lines)


def check_country_meaning(fund_code: str, lines: Sequence[HoldingLine]) -> None:
    """Stop if the filed country no longer looks like the country a line trades in.

    The form does not say what the country of a line means, and the listing
    rule depends on it being the trading place (ADR 0019). An ISO currency
    code begins with the code of its country, so a line held in Korean won
    should say Korea. If many lines disagree, Vanguard has changed its habit,
    and loading on would put securities in the wrong home market.

    Args:
        fund_code: The fund, for the message.
        lines: The fund's lines.

    Raises:
        UniverseError: If more than two lines in a hundred, among those that
            give a country and are held in a currency other than the euro,
            give another country than their currency's.
    """
    checked = [
        line for line in lines if line.trading_country is not None and line.currency != _EURO
    ]
    disagreeing = sum(1 for line in checked if line.trading_country != line.currency[:2])
    if disagreeing * 100 > _MAX_DISAGREEMENT_PERCENT * len(checked):
        raise UniverseError(
            f"{fund_code}: {disagreeing:,} of {len(checked):,} lines give a country other than "
            f"that of their currency, more than {_MAX_DISAGREEMENT_PERCENT} in a hundred; the "
            "country in this filing may no longer be the country a security trades in"
        )


@dataclass(frozen=True, slots=True)
class VanguardAdapter:
    """Reads a Vanguard fund: its SEC filing plus Vanguard's own holdings file.

    Attributes:
        folder: Where Vanguard's files are kept, one per fund. A file that is
            missing there is downloaded into it.
        fetch: What performs a request. Tests pass their own.
    """

    folder: Path
    fetch: FetchPage = fetch_from_vanguard

    def file_path(self, fund: FundDefinition) -> Path:
        """Return where Vanguard's file for a fund is kept."""
        return self.folder / f"{fund.code}.json"

    def obtain(self, fund: FundDefinition) -> bool:
        """Download Vanguard's file for a fund unless it is already there.

        Args:
            fund: The fund.

        Returns:
            True when the file was downloaded, False when it was there.

        Raises:
            SponsorFileError: If the fund is not one of Vanguard's known
                here, or the file cannot be downloaded or is not usable.
        """
        path = self.file_path(fund)
        if path.is_file():
            return False
        fund_id = _FUND_IDS.get(fund.code)
        if fund_id is None:
            raise SponsorFileError(
                f"there is no Vanguard fund id for {fund.code}; add it to the Vanguard adapter"
            )
        download_vanguard_file(fund_id, path, self.fetch)
        return True

    def holdings(self, fund: FundDefinition, filed: Sequence[FiledLine]) -> FundHoldings:
        """Return a Vanguard fund's holdings as common lines.

        Args:
            fund: The fund.
            filed: The lines of the fund's SEC filing, in order.

        Returns:
            The common lines, with a ticker and a SEDOL where the pairing is
            certain, with Vanguard's name for every security its file has,
            and the date of Vanguard's file.

        Raises:
            SponsorFileError: If Vanguard's file cannot be read.
            UniverseError: If the filed countries no longer look like trading
                places.
        """
        file = read_vanguard_file(self.file_path(fund))
        lines = join(filed, file.rows)
        check_country_meaning(fund.code, lines)
        return FundHoldings(fund=fund, sponsor_file_date=file.as_of, lines=lines)
