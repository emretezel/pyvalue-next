"""Smoke test for the installed pyvalue package.

Author: Emre Tezel
"""

import tomllib
from pathlib import Path

import pyvalue

# Repository root: tests/unit/test_package.py -> tests/unit -> tests -> root.
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def test_installed_version_matches_this_checkout() -> None:
    """The importable ``pyvalue`` is this checkout, not the legacy project.

    The legacy project installs a package with the same name at version 0.1.0.
    If the wrong conda environment is active, or the editable install is stale,
    the version the import reports differs from the one declared in this
    checkout's ``pyproject.toml``.
    """
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        declared = tomllib.load(handle)["project"]["version"]

    # TOML values are untyped; narrow before comparing so a non-string version
    # fails here with a clear message instead of a confusing inequality.
    assert isinstance(declared, str)
    assert pyvalue.__version__ == declared
