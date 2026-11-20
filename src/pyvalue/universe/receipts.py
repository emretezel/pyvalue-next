"""Recognise a depositary receipt among holdings lines.

A depositary receipt (an ADR, a GDR) is a certificate for a company's shares,
traded on a foreign market. pyvalue analyses the company through its own
shares, so the load needs to know which lines are receipts (ADR 0006).

The filing form has no field for it. One sponsor labels its receipts in the
conditional category, the other files them as ordinary common shares, so the
check reads the label and falls back on wording.

Author: Emre Tezel
"""

import re

from pyvalue.universe.nport import CONDITIONAL_CATEGORY, HoldingLine

# The labels Dimensional gives its receipts in the conditional category. The
# same category also holds units, rights and cash, which are not receipts.
RECEIPT_LABELS: frozenset[str] = frozenset({"ADR", "GDR", "DEPOSITORY RECEIPT"})

# Words that mark a receipt in a security title or an issuer name. Each must
# stand as a whole word: "ADR" marks a receipt, "ADRIATIC" does not. The list
# can grow without a new decision record (ADR 0006).
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
        True when the filer labelled the line as a receipt, or its title or
        its issuer name contains one of the receipt words.
    """
    labelled = line.category == CONDITIONAL_CATEGORY and line.category_label in RECEIPT_LABELS
    return (
        labelled
        or _RECEIPT_WORDING.search(line.title) is not None
        or _RECEIPT_WORDING.search(line.issuer_name) is not None
    )
