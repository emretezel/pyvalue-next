"""The ``holding`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Holding:
    """One row of ``holding``: one share line of a fund's loaded filing (ADR 0017).

    The row records what the fund's documents say about the line. The one
    thing in it that pyvalue decided is ``instrument_id``.

    Attributes:
        fund_code: The fund that reports the line.
        line_number: The line's position in the filing, counted from 1.
        instrument_id: The security the line was loaded as, or ``None`` when
            the line was not loaded.
        not_loaded_reason: Why the line was not loaded; ``None`` exactly when
            ``instrument_id`` is set.
        isin: The ISIN as filed. It differs from the instrument's ISIN for a
            depositary receipt read as its ordinary share (ADR 0015).
        issuer_name: The issuer's name as filed.
        title: The security's title, or ``None`` when the filing gives none.
        lei: The issuer's legal-entity identifier, or ``None`` when the
            filing gives none or a placeholder.
        cusip: The US security number, or ``None`` likewise.
        sedol: The London Stock Exchange's security number from the sponsor's
            own file, or ``None`` when none was attached (ADR 0016).
        ticker: The ticker as the sponsor writes it, or ``None`` likewise.
        asset_category: The form's asset category: ``EC``, ``EP``, ``STIV``
            or ``OTHER``.
        asset_category_label: The filer's own label for the ``OTHER``
            category, such as ``ADR``; ``None`` otherwise.
        issuer_type: The form's issuer type, such as ``CORP``.
        trading_country: The ISO 3166 code of the country the line trades in.
        currency: The ISO 4217 code of the currency the fund holds the line in.
    """

    fund_code: str
    line_number: int
    instrument_id: int | None
    not_loaded_reason: str | None
    isin: str
    issuer_name: str
    title: str | None
    lei: str | None
    cusip: str | None
    sedol: str | None
    ticker: str | None
    asset_category: str
    asset_category_label: str | None
    issuer_type: str
    trading_country: str
    currency: str


def _text(value: str | int | None) -> str | None:
    """Return an optional text column as ``str`` or ``None``."""
    return None if value is None else str(value)


class HoldingRepository(Repository):
    """Every statement that reads or changes ``holding``."""

    table: ClassVar[str] = "holding"

    def all(self) -> tuple[Holding, ...]:
        """Return every holding line, by fund and then in the order of its filing."""
        rows = self._execute(
            "SELECT fund_code, line_number, instrument_id, not_loaded_reason, isin, issuer_name, "
            "title, lei, cusip, sedol, ticker, asset_category, asset_category_label, issuer_type, "
            "trading_country, currency FROM holding ORDER BY fund_code, line_number"
        ).fetchall()
        return tuple(
            Holding(
                fund_code=str(fund_code),
                line_number=int(line_number),
                instrument_id=None if instrument_id is None else int(instrument_id),
                not_loaded_reason=_text(not_loaded_reason),
                isin=str(isin),
                issuer_name=str(issuer_name),
                title=_text(title),
                lei=_text(lei),
                cusip=_text(cusip),
                sedol=_text(sedol),
                ticker=_text(ticker),
                asset_category=str(asset_category),
                asset_category_label=_text(asset_category_label),
                issuer_type=str(issuer_type),
                trading_country=str(trading_country),
                currency=str(currency),
            )
            for (
                fund_code,
                line_number,
                instrument_id,
                not_loaded_reason,
                isin,
                issuer_name,
                title,
                lei,
                cusip,
                sedol,
                ticker,
                asset_category,
                asset_category_label,
                issuer_type,
                trading_country,
                currency,
            ) in rows
        )

    def add(self, holding: Holding) -> None:
        """Add one holding line.

        Args:
            holding: The line as it should be stored.

        Raises:
            ConstraintError: If a value has the wrong shape, the fund or the
                instrument does not exist, the fund already has a line with
                this number, or the line both names an instrument and gives a
                reason for not being loaded (or does neither).
        """
        self._execute(
            "INSERT INTO holding (fund_code, line_number, instrument_id, not_loaded_reason, isin, "
            "issuer_name, title, lei, cusip, sedol, ticker, asset_category, asset_category_label, "
            "issuer_type, trading_country, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                holding.fund_code,
                holding.line_number,
                holding.instrument_id,
                holding.not_loaded_reason,
                holding.isin,
                holding.issuer_name,
                holding.title,
                holding.lei,
                holding.cusip,
                holding.sedol,
                holding.ticker,
                holding.asset_category,
                holding.asset_category_label,
                holding.issuer_type,
                holding.trading_country,
                holding.currency,
            ),
        )

    def remove_of_fund(self, fund_code: str) -> None:
        """Remove every holding line of one fund.

        A fund's lines are a copy of one filing. When the filing is loaded
        again, or a newer one is loaded, the copy is replaced as a whole
        (ADR 0017). Removing the lines of a fund that has none is not an error.

        Args:
            fund_code: The fund whose lines are removed.
        """
        self._execute("DELETE FROM holding WHERE fund_code = ?", (fund_code,))
