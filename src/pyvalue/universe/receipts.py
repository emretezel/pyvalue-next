"""Recognise a depositary receipt among holdings lines.

A depositary receipt (an ADR, a GDR) is a certificate for a company's shares,
traded on a foreign market. pyvalue analyses the company through its own
shares, so the load needs to know which lines are receipts (ADR 0006).

The filing form has no field for it. One sponsor labels its receipts in the
conditional category, another files them as ordinary common shares, so the
check reads the label and falls back on wording: in the filing's title and
issuer name, and in the name the sponsor's own holdings file gives the
security. The last one matters for Vanguard, whose filing cuts a title at 16
characters, just where "ADR" would stand (ADR 0020).

Author: Emre Tezel
"""

import re

from pyvalue.universe.holdings import HoldingLine
from pyvalue.universe.nport import CONDITIONAL_CATEGORY

# The labels Dimensional gives its receipts in the conditional category. The
# same category also holds units, rights and cash, which are not receipts.
RECEIPT_LABELS: frozenset[str] = frozenset({"ADR", "GDR", "DEPOSITORY RECEIPT"})

# Words that mark a receipt in a security title, an issuer name or a sponsor's
# own name for the security. Each must stand as a whole word: "ADR" marks a
# receipt, "ADRIATIC" does not. The list can grow without a new decision
# record (ADR 0006).
_RECEIPT_WORDING: re.Pattern[str] = re.compile(
    r"\b(?:"
    r"ADR|ADRS|ADS|GDR|GDRS|NVDR|BDR|CDI|SDR|EDR"
    r"|DEPOSITARY (?:RECEIPTS?|SHARES?|INTERESTS?)"
    r"|DEPOSITORY (?:RECEIPTS?|SHARES?|INTERESTS?)"
    r"|DEP(?:\.|OSITARY)? ?RCPT"
    r"|SPONSORED|SPON|SPN"
    r")\b",
    re.IGNORECASE,
)


def is_receipt(line: HoldingLine) -> bool:
    """Say whether a holdings line is a depositary receipt.

    Args:
        line: One line of a filing.

    Returns:
        True when the filer labelled the line as a receipt, or its title, its
        issuer name or the sponsor's own name for the security contains one
        of the receipt words.
    """
    labelled = line.category == CONDITIONAL_CATEGORY and line.category_label in RECEIPT_LABELS
    wordings = (line.title, line.issuer_name, line.sponsor_name or "")
    return labelled or any(_RECEIPT_WORDING.search(text) is not None for text in wordings)
