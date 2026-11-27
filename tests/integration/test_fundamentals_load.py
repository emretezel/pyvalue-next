"""End to end: from the sample filings to the statement tables and their report.

The commands run one after the other in a temporary folder: ``db migrate``,
``universe load``, ``symbols load``, ``listings fill`` and then
``fundamentals load`` (ADR 0029, ADR 0030). The payloads are the samples of
``tests/fixtures/eodhd_fundamentals``, saved where the download keeps them;
each company has one or two planted defects, and
``expected/findings.csv`` is the report they give, byte for byte.

No request leaves the test: the load never reaches the network.

Author: Emre Tezel
"""

import shutil
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.fundamentals.saved_payloads import pack, payload_file
from pyvalue.universe import FUNDS

pytestmark = pytest.mark.integration

# What the command prints after the database line, for the sample data.
_PRINTED: list[str] = [
    "Payloads folder: data/eodhd/fundamentals",
    "Companies with a listing at EODHD: 5",
    "  With statements stored: 4",
    "Reporting periods: 14",
    "  Income statements: 10",
    "  Cash-flow statements: 10",
    "  Balance sheets: 13",
    "Findings: 20",
    "  Left out: 11",
    "    off_chain: 1",
    "    length_not_proven: 8",
    "    currencies_differ: 1",
    "    scale_outlier: 1",
    "  A figure left empty: 2",
    "    impossible_negative: 1",
    "    zero_interest_with_debt: 1",
    "  Stored with a warning: 7",
    "    gross_profit_mismatch: 1",
    "    sub_unit_label: 1",
    "    stale_payload: 1",
    "    other_isin: 1",
    "    payloads_disagree: 2",
    "    no_payload: 1",
    "The findings are listed in data/fundamentals/findings.csv",
]


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    nport_samples: Path,
    vanguard_samples: Path,
    listings_samples: Path,
    fundamentals_samples: Path,
) -> Path:
    """Return a temporary working folder after the listing fill and the download.

    The filings, Vanguard's files and the symbol lists are where the commands
    look for them, the four commands before the load have run, and each
    sample payload is saved under the name the download gives it.
    """
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    for folder in ("sec", "vanguard", "eodhd"):
        (data / folder).mkdir(parents=True)
    for fund in FUNDS:
        shutil.copyfile(nport_samples / f"{fund.code}.xml", data / "sec" / fund.filing_file_name)
        shutil.copyfile(
            vanguard_samples / f"{fund.code}.json", data / "vanguard" / f"{fund.code}.json"
        )
    for sample in sorted(listings_samples.glob("symbols_*.json")):
        shutil.copyfile(sample, data / "eodhd" / sample.name)
    for sample in sorted(fundamentals_samples.glob("*.json")):
        code, symbol = sample.stem.split("_", 1)
        saved = data / "eodhd" / "fundamentals" / payload_file(code, symbol)
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(pack(sample.read_bytes()))
    for command in (["db", "migrate"], ["universe", "load"], ["symbols", "load"]):
        assert main(command) == 0
    assert main(["listings", "fill"]) == 0
    return tmp_path


def test_the_sample_payloads_give_the_expected_tables_and_report(
    workspace: Path, fundamentals_samples: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every planted defect is found once, and the counts say what was stored."""
    capsys.readouterr()

    assert main(["fundamentals", "load"]) == 0

    report = workspace / "data" / "fundamentals" / "findings.csv"
    expected = fundamentals_samples / "expected" / "findings.csv"
    assert report.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
    printed = capsys.readouterr().out.splitlines()
    assert printed[1:] == _PRINTED


def test_a_second_load_gives_the_same_report_and_the_same_counts(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproducible: the tables are replaced, not added to."""
    report = workspace / "data" / "fundamentals" / "findings.csv"
    assert main(["fundamentals", "load"]) == 0
    first = report.read_bytes()
    printed = capsys.readouterr().out

    assert main(["fundamentals", "load"]) == 0

    assert report.read_bytes() == first
    assert capsys.readouterr().out == printed


def test_the_load_never_changes_a_saved_payload(workspace: Path) -> None:
    """The payloads are the only copy outside a subscription (ADR 0028)."""
    payloads = workspace / "data" / "eodhd" / "fundamentals"
    before = {path: path.read_bytes() for path in payloads.rglob("*.json.gz")}

    assert main(["fundamentals", "load"]) == 0

    assert {path: path.read_bytes() for path in payloads.rglob("*.json.gz")} == before
