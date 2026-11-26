"""Read an SEC holdings filing (form N-PORT) into plain values.

This module only reads. It does not judge a line: whether an ISIN is valid,
whether a line is a receipt and whether it is loaded are decided by the load
(``pyvalue.universe.load``). It returns every line of the filing, whatever its
category, so that the load can account for each one.

Every US-registered fund files this form, so the reader is shared by all fund
sponsors. What a sponsor means by a field that the form leaves open, such as
the country, is the business of that sponsor's adapter (ADR 0016).

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

# What a filer writes into a field that the form requires and that does not
# apply to the line. It is the form's way of saying "none", so it is read as
# no value.
_NOT_APPLICABLE: str = "N/A"

# What some filers write for a security that has no CUSIP: nine zeros. No
# real security has that number.
_NO_CUSIP: str = "000000000"


@dataclass(frozen=True, slots=True)
class FiledLine:
    """One holding of a fund, as the filing states it.

    Attributes:
        number: The line's position in the filing, counted from 1.
        issuer_name: The name of the issuer.
        title: The title of the security; empty when the filing gives none.
        lei: The issuer's legal-entity identifier as filed; ``None`` when the
            filing gives none or the form's ``N/A``.
        isin: The security's ISIN exactly as filed; ``None`` when the line
            carries no ISIN.
        cusip: The security's CUSIP as filed; ``None`` when the filing gives
            none, the form's ``N/A`` or nine zeros.
        category: The form's asset category code, such as ``EC`` (common
            equity) or ``DBT`` (debt), or ``OTHER`` for the conditional
            category.
        category_label: The filer's own label for a line in the conditional
            category, such as ``ADR``; ``None`` for every other line.
        issuer_type: The form's issuer type code, such as ``CORP`` (a
            company) or ``RF`` (a registered fund), or ``OTHER`` for the
            conditional type.
        country: The ISO 3166 country code the filing gives for the line;
            ``None`` when it gives the form's ``N/A``, as derivative lines
            do. Whether it is where the security trades or where the issuer
            is registered is the filer's habit.
        currency: The ISO 4217 code of the currency the fund holds the line
            in.
    """

    number: int
    issuer_name: str
    title: str
    lei: str | None
    isin: str | None
    cusip: str | None
    category: str
    category_label: str | None
    issuer_type: str
    country: str | None
    currency: str


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
    lines: tuple[FiledLine, ...]


def _text(parent: ET.Element, tag: str) -> str | None:
    """Return the text of a child element, or ``None`` when it is absent or empty."""
    child = parent.find(_NS + tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _applicable(parent: ET.Element, tag: str) -> str | None:
    """Return the text of a child element, or ``None`` when it says ``N/A`` or nothing."""
    text = _text(parent, tag)
    return None if text == _NOT_APPLICABLE else text


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


def _coded(
    holding: ET.Element, plain: str, conditional: str, what: str, number: int, path: Path
) -> tuple[str, str | None]:
    """Read a fact the form states in one of two ways.

    The asset category and the issuer type are each stated either by a plain
    element holding one of the form's codes, or by a conditional element whose
    attribute holds the code (``OTHER``) and whose ``desc`` holds the filer's
    own label.

    Args:
        holding: The line.
        plain: The name of the plain element, which is also the name of the
            attribute that holds the code on the conditional element.
        conditional: The name of the conditional element.
        what: What the fact is called in an error message.
        number: The line's position, for the error message.
        path: The filing, for the error message.

    Returns:
        The code, and the label when the conditional element gave one.

    Raises:
        FilingError: If the line states the fact in neither way.
    """
    code = _text(holding, plain)
    if code is not None:
        return code, None
    element = holding.find(_NS + conditional)
    code = "" if element is None else element.get(plain, "").strip()
    if element is None or not code:
        raise FilingError(f"{path}: line {number} has no {what}")
    return code, element.get("desc", "").strip() or None


def _currency(holding: ET.Element, number: int, path: Path) -> str:
    """Read the currency a line is held in.

    A line held in US dollars states it in a plain element. Any other line
    states it on the conditional element, beside the exchange rate.
    """
    currency = _text(holding, "curCd")
    if currency is None:
        conditional = holding.find(_NS + "currencyConditional")
        currency = None if conditional is None else conditional.get("curCd", "").strip() or None
    if currency is None:
        raise FilingError(f"{path}: line {number} has no currency")
    return currency


def _line(holding: ET.Element, number: int, path: Path) -> FiledLine:
    """Read one holding."""
    issuer_name = _text(holding, "name")
    if issuer_name is None:
        raise FilingError(f"{path}: line {number} has no issuer name")

    category, category_label = _coded(
        holding, "assetCat", "assetConditional", "asset category", number, path
    )
    # The label of the conditional issuer type says nothing the load uses:
    # the filings give "N/A" there.
    issuer_type, _ = _coded(holding, "issuerCat", "issuerConditional", "issuer type", number, path)
    cusip = _applicable(holding, "cusip")

    return FiledLine(
        number=number,
        issuer_name=issuer_name,
        title=_text(holding, "title") or "",
        lei=_applicable(holding, "lei"),
        isin=_isin(holding),
        cusip=None if cusip == _NO_CUSIP else cusip,
        category=category,
        category_label=category_label,
        issuer_type=issuer_type,
        country=_applicable(holding, "invCountry"),
        currency=_currency(holding, number, path),
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
