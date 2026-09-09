"""Filesystem access to the image assets shipped inside the package."""
from __future__ import annotations

from pathlib import Path

_ASSET_DIR = Path(__file__).resolve().parent


def tab_close_icon_path() -> Path:
    """Return the glyph drawn on each tab's close button."""
    return _ASSET_DIR / "tab_close.svg"
