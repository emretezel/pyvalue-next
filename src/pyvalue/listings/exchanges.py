"""Our exchanges: the committed file that fills the ``exchange`` table.

Which markets pyvalue knows is reference data of its own, kept in
``pyvalue/listings/reference/exchange.csv`` (ADR 0018): the ISO 10383 market
code, a name and the country. The file is shipped inside the package, so an
installed copy knows the same exchanges. It lists the markets a provider
serves; a market no provider serves needs no row.

A file has no constraints of its own, so every row is checked here, by the
same rules the table has.

Author: Emre Tezel
"""

import re
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from pyvalue.csv_file import read_csv
from pyvalue.db import Exchange
from pyvalue.listings.errors import ListingsError
from pyvalue.providers import ExchangeCodes

# The columns of the file, in order.
_HEADER: tuple[str, ...] = ("mic", "name", "country")

# An ISO 10383 market code and an ISO 3166 country code, as the table accepts them.
_MIC: re.Pattern[str] = re.compile(r"[A-Z0-9]{4}")
_COUNTRY: re.Pattern[str] = re.compile(r"[A-Z]{2}")


def _exchange(row: list[str], where: str) -> Exchange:
    """Turn one row of the file into an exchange, or say what is wrong with it."""
    mic, name, country = row
    if _MIC.fullmatch(mic) is None:
        raise ListingsError(
            f"{where}: '{mic}' is not a market code (four upper-case letters or digits)"
        )
    if not name or name != name.strip():
        raise ListingsError(f"{where}: the name must be filled in, without spaces around it")
    if _COUNTRY.fullmatch(country) is None:
        raise ListingsError(f"{where}: '{country}' is not a country code (two upper-case letters)")
    return Exchange(mic=mic, name=name, country=country)


def read_exchanges(path: Path) -> tuple[Exchange, ...]:
    """Read a file of exchanges.

    Args:
        path: A comma-separated file with the header ``mic,name,country``.

    Returns:
        The exchanges, in the order of the file.

    Raises:
        ListingsError: If the file cannot be read, its header is wrong, a row
            is invalid, or two rows have the same market code. The message
            names the row, counting the header as row 1.
    """
    exchanges: list[Exchange] = []
    seen: dict[str, str] = {}
    for where, cells in read_csv(path, _HEADER, ListingsError, "the exchanges file"):
        exchange = _exchange(cells, where)
        if exchange.mic in seen:
            raise ListingsError(
                f"{where}: {exchange.mic} already has a row, at {seen[exchange.mic]}"
            )
        seen[exchange.mic] = where
        exchanges.append(exchange)
    return tuple(exchanges)


def packaged_exchanges() -> tuple[Exchange, ...]:
    """Return the exchanges shipped with pyvalue."""
    packaged = resources.files("pyvalue.listings").joinpath("reference", "exchange.csv")
    # as_file gives a real file even if the package were installed zipped.
    with resources.as_file(packaged) as path:
        return read_exchanges(path)


def require_our_exchanges(codes: ExchangeCodes, exchanges: Iterable[Exchange]) -> None:
    """Check that every exchange a provider's file names is one of ours.

    The two files are maintained by hand and separately. The table would
    refuse a code for an exchange that does not exist, but only in the middle
    of a load; this says it first, and names every such exchange at once.

    Args:
        codes: A provider's exchange file.
        exchanges: Our exchanges.

    Raises:
        ListingsError: If the provider's file names a market code that the
            exchanges file does not have.
    """
    ours = {exchange.mic for exchange in exchanges}
    missing = sorted({mic for mic, _ in codes.markets()} - ours)
    if missing:
        raise ListingsError(
            f"the provider's exchange file names exchanges that the exchanges file "
            f"does not have: {', '.join(missing)}"
        )
