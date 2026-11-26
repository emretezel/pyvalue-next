"""The common holding line, and the interface of a sponsor's adapter.

A fund's holdings come from documents that differ from one fund company
(sponsor) to the next: the SEC filing is the same form for all, but what a
sponsor means by its fields differs, and each sponsor has its own holdings
file besides. An adapter reads one sponsor's documents and hands the load the
same kind of line whatever the sponsor. The load sees only what is defined
here (ADR 0016).

Author: Emre Tezel
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pyvalue.universe.funds import FundDefinition
from pyvalue.universe.nport import FiledLine


@dataclass(frozen=True, slots=True)
class HoldingLine:
    """One holding of a fund, as its documents state it, in the shape every sponsor shares.

    Attributes:
        number: The line's position in the filing, counted from 1.
        issuer_name: The name of the issuer, as filed.
        title: The title of the security; empty when the filing gives none.
        lei: The issuer's legal-entity identifier as filed; ``None`` when the
            filing gives none. It is not yet checked for its check digits.
        isin: The security's ISIN as filed; ``None`` when the line carries
            none.
        cusip: The security's CUSIP as filed; ``None`` when the filing gives
            none.
        category: The form's asset category code, such as ``EC``, or
            ``OTHER`` for the conditional category.
        category_label: The filer's own label for a line in the conditional
            category, such as ``ADR``; ``None`` for every other line.
        trading_country: The ISO 3166 code of the country the line trades
            in, as the sponsor's adapter says; ``None`` when the documents do
            not say, as for a derivative.
        currency: The ISO 4217 code of the currency the fund holds the line
            in.
        ticker: The ticker the sponsor's own file gives for the line;
            ``None`` when the adapter could attach none.
        sedol: The SEDOL the sponsor's own file gives for the line; ``None``
            likewise.
        sponsor_name: The name the sponsor's own file gives the security;
            ``None`` when the file does not have the security, or the sponsor
            has no such file. The receipt check reads it (ADR 0020); it is
            not stored.
    """

    number: int
    issuer_name: str
    title: str
    lei: str | None
    isin: str | None
    cusip: str | None
    category: str
    category_label: str | None
    trading_country: str | None
    currency: str
    ticker: str | None
    sedol: str | None
    sponsor_name: str | None


@dataclass(frozen=True, slots=True)
class FundHoldings:
    """The holdings of one fund, ready for the load.

    Attributes:
        fund: The fund.
        sponsor_file_date: The day the sponsor's own file states the holdings
            for, or ``None`` for a sponsor that has no such file.
        lines: Every line of the fund's filing, in the order of the filing.
    """

    fund: FundDefinition
    sponsor_file_date: date | None
    lines: tuple[HoldingLine, ...]


class SponsorAdapter(Protocol):
    """Turns one sponsor's documents into common holding lines.

    The SEC filing is read for every sponsor alike and handed to the adapter.
    The adapter adds what only the sponsor's own documents give, and says what
    the sponsor means by the fields the form leaves open.
    """

    def obtain(self, fund: FundDefinition) -> bool:
        """Make sure the sponsor's own documents for a fund are at hand.

        Args:
            fund: The fund.

        Returns:
            True when something was downloaded, False when everything was
            already there.

        Raises:
            SponsorFileError: If a document cannot be downloaded or is not
                what it should be.
        """
        ...

    def holdings(self, fund: FundDefinition, filed: Sequence[FiledLine]) -> FundHoldings:
        """Return a fund's holdings as common lines.

        Args:
            fund: The fund.
            filed: The lines of the fund's SEC filing, in order.

        Returns:
            One common line per filed line, in the same order.

        Raises:
            SponsorFileError: If the sponsor's own documents cannot be read.
            UniverseError: If the documents do not mean what the adapter
                takes them to mean.
        """
        ...
