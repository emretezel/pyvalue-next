"""Where a provider's fundamentals payloads are kept, and under which names.

One file per provider line, under one folder per exchange code (ADR 0028):
``data/eodhd/fundamentals/US/BRK-B.json.gz``. The file holds the provider's
answer as it arrived, gzip-compressed. A saved file is also the record that
the line was downloaded, so the name of a line's file has to be the same on
every run and must never be shared by two lines.

Author: Emre Tezel
"""

import gzip
from pathlib import Path

from pyvalue.fundamentals.errors import FundamentalsError
from pyvalue.saved_file import save_whole

# Relative on purpose, like the database path: the payloads belong to the
# folder pyvalue is run from, and `data/` is never committed.
DEFAULT_PAYLOADS_DIR: Path = Path("data") / "eodhd" / "fundamentals"

# What a payload's file name ends with.
_SUFFIX: str = ".json.gz"

# The characters that are kept as they are in a file or folder name. Every
# other character is escaped. Small letters are not in the set on purpose:
# the usual macOS file system ignores case, so `Abc` and `ABC` would be one
# file there, and escaping the small letters keeps the two apart.
_PLAIN: frozenset[str] = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _name_part(text: str) -> str:
    """Return a provider's code or symbol as a part of a file name.

    Every character outside ``A-Z``, ``0-9``, ``-`` and ``_`` is written as
    ``%XX`` for each of its UTF-8 bytes, so ``PE&OLES`` becomes
    ``PE%26OLES``. The percent sign is escaped too, so two different texts
    never give the same name, and no name holds a path separator or a dot.
    """
    return "".join(
        character
        if character in _PLAIN
        else "".join(f"%{byte:02X}" for byte in character.encode("utf-8"))
        for character in text
    )


def payload_file(provider_exchange_code: str, provider_symbol: str) -> Path:
    """Return where the payload of one provider line is kept, relative to the payloads folder.

    Args:
        provider_exchange_code: The provider's exchange code, such as ``US``.
        provider_symbol: The provider's symbol under that code, such as
            ``BRK-B``.
    """
    return Path(_name_part(provider_exchange_code)) / f"{_name_part(provider_symbol)}{_SUFFIX}"


def pack(body: bytes) -> bytes:
    """Return a payload as the bytes of its file: gzip-compressed.

    The gzip header would carry the time of writing. It is set to zero, so
    the same payload always gives the same file.

    Args:
        body: The provider's answer, as it arrived.
    """
    return gzip.compress(body, mtime=0)


def save_payload(body: bytes, destination: Path) -> None:
    """Keep one payload as a file that is whole or absent.

    Args:
        body: The provider's answer, as it arrived.
        destination: The payload's file. Its folder is created when missing.

    Raises:
        FundamentalsError: If the file cannot be written.
    """
    save_whole(pack(body), destination, FundamentalsError)
