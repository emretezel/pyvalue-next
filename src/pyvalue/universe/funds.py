"""The funds the universe is built from, and the filing each is read from.

The funds are fixed by ADR 0016 and the exact filings are pinned here by their
SEC filing numbers (ADR 0009). To load newer holdings, change the filing
numbers and dates here. To use another fund company, add its funds here and
give the company an adapter.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from pyvalue.universe.errors import FilingError
from pyvalue.universe.nport import HoldingLine, read_filing


class Scope(StrEnum):
    """Whether a fund is expected to hold US-coded ISINs.

    The listing rule reads it to find depositary receipts: a US-coded ISIN in
    a fund of non-US companies (ADR 0019). The values are what the ``fund``
    table stores.
    """

    US = "US"
    NON_US = "NON_US"


class Sponsor(StrEnum):
    """The company that runs a fund, which decides how its documents are read.

    Each sponsor has one adapter that turns its documents into the common
    holding line (ADR 0016).
    """

    VANGUARD = "vanguard"


@dataclass(frozen=True, slots=True)
class FundDefinition:
    """One fund, and its holdings filing named precisely enough to fetch it again.

    Attributes:
        code: pyvalue's own code for the fund: its ticker. It names the fund
            in files, in output and in the ``fund`` table.
        name: The fund's name.
        scope: Whether the fund holds US or non-US companies.
        sponsor: The company that runs the fund.
        series_id: The SEC's id of the fund. A filing states it, which is how
            a downloaded file is checked against this definition.
        registrant_cik: The SEC's number of the registrant, without leading
            zeros. It is part of the filing's address.
        filing_number: The SEC's number of the pinned filing (its accession
            number).
        holdings_date: The day that filing states the holdings for.
    """

    code: str
    name: str
    scope: Scope
    sponsor: Sponsor
    series_id: str
    registrant_cik: int
    filing_number: str
    holdings_date: date

    @property
    def filing_url(self) -> str:
        """The permanent address of the filing's holdings document at the SEC."""
        folder = self.filing_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{self.registrant_cik}/{folder}/primary_doc.xml"

    @property
    def filing_file_name(self) -> str:
        """The name the filing is kept under locally, such as ``VTI_<number>.xml``."""
        return f"{self.code}_{self.filing_number}.xml"


# The order is the order of loading, and it matters: the first fund that names
# a company decides how its name is spelled in the database (ADR 0006).
FUNDS: tuple[FundDefinition, ...] = (
    FundDefinition(
        code="VTI",
        name="Vanguard Total Stock Market Index Fund",
        scope=Scope.US,
        sponsor=Sponsor.VANGUARD,
        series_id="S000002848",
        registrant_cik=36405,
        filing_number="0000036405-26-000480",
        holdings_date=date(2026, 6, 30),
    ),
    FundDefinition(
        code="VXUS",
        name="Vanguard Total International Stock Index Fund",
        scope=Scope.NON_US,
        sponsor=Sponsor.VANGUARD,
        series_id="S000002932",
        registrant_cik=736054,
        filing_number="0000736054-26-000275",
        holdings_date=date(2026, 7, 31),
    ),
)


def read_pinned_filing(path: Path, fund: FundDefinition) -> tuple[HoldingLine, ...]:
    """Read a filing file and make sure it is the fund's pinned filing.

    Args:
        path: The local file.
        fund: The fund whose pinned filing the file is supposed to be.

    Returns:
        Every line of the filing.

    Raises:
        FilingError: If the file cannot be read as a filing, or it states
            another fund or another holdings date than the definition. That
            catches a file saved under the wrong name and an error page saved
            in place of a filing.
    """
    filing = read_filing(path)
    if filing.series_id != fund.series_id or filing.holdings_date != fund.holdings_date:
        raise FilingError(
            f"{path} is not the pinned {fund.code} filing: it states fund "
            f"{filing.series_id} and holdings date {filing.holdings_date.isoformat()}, where "
            f"{fund.series_id} and {fund.holdings_date.isoformat()} are expected"
        )
    return filing.lines
