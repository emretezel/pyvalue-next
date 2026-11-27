"""Fundamentals: a provider's payloads for the listings, kept as files.

The component downloads the fundamentals of every provider line a listing is
on and keeps each answer as one compressed file (ADR 0028). It reads the
database to know the listings and writes nothing to it. Reading the payloads
into tables is not built yet.

Author: Emre Tezel
"""

from pyvalue.fundamentals.download import (
    FundamentalsDownload,
    Line,
    LineOutcome,
    Status,
    Stop,
    download_fundamentals,
)
from pyvalue.fundamentals.errors import FundamentalsError
from pyvalue.fundamentals.report import DEFAULT_REPORT_DIR
from pyvalue.fundamentals.saved_payloads import DEFAULT_PAYLOADS_DIR, payload_file

__all__ = [
    "DEFAULT_PAYLOADS_DIR",
    "DEFAULT_REPORT_DIR",
    "FundamentalsDownload",
    "FundamentalsError",
    "Line",
    "LineOutcome",
    "Status",
    "Stop",
    "download_fundamentals",
    "payload_file",
]
