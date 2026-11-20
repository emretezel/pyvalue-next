"""Tests that pin the structural rules of ``docs/architecture.md``.

These rules are easy to state and easy to break without noticing, so they are
checked on every run instead of being left to review.

Author: Emre Tezel
"""

import ast
import sqlite3
from pathlib import Path

import pyvalue.db
from pyvalue.db.repository import Repository

# Repository root: tests/unit/test_architecture_rules.py -> tests/unit -> tests -> root.
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_SOURCE: Path = _REPO_ROOT / "src" / "pyvalue"
_DATABASE_PACKAGE: Path = _SOURCE / "db"
_TABLE_DOCS: Path = _REPO_ROOT / "docs" / "database"


def _imports_sqlite3(module: Path) -> bool:
    """Say whether a module imports ``sqlite3`` in any form."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "sqlite3" for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlite3":
            return True
    return False


def test_only_the_database_package_imports_sqlite3() -> None:
    """One home for database access: every other package calls ``pyvalue.db``."""
    offenders = [
        str(module.relative_to(_REPO_ROOT))
        for module in sorted(_SOURCE.rglob("*.py"))
        if _DATABASE_PACKAGE not in module.parents and _imports_sqlite3(module)
    ]

    assert offenders == [], f"sqlite3 is imported outside pyvalue.db: {offenders}"


def test_the_import_check_can_see_an_import() -> None:
    """Guard the guard: the database package itself must be reported as importing sqlite3."""
    assert _imports_sqlite3(_DATABASE_PACKAGE / "connection.py")


def test_every_table_has_a_documentation_file(migrated_db: sqlite3.Connection) -> None:
    """``docs/database/`` holds one file per table of the current schema."""
    tables = [
        str(name)
        for (name,) in migrated_db.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]

    missing = [table for table in tables if not (_TABLE_DOCS / f"{table}.md").is_file()]
    assert missing == [], f"tables without a file under docs/database/: {missing}"


def test_no_documentation_file_describes_a_table_that_is_gone(
    migrated_db: sqlite3.Connection,
) -> None:
    """A dropped or renamed table must not leave its old file behind."""
    tables = {
        str(name)
        for (name,) in migrated_db.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }

    # README.md is the folder's overview, not a table.
    stale = sorted(
        file.stem
        for file in _TABLE_DOCS.glob("*.md")
        if file.name != "README.md" and file.stem not in tables
    )
    assert stale == [], f"files under docs/database/ for tables that do not exist: {stale}"


def test_every_view_is_documented_with_a_table_it_reads(migrated_db: sqlite3.Connection) -> None:
    """A view has no file of its own; it is described in the files of its tables."""
    views = [
        str(name)
        for (name,) in migrated_db.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'view' ORDER BY name"
        )
    ]
    documentation = "\n".join(
        file.read_text(encoding="utf-8") for file in sorted(_TABLE_DOCS.glob("*.md"))
    )

    missing = [view for view in views if f"`{view}`" not in documentation]
    assert missing == [], f"views not mentioned under docs/database/: {missing}"


def _inner_database_imports(module: Path) -> list[str]:
    """Return the modules inside ``pyvalue.db`` that a module imports by name."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if alias.name.startswith("pyvalue.db."))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pyvalue.db."):
            found.append(node.module or "")
    return found


def test_other_packages_enter_the_database_package_through_its_front_door() -> None:
    """One door: outside ``pyvalue.db``, only the names the package exports are imported."""
    offenders = {
        str(module.relative_to(_REPO_ROOT)): _inner_database_imports(module)
        for module in sorted(_SOURCE.rglob("*.py"))
        if _DATABASE_PACKAGE not in module.parents and _inner_database_imports(module)
    }

    assert offenders == {}, f"modules inside pyvalue.db are imported from outside: {offenders}"


def test_the_front_door_check_can_see_an_inner_import() -> None:
    """Guard the guard: inside the package, modules do import each other by name."""
    assert _inner_database_imports(_DATABASE_PACKAGE / "unit_of_work.py")


def test_the_database_package_hands_out_no_connection() -> None:
    """A component never sees a connection (ADR 0008), so ``connect`` is not exported."""
    assert "connect" not in pyvalue.db.__all__
    assert "Database" in pyvalue.db.__all__


def test_every_repository_owns_one_existing_table(migrated_db: sqlite3.Connection) -> None:
    """One repository class per table (ADR 0008): no table has two, none is made up."""
    tables = {
        str(name)
        for (name,) in migrated_db.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    # Importing pyvalue.db has defined every repository class there is.
    owned = sorted(repository.table for repository in Repository.__subclasses__())

    assert owned, "no repository class was found"
    assert set(owned) <= tables, f"repositories for tables that do not exist: {owned}"
    assert len(owned) == len(set(owned)), f"a table has two repository classes: {owned}"


def test_a_repository_is_named_after_its_table() -> None:
    """The class for ``provider_listing`` would be ``ProviderListingRepository``."""
    for repository in Repository.__subclasses__():
        expected = "".join(part.capitalize() for part in repository.table.split("_")) + "Repository"

        assert repository.__name__ == expected
