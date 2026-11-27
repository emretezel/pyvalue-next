"""A provider's exchange codes: the committed file that maps them to our exchanges.

A provider names exchanges in its own way. EODHD calls Korea Exchange ``KO``
and puts every US venue under one code, ``US``, telling them apart only by a
label on each symbol line. The file ``<provider>_exchange.csv`` says which of
our exchanges each code, or each code and label, stands for (ADR 0018), and
what is left out on purpose (ADR 0024):

- a row without a label and without a market leaves a whole code out, such as
  Germany's regional exchanges;
- a row with a label and without a market leaves the lines with that label
  out, such as US over-the-counter lines, and the US lines EODHD gives no
  venue, which it labels with the code itself (ADR 0027).

The file is shipped inside the package. It knows nothing of the ``exchange``
table: that the markets it names are ours is checked by the component that
uses both (``pyvalue.listings``).

Author: Emre Tezel
"""

import re
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Final

from pyvalue.csv_file import read_csv
from pyvalue.providers.errors import ProviderError

# The columns of the file, in order.
_HEADER: tuple[str, ...] = ("provider_exchange_code", "provider_venue", "mic")

# An ISO 10383 market code, as the ``exchange`` table accepts it.
_MIC: re.Pattern[str] = re.compile(r"[A-Z0-9]{4}")


class VenueStatus(Enum):
    """Why a symbol line has no market of ours."""

    LEFT_OUT = "left out on purpose"
    UNKNOWN = "not in the file"


@dataclass(frozen=True, slots=True)
class ExchangeCode:
    """One row of the file.

    Attributes:
        provider_exchange_code: The code the provider uses, in its requests
            and in its lists.
        provider_venue: The venue label the provider writes on a symbol line,
            or ``None`` when every line of the code is on one exchange.
        mic: Our exchange, or ``None`` for what is left out on purpose.
    """

    provider_exchange_code: str
    provider_venue: str | None
    mic: str | None


class ExchangeCodes:
    """The file as a whole, and the questions it answers.

    Create it with ``read_exchange_codes``, which checks the rows against
    each other; the questions below rely on those checks.
    """

    def __init__(self, rows: tuple[ExchangeCode, ...]) -> None:
        """Index the rows of a checked file.

        Args:
            rows: The rows, in the order of the file.
        """
        self.rows: Final[tuple[ExchangeCode, ...]] = rows
        # A code whose lines are all on one exchange: code -> that exchange.
        self._single: dict[str, str] = {}
        # A code whose lines are told apart by label: code -> label -> the
        # exchange, or None for a label that is left out.
        self._by_label: dict[str, dict[str, str | None]] = {}
        for row in rows:
            if row.provider_venue is None:
                if row.mic is not None:
                    self._single[row.provider_exchange_code] = row.mic
            else:
                labels = self._by_label.setdefault(row.provider_exchange_code, {})
                labels[row.provider_venue] = row.mic

    def codes_with_a_market(self) -> tuple[str, ...]:
        """Return the codes that have at least one exchange of ours, in file order.

        These are the codes whose symbol lists are downloaded and stored.
        """
        seen: dict[str, None] = {}
        for row in self.rows:
            if row.mic is not None:
                seen.setdefault(row.provider_exchange_code)
        return tuple(seen)

    def codes_left_out(self) -> frozenset[str]:
        """Return the codes no row gives an exchange.

        They are left out on purpose, so a provider that offers them offers
        nothing the file lacks.
        """
        with_a_market = set(self.codes_with_a_market())
        return frozenset(
            row.provider_exchange_code
            for row in self.rows
            if row.provider_exchange_code not in with_a_market
        )

    def markets(self) -> tuple[tuple[str, str], ...]:
        """Return each pair of exchange and code once, in file order.

        One pair is one row of ``provider_exchange``: several labels of a
        code can stand for the same exchange.
        """
        seen: dict[tuple[str, str], None] = {}
        for row in self.rows:
            if row.mic is not None:
                seen.setdefault((row.mic, row.provider_exchange_code))
        return tuple(seen)

    def market_of(
        self, provider_exchange_code: str, provider_venue: str | None
    ) -> str | VenueStatus:
        """Say which exchange of ours a symbol line is on.

        Args:
            provider_exchange_code: The code whose list the line is in. It
                must be one of ``codes_with_a_market``.
            provider_venue: The venue label on the line, or ``None`` when the
                line carries none.

        Returns:
            The exchange's market code; or ``VenueStatus.LEFT_OUT`` for a
            label the file leaves out on purpose; or ``VenueStatus.UNKNOWN``
            for a label the file does not have, which includes a line
            without a label under a code whose rows carry labels.

        Raises:
            ProviderError: If the code has no exchange in the file.
        """
        single = self._single.get(provider_exchange_code)
        if single is not None:
            # Every line of the code is on one exchange, whatever it is labelled.
            return single
        labels = self._by_label.get(provider_exchange_code)
        if labels is None or all(mic is None for mic in labels.values()):
            raise ProviderError(
                f"the exchange code {provider_exchange_code} has no exchange in the file"
            )
        if provider_venue is None or provider_venue not in labels:
            return VenueStatus.UNKNOWN
        mic = labels[provider_venue]
        return VenueStatus.LEFT_OUT if mic is None else mic


def _exchange_code(row: list[str], where: str) -> ExchangeCode:
    """Turn one row of the file into an exchange code, or say what is wrong with it."""
    code, venue, mic = row
    if not code or code != code.strip():
        raise ProviderError(
            f"{where}: the exchange code must be filled in, without spaces around it"
        )
    if venue != venue.strip():
        raise ProviderError(f"{where}: the venue label '{venue}' has spaces around it")
    if mic and _MIC.fullmatch(mic) is None:
        raise ProviderError(
            f"{where}: '{mic}' is not a market code (four upper-case letters or digits)"
        )
    return ExchangeCode(provider_exchange_code=code, provider_venue=venue or None, mic=mic or None)


def read_exchange_codes(path: Path) -> ExchangeCodes:
    """Read a provider's exchange file.

    Args:
        path: A comma-separated file with the header
            ``provider_exchange_code,provider_venue,mic``.

    Returns:
        The file, ready to be asked.

    Raises:
        ProviderError: If the file cannot be read, its header is wrong, a
            row is invalid, a code and label appear twice, a code has both a
            row without a label and another row, or one exchange is given
            two codes. The message names the row, counting the header as
            row 1.
    """
    rows: list[ExchangeCode] = []
    seen: dict[tuple[str, str | None], str] = {}
    code_of: dict[str, str] = {}
    for where, cells in read_csv(path, _HEADER, ProviderError, "the exchange codes file"):
        row = _exchange_code(cells, where)
        code = row.provider_exchange_code
        key = (code, row.provider_venue)
        if key in seen:
            raise ProviderError(f"{where}: {code} already has this row, at {seen[key]}")
        # A code is either one exchange (or left out) as a whole, or told
        # apart by label. Both at once would leave the lines without a label
        # with two answers.
        mixed = (
            any(other == code and label is not None for other, label in seen)
            if row.provider_venue is None
            else (code, None) in seen
        )
        if mixed:
            raise ProviderError(
                f"{where}: {code} has a row without a venue label and a row with one; "
                "a code has either one row without a label or rows with labels"
            )
        if row.mic is not None:
            # The provider_exchange table holds one code per exchange and
            # provider, so the file must not ask for two.
            first = code_of.setdefault(row.mic, code)
            if first != code:
                raise ProviderError(
                    f"{where}: the exchange {row.mic} already has the code {first}; "
                    "an exchange has one code"
                )
        seen[key] = where
        rows.append(row)
    return ExchangeCodes(tuple(rows))


def packaged_exchange_codes(file_name: str) -> ExchangeCodes:
    """Read a provider's exchange file shipped inside the installed package.

    Args:
        file_name: The file's name in ``pyvalue/providers``, such as
            ``eodhd_exchange.csv``.
    """
    packaged = resources.files("pyvalue.providers").joinpath(file_name)
    # as_file gives a real file even if the package were installed zipped.
    with resources.as_file(packaged) as path:
        return read_exchange_codes(path)
