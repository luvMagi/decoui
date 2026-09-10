"""Regression tests for inline stylesheets leaking onto child controls.

A stylesheet set on a widget reaches that widget's whole subtree, and it
outranks the application stylesheet. So a selectorless declaration written for
one container -- ``background: transparent`` on a scroll area's content widget,
say -- silently repaints every control inside it, and Qt resolves the result
into those controls' palettes.

That is not always visible where it is written. Under Fusion ``transparent``
means "do not paint" and whatever is behind shows through, so the row looks
right; the Windows 11 style paints from the palette instead and drew the
history page's filter controls as black text on black. These tests check the
palettes rather than the rendering, because the palette is the part that is the
same on every platform.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

from decoui.example import TextTools
from decoui.registry import build_tree
from decoui.storage.db import init_db, set_db_path
from decoui.theme import Theme, builtin_themes, set_active_theme
from decoui.ui.history_page import HistoryPage
from decoui.ui.nav_tree import NavTree
from decoui.ui.retheme import retheme_application
from decoui.ui.tag_bar import TagBar
from decoui.widget_builder import _PathWidget


@pytest.fixture()
def themed(tmp_path: Path, qt_app: QApplication) -> Iterator[QApplication]:
    """Run under a real applied theme, and put the old one back afterwards.

    Yields:
        The Qt application, with decoui's stylesheet actually installed --
        without which every palette here would be Qt's default rather than the
        theme's.
    """
    set_db_path(tmp_path / "history.db")
    init_db()
    stylesheet, font = qt_app.styleSheet(), qt_app.font()
    yield qt_app
    set_active_theme(builtin_themes()["light"])
    qt_app.setStyleSheet(stylesheet)
    qt_app.setFont(font)


@pytest.mark.parametrize("theme_id", sorted(builtin_themes()))
def test_history_filter_controls_keep_the_theme_field_colour(
    themed: QApplication, theme_id: str
) -> None:
    """Verify the filter row's dropdowns are drawn on the theme's field colour.

    They sit inside a scroll area whose content widget is made transparent so
    the page shows through. Written without a selector that transparency
    reaches the dropdowns as well, and Qt resolves it to black -- against text
    that every built-in theme keeps dark.

    Args:
        themed: The application, ready to be themed.
        theme_id: The built-in theme under test.
    """
    theme: Theme = builtin_themes()[theme_id]
    retheme_application(theme)
    page = HistoryPage({"tool.a": "Alpha"})
    page.show()

    for combo in page.findChildren(QComboBox):
        combo.ensurePolished()
        base = combo.palette().color(QPalette.ColorRole.Base).name()
        assert base.lower() == theme.colors["bg.field"].lower()


@pytest.mark.parametrize("build", [
    pytest.param(lambda: HistoryPage({"tool.a": "Alpha"}), id="history"),
    pytest.param(lambda: TagBar(["alpha", "beta"]), id="tagbar"),
])
def test_a_container_never_styles_itself_without_a_selector(
    themed: QApplication, build
) -> None:
    """Verify no widget with children carries a selectorless stylesheet.

    This is the shape of the bug rather than one instance of it. A widget with
    no children can say ``background: transparent`` harmlessly -- a status
    badge does. A widget with children cannot: the declaration is inherited by
    all of them and beats the application stylesheet's own rules for whatever
    they happen to be.

    Args:
        themed: The application, ready to be themed.
        build: Builds the widget tree under test.
    """
    retheme_application(builtin_themes()["light"])
    root = build()
    root.show()

    offenders = [
        f"{widget.__class__.__name__}({widget.objectName() or '-'}): {widget.styleSheet()!r}"
        for widget in (root, *root.findChildren(QWidget))
        if widget.styleSheet()
        and widget.findChildren(QWidget)
        and "{" not in widget.styleSheet()
    ]
    assert not offenders


@pytest.mark.parametrize("theme_id", sorted(builtin_themes()))
def test_the_sidebar_selection_never_falls_back_to_qt_blue(
    themed: QApplication, theme_id: str
) -> None:
    """Verify the tool list's Highlight role comes from the theme.

    The selected row's fill and ink are QSS, but the platform style also paints
    that row's focus outline and takes the colour from the palette, which no
    theme had ever set. Under Fusion that left a bright blue four-cornered box
    in the indent column of whichever tool was selected -- in a colour no theme
    contained.

    Args:
        themed: The application, ready to be themed.
        theme_id: The built-in theme under test.
    """
    theme: Theme = builtin_themes()[theme_id]
    retheme_application(theme)
    nav = NavTree(build_tree(TextTools))
    nav.show()

    palette = nav._tw.palette()
    assert palette.color(QPalette.ColorRole.Highlight).name().lower() == (
        theme.colors["bg.tree_selected"].lower()
    )
    assert palette.color(QPalette.ColorRole.HighlightedText).name().lower() == (
        theme.colors["text.on_sidebar_selected"].lower()
    )


def test_a_retheme_moves_the_sidebar_selection_palette(themed: QApplication) -> None:
    """Verify the palette is refreshed rather than left on the old theme.

    It is set in code, so nothing about swapping the application stylesheet
    reaches it; only NavTree.retheme() does.

    Args:
        themed: The application, ready to be themed.
    """
    retheme_application(builtin_themes()["light"])
    nav = NavTree(build_tree(TextTools))
    nav.show()

    retheme_application(builtin_themes()["cockpit"])

    assert nav._tw.palette().color(QPalette.ColorRole.Highlight).name().lower() == (
        builtin_themes()["cockpit"].colors["bg.tree_selected"].lower()
    )


def test_the_path_pickers_never_clip_their_labels(themed: QApplication) -> None:
    """Verify both picker buttons are at least as wide as their own text.

    They used to carry a fixed 72px, chosen against "File..." -- which clipped
    every longer translation, Japanese included at 93px, and clipped further
    under a theme that sets capitals or letter-spacing.
    """
    retheme_application(builtin_themes()["light"])
    widget = _PathWidget()
    widget.resize(420, 32)
    widget.show()

    for button in (widget._file_btn, widget._dir_btn):
        assert button.width() >= button.sizeHint().width()
    assert widget._file_btn.width() == widget._dir_btn.width()
