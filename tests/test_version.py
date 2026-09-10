"""The two places the version is written must agree."""

from __future__ import annotations

import tomllib
from pathlib import Path

import decoui


def test_the_package_reports_the_version_it_was_built_as() -> None:
    """Verify ``decoui.__version__`` matches the version in pyproject.toml.

    They are two independent strings, and nothing else compares them: v0.4.0
    went to PyPI with ``decoui.__version__`` still reading ``0.2.2``, because
    only the packaging one had been bumped. Anyone asking the installed package
    what it was got a wrong answer for a whole release.
    """
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    assert decoui.__version__ == declared
