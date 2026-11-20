"""The ``company`` table: its record and its repository.

Author: Emre Tezel
"""

from dataclasses import dataclass
from typing import ClassVar

from pyvalue.db.errors import DatabaseError
from pyvalue.db.repository import Repository


@dataclass(frozen=True, slots=True)
class Company:
    """One row of ``company``: a legal entity that issues securities.

    Attributes:
        company_id: The row's id.
        name: The company's name as it was first loaded.
        lei: The legal-entity identifier, or ``None`` when none is known.
    """

    company_id: int
    name: str
    lei: str | None


class CompanyRepository(Repository):
    """Every statement that reads or changes ``company``."""

    table: ClassVar[str] = "company"

    def all(self) -> tuple[Company, ...]:
        """Return every company, in the order the rows were added."""
        rows = self._execute(
            "SELECT company_id, name, lei FROM company ORDER BY company_id"
        ).fetchall()
        return tuple(
            Company(
                company_id=int(company_id),
                name=str(name),
                lei=None if lei is None else str(lei),
            )
            for company_id, name, lei in rows
        )

    def add(self, name: str, lei: str | None) -> Company:
        """Add a company.

        Args:
            name: The company's name: not empty, no surrounding spaces.
            lei: Its legal-entity identifier, or ``None``.

        Returns:
            The new row, with the id the database gave it.

        Raises:
            ConstraintError: If the name or the identifier has the wrong
                shape, or another company already has the identifier.
        """
        # RETURNING hands back the new id with the insert itself. Fetching the
        # one row also finishes the statement, which the commit needs.
        row = self._execute(
            "INSERT INTO company (name, lei) VALUES (?, ?) RETURNING company_id", (name, lei)
        ).fetchone()
        return Company(company_id=int(row[0]), name=name, lei=lei)

    def set_lei(self, company_id: int, lei: str) -> None:
        """Give a company its legal-entity identifier.

        Args:
            company_id: The company to change.
            lei: The identifier.

        Raises:
            ConstraintError: If the identifier has the wrong shape, or another
                company already has it.
            DatabaseError: If there is no company with this id.
        """
        cursor = self._execute("UPDATE company SET lei = ? WHERE company_id = ?", (lei, company_id))
        # An UPDATE that matches no row succeeds silently in SQL. Here it means
        # the caller holds an id that does not exist, which must not pass.
        if cursor.rowcount != 1:
            raise DatabaseError(f"there is no company with id {company_id}")
