"""The universe load: the funds' SEC holdings filings into ``company`` and ``instrument``.

Which funds, and why, is ADR 0016. The rules of the load are ADR 0006. How it
is run, where its files go and what it leaves for an agent is ADR 0009. How a
decision on a company's legal-entity identifier is applied is ADR 0010, and
which identifier it may name is ADR 0011. How a decision on a company's name
is applied is ADR 0012, and how a security is kept out of the universe is
ADR 0013. How a depositary receipt is read as its ordinary share is ADR 0015.

Author: Emre Tezel
"""

from pyvalue.universe.errors import FilingError, SponsorFileError, UniverseError
from pyvalue.universe.exclusions import Exclusion
from pyvalue.universe.funds import FUNDS, FundDefinition, Scope, Sponsor
from pyvalue.universe.holdings import FundHoldings, HoldingLine, SponsorAdapter
from pyvalue.universe.lei_decisions import LeiDecision
from pyvalue.universe.load import (
    AgentCase,
    AgentCaseReason,
    LoadResult,
    NotLoadedLine,
    NotLoadedReason,
    load_holdings,
)
from pyvalue.universe.name_decisions import NameDecision
from pyvalue.universe.nport import FiledLine
from pyvalue.universe.ordinary_shares import OrdinaryShare
from pyvalue.universe.output import OutputFiles
from pyvalue.universe.pipeline import (
    DEFAULT_FILINGS_DIR,
    DEFAULT_OUTPUT_DIR,
    UniverseLoad,
    load_universe,
)
from pyvalue.universe.vanguard import DEFAULT_VANGUARD_DIR, VanguardAdapter

__all__ = [
    "DEFAULT_FILINGS_DIR",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_VANGUARD_DIR",
    "FUNDS",
    "AgentCase",
    "AgentCaseReason",
    "Exclusion",
    "FiledLine",
    "FilingError",
    "FundDefinition",
    "FundHoldings",
    "HoldingLine",
    "LeiDecision",
    "LoadResult",
    "NameDecision",
    "NotLoadedLine",
    "NotLoadedReason",
    "OrdinaryShare",
    "OutputFiles",
    "Scope",
    "Sponsor",
    "SponsorAdapter",
    "SponsorFileError",
    "UniverseError",
    "UniverseLoad",
    "VanguardAdapter",
    "load_holdings",
    "load_universe",
]
