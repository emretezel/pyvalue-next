"""Tests for ``pyvalue.universe.vanguard_file``: downloading and reading Vanguard's file.

No test here touches the network: a download is tested against a stand-in
that serves pages built in the test.

Author: Emre Tezel
"""

import json
from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import SponsorFileError
from pyvalue.universe.vanguard_file import (
    VanguardRow,
    download_vanguard_file,
    page_url,
    read_vanguard_file,
)

_AS_OF: str = "2026-10-31T00:00:00-04:00"


def _row(number: int) -> dict[str, object]:
    """Build one row as Vanguard writes it, with values that tell the rows apart."""
    return {
        "type": "portfolioHolding",
        "longName": f"Company {number}",
        "ticker": f"T{number}",
        "isin": f"US{number:09d}0",
        "sedol": f"B{number:06d}",
        "cusip": "",
    }


def _document(rows: list[dict[str, object]], size: int | None = None, as_of: str = _AS_OF) -> bytes:
    """Build a page, or a whole file, of Vanguard's shape."""
    return json.dumps(
        {"size": len(rows) if size is None else size, "asOfDate": as_of, "fund": {"entity": rows}}
    ).encode("utf-8")


class _Site:
    """Stands in for Vanguard: serves a list of rows 500 at a time and records the requests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.requests: list[str] = []

    def fetch(self, url: str) -> bytes:
        """Answer one page request the way Vanguard does."""
        self.requests.append(url)
        start = int(url.split("start=")[1].split("&")[0])
        return _document(self.rows[start - 1 : start + 499], size=len(self.rows))


def _write(tmp_path: Path, body: bytes | str) -> Path:
    """Write a file into the temporary folder and return its path."""
    path = tmp_path / "VTI.json"
    if isinstance(body, str):
        path.write_text(body, encoding="utf-8")
    else:
        path.write_bytes(body)
    return path


# --- The address -----------------------------------------------------------------------------


def test_a_page_is_addressed_by_fund_id_and_first_row() -> None:
    """The address behind Vanguard's fund pages, 500 rows at a time (ADR 0016)."""
    assert page_url("0970", 501) == (
        "https://investor.vanguard.com/vmf/api/0970/portfolio-holding/stock.json"
        "?start=501&count=500"
    )


# --- Downloading -----------------------------------------------------------------------------


def test_a_fund_of_one_page_is_downloaded_with_one_request(tmp_path: Path) -> None:
    """A short list needs no second page."""
    site = _Site([_row(number) for number in range(1, 8)])
    destination = tmp_path / "data" / "vanguard" / "VTI.json"

    download_vanguard_file("0970", destination, site.fetch)

    assert site.requests == [page_url("0970", 1)]
    assert len(read_vanguard_file(destination).rows) == 7
    assert sorted(path.name for path in destination.parent.iterdir()) == ["VTI.json"]


def test_every_page_is_fetched_and_the_pages_are_joined_in_order(tmp_path: Path) -> None:
    """1,001 rows are three pages; the saved file holds them all, in Vanguard's order."""
    site = _Site([_row(number) for number in range(1, 1002)])
    destination = tmp_path / "VXUS.json"

    download_vanguard_file("3369", destination, site.fetch)

    assert site.requests == [page_url("3369", start) for start in (1, 501, 1001)]
    file = read_vanguard_file(destination)
    assert file.as_of == date(2026, 10, 31)
    assert [row.ticker for row in file.rows] == [f"T{number}" for number in range(1, 1002)]


@pytest.mark.parametrize("count", [500, 1000], ids=["one full page", "two full pages"])
def test_a_list_that_ends_on_a_page_boundary_needs_no_empty_request(
    tmp_path: Path, count: int
) -> None:
    """The stated number of rows says how many pages there are."""
    site = _Site([_row(number) for number in range(1, count + 1)])

    download_vanguard_file("0970", tmp_path / "VTI.json", site.fetch)

    assert len(site.requests) == count // 500


def test_the_saved_file_has_the_shape_of_a_page(tmp_path: Path) -> None:
    """The file is Vanguard's own document, only with every row in it."""
    site = _Site([_row(number) for number in range(1, 503)])
    destination = tmp_path / "VTI.json"

    download_vanguard_file("0970", destination, site.fetch)

    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["size"] == 502
    assert document["asOfDate"] == _AS_OF
    assert document["fund"]["entity"] == site.rows


def test_pages_of_two_different_months_are_not_joined(tmp_path: Path) -> None:
    """The list changed while it was read: nothing is kept."""
    rows = [_row(number) for number in range(1, 601)]
    destination = tmp_path / "vanguard" / "VTI.json"

    def fetch(url: str) -> bytes:
        if "start=1&" in url:
            return _document(rows[:500], size=600)
        return _document(rows[500:], size=600, as_of="2026-11-30T00:00:00-05:00")

    with pytest.raises(SponsorFileError, match="as of 2026-11-30.*nothing was kept"):
        download_vanguard_file("0970", destination, fetch)

    assert not destination.parent.exists()


def test_a_later_page_that_states_another_size_is_refused(tmp_path: Path) -> None:
    """A holding was added or dropped between two requests."""
    rows = [_row(number) for number in range(1, 601)]

    def fetch(url: str) -> bytes:
        return _document(rows[:500], size=600) if "start=1&" in url else _document(rows[500:])

    with pytest.raises(SponsorFileError, match="states 100 rows .* first page stated 600"):
        download_vanguard_file("0970", tmp_path / "VTI.json", fetch)


def test_fewer_rows_than_stated_are_refused(tmp_path: Path) -> None:
    """A cut-off answer must not pass for the whole list."""

    def fetch(url: str) -> bytes:
        return _document([_row(1), _row(2)], size=3)

    with pytest.raises(SponsorFileError, match="states 3 rows and 2 arrived; nothing was kept"):
        download_vanguard_file("0970", tmp_path / "VTI.json", fetch)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("size", [0, -1, 100_001], ids=["none", "negative", "absurdly many"])
def test_a_size_that_cannot_be_right_is_refused_before_any_further_request(
    tmp_path: Path, size: int
) -> None:
    """A wrong number of rows must not turn into an endless run of requests."""
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        return _document([], size=size)

    with pytest.raises(SponsorFileError, match="which cannot be right"):
        download_vanguard_file("0970", tmp_path / "VTI.json", fetch)

    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"<html><body>Not found</body></html>", id="an error page"),
        pytest.param(b"", id="nothing"),
        pytest.param(b"[1, 2, 3]", id="JSON of another kind"),
        pytest.param(b'{"asOfDate": "2026-10-31", "fund": {"entity": []}}', id="no size"),
        pytest.param(b'{"size": true, "asOfDate": "x", "fund": {"entity": []}}', id="size true"),
        pytest.param(b'{"size": 1, "fund": {"entity": []}}', id="no date"),
        pytest.param(b'{"size": 1, "asOfDate": "2026-10-31"}', id="no rows"),
        pytest.param(b'{"size": 1, "asOfDate": "2026-10-31", "fund": []}', id="fund not a block"),
    ],
)
def test_an_answer_that_is_not_vanguards_file_is_refused(tmp_path: Path, body: bytes) -> None:
    """An error page saved as the file would give every line no ticker, silently."""

    def fetch(url: str) -> bytes:
        return body

    with pytest.raises(SponsorFileError, match="is not a Vanguard holdings file"):
        download_vanguard_file("0970", tmp_path / "VTI.json", fetch)

    assert list(tmp_path.iterdir()) == []


def test_a_file_that_does_not_read_back_is_not_kept(tmp_path: Path) -> None:
    """Rows that are not holdings pass the page check and fail the reader: nothing is kept."""

    def fetch(url: str) -> bytes:
        return json.dumps({"size": 1, "asOfDate": _AS_OF, "fund": {"entity": ["x"]}}).encode()

    with pytest.raises(SponsorFileError, match="did not return a usable holdings file"):
        download_vanguard_file("0970", tmp_path / "VTI.json", fetch)

    assert list(tmp_path.iterdir()) == []


def test_a_failed_fetch_leaves_nothing_behind(tmp_path: Path) -> None:
    """The fetch's own error passes through, and no file or folder is made."""
    destination = tmp_path / "vanguard" / "VTI.json"

    def fetch(url: str) -> bytes:
        raise SponsorFileError("cannot download: no network")

    with pytest.raises(SponsorFileError, match="no network"):
        download_vanguard_file("0970", destination, fetch)

    assert not destination.parent.exists()


def test_a_folder_that_cannot_be_made_is_reported(tmp_path: Path) -> None:
    """A file where the folder should be is a condition to report, not a crash."""
    blocker = tmp_path / "vanguard"
    blocker.write_text("a file where a folder is expected")
    site = _Site([_row(1)])

    with pytest.raises(SponsorFileError, match="cannot save Vanguard's holdings file"):
        download_vanguard_file("0970", blocker / "VTI.json", site.fetch)


# --- Reading ---------------------------------------------------------------------------------


def test_the_sample_file_is_read_row_by_row(vanguard_samples: Path) -> None:
    """The sample that goes with the sample filings (tests/fixtures/vanguard/README.md)."""
    file = read_vanguard_file(vanguard_samples / "VTI.json")

    assert file.as_of == date(2026, 10, 31)
    assert file.rows == (
        VanguardRow(isin="US00000A0014", ticker="ALPH", sedol="B000A01"),
        VanguardRow(isin="US00000A0022", ticker="ALPH.PA", sedol="B000A02"),
        VanguardRow(isin="US00000B0013", ticker=None, sedol="B000B01"),
        VanguardRow(isin="US00000B0021", ticker="BETB", sedol="B000B02"),
        VanguardRow(isin="US00000B0021", ticker="BETB.X", sedol="B000B03"),
        VanguardRow(isin=None, ticker="ESU6", sedol=None),
        VanguardRow(isin="US00000R0017", ticker="RHO", sedol="B000R01"),
    )


def test_the_date_is_read_without_its_time_and_zone(tmp_path: Path) -> None:
    """Vanguard states the day as midnight in New York."""
    path = _write(tmp_path, _document([_row(1)], as_of="2026-10-31T00:00:00-04:00"))

    assert read_vanguard_file(path).as_of == date(2026, 10, 31)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        pytest.param(
            {"isin": "", "ticker": "", "sedol": ""},
            VanguardRow(None, None, None),
            id="empty texts",
        ),
        pytest.param({}, VanguardRow(None, None, None), id="absent values"),
        pytest.param(
            {"isin": None, "ticker": 7, "sedol": ["B000A01"]},
            VanguardRow(None, None, None),
            id="values that are not text",
        ),
        pytest.param(
            {"isin": " US00000A0014 ", "ticker": " NOVO B ", "sedol": " B000A01 "},
            VanguardRow("US00000A0014", "NOVO B", "B000A01"),
            id="padded values, a space inside a ticker kept",
        ),
        pytest.param(
            {"isin": "US00000A0014", "ticker": "GCC*", "sedol": "N/A"},
            VanguardRow("US00000A0014", "GCC*", None),
            id="a placeholder for the SEDOL",
        ),
        pytest.param(
            {"isin": "US00000A0014", "ticker": "X", "sedol": "b000a01"},
            VanguardRow("US00000A0014", "X", None),
            id="a SEDOL in lower case",
        ),
        pytest.param(
            {"isin": "US00000A0014", "ticker": "X", "sedol": "B000A012"},
            VanguardRow("US00000A0014", "X", None),
            id="a SEDOL one character long",
        ),
    ],
)
def test_a_row_is_read_leniently_and_a_sedol_strictly(
    tmp_path: Path, values: dict[str, object], expected: VanguardRow
) -> None:
    """An absent value is no value; a SEDOL of another shape would not fit the database."""
    path = _write(tmp_path, _document([values]))

    assert read_vanguard_file(path).rows == (expected,)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param("not json", "is not a Vanguard holdings file", id="not JSON"),
        pytest.param("[]", "is not a Vanguard holdings file", id="JSON of another kind"),
        pytest.param(
            _document([_row(1)], size=2).decode(), "states 2 rows and holds 1", id="a row missing"
        ),
        pytest.param(
            _document([_row(1)], as_of="last October").decode(),
            "the date 'last October' is not a date",
            id="unreadable date",
        ),
        pytest.param(
            json.dumps({"size": 1, "asOfDate": _AS_OF, "fund": {"entity": [7]}}),
            "row 1 is not a holding",
            id="a row that is no holding",
        ),
    ],
)
def test_a_file_that_is_not_usable_is_refused(tmp_path: Path, body: str, message: str) -> None:
    """A damaged file fails with its path and the reason, not with a parser trace."""
    path = _write(tmp_path, body)

    with pytest.raises(SponsorFileError, match=message):
        read_vanguard_file(path)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(SponsorFileError, match="cannot read Vanguard's holdings file"):
        read_vanguard_file(tmp_path / "absent.json")
