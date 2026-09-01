"""Tests for the shared log viewer window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from decoui.ui.log_window import LogEntry, LogWindow
from decoui.ui.log_window import _LEVEL_COLORS as LOG_WINDOW_LEVEL_COLORS
from decoui.ui.tool_page import _LEVEL_COLORS as TOOL_PAGE_LEVEL_COLORS


def test_info_and_stdout_use_phosphor_green() -> None:
    """Verify both log views use the same avionics-style green."""
    for level_colors in (LOG_WINDOW_LEVEL_COLORS, TOOL_PAGE_LEVEL_COLORS):
        assert level_colors["stdout"] == "#39FF14"
        assert level_colors["INFO"] == "#39FF14"


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
