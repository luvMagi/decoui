"""Tests for main-window navigation, tabs, and layout persistence."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QScrollArea,
    QTreeWidget,
)

from decoui.registry import ToolInfo, ToolSetInfo
from decoui.storage.db import get_setting, init_db, set_db_path
from decoui.ui.main_window import MainWindow
from decoui.ui.nav_tree import NavTree


class _ExampleTools:
    """Provide simple methods for main-window test registrations."""

    def first(self) -> None:
        """Represent the first test tool."""

    def second(self) -> None:
        """Represent the second test tool."""


def _tool_info(name: str) -> ToolInfo:
    """Build minimal tool metadata for a named example method."""
    return ToolInfo(
        tool_id=f"_ExampleTools.{name}",
        method_name=name,
        method=getattr(_ExampleTools, name),
        label=name.title(),
        description="",
        icon=None,
        confirm=False,
        timeout=None,
        placeholders={},
        params=[],
        return_annotation=None,
    )


def _tool_tree() -> list[ToolSetInfo]:
    """Build a two-tool navigation tree for UI tests."""
    return [
        ToolSetInfo(
            cls=_ExampleTools,
            label="Examples",
            tags=[],
            icon=None,
            description="",
            tools=[_tool_info("first"), _tool_info("second")],
        )
    ]


def _prepare_database(tmp_path: Path) -> None:
    """Configure an isolated database for a main-window test."""
    set_db_path(tmp_path / "main-window.db")
    init_db()


def test_tool_entries_open_as_switchable_tabs(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify tools retain independent pages while their tabs are switched."""
    _prepare_database(tmp_path)
    tree = _tool_tree()
    window = MainWindow(tree)

    window._show_tool(tree[0].tools[0])
    first_page = window._tabs.currentWidget()
    window._show_tool(tree[0].tools[1])
    second_page = window._tabs.currentWidget()

    assert window._tabs.count() == 2
    assert first_page is not second_page
    assert window._stack.currentWidget() is window._tabs

    window._close_tool_tab(0)
    assert window._tabs.count() == 1

    window._show_tool(tree[0].tools[0])
    assert window._tabs.count() == 2
    assert window._tabs.currentWidget() is first_page

    window.close()


def test_tab_context_menu_closes_selected_or_other_tabs(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify tab context actions close the selected tab or all other tabs."""
    _prepare_database(tmp_path)
    tree = _tool_tree()
    window = MainWindow(tree)
    window._show_tool(tree[0].tools[0])
    first_page = window._tabs.currentWidget()
    window._show_tool(tree[0].tools[1])
    second_page = window._tabs.currentWidget()

    first_tab_index = window._tabs.indexOf(first_page)
    context_menu = window._create_tab_context_menu(first_tab_index)

    assert [action.text() for action in context_menu.actions()] == [
        "Close Tab",
        "Close Others",
        "Close All",
    ]

    context_menu.actions()[1].trigger()
    assert window._tabs.count() == 1
    assert window._tabs.currentWidget() is first_page

    window._show_tool(tree[0].tools[1])
    second_tab_index = window._tabs.indexOf(second_page)
    context_menu = window._create_tab_context_menu(second_tab_index)
    context_menu.actions()[0].trigger()

    assert window._tabs.count() == 1
    assert window._tabs.currentWidget() is first_page

    window._show_tool(tree[0].tools[1])
    context_menu = window._create_tab_context_menu(0)
    context_menu.actions()[2].trigger()

    assert window._tabs.count() == 0
    assert window._stack.currentWidget() is window._welcome

    window.close()


def test_sidebar_width_is_restored(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify a resized sidebar is restored in the next main window."""
    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.show()
    window._splitter.setSizes([310, 790])
    qt_app.processEvents()
    saved_width = window._splitter.sizes()[0]
    window._save_sidebar_width()
    window.close()

    assert get_setting("ui.sidebar.width") == str(saved_width)

    restored_window = MainWindow(_tool_tree())
    restored_window.show()
    qt_app.processEvents()

    assert abs(restored_window._splitter.sizes()[0] - saved_width) <= 1

    restored_window.close()


def test_tool_entry_indentation_is_halved(qt_app: QApplication) -> None:
    """Verify child tool entries use half the platform default indentation."""
    default_tree = QTreeWidget()
    expected_indentation = max(1, default_tree.indentation() // 2)
    nav = NavTree([])

    assert nav._tw.indentation() == expected_indentation

    nav.close()
    default_tree.close()


def test_sidebar_splitter_offers_a_grabbable_handle(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify the sidebar divider is wide enough to aim at.

    The stylesheet draws it as a hairline. Left at the default handle width
    that leaves a target only a few pixels across, and the sidebar reads as
    fixed-width because nobody can find the edge to drag.
    """
    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.resize(1200, 800)
    window.show()

    assert window._splitter.handleWidth() >= 6
    assert window._splitter.handle(1).width() >= 6

    window.close()


def test_sidebar_width_can_actually_be_dragged(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify dragging the handle really resizes the sidebar.

    Asserting on the handle's size alone would not catch a splitter that was
    disabled, collapsed, or pinned by a minimum width, so this drives a real
    drag through the handle's own event handlers.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.resize(1200, 800)
    window.show()
    splitter = window._splitter
    handle = splitter.handle(1)
    before = splitter.sizes()

    centre = QPoint(handle.width() // 2, 300)
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=centre)
    QTest.mouseMove(handle, centre + QPoint(120, 0))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=centre + QPoint(120, 0))

    assert splitter.sizes()[0] > before[0]

    window.close()


def test_tag_bar_keeps_the_first_pill_off_the_window_edge(
    qt_app: QApplication,
) -> None:
    """Verify the top row is inset rather than flush against the frame.

    At the original 4px the "Tags:" label sat against the window edge and the
    first pill crowded it.
    """
    from decoui.ui.tag_bar import TagBar

    bar = TagBar(["basic", "demo"])
    bar.resize(1200, 42)
    bar.show()

    label = bar.findChild(QLabel)
    scroll = bar.findChild(QScrollArea)
    first_pill = next(
        button for button in bar.findChildren(QPushButton) if button.text() == "All"
    )
    pill_x = first_pill.mapTo(bar, first_pill.rect().topLeft()).x()

    assert label.x() >= 10
    assert pill_x - (label.x() + label.width()) >= 14
    # The scrolling area must not draw a panel border of its own: it lands
    # alongside the first pill's border and the two read as one smudged line.
    assert scroll.frameWidth() == 0

    bar.close()


def test_sidebar_is_not_capped_by_the_widest_hidden_page(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify a page nobody is looking at cannot limit the sidebar.

    A QStackedWidget's minimum width is the widest of all its pages, so the
    History page's filter row used to fix how far the divider could travel even
    while a tool page was showing. On a 1000px window that left the sidebar a
    couple of hundred pixels of travel.
    """
    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.resize(1000, 800)
    window.show()
    splitter = window._splitter

    splitter.setSizes([10_000, 0])
    qt_app.processEvents()

    assert splitter.sizes()[0] >= 500

    window.close()


def test_content_area_cannot_be_collapsed_away(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify the divider stops at the content area's declared minimum.

    Letting the sidebar travel further would hide the tool page entirely, and a
    splitter ignores a child's minimum width while that child stays
    collapsible.
    """
    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.resize(1200, 800)
    window.show()
    splitter = window._splitter

    splitter.setSizes([10_000, 0])
    qt_app.processEvents()

    assert splitter.sizes()[1] >= window._stack.minimumWidth()
    assert not splitter.isCollapsible(1)

    window.close()


def test_history_width_does_not_track_tool_label_length(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify long tool labels cannot widen the History page without limit.

    Labels come from the application, so a combo box sized to its longest entry
    hands an application author unwitting control over the window's minimum
    width.
    """
    from decoui.ui.history_page import HistoryPage

    _prepare_database(tmp_path)
    short = HistoryPage({"Tools.run": "Run"})
    long = HistoryPage({
        "Tools.run": "A Very Long Toolset Name / An Extremely Long Tool Label Indeed",
    })

    assert long.minimumSizeHint().width() <= short.minimumSizeHint().width() + 20

    short.close()
    long.close()


def test_history_can_be_left_with_no_tool_open(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify History is escapable even when nothing else is open.

    The page fills the content area, and until it had a close button the only
    way out was to open a tool -- so a fresh window that went straight to
    History had no route back at all.
    """
    _prepare_database(tmp_path)
    window = MainWindow(_tool_tree())
    window.show()
    window._show_history()
    assert window._stack.currentWidget() is window._history_page

    window._history_page.close_requested.emit()

    assert window._stack.currentWidget() is window._welcome

    window.close()


def test_leaving_history_returns_to_the_open_tabs(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify closing History goes back to the work, not to the welcome page."""
    _prepare_database(tmp_path)
    tree = _tool_tree()
    window = MainWindow(tree)
    window.show()
    window._show_tool(tree[0].tools[0])
    window._show_history()

    window._history_page.close_requested.emit()

    assert window._stack.currentWidget() is window._tabs

    window.close()


def test_history_close_button_is_present(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify the way out is a visible control, not only a signal."""
    from decoui.ui.history_page import HistoryPage

    _prepare_database(tmp_path)
    page = HistoryPage({"Tools.run": "Run"})

    buttons = [
        button.text()
        for button in page.findChildren(QPushButton)
        if "close" in button.text().casefold()
    ]
    assert buttons

    page.close()
