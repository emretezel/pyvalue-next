"""Fundamentals: a provider's payloads for the listings, and the statements in them.

The component downloads the fundamentals of every provider line a listing is
on and keeps each answer as one compressed file (ADR 0028); the download
reads the database and writes nothing to it. The statements load then reads
the fiscal years of the saved payloads into the four statement tables,
checking every row, and writes what it found to a report (ADR 0029,
ADR 0030).

Author: Emre Tezel
"""

from pyvalue.fundamentals.checks import OUTCOME_OF, Check, Outcome
from pyvalue.fundamentals.download import (
    FundamentalsDownload,
    Line,
    LineOutcome,
    Status,
    Stop,
    download_fundamentals,
)
from pyvalue.fundamentals.errors import FundamentalsError
from pyvalue.fundamentals.load import StatementsLoad, load_statements
from pyvalue.fundamentals.report import DEFAULT_REPORT_DIR
from pyvalue.fundamentals.saved_payloads import DEFAULT_PAYLOADS_DIR, payload_file

__all__ = [
    "DEFAULT_PAYLOADS_DIR",
    "DEFAULT_REPORT_DIR",
    "OUTCOME_OF",
    "Check",
    "FundamentalsDownload",
    "FundamentalsError",
    "Line",
    "LineOutcome",
    "Outcome",
    "StatementsLoad",
    "Status",
    "Stop",
    "download_fundamentals",
    "load_statements",
    "payload_file",
]
