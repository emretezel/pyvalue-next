"""Validity of the two identifiers a holdings line carries.

The database checks the shape of an ISIN and of a legal-entity identifier
(ADR 0001, ADR 0003). The load is stricter: both standards end in check digits,
and a filing value that fails them is a typing error or a placeholder, not an
identifier (ADR 0009). Whatever passes here also passes the database's checks;
a test pins that.

Author: Emre Tezel
"""

import re

# ISO 6166: a two-letter prefix, nine letters or digits, one check digit.
_ISIN_SHAPE: re.Pattern[str] = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")

# ISO 17442: eighteen letters or digits, two check digits.
_LEI_SHAPE: re.Pattern[str] = re.compile(r"[A-Z0-9]{18}[0-9]{2}")


def _as_digits(text: str) -> str:
    """Write each letter as its two-digit number: A is 10, B is 11, up to Z is 35.

    Both standards compute their check digits on this all-digit form. Base 36
    gives exactly that numbering, and leaves a digit as it is.
    """
    return "".join(str(int(character, 36)) for character in text)


def is_valid_isin(text: str) -> bool:
    """Say whether ``text`` is an ISIN with a correct check digit.

    Args:
        text: The value as a filing gives it.

    Returns:
        True when the text has the ISO 6166 shape and its last digit is the
        one the standard computes from the eleven characters before it.
    """
    if _ISIN_SHAPE.fullmatch(text) is None:
        return False
    # The Luhn formula: from the right, every second digit is doubled, and a
    # doubled digit above 9 counts as the sum of its two digits (which equals
    # subtracting 9). A valid number sums to a multiple of ten.
    total = 0
    for position, character in enumerate(reversed(_as_digits(text))):
        digit = int(character)
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def is_valid_lei(text: str) -> bool:
    """Say whether ``text`` is a legal-entity identifier with correct check digits.

    Args:
        text: The value as a filing gives it. Filings write ``N/A`` when the
            issuer has no identifier.

    Returns:
        True when the text has the ISO 17442 shape and its last two digits are
        the ones the standard computes from the eighteen characters before
        them (ISO 7064, MOD 97-10: the scheme bank account numbers also use).
    """
    if _LEI_SHAPE.fullmatch(text) is None:
        return False
    # The standard sets the check digits to 98 minus a remainder of 0 to 96,
    # so they lie between 02 and 98. The remainder test alone would also pass
    # 00, 01 and 99 (each is 97 away from a real pair), which no issued
    # identifier ends in.
    if not 2 <= int(text[18:]) <= 98:
        return False
    # Read as one number, with letters written as digits, a valid identifier
    # leaves the remainder 1 when divided by 97.
    return int(_as_digits(text)) % 97 == 1
