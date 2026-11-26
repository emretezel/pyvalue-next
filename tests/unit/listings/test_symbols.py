"""Tests for ``pyvalue.listings.symbols``: the symbols load of ADR 0024.

They run on the made-up sample lists of ``tests/fixtures/eodhd`` (see the
README there for what each line shows). No test reaches the network: the load
only reads files.

Author: Emre Tezel
"""

import json
from pathlib import Path

import pytest

from pyvalue.db import Database, Exchange, Provider, ProviderExchange, ProviderSymbol
from pyvalue.listings import ListingsError, NotStoredReason, SymbolsLoad, load_symbols
from pyvalue.listings.symbols import prepare_list
from pyvalue.providers import ExchangeCodes, read_exchange_codes
from pyvalue.providers.eodhd import SymbolLine, parse_symbol_list

_CODES_HEADER: str = "provider_exchange_code,provider_venue,mic\n"


def _load(
    database: Database, lists_dir: Path, exchanges: tuple[Exchange, ...], codes: ExchangeCodes
) -> SymbolsLoad:
    """Run the load on the sample files."""
    return load_symbols(database, lists_dir, exchanges, codes)


def _stored(database: Database, code: str) -> int:
    """Return how many lines are stored under one EODHD code."""
    with database.unit_of_work() as work:
        return work.provider_symbols.count_of_code("eodhd", code)


def _line(entry: dict[str, object]) -> dict[str, object]:
    """Return a full sample line with some values replaced."""
    return {
        "Code": "NEW",
        "Name": "New Corp",
        "Country": "USA",
        "Exchange": "NYSE",
        "Currency": "USD",
        "Type": "Common Stock",
        "Isin": None,
        **entry,
    }


def _append(lists_dir: Path, code: str, *entries: dict[str, object]) -> None:
    """Add lines to a saved sample list."""
    path = lists_dir / f"symbols_{code}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document.extend(_line(entry) for entry in entries)
    path.write_text(json.dumps(document), encoding="utf-8")


def _many(count: int, prefix: str = "S") -> list[dict[str, object]]:
    """Return that many distinct valid Korean lines."""
    return [
        _line({"Code": f"{prefix}{number:05d}", "Exchange": "KO", "Currency": "KRW"})
        for number in range(count)
    ]


# --- Taking a list apart -----------------------------------------------------------------------


def test_the_us_sample_list_gives_four_rows_on_two_exchanges(
    eodhd_samples: Path, sample_codes: ExchangeCodes
) -> None:
    """The label on a line picks the exchange; what is not a share is left out."""
    path = eodhd_samples / "symbols_US.json"
    prepared = prepare_list("US", parse_symbol_list(path.read_bytes(), str(path)), sample_codes)

    # The label picked the exchange and the type let the line in; neither is
    # part of the row (ADR 0025).
    assert prepared.symbols == (
        ProviderSymbol("eodhd", "US", "ALFA", "XNYS", "Alpha Corp", "USD", "US00000A0014"),
        ProviderSymbol("eodhd", "US", "BETA-B", "XNAS", "Beta Inc Class B", "USD", "US00000B0021"),
        # An empty ISIN is no ISIN; AMEX is a second label for New York.
        ProviderSymbol("eodhd", "US", "DLTA", "XNYS", "Delta Ltd", "USD", None),
        # A preferred share is stored like a common one.
        ProviderSymbol("eodhd", "US", "ZETA-P", "XNYS", "Zeta Corp Pref", "USD", "US00000F0068"),
    )
    assert prepared.lines == 8
    assert dict(prepared.not_shares) == {"ETF": 1, "FUND": 1}
    assert (prepared.without_symbol, prepared.without_currency, prepared.left_out) == (1, 0, 1)
    assert (prepared.without_isin, prepared.invalid_isin) == (1, 0)
    assert dict(prepared.unknown_labels) == {}
    assert prepared.repeated == ()


def test_an_isin_that_is_not_valid_is_stored_as_none(
    eodhd_samples: Path, sample_codes: ExchangeCodes
) -> None:
    """The Korean sample has one line without an ISIN and one with an ISIN cut short."""
    path = eodhd_samples / "symbols_KO.json"
    prepared = prepare_list("KO", parse_symbol_list(path.read_bytes(), str(path)), sample_codes)

    assert [(row.provider_symbol, row.isin) for row in prepared.symbols] == [
        ("000100", "KR7000100008"),
        ("000105", "KR7000101006"),
        ("000200", None),
        ("000400", None),
    ]
    assert (prepared.without_isin, prepared.invalid_isin) == (2, 1)


def test_an_isin_with_a_wrong_check_digit_is_not_valid(sample_codes: ExchangeCodes) -> None:
    """It has the right shape, and could still never equal a security's ISIN."""
    line = SymbolLine("000100", "Alpha", "KO", "KRW", "Common Stock", "KR7000100009")

    prepared = prepare_list("KO", (line,), sample_codes)

    assert prepared.symbols[0].isin is None
    assert prepared.invalid_isin == 1


def test_a_currency_code_is_stored_as_the_provider_gives_it(
    eodhd_samples: Path, sample_codes: ExchangeCodes
) -> None:
    """A sub-unit and a code we do not know are for the listing rule (ADR 0019)."""
    path = eodhd_samples / "symbols_LSE.json"
    prepared = prepare_list("LSE", parse_symbol_list(path.read_bytes(), str(path)), sample_codes)

    assert [(row.provider_symbol, row.provider_currency) for row in prepared.symbols] == [
        ("ALP", "GBX"),
        ("0A1B", "USD"),
        ("GAM", "Unknown"),
        ("EPS", "GBP"),
    ]
    # DEL has no currency at all, which the table cannot hold.
    assert prepared.without_currency == 1


def test_a_type_in_another_spelling_is_counted_under_that_spelling(
    sample_codes: ExchangeCodes,
) -> None:
    """So a spelling EODHD starts to use is seen in the report, not silently dropped."""
    lines = (
        SymbolLine("A", "A Corp", "KO", "KRW", "common stock", None),
        SymbolLine("B", "B Corp", "KO", "KRW", "Common Stock", None),
        SymbolLine("C", "C Corp", "KO", "KRW", None, None),
    )

    prepared = prepare_list("KO", lines, sample_codes)

    assert [row.provider_symbol for row in prepared.symbols] == ["B"]
    assert dict(prepared.not_shares) == {"(no type)": 1, "common stock": 1}


def test_unknown_labels_are_collected_on_share_lines_only(sample_codes: ExchangeCodes) -> None:
    """A fund under an unknown label does not matter; a share without any label does."""
    lines = (
        SymbolLine("A", "A Corp", "BATS", "USD", "Common Stock", None),
        SymbolLine("B", "B Corp", "BATS", "USD", "Common Stock", None),
        SymbolLine("C", "C Corp", None, "USD", "Common Stock", None),
        SymbolLine("D", "D Fund", "NYSE ARCA", "USD", "ETF", None),
        SymbolLine("E", "E Corp", "NYSE", "USD", "Common Stock", None),
    )

    prepared = prepare_list("US", lines, sample_codes)

    assert dict(prepared.unknown_labels) == {"(no label)": 1, "BATS": 2}


def test_a_symbol_twice_among_the_lines_to_store_is_named_once(
    sample_codes: ExchangeCodes,
) -> None:
    """A repeat among lines that are not stored anyway is no concern."""
    lines = (
        SymbolLine("A", "A Corp", "NYSE", "USD", "Common Stock", None),
        SymbolLine("A", "A Corp again", "NASDAQ", "USD", "Common Stock", None),
        SymbolLine("A", "A Corp a third time", "NYSE", "USD", "Common Stock", None),
        SymbolLine("B", "B Fund", "NYSE", "USD", "ETF", None),
        SymbolLine("B", "B Fund again", "NYSE", "USD", "ETF", None),
    )

    prepared = prepare_list("US", lines, sample_codes)

    assert prepared.repeated == ("A",)


# --- The exchange tables -----------------------------------------------------------------------


def test_the_load_fills_the_three_exchange_tables(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """Five exchanges, the provider, and one mapping per pair of exchange and code."""
    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    tables = outcome.tables
    assert (tables.exchanges, tables.exchanges_added, tables.exchanges_corrected) == (5, 5, 0)
    assert (tables.mappings, tables.mappings_added) == (5, 5)
    with database.unit_of_work() as work:
        assert work.exchanges.all() == sample_exchanges
        assert work.provider_exchanges.of_provider("eodhd") == (
            ProviderExchange("eodhd", "XKRX", "KO"),
            ProviderExchange("eodhd", "XLON", "LSE"),
            ProviderExchange("eodhd", "XNAS", "US"),
            ProviderExchange("eodhd", "XNYS", "US"),
            ProviderExchange("eodhd", "XWAR", "WAR"),
        )


def test_a_second_load_adds_and_corrects_nothing(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """Running it again with the same files changes nothing."""
    first = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    second = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    assert (second.tables.exchanges_added, second.tables.exchanges_corrected) == (0, 0)
    assert second.tables.mappings_added == 0
    assert second.lists == first.lists
    assert [_stored(database, code) for code in ("KO", "LSE", "US")] == [4, 4, 4]


def test_a_changed_name_in_the_file_corrects_the_row(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """The row is corrected in place, and the lists stored on it stay."""
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    renamed = tuple(
        Exchange(exchange.mic, "KRX", exchange.country) if exchange.mic == "XKRX" else exchange
        for exchange in sample_exchanges
    )

    outcome = _load(database, eodhd_lists_dir, renamed, sample_codes)

    assert (outcome.tables.exchanges_added, outcome.tables.exchanges_corrected) == (0, 1)
    with database.unit_of_work() as work:
        assert Exchange("XKRX", "KRX", "KR") in work.exchanges.all()
    assert _stored(database, "KO") == 4


def test_a_new_exchange_and_code_in_the_files_are_added(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
    tmp_path: Path,
) -> None:
    """The files grow when a provider adds a market; the load follows."""
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    more_exchanges = (*sample_exchanges, Exchange("XKOS", "KOSDAQ", "KR"))
    path = tmp_path / "codes.csv"
    path.write_text(
        _CODES_HEADER
        + "".join(
            f"{row.provider_exchange_code},{row.provider_venue or ''},{row.mic or ''}\n"
            for row in sample_codes.rows
        )
        + "KQ,,XKOS\n",
        encoding="utf-8",
    )

    outcome = _load(database, eodhd_lists_dir, more_exchanges, read_exchange_codes(path))

    assert (outcome.tables.exchanges_added, outcome.tables.mappings_added) == (1, 1)
    assert outcome.lists[-1].provider_exchange_code == "KQ"
    assert outcome.lists[-1].not_stored is NotStoredReason.NO_SAVED_LIST


def test_a_database_with_an_exchange_the_file_no_longer_has_is_refused(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """The load deletes nothing, so it says that a rebuild is needed (ADR 0024)."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange("XJPX", "Japan Exchange Group", "JP"))

    with pytest.raises(ListingsError, match="exchanges file no longer has: XJPX. .* rebuilt"):
        _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    # Nothing was written: the refusal comes before the first change.
    with database.unit_of_work() as work:
        assert [exchange.mic for exchange in work.exchanges.all()] == ["XJPX"]
    assert _stored(database, "KO") == 0


def test_a_database_with_a_code_the_file_no_longer_has_is_refused(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """A code that was corrected in the file shows up as one the file no longer has."""
    with database.unit_of_work() as work:
        work.exchanges.save(Exchange("XKRX", "Korea Exchange", "KR"))
        work.providers.save(Provider("eodhd", "EODHD"))
        work.provider_exchanges.add(ProviderExchange("eodhd", "XKRX", "KOSPI"))

    with pytest.raises(
        ListingsError, match="exchange file no longer has: KOSPI for XKRX. .* rebuilt"
    ):
        _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    with database.unit_of_work() as work:
        assert work.provider_exchanges.of_provider("eodhd") == (
            ProviderExchange("eodhd", "XKRX", "KOSPI"),
        )


def test_the_two_files_are_checked_against_each_other_first(
    database: Database, eodhd_lists_dir: Path, sample_codes: ExchangeCodes
) -> None:
    """A provider file that names an exchange we do not have stops the load at once."""
    only_korea = (Exchange("XKRX", "Korea Exchange", "KR"),)

    with pytest.raises(ListingsError, match="does not have: XLON, XNAS, XNYS, XWAR"):
        _load(database, eodhd_lists_dir, only_korea, sample_codes)

    with database.unit_of_work() as work:
        assert work.exchanges.all() == ()


# --- The lists ---------------------------------------------------------------------------------


def test_the_load_stores_each_saved_list_and_reports_the_one_that_is_missing(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """One outcome per code that has a market, in the order of the provider's file."""
    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    assert [(each.provider_exchange_code, each.stored) for each in outcome.lists] == [
        ("KO", 4),
        ("LSE", 4),
        ("US", 4),
        ("WAR", None),
    ]
    assert outcome.lines_stored == 12
    assert [each.provider_exchange_code for each in outcome.stored] == ["KO", "LSE", "US"]
    (missing,) = outcome.not_stored
    assert missing.not_stored is NotStoredReason.NO_SAVED_LIST
    assert missing.detail.endswith("symbols_WAR.json is not there")
    assert [_stored(database, code) for code in ("KO", "LSE", "US", "WAR")] == [4, 4, 4, 0]


def test_a_stored_list_carries_the_counts_of_what_was_left_out(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """The counts of the US sample: see tests/fixtures/eodhd/README.md."""
    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    us = outcome.lists[2]
    assert (us.lines, us.stored, us.not_stored, us.detail) == (8, 4, None, "")
    assert dict(us.not_shares) == {"ETF": 1, "FUND": 1}
    assert (us.without_symbol, us.without_currency, us.left_out) == (1, 0, 1)
    assert (us.without_isin, us.invalid_isin) == (1, 0)


def test_a_list_is_replaced_as_a_whole(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """A line that left the list leaves the table; a new one arrives."""
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    (eodhd_lists_dir / "symbols_KO.json").write_text(
        json.dumps(_many(3, prefix="N")), encoding="utf-8"
    )

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    assert outcome.lists[0].stored == 3
    assert _stored(database, "KO") == 3
    # The other lists were stored again, unchanged.
    assert [_stored(database, code) for code in ("LSE", "US")] == [4, 4]


def test_a_label_the_file_does_not_have_stops_that_list_and_no_other(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """Every unknown label is named at once, and the stored rows stay (ADR 0024)."""
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    _append(
        eodhd_lists_dir,
        "US",
        {"Code": "NEW1", "Exchange": "BATS"},
        {"Code": "NEW2", "Exchange": "BATS"},
        {"Code": "NEW3", "Exchange": ""},
    )

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    us = outcome.lists[2]
    assert (us.stored, us.not_stored) == (None, NotStoredReason.UNKNOWN_LABELS)
    assert us.detail == "(no label) (1 lines), BATS (2 lines)"
    assert [each.stored for each in outcome.lists[:2]] == [4, 4]
    # The four rows of the earlier load are still there.
    assert _stored(database, "US") == 4


def test_a_list_with_a_symbol_twice_is_not_stored(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """Which of the two lines is right is not something the load can know."""
    _append(eodhd_lists_dir, "US", {"Code": "ALFA", "Exchange": "NASDAQ"})

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    us = outcome.lists[2]
    assert (us.stored, us.not_stored, us.detail) == (None, NotStoredReason.REPEATED_SYMBOLS, "ALFA")
    assert _stored(database, "US") == 0


def test_many_repeated_symbols_are_named_up_to_ten(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """The report stays one line however many there are."""
    lines = _many(12)
    (eodhd_lists_dir / "symbols_KO.json").write_text(json.dumps(lines + lines), encoding="utf-8")

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    assert outcome.lists[0].not_stored is NotStoredReason.REPEATED_SYMBOLS
    assert outcome.lists[0].detail.endswith("S00009 and 2 more")


def test_a_list_that_is_suspiciously_short_does_not_replace_the_stored_one(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """A stub answer for a dropped exchange must not empty the table (ADR 0018)."""
    path = eodhd_lists_dir / "symbols_KO.json"
    path.write_text(json.dumps(_many(60)), encoding="utf-8")
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    path.write_text(json.dumps(_many(29)), encoding="utf-8")

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    korea = outcome.lists[0]
    assert (korea.stored, korea.not_stored) == (None, NotStoredReason.SUSPICIOUSLY_SHORT)
    assert korea.detail == "29 lines to store against 60 stored"
    assert _stored(database, "KO") == 60


def test_a_list_that_shrank_a_little_replaces_the_stored_one(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
) -> None:
    """Companies do leave an exchange."""
    path = eodhd_lists_dir / "symbols_KO.json"
    path.write_text(json.dumps(_many(60)), encoding="utf-8")
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    path.write_text(json.dumps(_many(31)), encoding="utf-8")

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    assert outcome.lists[0].stored == 31
    assert _stored(database, "KO") == 31


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        pytest.param(b"Unauthorized", "is not an EODHD symbol list", id="an error text"),
        pytest.param(b'{"error": "x"}', "it is not a list", id="an object"),
        pytest.param(b'[{"Code": "A"}]', "entry 1 has no field Name", id="another shape"),
    ],
)
def test_a_saved_file_that_is_not_a_symbol_list_is_reported_and_nothing_is_replaced(
    database: Database,
    eodhd_lists_dir: Path,
    sample_exchanges: tuple[Exchange, ...],
    sample_codes: ExchangeCodes,
    content: bytes,
    detail: str,
) -> None:
    """The stored rows of that code stay, and the other lists are stored."""
    _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)
    (eodhd_lists_dir / "symbols_KO.json").write_bytes(content)

    outcome = _load(database, eodhd_lists_dir, sample_exchanges, sample_codes)

    korea = outcome.lists[0]
    assert (korea.stored, korea.not_stored) == (None, NotStoredReason.NOT_A_LIST)
    assert detail in korea.detail
    assert "symbols_KO.json" in korea.detail
    assert _stored(database, "KO") == 4
    assert [each.stored for each in outcome.lists[1:3]] == [4, 4]


def test_the_load_works_with_the_shipped_files_and_no_saved_list(
    database: Database, tmp_path: Path
) -> None:
    """A checkout before the first download: the tables are filled, every list is missing."""
    outcome = load_symbols(database, tmp_path / "eodhd")

    assert outcome.tables.exchanges == outcome.tables.exchanges_added == 61
    assert outcome.tables.mappings == outcome.tables.mappings_added == 61
    assert len(outcome.lists) == 59
    assert {each.not_stored for each in outcome.lists} == {NotStoredReason.NO_SAVED_LIST}
    assert outcome.lines_stored == 0
