"""Tests for ``pyvalue.universe.receipts``: the receipt check of ADR 0006.

Author: Emre Tezel
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.universe import HoldingLine
from pyvalue.universe.receipts import RECEIPT_LABELS, is_receipt

# Words that say nothing about receipts, for building names that must pass.
_PLAIN_WORDS: tuple[str, ...] = (
    "ALPHA",
    "Holdings",
    "PLC",
    "Corp",
    "CL",
    "A",
    "Trust",
    "Industries",
    "SA",
    "Ltd",
    "PFD",
    "KK",
)


def _line(
    *,
    issuer_name: str = "ALPHA CORP",
    title: str = "ALPHA CORP",
    category: str = "EC",
    category_label: str | None = None,
    sponsor_name: str | None = None,
) -> HoldingLine:
    """Build a holdings line that differs from a plain common share only as stated."""
    return HoldingLine(
        number=1,
        issuer_name=issuer_name,
        title=title,
        lei=None,
        isin="US00000A0014",
        cusip=None,
        category=category,
        category_label=category_label,
        trading_country="US",
        currency="USD",
        ticker=None,
        sedol=None,
        sponsor_name=sponsor_name,
    )


def test_a_plain_common_share_is_not_a_receipt() -> None:
    """The default line of these tests is ordinary."""
    assert not is_receipt(_line())


@pytest.mark.parametrize("label", sorted(RECEIPT_LABELS))
def test_a_line_labelled_as_a_receipt_is_one(label: str) -> None:
    """Dimensional's three labels in the conditional category (ADR 0006)."""
    assert is_receipt(_line(category="OTHER", category_label=label))


@pytest.mark.parametrize("label", ["UNITS", "RIGHTS", "currency", "adr", None])
def test_other_labels_of_the_conditional_category_are_not_receipts(label: str | None) -> None:
    """Units, rights and cash share the category with receipts and are not receipts."""
    assert not is_receipt(_line(category="OTHER", category_label=label))


def test_a_receipt_label_outside_the_conditional_category_means_nothing() -> None:
    """The label is read only where a filer can put one."""
    assert not is_receipt(_line(category="EC", category_label="ADR"))


@pytest.mark.parametrize(
    "title",
    [
        "ZETA LTD ADR",
        "ZETA LTD ADRS",
        "ZETA LTD ADS",
        "ZETA LTD GDR",
        "ZETA LTD GDRS",
        "ZETA PCL NVDR",
        "ZETA SA BDR",
        "ZETA LTD CDI",
        "ZETA AB SDR",
        "ZETA LTD EDR",
        "ZETA LTD SPONSORED",
        "ZETA LTD SPON",
        "ZETA LTD SPN",
        "ZETA LTD DEPOSITARY RECEIPT",
        "ZETA LTD DEPOSITARY RECEIPTS",
        "ZETA LTD DEPOSITORY RECEIPT",
        "ZETA LTD DEPOSITARY SHARES",
        "ZETA LTD DEPOSITORY SHARE",
        "ZETA LTD DEPOSITARY INTERESTS",
        "ZETA LTD DEP RCPT",
        "ZETA LTD DEP. RCPT",
        "ZETA LTD DEPOSITARY RCPT",
        "Zeta Ltd adr",
        "ADR ZETA LTD",
        "ZETA LTD (ADR)",
        "ZETA LTD-ADR",
    ],
)
def test_receipt_wording_in_the_title_marks_a_receipt(title: str) -> None:
    """Every word of the list, in either case and next to punctuation."""
    assert is_receipt(_line(title=title))


def test_receipt_wording_in_the_issuer_name_marks_a_receipt() -> None:
    """Some filings carry the word in the name and not in the title."""
    assert is_receipt(_line(issuer_name="ZETA LTD ADR", title="ZETA LTD"))


@pytest.mark.parametrize(
    "title",
    [
        "ADRIATIC METALS PLC",
        "SPONGE HOLDINGS INC",
        "GDRX HOLDINGS INC",
        "BADR CORP",
        "CDIC LTD",
        "ADSORBENTS INC",
        "DEPOSITARY BANK CORP",
        "FIRST DEPOSITORY TRUST",
        "SDRL LTD",
        "ZETA LTD ORD",
    ],
)
def test_a_receipt_word_inside_another_word_marks_nothing(title: str) -> None:
    """The words count only when they stand alone."""
    assert not is_receipt(_line(issuer_name=title, title=title))


@given(words=st.lists(st.sampled_from(_PLAIN_WORDS), min_size=1, max_size=6))
def test_names_made_of_plain_words_are_never_receipts(words: list[str]) -> None:
    """No combination of ordinary words adds up to a receipt word."""
    name = " ".join(words)

    assert not is_receipt(_line(issuer_name=name, title=name))


@given(
    words=st.lists(st.sampled_from(_PLAIN_WORDS), max_size=4),
    position=st.integers(min_value=0, max_value=4),
    marker=st.sampled_from(["ADR", "GDR", "NVDR", "SPONSORED", "DEPOSITARY RECEIPT"]),
)
def test_a_receipt_word_is_found_wherever_it_stands(
    words: list[str], position: int, marker: str
) -> None:
    """Front, middle or end of the title makes no difference."""
    words.insert(min(position, len(words)), marker)

    assert is_receipt(_line(title=" ".join(words)))


# --- The sponsor's own name for the security (ADR 0020) ----------------------------------------


@pytest.mark.parametrize(
    ("title", "sponsor_name"),
    [
        pytest.param("LATAM AIRLINES G", "Latam Airlines Group SA ADR", id="Latam Airlines"),
        pytest.param("GRUPO CIBEST SA-", "Grupo Cibest SA ADR", id="Grupo Cibest"),
        pytest.param("DR. REDDY'S LABO", "Dr Reddy's Laboratories Ltd. ADR", id="Dr Reddy's"),
        pytest.param("POLYUS PJSC-G", "Polyus PJSC GDR", id="a GDR"),
        pytest.param("PHOSAGRO PJSC-BL", "PHOSAGRO PJSC-BLOCKED GDRS", id="upper case, plural"),
    ],
)
def test_the_sponsors_own_name_marks_a_receipt_the_cut_title_hides(
    title: str, sponsor_name: str
) -> None:
    """Vanguard's filing cuts a title at 16 characters; its own file gives the whole name."""
    assert not is_receipt(_line(title=title))
    assert is_receipt(_line(title=title, sponsor_name=sponsor_name))


@pytest.mark.parametrize(
    "sponsor_name",
    [
        pytest.param(None, id="no name: the file does not have the security"),
        pytest.param("Alpha Corp.", id="a plain name"),
        pytest.param("Adriatic Metals plc", id="a receipt word inside another word"),
        pytest.param("Spondon Holdings Class A", id="another one"),
    ],
)
def test_a_sponsor_name_without_receipt_wording_marks_nothing(sponsor_name: str | None) -> None:
    """The same whole-word rule as for the title and the issuer name."""
    assert not is_receipt(_line(sponsor_name=sponsor_name))


def test_a_line_the_filing_already_marks_stays_a_receipt_whatever_the_sponsor_says() -> None:
    """The four things the check reads add up; none of them takes a receipt back."""
    assert is_receipt(_line(title="ZETA LTD ADR", sponsor_name="Zeta Ltd."))
    assert is_receipt(_line(category="OTHER", category_label="GDR", sponsor_name=None))
