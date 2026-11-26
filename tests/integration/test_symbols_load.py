"""End to end: the exchange files and the sample EODHD lists into the database.

The load runs through the command, on the files shipped with pyvalue and the
made-up sample lists of ``tests/fixtures/eodhd``, and what it stored is read
back through a unit of work. No request is made: the load only reads files.

Author: Emre Tezel
"""

import shutil
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.db import Database, Exchange, ProviderExchange
from pyvalue.listings import packaged_exchanges

pytestmark = pytest.mark.integration


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eodhd_samples: Path) -> Path:
    """Return a temporary working folder with a migrated database and the saved sample lists."""
    monkeypatch.chdir(tmp_path)
    assert main(["db", "migrate"]) == 0
    lists = tmp_path / "data" / "eodhd"
    lists.mkdir()
    for sample in sorted(eodhd_samples.glob("*.json")):
        shutil.copyfile(sample, lists / sample.name)
    return tmp_path


def _counts(database: Database) -> dict[str, int]:
    """Return the number of stored lines under each code that has a saved list."""
    with database.unit_of_work() as work:
        return {
            code: work.provider_symbols.count_of_code("eodhd", code)
            for code in ("KO", "LSE", "US", "XETRA")
        }


def test_the_load_fills_the_exchange_tables_and_stores_the_saved_lists(workspace: Path) -> None:
    """From an empty database to our exchanges, EODHD's codes and twelve symbol lines."""
    database = Database(workspace / "data" / "pyvalue.db")

    assert main(["symbols", "load"]) == 0

    with database.unit_of_work() as work:
        exchanges = work.exchanges.all()
        mappings = work.provider_exchanges.of_provider("eodhd")
    assert exchanges == tuple(sorted(packaged_exchanges(), key=lambda exchange: exchange.mic))
    assert Exchange("XETR", "Xetra", "DE") in exchanges
    # EODHD's US covers three of our exchanges, and KOSDAQ is not KOSPI.
    assert [mapping.mic for mapping in mappings if mapping.provider_exchange_code == "US"] == [
        "XCBO",
        "XNAS",
        "XNYS",
    ]
    assert ProviderExchange("eodhd", "XKOS", "KQ") in mappings
    assert ProviderExchange("eodhd", "XKRX", "KO") in mappings
    assert len(mappings) == 61
    assert _counts(database) == {"KO": 4, "LSE": 4, "US": 4, "XETRA": 0}


def test_the_same_files_give_the_same_database_and_the_same_report(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproducible: a second run stores the same rows and prints the same lines."""
    database = Database(workspace / "data" / "pyvalue.db")
    capsys.readouterr()

    assert main(["symbols", "load"]) == 0
    first_report = capsys.readouterr().out
    first_counts = _counts(database)
    assert main(["symbols", "load"]) == 0
    second_report = capsys.readouterr().out

    assert _counts(database) == first_counts
    # Only the two lines that say what was added differ.
    assert first_report.splitlines()[3:] == second_report.splitlines()[3:]


def test_a_refreshed_list_replaces_the_stored_one_and_leaves_the_others(workspace: Path) -> None:
    """What a later download changes in one file changes that list only."""
    database = Database(workspace / "data" / "pyvalue.db")
    assert main(["symbols", "load"]) == 0
    korea = workspace / "data" / "eodhd" / "symbols_KO.json"
    korea.write_text(
        '[{"Code": "000500", "Name": "Epsilon Steel Co Ltd", "Country": "Korea", '
        '"Exchange": "KO", "Currency": "KRW", "Type": "Common Stock", "Isin": null}]',
        encoding="utf-8",
    )

    assert main(["symbols", "load"]) == 0

    assert _counts(database) == {"KO": 1, "LSE": 4, "US": 4, "XETRA": 0}


def test_the_symbols_load_leaves_the_universe_tables_alone(workspace: Path) -> None:
    """It writes four tables and no other."""
    database = Database(workspace / "data" / "pyvalue.db")

    assert main(["symbols", "load"]) == 0

    with database.unit_of_work() as work:
        assert work.companies.all() == ()
        assert work.instruments.all() == ()
        assert work.funds.all() == ()
        assert work.holdings.all() == ()
