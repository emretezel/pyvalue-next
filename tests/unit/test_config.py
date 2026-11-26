"""Tests for ``pyvalue.config``: reading ``private/config.toml``.

Author: Emre Tezel
"""

from pathlib import Path

import pytest

from pyvalue.config import DEFAULT_CONFIG_PATH, ConfigError, eodhd_api_key, sec_user_agent
from pyvalue.errors import PyvalueError

# Stands in for a secret that shares the file with the SEC contact line.
_SECRET: str = "sample-api-key-0123456789"


def _write(tmp_path: Path, text: str) -> Path:
    """Write a settings file into the temporary folder and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_default_file_is_private_config_of_the_working_folder() -> None:
    """Settings belong to the folder pyvalue is run from, in the folder git ignores."""
    assert Path("private") / "config.toml" == DEFAULT_CONFIG_PATH
    assert not DEFAULT_CONFIG_PATH.is_absolute()


def test_the_contact_string_is_read_from_the_sec_section(tmp_path: Path) -> None:
    """Other sections of the file are no concern of this function."""
    path = _write(
        tmp_path,
        f'[eodhd]\napi_key = "{_SECRET}"\n\n'
        '[sec]\nuser_agent = "Sample Person sample@example.org"\n',
    )

    assert sec_user_agent(path) == "Sample Person sample@example.org"


def test_surrounding_spaces_are_dropped(tmp_path: Path) -> None:
    """A header value must not start or end with a space."""
    path = _write(tmp_path, '[sec]\nuser_agent = "  Sample Person sample@example.org "\n')

    assert sec_user_agent(path) == "Sample Person sample@example.org"


def test_the_default_path_is_used_when_none_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command passes the function itself, so the default must work unaided."""
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "config.toml").write_text(
        '[sec]\nuser_agent = "Sample Person sample@example.org"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert sec_user_agent() == "Sample Person sample@example.org"


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(f'[eodhd]\napi_key = "{_SECRET}"\n', id="no section"),
        pytest.param(f'[eodhd]\napi_key = "{_SECRET}"\n\n[sec]\n', id="empty section"),
        pytest.param(f'[sec]\nother = "{_SECRET}"\n', id="no line"),
        pytest.param('[sec]\nuser_agent = ""\n', id="empty value"),
        pytest.param('[sec]\nuser_agent = "   "\n', id="blank value"),
        pytest.param("[sec]\nuser_agent = 42\n", id="a number"),
        pytest.param(f'sec = "{_SECRET}"\n', id="section that is a value"),
        pytest.param("", id="empty file"),
    ],
)
def test_a_missing_contact_line_says_what_to_add(tmp_path: Path, content: str) -> None:
    """The message names the file, the section and the line, and no value from the file."""
    path = _write(tmp_path, content)

    with pytest.raises(ConfigError, match=r"has no SEC contact; add a section \[sec\]") as raised:
        sec_user_agent(path)

    message = str(raised.value)
    assert str(path) in message
    assert "user_agent" in message
    assert _SECRET not in message


def test_a_missing_file_says_what_to_create(tmp_path: Path) -> None:
    """A fresh checkout has no settings file at all."""
    path = tmp_path / "private" / "config.toml"

    with pytest.raises(ConfigError, match=r"does not exist; create it and add a section \[sec\]"):
        sec_user_agent(path)


def test_a_file_that_is_not_toml_is_reported_without_its_content(tmp_path: Path) -> None:
    """The parser's position is useful; the text around it could be a secret."""
    path = _write(tmp_path, f'[sec]\nuser_agent = "unterminated\napi_key = "{_SECRET}"\n')

    with pytest.raises(ConfigError, match="is not valid TOML") as raised:
        sec_user_agent(path)

    assert _SECRET not in str(raised.value)


def test_a_path_that_cannot_be_read_is_reported(tmp_path: Path) -> None:
    """A folder where the file should be is a condition to report, not a crash."""
    with pytest.raises(ConfigError, match="cannot read"):
        sec_user_agent(tmp_path)


def test_a_settings_problem_is_one_of_pyvalues_own_errors() -> None:
    """So the command line prints it as one line and exits with status 1."""
    assert issubclass(ConfigError, PyvalueError)


# --- The EODHD key -----------------------------------------------------------------------------


def test_the_key_is_read_from_the_eodhd_section(tmp_path: Path) -> None:
    """Other sections of the file are no concern of this function."""
    path = _write(
        tmp_path,
        f'[eodhd]\napi_key = "{_SECRET}"\n\n'
        '[sec]\nuser_agent = "Sample Person sample@example.org"\n',
    )

    assert eodhd_api_key(path) == _SECRET


def test_spaces_around_the_key_are_dropped(tmp_path: Path) -> None:
    """A key pasted with a trailing space would be refused by the provider."""
    assert eodhd_api_key(_write(tmp_path, f'[eodhd]\napi_key = "  {_SECRET} "\n')) == _SECRET


@pytest.mark.parametrize(
    "content",
    [
        pytest.param('[sec]\nuser_agent = "Sample Person sample@example.org"\n', id="no section"),
        pytest.param("[eodhd]\n", id="no line"),
        pytest.param('[eodhd]\napi_key = ""\n', id="empty"),
        pytest.param('[eodhd]\napi_key = "   "\n', id="only spaces"),
        pytest.param("[eodhd]\napi_key = 12345\n", id="a number"),
        pytest.param('eodhd = "not a section"\n', id="not a section"),
    ],
)
def test_a_missing_or_unusable_key_says_what_to_add(tmp_path: Path, content: str) -> None:
    """The message names the section and the line."""
    with pytest.raises(ConfigError, match="has no EODHD key; add a section .eodhd. with the line"):
        eodhd_api_key(_write(tmp_path, content))


def test_a_missing_file_says_what_to_create_for_the_key(tmp_path: Path) -> None:
    """The hint is the one for the setting that was asked for."""
    with pytest.raises(ConfigError, match="does not exist; create it and add a section .eodhd."):
        eodhd_api_key(tmp_path / "missing.toml")


def test_no_message_about_the_key_carries_a_value_of_the_file(tmp_path: Path) -> None:
    """Not the key itself when the file is broken further down, and not the contact line."""
    path = _write(
        tmp_path,
        f'[sec]\nuser_agent = "Sample Person sample@example.org"\n[eodhd]\napi_key = "{_SECRET}\n',
    )

    with pytest.raises(ConfigError) as raised:
        eodhd_api_key(path)

    assert _SECRET not in str(raised.value)
    assert "sample@example.org" not in str(raised.value)


def test_the_key_error_is_one_a_person_can_fix() -> None:
    """The command line prints it as one line."""
    assert issubclass(ConfigError, PyvalueError)
