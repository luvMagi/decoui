"""Tests for the shared log viewer window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from decoui.theme import active_theme
from decoui.ui.log_window import LogEntry, LogWindow, console_style, level_colors
from decoui.ui.tool_page import level_colors as tool_page_level_colors


def test_stdout_is_distinct_from_info() -> None:
    """Verify raw print output reads apart from INFO in both log views.

    They are the two most common line sources, and a run reads as noise if they
    look the same.
    """
    colors = level_colors()

    assert tool_page_level_colors() == colors
    assert colors["stdout"] != colors["INFO"]


def test_level_colours_come_from_the_theme() -> None:
    """Verify no log colour is hard-coded any more.

    Until the console became themeable these were fixed phosphor values, which
    made a light console impossible.
    """
    theme_colors = active_theme().colors

    for level, colour in level_colors().items():
        assert colour in theme_colors.values(), level


def test_console_style_frames_the_output_area() -> None:
    """Verify the console reads as an inset area rather than a bare rectangle.

    A panel-styled theme needs a border to nest the console inside the page;
    without one it is a flat block butted against the surrounding surface.
    """
    theme = active_theme()

    style = console_style()

    assert theme.colors["bg.console"] in style
    assert theme.colors["border.console"] in style
    assert ", ".join(theme.font.mono_family) in style


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
