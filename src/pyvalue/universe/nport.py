"""Read an SEC holdings filing (form N-PORT) into plain values.

This module only reads. It does not judge a line: whether an ISIN is valid,
whether a line is a receipt and whether it is loaded are decided by the load
(``pyvalue.universe.load``). It returns every line of the filing, whatever its
category, so that the load can account for each one.

Author: Emre Tezel
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pyvalue.universe.errors import FilingError

# Every element of the form lives in this XML namespace.
_NS: str = "{http://www.sec.gov/edgar/nport}"

# The category a filer uses when none of the form's own categories fits. It
# comes with a free-text label, and sponsors use it differently: Dimensional
# files depositary receipts, units and rights here, Vanguard does not use it
# for shares at all (ADR 0006).
CONDITIONAL_CATEGORY: str = "OTHER"


@dataclass(frozen=True, slots=True)
class HoldingLine:
    """One holding of a fund, as the filing states it.

    Attributes:
        number: The line's position in the filing, counted from 1.
        issuer_name: The name of the issuer.
        title: The title of the security; empty when the filing gives none.
        lei: The issuer's legal-entity identifier exactly as filed, which
            includes placeholders such as ``N/A``; ``None`` when absent.
        isin: The security's ISIN exactly as filed; ``None`` when the line
            carries no ISIN.
        category: The form's asset category code, such as ``EC`` (common
            equity) or ``DBT`` (debt), or ``OTHER`` for the conditional
            category.
        category_label: The filer's own label for a line in the conditional
            category, such as ``ADR``; ``None`` for every other line.
    """

    number: int
    issuer_name: str
    title: str
    lei: str | None
    isin: str | None
    category: str
    category_label: str | None


@dataclass(frozen=True, slots=True)
class Filing:
    """The part of one filing the load needs.

    Attributes:
        series_id: The SEC's id of the fund, such as ``S000002848``.
        holdings_date: The day the holdings are stated for.
        lines: Every holding, in the order of the filing.
    """

    series_id: str
    holdings_date: date
    lines: tuple[HoldingLine, ...]


def _text(parent: ET.Element, tag: str) -> str | None:
    """Return the text of a child element, or ``None`` when it is absent or empty."""
    child = parent.find(_NS + tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _isin(holding: ET.Element) -> str | None:
    """Return the ISIN among a line's identifiers, or ``None``.

    A line names its security by one or more identifiers. Only the ISIN is of
    use to the load; a line identified by a ticker or by the filer's internal
    number alone has none.
    """
    element = holding.find(f"{_NS}identifiers/{_NS}isin")
    if element is None:
        return None
    return element.get("value", "").strip() or None


def _line(holding: ET.Element, number: int, path: Path) -> HoldingLine:
    """Read one holding."""
    issuer_name = _text(holding, "name")
    if issuer_name is None:
        raise FilingError(f"{path}: line {number} has no issuer name")

    # A line states its category in one of two ways: a plain element holding
    # one of the form's codes, or the conditional element with a label.
    category = _text(holding, "assetCat")
    category_label: str | None = None
    if category is None:
        conditional = holding.find(_NS + "assetConditional")
        if conditional is None:
            raise FilingError(f"{path}: line {number} has no asset category")
        category = conditional.get("assetCat", "").strip()
        category_label = conditional.get("desc", "").strip() or None
        if not category:
            raise FilingError(f"{path}: line {number} has no asset category")

    return HoldingLine(
        number=number,
        issuer_name=issuer_name,
        title=_text(holding, "title") or "",
        lei=_text(holding, "lei"),
        isin=_isin(holding),
        category=category,
        category_label=category_label,
    )


def read_filing(path: Path) -> Filing:
    """Read a holdings filing from a file.

    Args:
        path: The filing's ``primary_doc.xml`` as the SEC serves it.

    Returns:
        The fund's series id, the holdings date and every line.

    Raises:
        FilingError: If the file cannot be read, is not an N-PORT filing, or
            lacks something every filing has.
    """
    try:
        # The standard parser does not fetch anything a document points at,
        # and the files come from sec.gov only (see pyvalue.universe.sec).
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise FilingError(f"cannot read the filing {path}: {error}") from error
    if root.tag != _NS + "edgarSubmission":
        raise FilingError(f"{path} is not an N-PORT filing")

    general = root.find(f"{_NS}formData/{_NS}genInfo")
    series_id = None if general is None else _text(general, "seriesId")
    stated_date = None if general is None else _text(general, "repPdDate")
    if series_id is None or stated_date is None:
        raise FilingError(f"{path} does not state its fund and its holdings date")
    try:
        holdings_date = date.fromisoformat(stated_date)
    except ValueError as error:
        raise FilingError(f"{path}: the holdings date '{stated_date}' is not a date") from error

    holdings = root.findall(f"{_NS}formData/{_NS}invstOrSecs/{_NS}invstOrSec")
    if not holdings:
        raise FilingError(f"{path} holds no lines")
    return Filing(
        series_id=series_id,
        holdings_date=holdings_date,
        lines=tuple(
            _line(holding, number, path) for number, holding in enumerate(holdings, start=1)
        ),
    )
