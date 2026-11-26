"""Smoke test for the installed pyvalue package.

Author: Emre Tezel
"""

import tomllib
from fnmatch import fnmatch
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


def test_every_data_file_of_the_package_is_shipped() -> None:
    """A committed file the code reads at run time is named in ``package-data``.

    The migrations, the decision files and the exchange files are read from
    inside the installed package. A new folder of such files that is not
    named in ``pyproject.toml`` works in this checkout and is missing from an
    installed copy, where nothing would say so until the file is read.
    """
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        patterns = tomllib.load(handle)["tool"]["setuptools"]["package-data"]["pyvalue"]
    assert isinstance(patterns, list)
    package = _REPO_ROOT / "src" / "pyvalue"

    not_shipped = [
        path.relative_to(package).as_posix()
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and path.suffix not in {".py", ".pyc"}
        and not path.name.startswith(".")
        and not any(fnmatch(path.relative_to(package).as_posix(), str(each)) for each in patterns)
    ]

    assert not_shipped == []
