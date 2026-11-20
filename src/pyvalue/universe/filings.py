"""The three holdings filings the universe is built from.

The funds are fixed by ADR 0004 and the exact filings are pinned here by their
SEC filing numbers (ADR 0009). The database does not record which filings it
was loaded from, so this constant and its commit history are that record. To
load newer holdings, change the filing numbers and dates here.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.universe.errors import FilingError
from pyvalue.universe.nport import HoldingLine, read_filing


@dataclass(frozen=True, slots=True)
class PinnedFiling:
    """One fund's holdings filing, named precisely enough to fetch it again.

    Attributes:
        ticker: The fund's ticker, used to name the fund in files and output.
        series_id: The SEC's id of the fund. A filing states it, which is how
            a downloaded file is checked against this pin.
        registrant_cik: The SEC's number of the registrant, without leading
            zeros. It is part of the filing's address.
        filing_number: The SEC's number of the filing (its accession number).
        holdings_date: The day the filing states the holdings for.
    """

    ticker: str
    series_id: str
    registrant_cik: int
    filing_number: str
    holdings_date: date

    @property
    def url(self) -> str:
        """The permanent address of the filing's holdings document at the SEC."""
        folder = self.filing_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{self.registrant_cik}/{folder}/primary_doc.xml"

    @property
    def file_name(self) -> str:
        """The name the filing is kept under locally, such as ``VTI_<number>.xml``."""
        return f"{self.ticker}_{self.filing_number}.xml"


# The order is the order of loading, and it matters: the first fund that names
# a company decides how its name is spelled in the database (ADR 0006).
PINNED_FILINGS: tuple[PinnedFiling, ...] = (
    PinnedFiling(
        ticker="VTI",
        series_id="S000002848",
        registrant_cik=36405,
        filing_number="0000036405-26-000480",
        holdings_date=date(2026, 6, 30),
    ),
    PinnedFiling(
        ticker="VXUS",
        series_id="S000002932",
        registrant_cik=736054,
        filing_number="0000736054-26-000275",
        holdings_date=date(2026, 7, 31),
    ),
    PinnedFiling(
        ticker="DFAX",
        series_id="S000070905",
        registrant_cik=1816125,
        filing_number="0001004726-26-009205",
        holdings_date=date(2026, 7, 31),
    ),
)


def read_pinned_filing(path: Path, pinned: PinnedFiling) -> tuple[HoldingLine, ...]:
    """Read a filing file and make sure it is the pinned filing.

    Args:
        path: The local file.
        pinned: The filing the file is supposed to be.

    Returns:
        Every line of the filing.

    Raises:
        FilingError: If the file cannot be read as a filing, or it states
            another fund or another holdings date than the pin. That catches a
            file saved under the wrong name and an error page saved in place
            of a filing.
    """
    filing = read_filing(path)
    if filing.series_id != pinned.series_id or filing.holdings_date != pinned.holdings_date:
        raise FilingError(
            f"{path} is not the pinned {pinned.ticker} filing: it states fund "
            f"{filing.series_id} and holdings date {filing.holdings_date.isoformat()}, where "
            f"{pinned.series_id} and {pinned.holdings_date.isoformat()} are expected"
        )
    return filing.lines
