"""Tests for ``pyvalue.listings.download``: the symbols download of ADR 0024.

No test reaches the network: each passes a stand-in that answers a request
from the made-up sample lists of ``tests/fixtures/eodhd`` and records what
was asked. The requests themselves are tested in ``tests/unit/test_http.py``.

Author: Emre Tezel
"""

import json
from pathlib import Path

import pytest

from pyvalue.listings import DownloadStatus, ListingsError, SymbolsDownload, download_symbols
from pyvalue.providers import ExchangeCodes, ProviderError
from pyvalue.providers.eodhd import ListNotFoundError, exchange_list_url, symbol_list_url

# Stands in for an API key.
_KEY: str = "sample-api-key-0123456789"


class _Provider:
    """Stands in for EODHD: answers a request from prepared bodies, and records it."""

    def __init__(self, samples: Path) -> None:
        """Prepare the answers of the sample lists."""
        self.answers: dict[str, bytes | Exception] = {
            exchange_list_url(): (samples / "exchanges.json").read_bytes(),
            **{
                symbol_list_url(code): (samples / f"symbols_{code}.json").read_bytes()
                for code in ("KO", "LSE", "US")
            },
        }
        self.requests: list[tuple[str, str]] = []

    def fetch(self, url: str, api_key: str) -> bytes:
        """Answer one request, or fail as prepared."""
        self.requests.append((url, api_key))
        answer = self.answers.get(url)
        if answer is None:
            pytest.fail(f"{url} was requested and no answer is prepared for it")
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def addresses(self) -> list[str]:
        """The addresses that were requested, in order."""
        return [url for url, _ in self.requests]


@pytest.fixture
def provider(eodhd_samples: Path) -> _Provider:
    """Return a stand-in for EODHD that serves the sample lists."""
    return _Provider(eodhd_samples)


def _lines(count: int) -> bytes:
    """Return a symbol list of that many valid lines."""
    return json.dumps(
        [
            {
                "Code": f"S{number:05d}",
                "Name": "Sample Co",
                "Country": "Korea",
                "Exchange": "KO",
                "Currency": "KRW",
                "Type": "Common Stock",
                "Isin": None,
            }
            for number in range(count)
        ]
    ).encode()


def _download(provider: _Provider, lists_dir: Path, codes: ExchangeCodes) -> SymbolsDownload:
    """Run the download against the stand-in."""
    return download_symbols(_KEY, lists_dir, codes, provider.fetch)


def test_the_exchange_list_and_the_list_of_every_offered_code_are_saved(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes, eodhd_samples: Path
) -> None:
    """Each answer is kept as it arrived, under the name of its code."""
    lists = tmp_path / "eodhd"

    outcome = _download(provider, lists, sample_codes)

    assert sorted(path.name for path in lists.iterdir()) == [
        "exchanges.json",
        "symbols_KO.json",
        "symbols_LSE.json",
        "symbols_US.json",
    ]
    for name in ("exchanges.json", "symbols_KO.json", "symbols_LSE.json", "symbols_US.json"):
        assert (lists / name).read_bytes() == (eodhd_samples / name).read_bytes()
    assert [(each.provider_exchange_code, each.status, each.lines) for each in outcome.lists] == [
        ("KO", DownloadStatus.SAVED, 5),
        ("LSE", DownloadStatus.SAVED, 5),
        ("US", DownloadStatus.SAVED, 8),
        ("WAR", DownloadStatus.NOT_OFFERED, None),
    ]


def test_the_exchange_list_is_asked_first_and_then_one_list_per_code(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """A code that is left out, or that EODHD no longer offers, is not requested."""
    _download(provider, tmp_path / "eodhd", sample_codes)

    assert provider.addresses == [
        exchange_list_url(),
        symbol_list_url("KO"),
        symbol_list_url("LSE"),
        symbol_list_url("US"),
    ]
    # The key goes to the fetch with every request, and the address carries none.
    assert {api_key for _, api_key in provider.requests} == {_KEY}
    assert all(_KEY not in url for url in provider.addresses)


def test_what_the_provider_offers_is_compared_with_the_file(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """A new market is named; a code left out on purpose is not (ADR 0024)."""
    outcome = _download(provider, tmp_path / "eodhd", sample_codes)

    assert outcome.offered == ("KO", "US", "LSE", "F", "CC", "HK")
    # F and CC are offered too, and the file leaves them out on purpose.
    assert outcome.offered_not_in_file == ("HK",)
    assert [
        each.provider_exchange_code for each in outcome.with_status(DownloadStatus.NOT_OFFERED)
    ] == ["WAR"]


def test_the_key_is_in_no_saved_file_and_no_file_name(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """What is kept is the provider's answer, under the name of its code."""
    lists = tmp_path / "eodhd"

    _download(provider, lists, sample_codes)

    for path in lists.iterdir():
        assert _KEY not in path.name
        assert _KEY.encode() not in path.read_bytes()


def test_a_later_download_replaces_a_saved_list(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """Refreshing is the same command."""
    lists = tmp_path / "eodhd"
    _download(provider, lists, sample_codes)
    provider.answers[symbol_list_url("KO")] = _lines(7)

    outcome = _download(provider, lists, sample_codes)

    korea = outcome.lists[0]
    assert (korea.status, korea.lines, korea.saved_before) == (DownloadStatus.SAVED, 7, 5)
    assert (lists / "symbols_KO.json").read_bytes() == _lines(7)


def test_an_answer_that_is_suspiciously_short_does_not_replace_the_saved_list(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """A stub must not overwrite the only good copy; the other lists are still saved."""
    lists = tmp_path / "eodhd"
    provider.answers[symbol_list_url("KO")] = _lines(60)
    _download(provider, lists, sample_codes)
    provider.answers[symbol_list_url("KO")] = _lines(29)

    outcome = _download(provider, lists, sample_codes)

    korea = outcome.lists[0]
    assert (korea.status, korea.lines, korea.saved_before) == (
        DownloadStatus.REFUSED_AS_SHORT,
        29,
        60,
    )
    assert (lists / "symbols_KO.json").read_bytes() == _lines(60)
    assert [each.status for each in outcome.lists[1:3]] == [DownloadStatus.SAVED] * 2


def test_a_saved_file_that_is_not_a_list_protects_nothing(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes, eodhd_samples: Path
) -> None:
    """A file that cannot be read as a symbol list is replaced by any answer that can."""
    lists = tmp_path / "eodhd"
    lists.mkdir()
    (lists / "symbols_KO.json").write_bytes(b"x" * 10_000)

    outcome = _download(provider, lists, sample_codes)

    assert (outcome.lists[0].status, outcome.lists[0].saved_before) == (DownloadStatus.SAVED, None)
    assert (lists / "symbols_KO.json").read_bytes() == (
        eodhd_samples / "symbols_KO.json"
    ).read_bytes()


def test_a_list_that_is_not_in_the_subscription_is_reported_and_the_rest_goes_on(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """EODHD answers "not found" for an exchange outside the plan."""
    lists = tmp_path / "eodhd"
    provider.answers[symbol_list_url("LSE")] = ListNotFoundError("cannot download: not found")

    outcome = _download(provider, lists, sample_codes)

    assert [(each.provider_exchange_code, each.status) for each in outcome.lists] == [
        ("KO", DownloadStatus.SAVED),
        ("LSE", DownloadStatus.NOT_IN_SUBSCRIPTION),
        ("US", DownloadStatus.SAVED),
        ("WAR", DownloadStatus.NOT_OFFERED),
    ]
    assert not (lists / "symbols_LSE.json").exists()


def test_any_other_failure_stops_the_run_and_keeps_what_was_saved(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """A key that is not accepted would fail every request, so the run ends at the first."""
    lists = tmp_path / "eodhd"
    provider.answers[symbol_list_url("LSE")] = ProviderError("cannot download: HTTP Error 401")

    with pytest.raises(ProviderError, match="HTTP Error 401"):
        _download(provider, lists, sample_codes)

    assert provider.addresses[-1] == symbol_list_url("LSE")
    assert (lists / "symbols_KO.json").is_file()
    assert not (lists / "symbols_US.json").exists()


def test_a_refused_exchange_list_stops_the_run_before_any_symbol_list(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """Nothing is requested after the first failure, and nothing is saved."""
    lists = tmp_path / "eodhd"
    provider.answers[exchange_list_url()] = ProviderError("cannot download: HTTP Error 401")

    with pytest.raises(ProviderError, match="HTTP Error 401"):
        _download(provider, lists, sample_codes)

    assert provider.addresses == [exchange_list_url()]
    assert not lists.exists()


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(b'{"error": "Unauthorized"}', id="an error object"),
        pytest.param(b"Too many requests", id="a text"),
        pytest.param(b'[{"Code": "A"}]', id="another shape"),
    ],
)
def test_an_answer_that_is_not_a_symbol_list_is_not_kept(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes, answer: bytes
) -> None:
    """The run stops, the saved list stays, and the message names the address without a key."""
    lists = tmp_path / "eodhd"
    _download(provider, lists, sample_codes)
    before = (lists / "symbols_KO.json").read_bytes()
    provider.answers[symbol_list_url("KO")] = answer

    with pytest.raises(ProviderError, match="is not an EODHD symbol list") as raised:
        _download(provider, lists, sample_codes)

    assert symbol_list_url("KO") in str(raised.value)
    assert _KEY not in str(raised.value)
    assert (lists / "symbols_KO.json").read_bytes() == before
    assert not list(lists.glob("*.part"))


def test_an_answer_that_is_not_an_exchange_list_is_not_kept(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """An error answered with a success status must not be read as "nothing is offered"."""
    lists = tmp_path / "eodhd"
    provider.answers[exchange_list_url()] = b'"Unauthorized"'

    with pytest.raises(ProviderError, match="is not an EODHD exchange list"):
        _download(provider, lists, sample_codes)

    assert not lists.exists()


def test_a_folder_that_cannot_be_written_is_reported(
    provider: _Provider, tmp_path: Path, sample_codes: ExchangeCodes
) -> None:
    """The message names the file, and the temporary file does not stay."""
    blocker = tmp_path / "eodhd"
    blocker.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(ListingsError, match="cannot save .*exchanges.json"):
        _download(provider, blocker, sample_codes)


def test_the_shipped_exchange_file_is_used_when_none_is_given(
    provider: _Provider, tmp_path: Path
) -> None:
    """With the real file, the three sample codes are offered and 56 are not."""
    outcome = download_symbols(_KEY, tmp_path / "eodhd", fetch=provider.fetch)

    assert len(outcome.lists) == 59
    assert len(outcome.with_status(DownloadStatus.SAVED)) == 3
    assert len(outcome.with_status(DownloadStatus.NOT_OFFERED)) == 56
    # Hong Kong is not in the shipped file: the download would say so.
    assert outcome.offered_not_in_file == ("HK",)
