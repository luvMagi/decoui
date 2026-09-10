"""Filesystem access to the image assets shipped inside the package."""
from __future__ import annotations

from pathlib import Path

_ASSET_DIR = Path(__file__).resolve().parent

#: Where the interface icons live, one SVG per icon, named after the thing they
#: mean rather than after the button that happens to use them: ``delete`` is
#: drawn once and used by a button and a context-menu action both.
_ICON_DIR = _ASSET_DIR / "icons"


def icon_path(name: str) -> Path:
    """Return the SVG shipped under ``name``.

    Every file in the icon directory strokes itself in the literal
    ``currentColor``. That is not something Qt's SVG renderer resolves -- it has
    no CSS cascade to resolve it against -- so these are not handed straight to
    ``QIcon``; :func:`decoui.ui.icons.theme_icon` substitutes a theme colour
    first. That indirection is the whole reason this returns a path rather than
    an icon.

    Args:
        name: File stem, e.g. ``"settings"`` or ``"tab-close"``.

    Returns:
        The path to the SVG. Not checked for existence: a missing icon is a
        packaging fault, and the caller reports it in the one place that can
        say which icon was wanted.
    """
    return _ICON_DIR / f"{name}.svg"
