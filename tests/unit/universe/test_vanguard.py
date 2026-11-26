"""Tests for ``pyvalue.universe.vanguard``: the adapter for Vanguard's funds.

Author: Emre Tezel
"""

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.universe import (
    FUNDS,
    FiledLine,
    HoldingLine,
    SponsorAdapter,
    SponsorFileError,
    UniverseError,
    VanguardAdapter,
)
from pyvalue.universe.funds import read_pinned_filing
from pyvalue.universe.vanguard import check_country_meaning, join
from pyvalue.universe.vanguard_file import VanguardRow

_ISIN: str = "US00000A0014"
_OTHER_ISIN: str = "GB00000D0016"


def _filed(
    number: int = 1,
    isin: str | None = _ISIN,
    *,
    country: str | None = "US",
    currency: str = "USD",
    category: str = "EC",
) -> FiledLine:
    """Build a line of a filing, a plain US common share unless stated otherwise."""
    return FiledLine(
        number=number,
        issuer_name="ALPHA CORP",
        title="ALPHA CORP",
        lei="549300ALPHA000000003",
        isin=isin,
        cusip="00000A001",
        category=category,
        category_label=None,
        issuer_type="CORP",
        country=country,
        currency=currency,
    )


def _line(country: str | None, currency: str) -> HoldingLine:
    """Build a common line of which only the country and the currency matter."""
    return HoldingLine(
        number=1,
        issuer_name="ALPHA CORP",
        title="ALPHA CORP",
        lei=None,
        isin=_ISIN,
        cusip=None,
        category="EC",
        category_label=None,
        issuer_type="CORP",
        trading_country=country,
        currency=currency,
        ticker=None,
        sedol=None,
        sponsor_name=None,
    )


def _never_fetched(url: str) -> bytes:
    """Fail the test if anything is fetched."""
    pytest.fail(f"{url} was fetched")


# --- The join --------------------------------------------------------------------------------


def test_one_line_and_one_row_are_paired() -> None:
    """The common line carries everything the filing says, plus the ticker and the SEDOL."""
    (line,) = join([_filed()], [VanguardRow(isin=_ISIN, ticker="ALPH", sedol="B000A01", name=None)])

    assert line == HoldingLine(
        number=1,
        issuer_name="ALPHA CORP",
        title="ALPHA CORP",
        lei="549300ALPHA000000003",
        isin=_ISIN,
        cusip="00000A001",
        category="EC",
        category_label=None,
        issuer_type="CORP",
        trading_country="US",
        currency="USD",
        ticker="ALPH",
        sedol="B000A01",
        sponsor_name=None,
    )


def test_the_country_of_a_vanguard_filing_is_the_trading_country() -> None:
    """ADR 0016: Vanguard files where a security trades, so the adapter passes it on."""
    filed = [
        _filed(1, _OTHER_ISIN, country="HK", currency="HKD"),
        _filed(2, None, country=None, currency="USD", category="DFE"),
    ]

    lines = join(filed, [])

    assert [line.trading_country for line in lines] == ["HK", None]


def test_an_isin_with_two_lines_gets_nothing_attached() -> None:
    """A share held on two markets: which line the one row belongs to is unknown."""
    filed = [_filed(1), _filed(2, _OTHER_ISIN), _filed(3)]
    rows = [
        VanguardRow(isin=_ISIN, ticker="ALPH", sedol="B000A01", name=None),
        VanguardRow(isin=_OTHER_ISIN, ticker="DLT", sedol="B000D01", name=None),
    ]

    lines = join(filed, rows)

    assert [(line.ticker, line.sedol) for line in lines] == [
        (None, None),
        ("DLT", "B000D01"),
        (None, None),
    ]


def test_an_isin_with_two_rows_gets_nothing_attached() -> None:
    """Two rows mean two markets, each with its own SEDOL: neither is known to be this line's."""
    rows = [
        VanguardRow(isin=_ISIN, ticker="ABX", sedol="B000A01", name=None),
        VanguardRow(isin=_ISIN, ticker="ABX", sedol="B000A02", name=None),
    ]

    (line,) = join([_filed()], rows)

    assert (line.ticker, line.sedol) == (None, None)


def test_a_line_without_an_isin_and_a_row_without_one_are_never_paired() -> None:
    """The ISIN is all the two documents share; without it there is no pairing."""
    filed = [_filed(1, None), _filed(2, None)]
    rows = [VanguardRow(isin=None, ticker="ESU6", sedol=None, name=None)]

    lines = join(filed, rows)

    assert [(line.ticker, line.sedol) for line in lines] == [(None, None), (None, None)]


def test_a_row_the_filing_does_not_have_is_ignored() -> None:
    """The documents have different dates; the filing decides what is in the universe."""
    lines = join(
        [_filed()], [VanguardRow(isin=_OTHER_ISIN, ticker="DLT", sedol="B000D01", name=None)]
    )

    assert [line.isin for line in lines] == [_ISIN]
    assert lines[0].ticker is None


def test_a_row_may_give_a_sedol_without_a_ticker() -> None:
    """Each value is attached for what it is; an empty one stays empty."""
    (line,) = join([_filed()], [VanguardRow(isin=_ISIN, ticker=None, sedol="B000A01", name=None)])

    assert (line.ticker, line.sedol) == (None, "B000A01")


def test_the_sponsors_name_is_attached_to_the_line_of_its_security() -> None:
    """ADR 0020: the receipt check reads it."""
    rows = [VanguardRow(isin=_ISIN, ticker="LTM", sedol="B000A01", name="Latam Airlines SA ADR")]

    (line,) = join([_filed()], rows)

    assert line.sponsor_name == "Latam Airlines SA ADR"


def test_the_name_goes_to_every_line_of_a_security_however_many_lines_and_rows() -> None:
    """A name belongs to the security, not to one market, so it needs no one-to-one pairing."""
    filed = [_filed(1), _filed(2), _filed(3, _OTHER_ISIN)]
    rows = [
        VanguardRow(isin=_ISIN, ticker="ABX", sedol="B000A01", name="Alpha Corp. ADR"),
        VanguardRow(isin=_ISIN, ticker="B", sedol="B000A02", name="Alpha Corp. ADR (New York)"),
        VanguardRow(isin=_OTHER_ISIN, ticker="DLT", sedol="B000D01", name=None),
    ]

    lines = join(filed, rows)

    # Two lines and two rows: no ticker for either line, and the first row's name for both.
    assert [(line.ticker, line.sponsor_name) for line in lines] == [
        (None, "Alpha Corp. ADR"),
        (None, "Alpha Corp. ADR"),
        ("DLT", None),
    ]


def test_a_row_without_a_name_does_not_hide_a_later_row_that_has_one() -> None:
    """The first row that names the security names it."""
    rows = [
        VanguardRow(isin=_ISIN, ticker="A", sedol=None, name=None),
        VanguardRow(isin=_ISIN, ticker="B", sedol=None, name="Alpha Corp. ADR"),
    ]

    (line,) = join([_filed()], rows)

    assert line.sponsor_name == "Alpha Corp. ADR"


def test_a_line_without_an_isin_gets_no_name() -> None:
    """A row without an ISIN belongs to no line, whatever it is called."""
    rows = [VanguardRow(isin=None, ticker="ESU6", sedol=None, name="E-mini S&P 500 Future")]

    (line,) = join([_filed(1, None)], rows)

    assert line.sponsor_name is None


@given(
    isins=st.lists(st.sampled_from(["A", "B", "C", None]), max_size=8),
    row_isins=st.lists(st.sampled_from(["A", "B", "C", "D", None]), max_size=8),
)
def test_the_join_keeps_every_line_in_order_and_pairs_only_one_to_one(
    isins: list[str | None], row_isins: list[str | None]
) -> None:
    """Whatever the two documents hold, no line is lost and no ambiguous pairing is made."""
    filed = [_filed(number, isin) for number, isin in enumerate(isins, start=1)]
    rows = [
        VanguardRow(isin=isin, ticker=f"T{position}", sedol=None, name=None)
        for position, isin in enumerate(row_isins)
    ]

    lines = join(filed, rows)

    assert [(line.number, line.isin) for line in lines] == [
        (line.number, line.isin) for line in filed
    ]
    for line in lines:
        certain = (
            line.isin is not None
            and isins.count(line.isin) == 1
            and row_isins.count(line.isin) == 1
        )
        assert (line.ticker is not None) == certain


# --- The guard on what the country means -------------------------------------------------------


def test_lines_whose_country_is_that_of_their_currency_pass() -> None:
    """A won line in Korea, a dollar line in the United States."""
    check_country_meaning("VXUS", [_line("KR", "KRW"), _line("US", "USD"), _line("GB", "GBP")])


def test_a_few_exceptions_pass() -> None:
    """A Shanghai B share is quoted in US dollars and trades in China: 1 line in 50."""
    lines = [_line("KR", "KRW")] * 49 + [_line("CN", "USD")]

    check_country_meaning("VXUS", lines)


def test_exactly_two_in_a_hundred_still_pass_and_one_more_does_not() -> None:
    """The limit of ADR 0016 is "more than 2%"."""
    at_the_limit = [_line("KR", "KRW")] * 98 + [_line("KY", "HKD")] * 2
    above = [_line("KR", "KRW")] * 97 + [_line("KY", "HKD")] * 3

    check_country_meaning("VXUS", at_the_limit)
    with pytest.raises(UniverseError, match="VXUS: 3 of 100 lines give a country other than"):
        check_country_meaning("VXUS", above)


def test_a_filing_that_gives_the_country_of_registration_is_refused() -> None:
    """What Dimensional files: Cayman companies that trade in Hong Kong say ``KY``."""
    lines = [_line("KY", "HKD")] * 30 + [_line("HK", "HKD")] * 70

    with pytest.raises(
        UniverseError, match="may no longer be the country a security trades in"
    ) as raised:
        check_country_meaning("VXUS", lines)

    assert "30 of 100" in str(raised.value)


def test_euro_lines_are_not_checked() -> None:
    """The euro belongs to no one country, so such a line can say any of them."""
    check_country_meaning("VXUS", [_line("NL", "EUR"), _line("FR", "EUR"), _line("DE", "EUR")])


def test_lines_without_a_country_are_not_checked() -> None:
    """A derivative gives no country; it neither agrees nor disagrees."""
    check_country_meaning("VXUS", [_line(None, "INR"), _line(None, "USD"), _line("US", "USD")])


def test_a_fund_with_nothing_to_check_passes() -> None:
    """No lines, or only euro lines: nothing contradicts the adapter."""
    check_country_meaning("VXUS", [])


# --- The adapter -----------------------------------------------------------------------------


def test_the_adapter_is_a_sponsor_adapter(vanguard_dir: Path) -> None:
    """The pipeline takes it wherever a sponsor's adapter is asked for."""
    adapter: SponsorAdapter = VanguardAdapter(vanguard_dir, _never_fetched)

    assert adapter.obtain(FUNDS[0]) is False


def test_a_file_that_is_there_is_not_downloaded_again(vanguard_dir: Path) -> None:
    """The saved file is the only copy of its month; a later run must not replace it."""
    adapter = VanguardAdapter(vanguard_dir, _never_fetched)

    assert [adapter.obtain(fund) for fund in FUNDS] == [False, False]


def test_a_missing_file_is_downloaded_under_the_funds_code(
    tmp_path: Path, vanguard_samples: Path
) -> None:
    """Vanguard's own id of the fund is in the address; the file is named by our code."""
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        return (vanguard_samples / "VXUS.json").read_bytes()

    adapter = VanguardAdapter(tmp_path / "vanguard", fetch)

    assert adapter.obtain(FUNDS[1]) is True
    assert requests == [
        "https://investor.vanguard.com/vmf/api/3369/portfolio-holding/stock.json?start=1&count=500"
    ]
    assert sorted(path.name for path in (tmp_path / "vanguard").iterdir()) == ["VXUS.json"]
    # The second time it is there.
    assert adapter.obtain(FUNDS[1]) is False
    assert len(requests) == 1


def test_vti_is_asked_for_under_its_own_vanguard_id(tmp_path: Path, vanguard_samples: Path) -> None:
    """Each fund has its own id at Vanguard."""
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        return (vanguard_samples / "VTI.json").read_bytes()

    VanguardAdapter(tmp_path, fetch).obtain(FUNDS[0])

    assert requests[0].startswith("https://investor.vanguard.com/vmf/api/0970/")


def test_a_fund_vanguard_has_no_id_for_is_refused_before_any_request(tmp_path: Path) -> None:
    """A new Vanguard fund needs its id added here; guessing an address is not an option."""
    other = replace(FUNDS[0], code="VT")

    with pytest.raises(SponsorFileError, match="there is no Vanguard fund id for VT"):
        VanguardAdapter(tmp_path, _never_fetched).obtain(other)


def test_the_holdings_of_the_sample_fund_carry_tickers_and_sedols(
    filings_dir: Path, vanguard_dir: Path
) -> None:
    """The sample documents together (tests/fixtures/vanguard/README.md)."""
    vti = FUNDS[0]
    filed = read_pinned_filing(filings_dir / vti.filing_file_name, vti)

    holdings = VanguardAdapter(vanguard_dir, _never_fetched).holdings(vti, filed)

    assert holdings.fund == vti
    assert holdings.sponsor_file_date == date(2026, 10, 31)
    assert [(line.number, line.ticker, line.sedol) for line in holdings.lines] == [
        (1, "ALPH", "B000A01"),
        (2, "ALPH.PA", "B000A02"),
        # An empty ticker in the file: the SEDOL alone is attached.
        (3, None, "B000B01"),
        # Two rows for this ISIN in the file.
        (4, None, None),
        # No ISIN: a contingent right, a future, cash.
        (5, None, None),
        (6, None, None),
        (7, None, None),
    ]


def test_the_international_sample_pairs_only_the_lines_that_are_alone(
    filings_dir: Path, vanguard_dir: Path
) -> None:
    """An ISIN that the sample filing carries on two lines gets no ticker on either."""
    vxus = FUNDS[1]
    filed = read_pinned_filing(filings_dir / vxus.filing_file_name, vxus)

    holdings = VanguardAdapter(vanguard_dir, _never_fetched).holdings(vxus, filed)

    paired = {line.number: (line.ticker, line.sedol) for line in holdings.lines if line.ticker}
    assert paired == {
        4: ("700", "B000Z01"),
        5: ("ETA", "B000H01"),
        10: ("LAMBDA", "B000L01"),
        13: ("EPS B", "B000E02"),
        16: ("KAPPA", "B000K02"),
        17: ("000990", "B000K01"),
        19: ("MUP", "B000M01"),
        # A SEDOL of the wrong shape in the file is read as none.
        24: ("OMC", None),
    }
    assert [line.trading_country for line in holdings.lines[:5]] == ["GB", "FR", "US", "HK", "US"]
    # Vanguard's own names, for every security its file has, two lines or one.
    assert [line.sponsor_name for line in holdings.lines[:5]] == [
        "Delta plc",
        "Epsilon SA",
        "Zeta Ltd. ADR",
        "Zeta Ltd.",
        "Eta Holdings Ltd. ADR",
    ]


def test_a_filing_whose_countries_are_not_trading_places_stops_the_fund(
    filings_dir: Path, vanguard_dir: Path
) -> None:
    """The guard runs on every load, so a change of Vanguard's habit cannot pass unseen."""
    vxus = FUNDS[1]
    filed = [
        replace(line, country="US")
        for line in read_pinned_filing(filings_dir / vxus.filing_file_name, vxus)
    ]

    with pytest.raises(UniverseError, match="VXUS: .* lines give a country other than"):
        VanguardAdapter(vanguard_dir, _never_fetched).holdings(vxus, filed)


def test_holdings_without_the_file_are_refused(filings_dir: Path, tmp_path: Path) -> None:
    """There is no fallback to lines without tickers (ADR 0016)."""
    vti = FUNDS[0]
    filed = read_pinned_filing(filings_dir / vti.filing_file_name, vti)

    with pytest.raises(SponsorFileError, match="cannot read Vanguard's holdings file"):
        VanguardAdapter(tmp_path / "empty", _never_fetched).holdings(vti, filed)


def test_a_damaged_file_is_refused(filings_dir: Path, vanguard_dir: Path) -> None:
    """A file that was cut off or overwritten is named, not half used."""
    vti = FUNDS[0]
    shutil.copyfile(filings_dir / vti.filing_file_name, vanguard_dir / "VTI.json")
    filed = read_pinned_filing(filings_dir / vti.filing_file_name, vti)

    with pytest.raises(SponsorFileError, match="is not a Vanguard holdings file"):
        VanguardAdapter(vanguard_dir, _never_fetched).holdings(vti, filed)
