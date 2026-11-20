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


class ConfigError(PyvalueError):
    """A setting pyvalue needs is missing or unusable."""


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
    try:
        with path.open("rb") as handle:
            settings = tomllib.load(handle)
    except FileNotFoundError as error:
        raise ConfigError(f"{path} does not exist; create it and {_SEC_CONTACT_HINT}") from error
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        # The parser's message gives a position, never the file's content.
        raise ConfigError(f"{path} is not valid TOML: {error}") from error

    # TOML values are untyped, so each level is narrowed before it is used.
    section = settings.get("sec")
    value = section.get("user_agent") if isinstance(section, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} has no SEC contact; {_SEC_CONTACT_HINT}")
    return value.strip()
