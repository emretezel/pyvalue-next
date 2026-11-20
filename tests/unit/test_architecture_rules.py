"""Tests that pin the structural rules of ``docs/architecture.md``.

These rules are easy to state and easy to break without noticing, so they are
checked on every run instead of being left to review.

Author: Emre Tezel
"""

import ast
import sqlite3
from pathlib import Path

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
