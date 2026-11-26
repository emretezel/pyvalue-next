"""Read pyvalue's local settings from ``private/config.toml``.

The file holds credentials and personal contact details, so it is never
committed, and nothing here ever puts one of its values into a message.

Author: Emre Tezel
"""

import tomllib
from pathlib import Path

from pyvalue.errors import PyvalueError

# Relative on purpose, like the database path: the settings belong to the
# folder pyvalue is run from, and `private/` is never committed.
DEFAULT_CONFIG_PATH: Path = Path("private") / "config.toml"

# What to tell a person whose settings lack the SEC contact line.
_SEC_CONTACT_HINT: str = (
    'add a section [sec] with the line user_agent = "Your Name your@email.address"; '
    "the SEC asks automated clients to identify themselves"
)


# What to tell a person whose settings lack the EODHD key.
_EODHD_KEY_HINT: str = (
    'add a section [eodhd] with the line api_key = "..."; it is the API token of an '
    "EODHD subscription"
)


class ConfigError(PyvalueError):
    """A setting pyvalue needs is missing or unusable."""


def _setting(path: Path, section: str, key: str, missing: str, hint: str) -> str:
    """Return one text setting, or say what to add.

    Args:
        path: The settings file.
        section: The TOML section the setting is in.
        key: The setting's name in that section.
        missing: How to name the setting in a message, such as "SEC contact".
        hint: What a person should add to the file.

    Raises:
        ConfigError: If the file is missing or is not valid TOML, or the
            setting is missing, empty or not text. No message carries a
            value from the file.
    """
    try:
        with path.open("rb") as handle:
            settings = tomllib.load(handle)
    except FileNotFoundError as error:
        raise ConfigError(f"{path} does not exist; create it and {hint}") from error
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        # The parser's message gives a position, never the file's content.
        raise ConfigError(f"{path} is not valid TOML: {error}") from error

    # TOML values are untyped, so each level is narrowed before it is used.
    table = settings.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} has no {missing}; {hint}")
    return value.strip()


def sec_user_agent(path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Return the contact string pyvalue sends to the SEC.

    Args:
        path: The settings file.

    Returns:
        The value of ``user_agent`` in the section ``[sec]``.

    Raises:
        ConfigError: If the file is missing or is not valid TOML, or the line
            is missing, empty or not text. The message says what to add.
    """
    return _setting(path, "sec", "user_agent", "SEC contact", _SEC_CONTACT_HINT)


def eodhd_api_key(path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Return the API key pyvalue sends to EODHD.

    The key is a credential: it is handed to the EODHD client and to nothing
    else, and it is never printed, logged or put into a message.

    Args:
        path: The settings file.

    Returns:
        The value of ``api_key`` in the section ``[eodhd]``.

    Raises:
        ConfigError: If the file is missing or is not valid TOML, or the line
            is missing, empty or not text. The message says what to add.
    """
    return _setting(path, "eodhd", "api_key", "EODHD key", _EODHD_KEY_HINT)
