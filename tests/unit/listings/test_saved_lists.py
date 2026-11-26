"""Tests for ``pyvalue.listings.saved_lists``: file names and the short-list test.

Author: Emre Tezel
"""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.listings.saved_lists import (
    DEFAULT_LISTS_DIR,
    EXCHANGE_LIST_FILE,
    suspiciously_short,
    symbol_list_file,
)


def test_the_lists_are_kept_under_data_of_the_working_folder() -> None:
    """Like the database: in the folder git ignores, relative to where pyvalue is run."""
    assert Path("data") / "eodhd" == DEFAULT_LISTS_DIR
    assert not DEFAULT_LISTS_DIR.is_absolute()


def test_each_list_has_a_file_of_its_own() -> None:
    """One file for the exchange list, one per exchange code."""
    assert EXCHANGE_LIST_FILE == "exchanges.json"
    assert symbol_list_file("US") == "symbols_US.json"
    assert symbol_list_file("KO") != symbol_list_file("KQ")


@pytest.mark.parametrize(
    ("new", "old", "expected"),
    [
        pytest.param(30, 2835, True, id="the stub EODHD once sent for a dropped exchange"),
        pytest.param(0, 20, True, id="everything gone from a small list"),
        pytest.param(0, 19, False, id="fewer than twenty lines lost"),
        pytest.param(10, 29, False, id="nineteen lost, although fewer than half remain"),
        pytest.param(9, 29, True, id="twenty lost and fewer than half remain"),
        pytest.param(500, 1000, False, id="exactly half remain"),
        pytest.param(499, 1000, True, id="just under half remain"),
        pytest.param(900, 1000, False, id="a hundred lost of a thousand"),
        pytest.param(1000, 1000, False, id="unchanged"),
        pytest.param(1200, 1000, False, id="grown"),
        pytest.param(40, 0, False, id="the first list"),
        pytest.param(0, 0, False, id="nothing before, nothing now"),
    ],
)
def test_a_list_is_too_short_when_it_lost_twenty_lines_and_more_than_half(
    new: int, old: int, expected: bool
) -> None:
    """Both conditions of ADR 0018 must hold."""
    assert suspiciously_short(new, old) is expected


@given(st.integers(min_value=0, max_value=200_000), st.integers(min_value=0, max_value=200_000))
def test_a_list_that_did_not_shrink_is_never_too_short(old: int, growth: int) -> None:
    """Whatever the sizes, the test only ever stops a list that got shorter."""
    assert not suspiciously_short(old + growth, old)


@given(st.integers(min_value=0, max_value=200_000), st.integers(min_value=0, max_value=200_000))
def test_a_shorter_new_list_is_never_judged_more_kindly(new: int, old: int) -> None:
    """If a list of some length is too short, every shorter one is too."""
    if suspiciously_short(new, old) and new > 0:
        assert suspiciously_short(new - 1, old)
