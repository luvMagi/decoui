"""Tests for main-window navigation, tabs, and layout persistence."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QTreeWidget

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
