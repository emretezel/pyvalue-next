"""Tests for ``pyvalue.universe.identifiers``: ISIN and legal-entity identifier checks.

Author: Emre Tezel
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyvalue.db import Database, migrate
from pyvalue.universe.identifiers import is_valid_isin, is_valid_lei

_LETTERS: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS: str = "0123456789"

# Identifier bodies of the right shape, still lacking their check digits.
_ISIN_BODIES: st.SearchStrategy[str] = st.from_regex(r"[A-Z]{2}[A-Z0-9]{9}", fullmatch=True)
_LEI_BODIES: st.SearchStrategy[str] = st.from_regex(r"[A-Z0-9]{18}", fullmatch=True)


class _UndoError(Exception):
    """Raised inside a unit of work to roll back what an example wrote."""


def _valid_isins(body: str) -> list[str]:
    """Return every completion of an 11-character body that is a valid ISIN."""
    return [body + digit for digit in _DIGITS if is_valid_isin(body + digit)]


def _valid_leis(body: str) -> list[str]:
    """Return every completion of an 18-character body that is a valid identifier."""
    return [f"{body}{number:02d}" for number in range(100) if is_valid_lei(f"{body}{number:02d}")]


def _other_character(character: str, shift: int) -> str:
    """Return another character of the same kind: a digit for a digit, a letter for a letter."""
    alphabet = _DIGITS if character in _DIGITS else _LETTERS
    return alphabet[(alphabet.index(character) + 1 + shift % (len(alphabet) - 1)) % len(alphabet)]


@pytest.mark.parametrize(
    "isin",
    [
        "US0378331005",  # Apple
        "US5949181045",  # Microsoft
        "US02079K3059",  # Alphabet class A: a letter inside the body
        "DE0007164600",  # SAP
        "JP3633400001",  # Toyota
        "KR7000660001",  # SK Hynix
        "GB0002374006",  # Diageo
    ],
)
def test_real_isins_are_valid(isin: str) -> None:
    """The check digit formula agrees with identifiers in real use."""
    assert is_valid_isin(isin)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("N/A", id="placeholder"),
        pytest.param("US0378331006", id="wrong check digit"),
        pytest.param("US037833100", id="one character short"),
        pytest.param("US03783310050", id="one character long"),
        pytest.param("us0378331005", id="lower case"),
        pytest.param("0S0378331005", id="digit in the country part"),
        pytest.param("US037833100X", id="letter where the check digit belongs"),
        pytest.param("US0378 31005", id="space inside"),
        pytest.param(" US0378331005", id="leading space"),
        pytest.param("US037833100５", id="a digit from outside ASCII"),
    ],
)
def test_other_text_is_not_a_valid_isin(text: str) -> None:
    """Shape and check digit must both hold."""
    assert not is_valid_isin(text)


@pytest.mark.parametrize(
    "lei",
    [
        "HWUPKR0MPOU8FGXBT394",  # Apple
        "5493000C01ZX7D35SD85",  # Berkshire Hathaway
        "5493006MHB84DD0ZWV18",  # Alphabet
        "529900D6BF99LW9R2E68",  # SAP
        "5493006W3QUS5LMH6R84",  # Toyota
    ],
)
def test_real_legal_entity_identifiers_are_valid(lei: str) -> None:
    """The check digit formula agrees with identifiers in real use."""
    assert is_valid_lei(lei)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("N/A", id="the placeholder filings use"),
        pytest.param("HWUPKR0MPOU8FGXBT395", id="wrong check digits"),
        pytest.param("HWUPKR0MPOU8FGXBT39", id="one character short"),
        pytest.param("HWUPKR0MPOU8FGXBT3940", id="one character long"),
        pytest.param("hwupkr0mpou8fgxbt394", id="lower case"),
        pytest.param("HWUPKR0MPOU8FGXBT3A4", id="letter among the check digits"),
        pytest.param("HWUPKR0MPOU8 GXBT394", id="space inside"),
        # These three pass the remainder test and are still not identifiers: the
        # standard never issues the check digits 00, 01 or 99.
        pytest.param("00000000000000000001", id="check digits 01"),
        pytest.param("00000000000000006500", id="check digits 00"),
        pytest.param("00000000000000003299", id="check digits 99"),
    ],
)
def test_other_text_is_not_a_valid_legal_entity_identifier(text: str) -> None:
    """Shape and check digits must both hold."""
    assert not is_valid_lei(text)


@given(body=_ISIN_BODIES)
def test_every_isin_body_has_exactly_one_check_digit(body: str) -> None:
    """Of the ten possible last digits, the formula accepts one and only one."""
    assert len(_valid_isins(body)) == 1


@given(body=_ISIN_BODIES, position=st.integers(min_value=0, max_value=11), shift=st.integers(0, 8))
def test_a_changed_digit_makes_an_isin_invalid(body: str, position: int, shift: int) -> None:
    """A single mistyped digit, the commonest error, is always caught."""
    (isin,) = _valid_isins(body)
    if isin[position] not in _DIGITS:
        # A letter stands for two digits, and the formula does not promise to
        # catch a change to both at once.
        return
    changed = isin[:position] + _other_character(isin[position], shift) + isin[position + 1 :]

    assert not is_valid_isin(changed)


@given(body=_LEI_BODIES)
def test_every_identifier_body_has_exactly_one_pair_of_check_digits(body: str) -> None:
    """Of the hundred possible endings, the formula accepts one and only one."""
    assert len(_valid_leis(body)) == 1


@given(body=_LEI_BODIES, position=st.integers(min_value=0, max_value=19), shift=st.integers(0, 24))
def test_a_changed_character_makes_an_identifier_invalid(
    body: str, position: int, shift: int
) -> None:
    """A digit mistyped as another digit, or a letter as another letter, is always caught."""
    (lei,) = _valid_leis(body)
    changed = lei[:position] + _other_character(lei[position], shift) + lei[position + 1 :]

    assert not is_valid_lei(changed)


@pytest.fixture(scope="module")
def shared_database(tmp_path_factory: pytest.TempPathFactory) -> Database:
    """Return one migrated database for all examples of this module.

    Every example rolls back what it writes, so no example sees another's rows.
    """
    path = tmp_path_factory.mktemp("identifiers") / "pyvalue.db"
    migrate(path)
    return Database(path)


@given(body=_ISIN_BODIES)
def test_the_database_accepts_every_isin_the_load_accepts(
    shared_database: Database, body: str
) -> None:
    """The load's check is stricter than the schema's, never looser."""
    (isin,) = _valid_isins(body)

    with pytest.raises(_UndoError), shared_database.unit_of_work() as work:
        company = work.companies.add("Probe Co", None)
        work.instruments.add(company.company_id, isin)
        raise _UndoError


@given(body=_LEI_BODIES)
def test_the_database_accepts_every_identifier_the_load_accepts(
    shared_database: Database, body: str
) -> None:
    """The load's check is stricter than the schema's, never looser."""
    (lei,) = _valid_leis(body)

    with pytest.raises(_UndoError), shared_database.unit_of_work() as work:
        work.companies.add("Probe Co", lei)
        raise _UndoError
