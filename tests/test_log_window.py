"""Tests for the shared log viewer window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from decoui.ui.log_window import LEVEL_COLORS, LogEntry, LogWindow
from decoui.ui.tool_page import LEVEL_COLORS as TOOL_PAGE_LEVEL_COLORS


def test_stdout_is_distinct_from_info() -> None:
    """Verify raw print output reads apart from INFO in both log views."""
    assert TOOL_PAGE_LEVEL_COLORS is LEVEL_COLORS
    assert LEVEL_COLORS["stdout"] == "#FFFFFF"
    assert LEVEL_COLORS["INFO"] == "#39FF14"


def test_none_button_clears_all_level_filters(qt_app: QApplication) -> None:
    """Verify that None deselects every level and hides all log entries."""
    window = LogWindow(
        "Test",
        [
            LogEntry("INFO", "Info message"),
            LogEntry("ERROR", "Error message"),
        ],
    )

    none_button = next(
        button
        for button in window.findChildren(QPushButton)
        if button.text() == "None"
    )
    none_button.click()

    assert window._active_levels == set()
    assert all(not button.isChecked() for button in window._level_btns.values())
    assert window._console.toPlainText() == ""

    window.close()
