"""Marker types for decoui widget mapping."""
from __future__ import annotations

from typing import Annotated


class Text(str):
    """Maps to QTextEdit (multi-line text area)."""


class FilePath(str):
    """Maps to QLineEdit with a file-picker button."""


class DirPath(str):
    """Maps to QLineEdit with a directory-picker button."""


class Choice(str):
    """Maps to QComboBox. Use with Annotated to specify choices."""


# Convenience Annotated aliases for constrained numeric types
Age = Annotated[int, {"min": 0, "max": 150}]
Rate = Annotated[float, {"min": 0.0, "max": 1.0, "step": 0.01}]
