"""Where a provider's downloaded lists are kept, and when one looks too short.

The download writes the lists as files and the load reads them (ADR 0024).
This module is what the two share: the folder, the file names, and the test
that both apply before they replace a good list with a new one.

Author: Emre Tezel
"""

from pathlib import Path

# Relative on purpose, like the database path: the lists belong to the folder
# pyvalue is run from, and `data/` is never committed.
DEFAULT_LISTS_DIR: Path = Path("data") / "eodhd"

# The file the provider's list of exchange codes is kept in.
EXCHANGE_LIST_FILE: str = "exchanges.json"

# A new list counts as suspiciously short when it has at least this many fewer
# lines than the one it would replace, and fewer than half as many (ADR 0018).
_FEWER_AT_LEAST: int = 20


def symbol_list_file(provider_exchange_code: str) -> str:
    """Return the name of the file the symbol list of one exchange code is kept in.

    Args:
        provider_exchange_code: The provider's exchange code, such as ``US``.
    """
    return f"symbols_{provider_exchange_code}.json"


def suspiciously_short(new: int, old: int) -> bool:
    """Say whether a new list is too short to replace the one that is there.

    EODHD once answered for an exchange it had dropped with a stub of 30
    lines (ADR 0018). Both conditions must hold, so a small list that loses a
    few lines and a large list that loses a few hundred both pass.

    Args:
        new: The number of lines of the new list.
        old: The number of lines of the list it would replace.
    """
    return old - new >= _FEWER_AT_LEAST and new * 2 < old
