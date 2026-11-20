"""Tests for ``pyvalue.universe.lei_decisions``: reading the decisions file of ADR 0010.

Author: Emre Tezel
"""

from datetime import date
from pathlib import Path

import pytest

from pyvalue.universe import LeiDecision, UniverseError
from pyvalue.universe.identifiers import is_valid_isin, is_valid_lei
from pyvalue.universe.lei_decisions import packaged_lei_decisions, read_lei_decisions

_HEADER: str = "isin,lei,company,decided_on,evidence\n"
_GOOD_ROW: str = "DE00000T0019,549300THET2000000069,Theta AG,2026-11-20,The register says so\n"


def _write(tmp_path: Path, text: str) -> Path:
    """Write a decisions file into the temporary folder and return its path."""
    path = tmp_path / "lei.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_is_read_row_by_row(nport_samples: Path) -> None:
    """The sample file that goes with the sample filings."""
    decisions = read_lei_decisions(nport_samples / "decisions" / "lei.csv")

    assert decisions == (
        LeiDecision(
            isin="DE00000T0019",
            lei="549300THET2000000069",
            company="Theta AG",
            decided_on=date(2026, 11, 20),
            evidence=(
                "Made up: the identifier VXUS files is retired, and the one DFAX files is "
                "its successor"
            ),
        ),
        LeiDecision(
            isin="JP300000I006",
            lei="549300SIGMA000000049",
            company="Iota KK",
            decided_on=date(2026, 11, 20),
            evidence=(
                "Made up: DFAX files the identifier of Delta PLC by mistake; this one is Iota's own"
            ),
        ),
    )


def test_a_file_with_only_the_header_holds_no_decision(tmp_path: Path) -> None:
    """Before the first decision, the file is its header."""
    assert read_lei_decisions(_write(tmp_path, _HEADER)) == ()


def test_evidence_may_contain_commas_quotes_and_other_scripts(tmp_path: Path) -> None:
    """Evidence quotes names from a register, whatever they are written in."""
    path = _write(
        tmp_path,
        _HEADER + 'DE00000T0019,549300THET2000000069,"Theta, AG",2026-11-20,'
        '"The register names ""广东电力发展股份有限公司"", not the other one"\n',
    )

    (decision,) = read_lei_decisions(path)

    assert decision.company == "Theta, AG"
    assert decision.evidence == 'The register names "广东电力发展股份有限公司", not the other one'


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("", "the first row must be isin,lei,company,decided_on,evidence", id="empty"),
        pytest.param(_GOOD_ROW, "the first row must be", id="no header"),
        pytest.param(
            "isin,lei,company,decided_on\n", "the first row must be", id="a column missing"
        ),
        pytest.param(
            "lei,isin,company,decided_on,evidence\n", "the first row must be", id="columns swapped"
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000069,Theta AG,2026-11-20\n",
            "row 2 has 4 cells where 5 are expected",
            id="a cell missing",
        ),
        pytest.param(
            _HEADER + _GOOD_ROW + "\n",
            "row 3 has 0 cells where 5 are expected",
            id="an empty row",
        ),
        pytest.param(
            _HEADER + "DE00000T0018,549300THET2000000069,Theta AG,2026-11-20,Why\n",
            "row 2: 'DE00000T0018' is not a valid ISIN",
            id="ISIN with a wrong check digit",
        ),
        pytest.param(
            _HEADER + " DE00000T0019,549300THET2000000069,Theta AG,2026-11-20,Why\n",
            "row 2: ' DE00000T0019' is not a valid ISIN",
            id="ISIN with a leading space",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000068,Theta AG,2026-11-20,Why\n",
            "row 2: '549300THET2000000068' is not a valid legal-entity identifier",
            id="identifier with wrong check digits",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,N/A,Theta AG,2026-11-20,Why\n",
            "row 2: 'N/A' is not a valid legal-entity identifier",
            id="a placeholder as identifier",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000069,,2026-11-20,Why\n",
            "row 2: the company and the evidence must both be filled in",
            id="no company name",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000069,Theta AG,2026-11-20,  \n",
            "row 2: the company and the evidence must both be filled in",
            id="blank evidence",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000069,Theta AG,20 November 2026,Why\n",
            r"row 2: '20 November 2026' is not a date \(YYYY-MM-DD\)",
            id="unreadable date",
        ),
        pytest.param(
            _HEADER + "DE00000T0019,549300THET2000000069,Theta AG,2026-02-30,Why\n",
            "row 2: '2026-02-30' is not a date",
            id="a day that does not exist",
        ),
        pytest.param(
            _HEADER + _GOOD_ROW + "DE00000T0019,549300THETA000000051,Theta AG,2026-11-21,Why\n",
            "row 3: DE00000T0019 was already decided in row 2",
            id="the same security twice",
        ),
    ],
)
def test_a_bad_file_is_refused_with_the_row_that_is_wrong(
    tmp_path: Path, content: str, message: str
) -> None:
    """A file has no constraints, so the reader is the check (ADR 0010)."""
    path = _write(tmp_path, content)

    with pytest.raises(UniverseError, match=message) as raised:
        read_lei_decisions(path)

    assert str(path) in str(raised.value)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is reported in pyvalue's own words."""
    with pytest.raises(UniverseError, match="cannot read the decisions file"):
        read_lei_decisions(tmp_path / "absent.csv")


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 must not surface as a decoding traceback."""
    path = tmp_path / "lei.csv"
    path.write_bytes(b"isin,lei,company,decided_on,evidence\n\xff\xfe\x00broken\n")

    with pytest.raises(UniverseError, match="cannot read the decisions file"):
        read_lei_decisions(path)


def test_the_decisions_shipped_with_the_package_are_valid() -> None:
    """The real file is read with the same checks on every test run."""
    decisions = packaged_lei_decisions()

    assert decisions, "the shipped decisions file holds no decision"
    assert all(is_valid_isin(decision.isin) for decision in decisions)
    assert all(is_valid_lei(decision.lei) for decision in decisions)
    assert len({decision.isin for decision in decisions}) == len(decisions)


def test_the_shipped_file_decides_both_securities_of_a_company_alike() -> None:
    """ADR 0010: the A and the B share of Guangdong Electric Power have one issuer."""
    decided = {decision.isin: decision.lei for decision in packaged_lei_decisions()}

    assert decided["CNE0000006J0"] == decided["CNE000000HW5"]
