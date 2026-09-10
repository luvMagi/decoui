"""Swap the theme of a running application, without rebuilding anything.

Most of decoui's colour lives in the application stylesheet, and Qt re-styles
every widget when that is replaced. The rest does not: a handful of widgets --
tag pills, status badges, the console -- set their own style in code, because
they need a shape or a colour the global rules cannot express. Those read the
theme once, as they are built, and a new stylesheet never reaches them.

So a re-theme is two passes over the open windows. Any widget that styled
itself declares a ``retheme()`` method that redoes exactly that work; this
module finds them by name rather than through a base class, so a widget opts in
by having the method and nothing else has to know it exists.

Nothing is destroyed or rebuilt. A tool that is running keeps running, its
console keeps its lines, and every page keeps the values typed into it -- which
is the whole reason this is a re-style pass and not a restart.

The interface **language** is not swapped this way: text is read at build time
in far more places than colour is, and there is no equivalent of the stylesheet
to catch the rest. Changing language still means restarting.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from ..theme import (
    Theme,
    apply_label_case,
    render_stylesheet,
    set_active_theme,
    theme_font,
)


def retheme_application(theme: Theme) -> None:
    """Make ``theme`` the live theme and repaint everything already on screen.

    Args:
        theme: The theme to switch to. It becomes the one
            :func:`decoui.theme.active_theme` returns, so widgets built after
            this call are born under it.

    Note:
        Safe to call with no QApplication running: the active theme is still
        recorded, which is all a test or a headless caller can observe.
    """
    set_active_theme(theme)

    app = QApplication.instance()
    if app is None:
        return

    app.setFont(theme_font(theme))
    app.setStyleSheet(render_stylesheet(theme))

    # Qt's own list, not one decoui keeps: LogWindow and HelpWindow are
    # WA_DeleteOnClose, and any list of our own would still hold the Python
    # wrappers of windows whose C++ side is gone.
    windows = list(app.topLevelWidgets())
    for window in windows:
        _retheme_tree(window)

    # Capitals last, and in a pass of their own. apply_label_case() works
    # through the widget font, and Qt re-resolves a widget's font whenever its
    # stylesheet changes -- so it has to run after every retheme() above has
    # finished setting stylesheets, not interleaved with them.
    for window in windows:
        apply_label_case(window)


def _retheme_tree(root: QWidget) -> None:
    """Call ``retheme()`` on every widget in one window that has one.

    Args:
        root: The top-level widget to walk, itself included.
    """
    for widget in (root, *root.findChildren(QWidget)):
        hook = getattr(widget, "retheme", None)
        if callable(hook):
            hook()
