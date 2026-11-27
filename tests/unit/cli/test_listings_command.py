"""Tests for ``pyvalue listings fill``.

The command reads and writes under the folder it is run from, so every test
runs it in a temporary folder. What the fill itself does is tested in
``tests/unit/listings``, and the whole chain of commands on the sample
filings in ``tests/integration/test_listings_fill.py``; these tests are about
the command: its option, what it prints, and how it stops.

No test touches the network: the fill only reads the database.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.cli import main
from pyvalue.cli.app import _REASON_WORDS
from pyvalue.db import (
    Database,
    Exchange,
    Fund,
    Holding,
    Provider,
    ProviderExchange,
    ProviderSymbol,
)
from pyvalue.listings import Reason
from pyvalue.listings.decisions import ListingDecision

_HYNIX: str = "KR7000660001"
_SAMSUNG: str = "KR7005930003"
_NAVER: str = "KR7035420009"


def _seed(path: Path) -> None:
    """Fill a migrated database with one market, three securities and their lines.

    SK Hynix has one line with its ISIN and is filled by the rule. Samsung's
    line carries its ISIN under a symbol the fund's ticker does not equal.
    Naver's line has a currency code that cannot be read.
    """
    with Database(path).unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XKRX", name="Korea Exchange", country="KR"))
        work.providers.save(Provider(provider_code="eodhd", name="EODHD"))
        work.provider_exchanges.add(
            ProviderExchange(provider_code="eodhd", mic="XKRX", provider_exchange_code="KO")
        )
        work.funds.save(
            Fund(
                fund_code="VXUS",
                name="Sample Fund",
                scope="NON_US",
                sec_series_id="S000000001",
                sec_filing_number="0000000000-26-000001",
                holdings_date=date(2026, 7, 31),
                sponsor_file_date=None,
            )
        )
        for number, (isin, ticker, symbol, currency) in enumerate(
            (
                (_HYNIX, "000660", "000660", "KRW"),
                (_SAMSUNG, "SAMSUNG", "005930", "KRW"),
                (_NAVER, "035420", "035420", "Unknown"),
            ),
            start=1,
        ):
            company = work.companies.add(f"Company {number}", None)
            instrument = work.instruments.add(company.company_id, isin)
            work.holdings.add(
                Holding(
                    fund_code="VXUS",
                    line_number=number,
                    instrument_id=instrument.instrument_id,
                    isin=isin,
                    issuer_name=f"Company {number}",
                    title=None,
                    lei=None,
                    cusip=None,
                    sedol=None,
                    ticker=ticker,
                    asset_category="EC",
                    trading_country="KR",
                    currency="KRW",
                )
            )
            work.provider_symbols.add(
                ProviderSymbol(
                    provider_code="eodhd",
                    provider_exchange_code="KO",
                    provider_symbol=symbol,
                    mic="XKRX",
                    provider_name=None,
                    provider_currency=currency,
                    isin=isin,
                )
            )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a temporary working folder whose database holds the three sample securities.

    There is no ``private`` folder: the command needs no setting. The command
    reads no decision unless a test gives some (``_decide``): the file shipped
    with pyvalue holds decisions on real securities, which are no part of
    these tests.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pyvalue.listings.fill.packaged_listing_decisions", lambda: ())
    assert main(["db", "migrate"]) == 0
    _seed(tmp_path / "data" / "pyvalue.db")
    return tmp_path


def _decide(
    monkeypatch: pytest.MonkeyPatch, *decisions: tuple[str, tuple[str, str, str] | None]
) -> None:
    """Make the command read these decisions in place of the file shipped with pyvalue."""
    chosen = tuple(
        ListingDecision(
            isin=isin,
            line=line,
            company="Sample Co",
            decided_on=date(2026, 11, 26),
            decided_by="agent",
            evidence="made up",
        )
        for isin, line in decisions
    )
    monkeypatch.setattr("pyvalue.listings.fill.packaged_listing_decisions", lambda: chosen)


def _listed(path: Path) -> list[tuple[str, str]]:
    """Return the exchange and ticker of every listing in a database."""
    with Database(path).unit_of_work() as work:
        return [(each.mic, each.ticker) for each in work.listings.all()]


def test_the_command_fills_and_says_what_became_of_every_security(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line per outcome, and the reasons in words."""
    capsys.readouterr()

    assert main(["listings", "fill"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Database: data/pyvalue.db",
        "Securities: 3",
        "Already had a listing: 0",
        "Filled by the rule: 1 (1 with ISIN and ticker agreeing, 0 by ISIN with no fund ticker)",
        "Filled by a decision: 0",
        "Decided to have no listing: 0",
        "Not held by a fund: 0",
        "Market not served: 0",
        "Waiting for a symbol list: 0",
        "For the agent: 2, listed in data/listings/cases_for_agent.csv",
        "  1 one line has the ISIN, but in another currency",
        "  1 one line has the ISIN, but the ticker differs",
        "Stored lines whose currency code cannot be read: 1 (Unknown 1)",
        "Decisions for a security that is not in the universe: 0",
    ]
    assert _listed(workspace / "data" / "pyvalue.db") == [("XKRX", "000660")]
    assert (workspace / "data" / "listings" / "cases_for_agent.csv").is_file()


def test_the_command_says_what_the_decisions_did(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A line chosen, a security given none, and a decision for a security that is gone."""
    _decide(
        monkeypatch,
        (_SAMSUNG, ("eodhd", "KO", "005930")),
        (_HYNIX, None),
        ("KR7051910008", None),
    )
    capsys.readouterr()

    assert main(["listings", "fill"]) == 0

    printed = capsys.readouterr().out
    assert "Filled by the rule: 0 (" in printed
    assert "Filled by a decision: 1\n" in printed
    assert "Decided to have no listing: 1\n" in printed
    assert "For the agent: 1, " in printed
    assert "Decisions for a security that is not in the universe: 1 (KR7051910008)\n" in printed
    assert _listed(workspace / "data" / "pyvalue.db") == [("XKRX", "005930")]


def test_the_command_names_the_countries_and_codes_that_wait(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second exchange code for Korea without a list holds every Korean security back."""
    with Database(workspace / "data" / "pyvalue.db").unit_of_work() as work:
        work.exchanges.save(Exchange(mic="XKOS", name="KOSDAQ", country="KR"))
        work.provider_exchanges.add(
            ProviderExchange(provider_code="eodhd", mic="XKOS", provider_exchange_code="KQ")
        )
    capsys.readouterr()

    assert main(["listings", "fill"]) == 0

    printed = capsys.readouterr().out
    assert "Waiting for a symbol list: 3 (KR 3)\n" in printed
    assert "  Exchange codes without a stored list: KQ\n" in printed
    assert "For the agent: 0, " in printed
    assert _listed(workspace / "data" / "pyvalue.db") == []


def test_the_database_option_points_the_command_elsewhere(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default database is left alone."""
    elsewhere = workspace / "elsewhere.db"
    assert main(["db", "migrate", "--db", str(elsewhere)]) == 0
    _seed(elsewhere)
    capsys.readouterr()

    assert main(["listings", "fill", "--db", str(elsewhere)]) == 0

    assert capsys.readouterr().out.startswith(f"Database: {elsewhere}\n")
    assert _listed(elsewhere) == [("XKRX", "000660")]
    assert _listed(workspace / "data" / "pyvalue.db") == []


def test_a_listing_that_contradicts_a_decision_is_one_line_and_status_one(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No traceback: a rebuild is something a person does (ADR 0026)."""
    assert main(["listings", "fill"]) == 0
    _decide(monkeypatch, (_HYNIX, None))
    capsys.readouterr()

    assert main(["listings", "fill"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("pyvalue: error: 1 securities have a listing")
    assert _HYNIX in captured.err
    assert "`pyvalue listings fill`" in captured.err
    assert captured.err.count("\n") == 1
    assert _listed(workspace / "data" / "pyvalue.db") == [("XKRX", "000660")]


def test_a_missing_database_is_one_line_and_status_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command does not create a database: that is ``pyvalue db migrate``."""
    monkeypatch.chdir(tmp_path)

    assert main(["listings", "fill"]) == 1

    assert "there is no database at data/pyvalue.db" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_every_reason_of_the_report_has_words_for_the_screen() -> None:
    """A new reason without words would stop the command after it has written."""
    assert set(_REASON_WORDS) == set(Reason)
    assert len(set(_REASON_WORDS.values())) == len(Reason)
