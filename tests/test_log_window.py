"""Tests for the shared log viewer window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from decoui.theme import active_theme
from decoui.ui.log_window import (
    LogEntry,
    LogWindow,
    console_style,
    default_color,
    insert_log_line,
    level_inks,
    timestamp_color,
)
from decoui.ui.tool_page import level_inks as tool_page_level_inks


def test_stdout_is_distinct_from_info() -> None:
    """Verify raw print output reads apart from INFO in both log views.

    They are the two most common line sources, and a run reads as noise if they
    look the same.
    """
    inks = level_inks()

    assert tool_page_level_inks() == inks
    assert inks["stdout"][1] != inks["INFO"][1]


def test_stdout_has_no_tag_ink() -> None:
    """Verify stdout is inked as one span.

    A ``print()`` line carries no level tag, so there is nothing for a tag
    colour to land on; reporting one would invite the renderer to split a line
    that has no prefix.
    """
    assert level_inks()["stdout"][0] is None
    assert all(inks[0] is not None
               for level, inks in level_inks().items() if level != "stdout")


def test_level_colours_come_from_the_theme() -> None:
    """Verify no log colour is hard-coded any more.

    Until the console became themeable these were fixed phosphor values, which
    made a light console impossible.
    """
    theme_colors = active_theme().colors

    for level, (tag, body) in level_inks().items():
        assert body in theme_colors.values(), level
        assert tag is None or tag in theme_colors.values(), level


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


def _spans(message: str, level: str = "INFO") -> list[tuple[str, str]]:
    """Render one line through the real inserter and read back its spans.

    Args:
        message: The line, in the shape the worker's formatter emits.
        level: The level to ink it as.

    Returns:
        ``(text, #rrggbb)`` per run of identically-inked characters.
    """
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QTextEdit

    view = QTextEdit()
    cursor = view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    insert_log_line(
        cursor, level, message, level_inks(), default_color(), timestamp_color()
    )

    spans: list[tuple[str, str]] = []
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    while cursor.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor
    ):
        colour = cursor.charFormat().foreground().color().name()
        char = cursor.selectedText()
        if spans and spans[-1][1] == colour:
            spans[-1] = (spans[-1][0] + char, colour)
        else:
            spans.append((char, colour))
        cursor.clearSelection()
    return spans


def test_a_formatted_line_is_inked_in_three_parts() -> None:
    """Verify the timestamp, the level tag and the message ink separately.

    This is the whole point of the split: a console is scanned by level, so the
    tag has to be the loud thing, and a wall of message text has to stay
    readable while it is.
    """
    inks = level_inks()

    spans = _spans("[12:03:44] WARNING  disk almost full", "WARNING")

    texts = [text for text, _ in spans]
    colours = [colour for _, colour in spans]
    assert texts[0] == "[12:03:44] "
    assert texts[1] == "WARNING  "
    assert texts[2].startswith("disk almost full")
    assert colours[0] == timestamp_color()
    assert colours[1] == inks["WARNING"][0]
    assert colours[2] == inks["WARNING"][1]


def test_an_unformatted_line_is_inked_whole() -> None:
    """Verify a line with no prefix takes the body ink and is not split.

    The worker emits a bare traceback when a tool raises, and every stdout line
    arrives without a prefix. Neither has a tag for the tag colour to land on.
    """
    spans = _spans("Traceback (most recent call last):", "ERROR")

    assert len(spans) == 1
    assert spans[0][1] == level_inks()["ERROR"][1]


def test_a_multi_line_record_keeps_one_prefix() -> None:
    """Verify only the first line of a multi-line record carries a tag.

    A formatted traceback is one record, so everything after the first newline
    is message text and must not be re-scanned for a level to colour.
    """
    spans = _spans("[12:03:44] ERROR    boom\n  File \"x.py\", line 1", "ERROR")

    assert [text for text, _ in spans][:2] == ["[12:03:44] ", "ERROR    "]
    assert len(spans) == 3


def test_the_timestamp_ink_is_shared_across_levels() -> None:
    """Verify the clock reading looks the same whatever the line's severity.

    It is one token on purpose -- a timestamp carries no severity, and five
    copies of the same grey is a worse thing to keep in step.
    """
    stamps = {
        _spans(f"[12:03:44] {level:<8} x", level)[0][1]
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    }

    assert stamps == {timestamp_color()}
