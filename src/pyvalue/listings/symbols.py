"""The symbols load: the committed exchange files and the saved lists into the database.

``pyvalue symbols load`` does two things, in this order (ADR 0024):

1. It adds what is missing in ``exchange``, ``provider`` and
   ``provider_exchange`` from the two committed files, and corrects a name or
   a country. It deletes nothing: a database that holds a row the files no
   longer have is refused and has to be rebuilt.
2. It stores each saved symbol list in ``provider_symbol``, one list per
   transaction, replacing the stored list of that code as a whole (ADR 0018).

It reads files and writes the database. It cannot reach the network: getting
the lists is the download's job (``pyvalue.listings.download``).

Author: Emre Tezel
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from pyvalue.db import (
    Database,
    Exchange,
    Provider,
    ProviderExchange,
    ProviderSymbol,
    UnitOfWork,
)
from pyvalue.identifiers import is_valid_isin
from pyvalue.listings.errors import ListingsError
from pyvalue.listings.exchanges import packaged_exchanges, require_our_exchanges
from pyvalue.listings.saved_lists import DEFAULT_LISTS_DIR, suspiciously_short, symbol_list_file
from pyvalue.providers import ExchangeCodes, ProviderError, VenueStatus, packaged_exchange_codes
from pyvalue.providers.eodhd import (
    EXCHANGE_FILE,
    PROVIDER_CODE,
    PROVIDER_NAME,
    SymbolLine,
    parse_symbol_list,
)

# The types of a symbol line that are stored: the two the table accepts
# (ADR 0018). Matched exactly; a line of any other type, or of one of these
# in another spelling, is counted by its type in the report.
_SHARE_TYPES: frozenset[str] = frozenset({"Common Stock", "Preferred Stock"})

# How a line without a type, and a line without a venue label, are named in
# the report.
_NO_TYPE: str = "(no type)"
_NO_LABEL: str = "(no label)"

# How many repeated symbols a report names before it only counts the rest.
_NAMED_AT_MOST: int = 10

# What to do about a database that holds a row the files no longer have.
_REBUILD: str = (
    "The load does not delete rows, so the database has to be rebuilt: set the file aside, "
    "run `pyvalue db migrate`, then `pyvalue universe load` and `pyvalue symbols load`"
)


class NotStoredReason(Enum):
    """Why the symbol list of a code was not stored."""

    NO_SAVED_LIST = "no saved list"
    NOT_A_LIST = "the saved file is not a symbol list"
    UNKNOWN_LABELS = "venue labels the exchange file does not have"
    REPEATED_SYMBOLS = "a symbol appears more than once"
    SUSPICIOUSLY_SHORT = "suspiciously short against the stored list"


@dataclass(frozen=True, slots=True)
class ExchangeTables:
    """What the load did to the three exchange tables.

    Attributes:
        exchanges: How many exchanges the file has.
        exchanges_added: How many of them were not in the database.
        exchanges_corrected: How many had another name or country there.
        mappings: How many pairs of exchange and provider code the file has.
        mappings_added: How many of them were not in the database.
    """

    exchanges: int
    exchanges_added: int
    exchanges_corrected: int
    mappings: int
    mappings_added: int


@dataclass(frozen=True, slots=True)
class ListOutcome:
    """What happened to the symbol list of one exchange code.

    Attributes:
        provider_exchange_code: The code.
        stored: The number of lines stored, or ``None`` when the list was not
            stored. Then the rows stored before, if any, are still there.
        not_stored: Why the list was not stored, or ``None`` when it was.
        detail: What a person needs to act on it: the labels, the symbols,
            the counts or the file. Empty for a stored list.
        lines: The number of lines of the saved list.
        not_shares: The lines whose type is not stored, counted by type.
        without_symbol: The share lines that carry no symbol.
        without_currency: The share lines that carry no currency.
        left_out: The share lines whose venue label is left out on purpose.
        without_isin: The lines to store that have no ISIN, or one that is
            not valid.
        invalid_isin: How many of those carried an ISIN that is not valid.
    """

    provider_exchange_code: str
    stored: int | None
    not_stored: NotStoredReason | None
    detail: str
    lines: int
    not_shares: Mapping[str, int]
    without_symbol: int
    without_currency: int
    left_out: int
    without_isin: int
    invalid_isin: int


@dataclass(frozen=True, slots=True)
class SymbolsLoad:
    """The outcome of one ``pyvalue symbols load``.

    Attributes:
        tables: What was done to the three exchange tables.
        lists: One outcome per exchange code that has a market, in the order
            of the provider's exchange file.
    """

    tables: ExchangeTables
    lists: tuple[ListOutcome, ...]

    @property
    def stored(self) -> tuple[ListOutcome, ...]:
        """The lists that were stored."""
        return tuple(outcome for outcome in self.lists if outcome.stored is not None)

    @property
    def not_stored(self) -> tuple[ListOutcome, ...]:
        """The lists that were not stored."""
        return tuple(outcome for outcome in self.lists if outcome.stored is None)

    @property
    def lines_stored(self) -> int:
        """How many lines were stored in all."""
        return sum(outcome.stored or 0 for outcome in self.lists)


@dataclass(frozen=True, slots=True)
class PreparedList:
    """One saved list, taken apart: what to store and what stands in the way.

    Attributes:
        symbols: The rows to store, in the order of the list.
        lines: The number of lines of the list.
        not_shares: The lines whose type is not stored, counted by type.
        without_symbol: The share lines that carry no symbol.
        without_currency: The share lines that carry no currency.
        left_out: The share lines whose venue label is left out on purpose.
        without_isin: The rows to store that have no ISIN.
        invalid_isin: How many of those carried an ISIN that is not valid.
        unknown_labels: The venue labels the exchange file does not have,
            each with its number of share lines. Not empty means the list
            is not stored.
        repeated: The symbols that appear more than once among the lines to
            store. Not empty means the list is not stored.
    """

    symbols: tuple[ProviderSymbol, ...]
    lines: int
    not_shares: Mapping[str, int]
    without_symbol: int
    without_currency: int
    left_out: int
    without_isin: int
    invalid_isin: int
    unknown_labels: Mapping[str, int]
    repeated: tuple[str, ...]

    def outcome(
        self,
        provider_exchange_code: str,
        stored: int | None,
        not_stored: NotStoredReason | None = None,
        detail: str = "",
    ) -> ListOutcome:
        """Return the outcome of this list, with its counts."""
        return ListOutcome(
            provider_exchange_code=provider_exchange_code,
            stored=stored,
            not_stored=not_stored,
            detail=detail,
            lines=self.lines,
            not_shares=self.not_shares,
            without_symbol=self.without_symbol,
            without_currency=self.without_currency,
            left_out=self.left_out,
            without_isin=self.without_isin,
            invalid_isin=self.invalid_isin,
        )


def _not_read(provider_exchange_code: str, reason: NotStoredReason, detail: str) -> ListOutcome:
    """Return the outcome of a list of which no line could be read."""
    return ListOutcome(
        provider_exchange_code=provider_exchange_code,
        stored=None,
        not_stored=reason,
        detail=detail,
        lines=0,
        not_shares=MappingProxyType({}),
        without_symbol=0,
        without_currency=0,
        left_out=0,
        without_isin=0,
        invalid_isin=0,
    )


def _fill_exchange_tables(
    work: UnitOfWork, exchanges: Sequence[Exchange], codes: ExchangeCodes
) -> ExchangeTables:
    """Add what is missing in the three exchange tables and correct what differs.

    Args:
        work: The unit of work to write in.
        exchanges: Our exchanges, from the committed file.
        codes: The provider's exchange file.

    Raises:
        ListingsError: If the database holds an exchange or a mapping the
            files do not have. Nothing has been written then.
    """
    wanted_exchanges = {exchange.mic: exchange for exchange in exchanges}
    wanted_mappings = set(codes.markets())
    stored_exchanges = {exchange.mic: exchange for exchange in work.exchanges.all()}
    stored_mappings = {
        (mapping.mic, mapping.provider_exchange_code)
        for mapping in work.provider_exchanges.of_provider(PROVIDER_CODE)
    }

    # Everything that would have to be deleted is found before anything is
    # written, so a refused database is left exactly as it was.
    extra_mappings = sorted(stored_mappings - wanted_mappings)
    if extra_mappings:
        named = ", ".join(f"{code} for {mic}" for mic, code in extra_mappings)
        raise ListingsError(
            f"the database holds {PROVIDER_NAME} exchange codes that the provider's exchange "
            f"file no longer has: {named}. {_REBUILD}"
        )
    extra_exchanges = sorted(set(stored_exchanges) - set(wanted_exchanges))
    if extra_exchanges:
        raise ListingsError(
            f"the database holds exchanges that the exchanges file no longer has: "
            f"{', '.join(extra_exchanges)}. {_REBUILD}"
        )

    added = corrected = 0
    for exchange in exchanges:
        stored = stored_exchanges.get(exchange.mic)
        if stored == exchange:
            continue
        work.exchanges.save(exchange)
        if stored is None:
            added += 1
        else:
            corrected += 1
    work.providers.save(Provider(provider_code=PROVIDER_CODE, name=PROVIDER_NAME))
    new_mappings = [pair for pair in codes.markets() if pair not in stored_mappings]
    for mic, code in new_mappings:
        work.provider_exchanges.add(
            ProviderExchange(provider_code=PROVIDER_CODE, mic=mic, provider_exchange_code=code)
        )
    return ExchangeTables(
        exchanges=len(exchanges),
        exchanges_added=added,
        exchanges_corrected=corrected,
        mappings=len(wanted_mappings),
        mappings_added=len(new_mappings),
    )


def prepare_list(
    provider_exchange_code: str, lines: Sequence[SymbolLine], codes: ExchangeCodes
) -> PreparedList:
    """Take a list apart: the rows to store, and what stands in the way of storing it.

    Each line meets the checks in the order of ADR 0024: is it a share, has it
    a symbol and a currency, is its venue label left out, is its label known.

    Args:
        provider_exchange_code: The code whose list this is.
        lines: The lines of the saved list.
        codes: The provider's exchange file.
    """
    symbols: list[ProviderSymbol] = []
    not_shares: Counter[str] = Counter()
    unknown_labels: Counter[str] = Counter()
    seen: set[str] = set()
    repeated: dict[str, None] = {}
    without_symbol = without_currency = left_out = without_isin = invalid_isin = 0
    for line in lines:
        if line.kind not in _SHARE_TYPES:
            not_shares[line.kind or _NO_TYPE] += 1
            continue
        if line.symbol is None:
            without_symbol += 1
            continue
        if line.currency is None:
            without_currency += 1
            continue
        market = codes.market_of(provider_exchange_code, line.venue)
        if market is VenueStatus.LEFT_OUT:
            left_out += 1
            continue
        if isinstance(market, VenueStatus):
            # Unknown. The whole list will not be stored; the labels are
            # collected so that all of them can be named at once.
            unknown_labels[line.venue or _NO_LABEL] += 1
            continue
        if line.symbol in seen:
            repeated.setdefault(line.symbol)
            continue
        seen.add(line.symbol)
        # The provider's ISIN is a claim. One that is not a valid ISIN could
        # never equal a security's, so it is stored as none (ADR 0018).
        isin = line.isin if line.isin is not None and is_valid_isin(line.isin) else None
        if isin is None:
            without_isin += 1
            if line.isin is not None:
                invalid_isin += 1
        symbols.append(
            ProviderSymbol(
                provider_code=PROVIDER_CODE,
                provider_exchange_code=provider_exchange_code,
                provider_symbol=line.symbol,
                mic=market,
                provider_venue=line.venue,
                provider_name=line.name,
                provider_type=line.kind,
                provider_currency=line.currency,
                isin=isin,
            )
        )
    return PreparedList(
        symbols=tuple(symbols),
        lines=len(lines),
        not_shares=MappingProxyType(dict(sorted(not_shares.items()))),
        without_symbol=without_symbol,
        without_currency=without_currency,
        left_out=left_out,
        without_isin=without_isin,
        invalid_isin=invalid_isin,
        unknown_labels=MappingProxyType(dict(sorted(unknown_labels.items()))),
        repeated=tuple(repeated),
    )


def _named(items: Sequence[str]) -> str:
    """Name the first few items and count the rest."""
    shown = ", ".join(items[:_NAMED_AT_MOST])
    rest = len(items) - _NAMED_AT_MOST
    return shown if rest <= 0 else f"{shown} and {rest} more"


def _store_list(
    database: Database, lists_dir: Path, provider_exchange_code: str, codes: ExchangeCodes
) -> ListOutcome:
    """Store the saved symbol list of one exchange code, or say why not.

    Args:
        database: The database to write.
        lists_dir: Where the saved lists are.
        provider_exchange_code: The code whose list is stored.
        codes: The provider's exchange file.

    Returns:
        What happened. When the list was not stored, the rows stored before
        are untouched.
    """
    code = provider_exchange_code
    path = lists_dir / symbol_list_file(code)
    if not path.is_file():
        return _not_read(code, NotStoredReason.NO_SAVED_LIST, f"{path} is not there")
    try:
        lines = parse_symbol_list(path.read_bytes(), str(path))
    except OSError as error:
        return _not_read(code, NotStoredReason.NOT_A_LIST, f"cannot read {path}: {error}")
    except ProviderError as error:
        return _not_read(code, NotStoredReason.NOT_A_LIST, str(error))

    prepared = prepare_list(code, lines, codes)
    if prepared.unknown_labels:
        labels = ", ".join(
            f"{label} ({count:,} lines)" for label, count in prepared.unknown_labels.items()
        )
        return prepared.outcome(code, None, NotStoredReason.UNKNOWN_LABELS, labels)
    if prepared.repeated:
        return prepared.outcome(
            code, None, NotStoredReason.REPEATED_SYMBOLS, _named(prepared.repeated)
        )

    # One transaction per list: it is replaced as a whole or not at all, and a
    # list that is not stored does not undo the ones before it. Every row has
    # passed the checks above, which are the table's own rules; should the
    # schema still refuse one, the error leaves this list as it was stored
    # and ends the load.
    with database.unit_of_work() as work:
        stored = work.provider_symbols.count_of_code(PROVIDER_CODE, code)
        if suspiciously_short(len(prepared.symbols), stored):
            return prepared.outcome(
                code,
                None,
                NotStoredReason.SUSPICIOUSLY_SHORT,
                f"{len(prepared.symbols):,} lines to store against {stored:,} stored",
            )
        work.provider_symbols.remove_of_code(PROVIDER_CODE, code)
        for symbol in prepared.symbols:
            work.provider_symbols.add(symbol)
    return prepared.outcome(code, len(prepared.symbols))


def load_symbols(
    database: Database,
    lists_dir: Path = DEFAULT_LISTS_DIR,
    exchanges: Sequence[Exchange] | None = None,
    codes: ExchangeCodes | None = None,
) -> SymbolsLoad:
    """Fill the exchange tables from the committed files and store the saved lists.

    Running it again with the same files changes nothing.

    Args:
        database: The database to write. It must be at the latest schema
            version.
        lists_dir: Where the downloaded lists are kept.
        exchanges: Our exchanges. Defaults to the file shipped with pyvalue.
        codes: The provider's exchange file. Defaults to the one shipped with
            pyvalue.

    Returns:
        What was done to the tables, and one outcome per exchange code.

    Raises:
        ListingsError: If the two files disagree, or the database holds an
            exchange or a mapping the files no longer have. Nothing is
            written then.
        ProviderError: If the provider's exchange file is not valid.
        DatabaseError: If the database is missing or not at the latest
            schema version, or refuses a row that passed every check here.
    """
    ours = packaged_exchanges() if exchanges is None else exchanges
    theirs = packaged_exchange_codes(EXCHANGE_FILE) if codes is None else codes
    require_our_exchanges(theirs, ours)

    with database.unit_of_work() as work:
        tables = _fill_exchange_tables(work, ours, theirs)
    lists = tuple(
        _store_list(database, lists_dir, code, theirs) for code in theirs.codes_with_a_market()
    )
    return SymbolsLoad(tables=tables, lists=lists)
