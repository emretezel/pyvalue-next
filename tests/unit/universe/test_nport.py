"""Tests for ``pyvalue.universe.nport``: reading a holdings filing.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import FiledLine, FilingError
from pyvalue.universe.nport import read_filing

_NAMESPACE: str = "http://www.sec.gov/edgar/nport"


def _filing_text(lines: str, *, general: str | None = None, root: str = "edgarSubmission") -> str:
    """Return the text of a minimal filing around the given holdings."""
    if general is None:
        general = "<seriesId>S000000001</seriesId><repPdDate>2026-07-31</repPdDate>"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><{root} xmlns="{_NAMESPACE}"><formData>'
        f"<genInfo>{general}</genInfo><invstOrSecs>{lines}</invstOrSecs></formData></{root}>"
    )


def _write(tmp_path: Path, text: str) -> Path:
    """Write a filing into the temporary folder and return its path."""
    path = tmp_path / "filing.xml"
    path.write_text(text, encoding="utf-8")
    return path


# What every real line states besides its name and category: the currency it
# is held in and the type of its issuer. The reader does not read the type
# (ADR 0022); it is here because the filings carry it.
_REST: str = "<curCd>USD</curCd><issuerCat>CORP</issuerCat>"

_PLAIN_LINE: str = (
    "<invstOrSec><name>ALPHA CORP</name><lei>549300ALPHA000000003</lei>"
    "<title>ALPHA CORP CL A</title><cusip>00000A001</cusip>"
    "<identifiers><isin value='US00000A0014'/></identifiers>"
    f"<assetCat>EC</assetCat>{_REST}<invCountry>US</invCountry></invstOrSec>"
)


def test_the_fund_and_the_holdings_date_are_read(nport_samples: Path) -> None:
    """A filing says which fund it is for and for which day."""
    filing = read_filing(nport_samples / "VXUS.xml")

    assert filing.series_id == "S000002932"
    assert filing.holdings_date == date(2026, 7, 31)


def test_every_line_is_read_whatever_its_category(nport_samples: Path) -> None:
    """Debt, derivatives and cash are returned too, so the load can account for them."""
    filing = read_filing(nport_samples / "VXUS.xml")

    assert [line.number for line in filing.lines] == list(range(1, 25))
    assert [line.category for line in filing.lines[:10]] == [
        "EC",
        "EC",
        "EC",
        "EC",
        "EC",
        "DBT",
        "DFE",
        "EC",
        "EC",
        "EC",
    ]


def test_a_plain_line_is_read_in_full(nport_samples: Path) -> None:
    """Everything the load and the adapter use of an ordinary share's line."""
    filing = read_filing(nport_samples / "VTI.xml")

    assert filing.lines[1] == FiledLine(
        number=2,
        issuer_name="ALPHA CORP",
        title="ALPHA CORP PFD SER A",
        lei="549300ALPHA000000003",
        isin="US00000A0022",
        cusip=None,
        category="EP",
        category_label=None,
        country="US",
        currency="USD",
    )


def test_the_conditional_category_is_read_with_its_label(nport_samples: Path) -> None:
    """Some sponsors file receipts, units and rights there; missing them was a real bug.

    Vanguard does not use the conditional category, but the form allows it,
    and lines 11 to 24 of the sample keep the reader's support for it tested.
    """
    filing = read_filing(nport_samples / "VXUS.xml")

    assert filing.lines[15] == FiledLine(
        number=16,
        issuer_name="Kappa Co Ltd",
        title="Kappa Co Ltd",
        lei="549300KAPPA000000078",
        isin="US00000K0012",
        cusip=None,
        category="OTHER",
        category_label="GDR",
        country="US",
        currency="USD",
    )
    assert [line.category_label for line in filing.lines if line.category == "OTHER"] == [
        "GDR",
        "DEPOSITORY RECEIPT",
        "UNITS",
        "RIGHTS",
        "currency",
        "ADR",
        "ADR",
    ]


def test_a_line_identified_without_an_isin_has_none(nport_samples: Path) -> None:
    """A ticker or the filer's own number is not an ISIN."""
    filing = read_filing(nport_samples / "VTI.xml")

    assert [line.isin for line in filing.lines[4:]] == [None, None, None]


def test_the_forms_not_applicable_is_read_as_no_identifier(nport_samples: Path) -> None:
    """A filer writes ``N/A`` where the form demands a value and there is none."""
    filing = read_filing(nport_samples / "VTI.xml")

    assert filing.lines[2].lei is None


def test_a_real_cusip_is_kept_and_a_placeholder_is_not(tmp_path: Path) -> None:
    """``N/A`` and nine zeros both say that the security has no CUSIP."""

    def line(cusip: str) -> str:
        return (
            f"<invstOrSec><name>ALPHA CORP</name>{cusip}<assetCat>EC</assetCat>{_REST}</invstOrSec>"
        )

    path = _write(
        tmp_path,
        _filing_text(
            line("<cusip>037833100</cusip>")
            + line("<cusip>N/A</cusip>")
            + line("<cusip>000000000</cusip>")
            + line("")
        ),
    )

    assert [entry.cusip for entry in read_filing(path).lines] == ["037833100", None, None, None]


def test_the_currency_is_read_from_either_place(nport_samples: Path) -> None:
    """A dollar line states its currency plainly, any other beside its exchange rate."""
    filing = read_filing(nport_samples / "VXUS.xml")

    assert [line.currency for line in filing.lines[:5]] == ["GBP", "EUR", "USD", "HKD", "USD"]


def test_the_country_is_read_as_filed(nport_samples: Path) -> None:
    """What the country means is the sponsor's habit; the reader only reads it."""
    filing = read_filing(nport_samples / "VXUS.xml")

    assert [line.country for line in filing.lines[:5]] == ["GB", "FR", "US", "HK", "US"]


def test_a_derivative_line_has_no_country(nport_samples: Path) -> None:
    """A currency forward gives ``N/A`` as its country, and states its issuer type conditionally."""
    forward = read_filing(nport_samples / "VXUS.xml").lines[6]

    assert forward.category == "DFE"
    assert forward.country is None


def test_a_line_without_an_issuer_type_is_read(tmp_path: Path) -> None:
    """The form's issuer type is not read (ADR 0022), so a line that lacks it is not refused."""
    path = _write(
        tmp_path,
        _filing_text(
            "<invstOrSec><name>ALPHA CORP</name><assetCat>EC</assetCat><curCd>USD</curCd>"
            "</invstOrSec>"
        ),
    )

    (line,) = read_filing(path).lines
    assert (line.issuer_name, line.category, line.currency) == ("ALPHA CORP", "EC", "USD")


def test_inner_spacing_of_a_name_is_kept(nport_samples: Path) -> None:
    """The reader does not tidy: 'Beta  Inc' arrives with its two spaces."""
    filing = read_filing(nport_samples / "VTI.xml")

    assert filing.lines[3].issuer_name == "Beta  Inc"


def test_characters_the_markup_escapes_are_read_back(nport_samples: Path) -> None:
    """An ampersand in a title is one character, not markup."""
    filing = read_filing(nport_samples / "VTI.xml")

    assert filing.lines[5].title == "E-MINI S&P 500 FUTURE"


def test_surrounding_whitespace_is_dropped_and_empty_values_are_absent(tmp_path: Path) -> None:
    """Filings pad values and leave elements empty; neither reaches the load."""
    path = _write(
        tmp_path,
        _filing_text(
            "<invstOrSec><name>  ALPHA CORP \n</name><lei> </lei><title></title>"
            "<identifiers><isin value='  US00000A0014 '/></identifiers>"
            "<currencyConditional curCd=' GBP ' exchangeRt='1.25'/>"
            "<assetConditional assetCat=' OTHER ' desc='  '/>"
            "<issuerConditional issuerCat=' OTHER ' desc=' N/A '/>"
            "<invCountry> GB </invCountry></invstOrSec>"
        ),
    )

    assert read_filing(path).lines == (
        FiledLine(
            number=1,
            issuer_name="ALPHA CORP",
            title="",
            lei=None,
            isin="US00000A0014",
            cusip=None,
            category="OTHER",
            category_label=None,
            country="GB",
            currency="GBP",
        ),
    )


def test_a_line_without_title_identifiers_or_identifier_element_is_read(tmp_path: Path) -> None:
    """Only the name, the category and the currency are indispensable."""
    path = _write(
        tmp_path,
        _filing_text(
            f"<invstOrSec><name>ALPHA CORP</name><assetCat>EC</assetCat>{_REST}</invstOrSec>"
        ),
    )

    assert read_filing(path).lines == (
        FiledLine(
            number=1,
            issuer_name="ALPHA CORP",
            title="",
            lei=None,
            isin=None,
            cusip=None,
            category="EC",
            category_label=None,
            country=None,
            currency="USD",
        ),
    )


def test_an_empty_isin_value_is_no_isin(tmp_path: Path) -> None:
    """An ISIN element without a value is treated as absent."""
    path = _write(
        tmp_path,
        _filing_text(
            "<invstOrSec><name>ALPHA CORP</name><identifiers><isin/></identifiers>"
            f"<assetCat>EC</assetCat>{_REST}</invstOrSec>"
        ),
    )

    assert read_filing(path).lines[0].isin is None


@pytest.mark.parametrize(
    ("line", "message"),
    [
        pytest.param(
            "<invstOrSec><title>X</title><assetCat>EC</assetCat></invstOrSec>",
            "line 2 has no issuer name",
            id="no issuer name",
        ),
        pytest.param(
            "<invstOrSec><name> </name><assetCat>EC</assetCat></invstOrSec>",
            "line 2 has no issuer name",
            id="blank issuer name",
        ),
        pytest.param(
            "<invstOrSec><name>BETA INC</name></invstOrSec>",
            "line 2 has no asset category",
            id="no category at all",
        ),
        pytest.param(
            "<invstOrSec><name>BETA INC</name><assetConditional desc='ADR'/></invstOrSec>",
            "line 2 has no asset category",
            id="conditional category without a code",
        ),
        pytest.param(
            "<invstOrSec><name>BETA INC</name><assetCat>EC</assetCat>"
            "<issuerCat>CORP</issuerCat></invstOrSec>",
            "line 2 has no currency",
            id="no currency at all",
        ),
        pytest.param(
            "<invstOrSec><name>BETA INC</name><assetCat>EC</assetCat>"
            "<issuerCat>CORP</issuerCat><currencyConditional exchangeRt='1.25'/></invstOrSec>",
            "line 2 has no currency",
            id="conditional currency without a code",
        ),
    ],
)
def test_a_line_that_lacks_what_every_line_has_is_refused(
    tmp_path: Path, line: str, message: str
) -> None:
    """The reader names the line, counted from 1, and reads nothing half."""
    path = _write(tmp_path, _filing_text(_PLAIN_LINE + line))

    with pytest.raises(FilingError, match=message):
        read_filing(path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("<html><body>Rate limit exceeded</body>", "cannot read the filing", id="html"),
        pytest.param("", "cannot read the filing", id="empty file"),
        pytest.param(
            _filing_text(_PLAIN_LINE, root="otherDocument"),
            "is not an N-PORT filing",
            id="another document",
        ),
        pytest.param(
            _filing_text(_PLAIN_LINE).replace(_NAMESPACE, "http://example.com/other"),
            "is not an N-PORT filing",
            id="another namespace",
        ),
        pytest.param(
            _filing_text(_PLAIN_LINE, general="<repPdDate>2026-07-31</repPdDate>"),
            "does not state its fund and its holdings date",
            id="no series id",
        ),
        pytest.param(
            _filing_text(_PLAIN_LINE, general="<seriesId>S000000001</seriesId>"),
            "does not state its fund and its holdings date",
            id="no holdings date",
        ),
        pytest.param(
            _filing_text(
                _PLAIN_LINE,
                general="<seriesId>S000000001</seriesId><repPdDate>31 July 2026</repPdDate>",
            ),
            "the holdings date '31 July 2026' is not a date",
            id="unreadable date",
        ),
        pytest.param(_filing_text(""), "holds no lines", id="no holdings"),
    ],
)
def test_a_file_that_is_not_a_usable_filing_is_refused(
    tmp_path: Path, text: str, message: str
) -> None:
    """An error page or a damaged download fails with the path, not a parser trace."""
    path = _write(tmp_path, text)

    with pytest.raises(FilingError, match=message):
        read_filing(path)


def test_a_filing_without_general_information_is_refused(tmp_path: Path) -> None:
    """The fund and date live in one block; without it the file cannot be checked."""
    text = f'<edgarSubmission xmlns="{_NAMESPACE}"><formData/></edgarSubmission>'

    with pytest.raises(FilingError, match="does not state its fund and its holdings date"):
        read_filing(_write(tmp_path, text))


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(FilingError, match="cannot read the filing"):
        read_filing(tmp_path / "absent.xml")
