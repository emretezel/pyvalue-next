"""Decisions on listings: the securities the rule could not fill (ADR 0019).

Where the listing rule is not sure, an agent or the author decides, and the
decision is one row of a committed file,
``pyvalue/listings/decisions/listing.csv``: this security is this line of the
provider, or this security gets no listing. The file is shipped inside the
package, so an installed copy fills the same listings. It is keyed by ISIN,
because database ids change when the database is rebuilt.

A decision names a line the way the provider does, by provider, exchange code
and symbol. Whether that line is stored, and whether the security may be
given it, is checked when the decision is applied (ADR 0026), not here.

Author: Emre Tezel
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.decision_file import read_decisions, read_packaged, valid_day, valid_isin
from pyvalue.listings.errors import ListingsError

# The component whose `decisions` folder holds the file.
_PACKAGE: str = "pyvalue.listings"

# The file's name in that folder.
_FILE: str = "listing.csv"

# The columns of the file, in order (ADR 0026).
_HEADER: tuple[str, ...] = (
    "isin",
    "outcome",
    "provider_code",
    "provider_exchange_code",
    "provider_symbol",
    "company",
    "decided_on",
    "decided_by",
    "evidence",
)

# The two things a decision can say.
_LISTING: str = "listing"
_NONE: str = "none"


@dataclass(frozen=True, slots=True)
class ListingDecision:
    """One decision: the line a security is listed on, or that it has none.

    Attributes:
        isin: The security.
        line: The provider's line the security is given, named by provider,
            exchange code and symbol; or ``None`` when the decision is that
            the security gets no listing.
        company: The company's name, for the reader of the file. Nothing
            reads it when the decision is applied.
        decided_on: The day the decision was taken.
        decided_by: Who decided: the author or the agent.
        evidence: What the decision rests on.
    """

    isin: str
    line: tuple[str, str, str] | None
    company: str
    decided_on: date
    decided_by: str
    evidence: str


def _line(outcome: str, cells: tuple[str, str, str], where: str) -> tuple[str, str, str] | None:
    """Return the line a row names, or ``None`` for a row that says "no listing"."""
    if outcome == _NONE:
        if any(cells):
            raise ListingsError(
                f"{where}: a row with the outcome '{_NONE}' names no line; leave the provider, "
                f"the exchange code and the symbol empty"
            )
        return None
    if outcome != _LISTING:
        raise ListingsError(
            f"{where}: the outcome must be '{_LISTING}' or '{_NONE}', not '{outcome}'"
        )
    # The symbol is compared with the stored one letter for letter, so a
    # stray space would make a good decision look out of date.
    if not all(cells) or any(cell != cell.strip() for cell in cells):
        raise ListingsError(
            f"{where}: a row with the outcome '{_LISTING}' names a line: the provider, the "
            f"exchange code and the symbol must all be filled in, without spaces around them"
        )
    return cells


def _decision(row: list[str], where: str) -> ListingDecision:
    """Turn one row of the file into a decision, or say what is wrong with it."""
    (
        isin,
        outcome,
        provider_code,
        exchange_code,
        symbol,
        company,
        decided_on,
        decided_by,
        evidence,
    ) = row
    valid_isin(isin, where, ListingsError)
    line = _line(outcome, (provider_code, exchange_code, symbol), where)
    # A listing decides which company's prices and accounts a security is
    # analysed on, and nothing but a person can check it afterwards. So the
    # columns that only people read are required as well.
    if not company.strip() or not decided_by.strip() or not evidence.strip():
        raise ListingsError(
            f"{where}: the company, who decided and the evidence must all be filled in"
        )
    return ListingDecision(
        isin=isin,
        line=line,
        company=company,
        decided_on=valid_day(decided_on, where, ListingsError),
        decided_by=decided_by,
        evidence=evidence,
    )


def read_listing_decisions(path: Path) -> tuple[ListingDecision, ...]:
    """Read a file of listing decisions.

    Args:
        path: A comma-separated file with the header
            ``isin,outcome,provider_code,provider_exchange_code,provider_symbol,company,decided_on,decided_by,evidence``.

    Returns:
        The decisions, in the order of the file.

    Raises:
        ListingsError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows are about the same security. The message
            names the row, counting the header as row 1.
    """
    return read_decisions(path, _HEADER, _decision, ListingsError)


def packaged_listing_decisions() -> tuple[ListingDecision, ...]:
    """Read the decisions shipped inside the installed package."""
    return read_packaged(_PACKAGE, _FILE, read_listing_decisions)
