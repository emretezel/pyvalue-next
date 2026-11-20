"""pyvalue: a value-investing toolkit.

The package will provide a curated global stock universe, data-quality checks
on fundamental data, and quality-at-a-reasonable-price screening. The
components built so far are described in ``docs/architecture.md``. This module
exposes only the package version.

Author: Emre Tezel
"""

from importlib.metadata import version

# The version is declared once, in ``pyproject.toml``. Reading it back from the
# installed metadata keeps a single source of truth instead of a second literal
# that could drift from the packaging metadata.
__version__: str = version("pyvalue")

__all__ = ["__version__"]
