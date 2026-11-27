"""Tests for ``pyvalue.fundamentals.saved_payloads``: where a payload is kept (ADR 0028).

A saved file is the record that a line was downloaded, so the name of a
line's file must never be shared by two lines, on any file system the
project runs on.

Author: Emre Tezel
"""

import gzip
import re
import urllib.parse
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.fundamentals import DEFAULT_PAYLOADS_DIR, FundamentalsError, payload_file
from pyvalue.fundamentals.saved_payloads import pack, save_payload

# What a code or a symbol can be: any text that is not empty. The tables
# refuse an empty one.
_PARTS = st.text(min_size=1, max_size=12)

# A name is made of these characters and nothing else.
_SAFE: re.Pattern[str] = re.compile(r"[A-Z0-9_%-]+")


def test_the_payloads_are_kept_beside_the_symbol_lists() -> None:
    """Under the provider's folder, which is never committed."""
    assert Path("data") / "eodhd" / "fundamentals" == DEFAULT_PAYLOADS_DIR


def test_a_payload_is_filed_under_its_exchange_code_and_named_by_its_symbol() -> None:
    """One folder per code, one file per symbol."""
    assert payload_file("US", "BRK-B") == Path("US") / "BRK-B.json.gz"
    assert payload_file("KO", "000660") == Path("KO") / "000660.json.gz"


def test_an_unusual_character_is_escaped() -> None:
    """One listed symbol holds an ``&``."""
    assert payload_file("MX", "PE&OLES") == Path("MX") / "PE%26OLES.json.gz"


def test_a_small_letter_is_escaped_too() -> None:
    """So that two symbols never share a file where case is ignored, as on macOS."""
    assert payload_file("US", "Ab") == Path("US") / "A%62.json.gz"
    assert payload_file("US", "Ab") != payload_file("US", "AB")


def test_a_symbol_cannot_leave_its_folder() -> None:
    """Dots and separators are escaped, so no name is a path."""
    assert payload_file("US", "../X") == Path("US") / "%2E%2E%2FX.json.gz"
    assert payload_file("..", "X") == Path("%2E%2E") / "X.json.gz"


def test_a_character_outside_ascii_is_escaped_byte_by_byte() -> None:
    """As an address would write it."""
    assert payload_file("MX", "PEÑOLES") == Path("MX") / "PE%C3%91OLES.json.gz"


@given(code=_PARTS, symbol=_PARTS)
def test_a_name_is_made_of_safe_characters_only(code: str, symbol: str) -> None:
    """Capital letters, digits, hyphen, underscore and the escape sign."""
    folder, name = payload_file(code, symbol).parts

    assert _SAFE.fullmatch(folder)
    assert _SAFE.fullmatch(name.removesuffix(".json.gz"))
    assert name.endswith(".json.gz")


@given(code=_PARTS, symbol=_PARTS)
def test_a_name_gives_the_code_and_the_symbol_back(code: str, symbol: str) -> None:
    """Nothing is lost: the name can be read as the line it belongs to."""
    folder, name = payload_file(code, symbol).parts

    assert urllib.parse.unquote(folder) == code
    assert urllib.parse.unquote(name.removesuffix(".json.gz")) == symbol


@given(first=st.tuples(_PARTS, _PARTS), second=st.tuples(_PARTS, _PARTS))
def test_two_lines_never_share_a_file_even_where_case_is_ignored(
    first: tuple[str, str], second: tuple[str, str]
) -> None:
    """The usual macOS file system treats ``Abc`` and ``ABC`` as one name."""
    if first != second:
        assert str(payload_file(*first)).lower() != str(payload_file(*second)).lower()


@given(body=st.binary(max_size=2000))
def test_a_packed_payload_unpacks_to_the_same_bytes(body: bytes) -> None:
    """The answer is kept as it arrived."""
    assert gzip.decompress(pack(body)) == body


@given(body=st.binary(max_size=2000))
def test_the_same_payload_always_gives_the_same_file(body: bytes) -> None:
    """No time of writing is kept in the file."""
    assert pack(body) == pack(body)


def test_a_saved_payload_reads_back_byte_for_byte(tmp_path: Path) -> None:
    """The folder of the exchange code is created with the first payload."""
    body = b'{"General": {"Code": "ALPH"}}'
    destination = tmp_path / "fundamentals" / payload_file("US", "ALPH")

    save_payload(body, destination)

    assert gzip.decompress(destination.read_bytes()) == body
    assert [path.name for path in destination.parent.iterdir()] == ["ALPH.json.gz"]


def test_a_payload_that_cannot_be_written_is_the_components_own_error(tmp_path: Path) -> None:
    """A person can act on it: the message names the file."""
    blocker = tmp_path / "fundamentals"
    blocker.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(FundamentalsError, match=r"cannot save .*ALPH\.json\.gz"):
        save_payload(b"{}", blocker / payload_file("US", "ALPH"))
