"""The width of the left-hand pane, shared by every window that has one.

The main window and the help window both open on a tree down the left side, and
they are meant to be used together -- help beside the form it explains. Two
panes of different widths sitting next to each other read as a misalignment
rather than as two windows, so there is one width and both use it.

One setting means one key, one default and one way of parsing what comes back
out of the database. Those are here rather than on either window, because a
second copy of a settings key is the kind of thing that fails silently: the
value is written under one spelling and looked for under another, and nothing
reports it.
"""
from __future__ import annotations

from ..storage.db import get_setting, set_setting

#: Settings key holding the pane's width in pixels.
SIDEBAR_WIDTH_SETTING = "ui.sidebar.width"

#: Width to open at when nothing has been stored: wide enough for a toolset
#: label and one level of indent under it.
DEFAULT_SIDEBAR_WIDTH = 220


def stored_sidebar_width() -> int:
    """Return the width the sidebar should open at.

    Returns:
        The stored width, or :data:`DEFAULT_SIDEBAR_WIDTH` when nothing is
        stored or what is stored cannot be read as a number. Never negative.
        A layout preference is not worth an exception on the path that builds
        the window, so an unusable value is treated as no value.
    """
    stored = get_setting(SIDEBAR_WIDTH_SETTING)
    try:
        width = int(stored) if stored is not None else DEFAULT_SIDEBAR_WIDTH
    except ValueError:
        width = DEFAULT_SIDEBAR_WIDTH
    return max(0, width)


def save_sidebar_width(width: int) -> None:
    """Store the pane's width.

    Args:
        width: The width in pixels, as the splitter reports it.
    """
    set_setting(SIDEBAR_WIDTH_SETTING, str(width))
