"""Shared resizable log viewer window (used by HistoryPage and ToolPage)."""
from __future__ import annotations

import re
from collections import namedtuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..theme import active_theme

LogEntry = namedtuple("LogEntry", ["level", "message"])

_ALL_LEVELS = ["stdout", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

#: Log level -> (tag token, body token). ``stdout`` has no tag: it is raw
#: ``print()`` output, which arrives without the formatter's prefix.
_LEVEL_TOKENS = {
    "stdout":   (None,                     "console.plain"),
    "DEBUG":    ("console.tag.debug",      "console.body.debug"),
    "INFO":     ("console.tag.info",       "console.body.info"),
    "WARNING":  ("console.tag.warning",    "console.body.warning"),
    "ERROR":    ("console.tag.error",      "console.body.error"),
    "CRITICAL": ("console.tag.critical",   "console.body.critical"),
}

#: Splits a formatted line into (timestamp, level tag, message). It has to
#: match what the worker's formatter writes -- ``"[%(asctime)s] %(levelname)-8s
#: %(message)s"`` with ``"%H:%M:%S"`` (:mod:`decoui.engine.worker`). Lines are
#: re-split at render time rather than stored in three pieces because history
#: rows hold the whole line as one string, and a run reopened from the history
#: table has to ink the same way as the run that produced it.
#:
#: DOTALL: a record's message can carry newlines -- a formatted traceback is
#: one record -- and all of it belongs to the body.
_LINE_RE = re.compile(r"^(\[\d\d:\d\d:\d\d\] )([A-Z]+ *)(.*)$", re.DOTALL)


def level_inks() -> dict[str, tuple[str | None, str]]:
    """Return the tag and body colours for each level under the active theme.

    Shared by the live console and this viewer, so a line keeps its colours
    when it is reopened in the log window.

    Returns:
        Level name to ``(tag colour, body colour)``, each ``#rrggbb``; the tag
        colour is ``None`` for ``stdout``, which carries no tag. ``stdout``
        reads apart from INFO on purpose: raw ``print()`` output should not
        look like a logged message.
    """
    colors = active_theme().colors
    return {
        level: (colors[tag] if tag else None, colors[body])
        for level, (tag, body) in _LEVEL_TOKENS.items()
    }


def timestamp_color() -> str:
    """Return the ink for the ``[HH:MM:SS]`` prefix under the active theme.

    Returns:
        A ``#rrggbb`` colour. Not per level: a clock reading is the same
        information whatever the line's severity.
    """
    return active_theme().colors["console.timestamp"]


def default_color() -> str:
    """Return the colour for a level the theme does not name.

    Returns:
        The plain console foreground, which is also what ``stdout`` uses.
    """
    return active_theme().colors["console.plain"]


def insert_log_line(
    cursor, level: str, message: str, inks, fallback: str, timestamp_ink: str
) -> None:
    """Insert one console line at the cursor, tag and body inked separately.

    The single place a log line becomes text, so the live console and the log
    window cannot drift apart on how a line is drawn.

    A line whose shape :data:`_LINE_RE` does not recognise is written whole in
    the body ink. That is not an edge case to be tidied away: the worker emits
    an unformatted traceback on an unhandled exception, and stdout lines never
    carry a prefix at all.

    Args:
        cursor: The text cursor to insert at, already positioned.
        level: ``'stdout'`` or a logging level name.
        message: The line, as it was emitted and as history stores it.
        inks: The mapping from :func:`level_inks`.
        fallback: Body colour for a level the theme does not name.
        timestamp_ink: Colour for the ``[HH:MM:SS]`` prefix, from
            :func:`timestamp_color`.
    """
    tag_color, body_color = inks.get(level, (None, fallback))
    body = QTextCharFormat()
    body.setForeground(QColor(body_color))
    # At CRITICAL the colour is doing too much work on its own.
    if level == "CRITICAL":
        body.setFontWeight(700)

    match = _LINE_RE.match(message) if tag_color else None
    if match is None:
        cursor.insertText(message + "\n", body)
        return

    timestamp, tag, rest = match.groups()
    # Copied from `body` rather than built fresh, so CRITICAL's weight carries
    # across all three spans and the line stays one visual unit.
    stamp_fmt = QTextCharFormat(body)
    stamp_fmt.setForeground(QColor(timestamp_ink))
    tag_fmt = QTextCharFormat(body)
    tag_fmt.setForeground(QColor(tag_color))
    cursor.insertText(timestamp, stamp_fmt)
    cursor.insertText(tag, tag_fmt)
    cursor.insertText(rest + "\n", body)


def console_style() -> str:
    """Return the stylesheet shared by both console views.

    The console is the one area that is meant to read as a terminal, so it gets
    its own background, its own border and a monospaced face -- all of them
    from the theme, so a panel-styled theme can inset it rather than leaving a
    flat rectangle butted against the page.

    Returns:
        A stylesheet for a read-only text view.
    """
    theme = active_theme()
    colors, shape, font = theme.colors, theme.shape, theme.font
    return (
        f"background:{colors['bg.console']};"
        f"color:{colors['console.plain']};"
        f"border:{shape['shape.border_width_control']:g}px "
        f"{shape['shape.border_style_control']} {colors['border.console']};"
        f"border-radius:{shape['shape.radius_control']:g}px;"
        f"font-family: {', '.join(font.mono_family)};"
        f"font-size: {font.mono_size_pt:g}pt;"
    )


class LogWindow(QMainWindow):
    """Standalone, filterable view of one run's console output.

    Opened from a tool page ("View Log") or from a history row. It holds a copy
    of the lines, so filtering here never disturbs the page it came from.
    """
    """Independent resizable log viewer with level filtering and search."""

    def __init__(self, title: str, logs):
        """Show the given lines with every level enabled.

        Args:
            title: Window title, normally the tool label.
            logs: The LogEntry sequence to display.
        """
        super().__init__(parent=None)
        self.setWindowTitle(t("log.title", title=title))
        self.resize(820, 580)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._logs = list(logs)
        self._active_levels: set[str] = set(_ALL_LEVELS)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Level filter buttons ──────────────────────────────────────────────
        level_row = QHBoxLayout()
        level_row.setSpacing(4)
        level_row.addWidget(QLabel(t("log.level"), central))

        all_btn = QPushButton(t("common.all"), central)
        all_btn.clicked.connect(self._select_all_levels)
        level_row.addWidget(all_btn)

        none_btn = QPushButton(t("common.none"), central)
        none_btn.clicked.connect(self._clear_all_levels)
        level_row.addWidget(none_btn)

        self._level_btns: dict[str, QPushButton] = {}
        for lvl in _ALL_LEVELS:
            btn = QPushButton(lvl, central)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.clicked.connect(lambda checked, l=lvl: self._toggle_level(l, checked))
            level_row.addWidget(btn)
            self._level_btns[lvl] = btn
        level_row.addStretch()
        layout.addLayout(level_row)

        # ── Search bar ────────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(t("common.search"), central))
        self._search = QLineEdit(central)
        self._search.setPlaceholderText(t("log.search_placeholder"))
        self._search.textChanged.connect(self._rerender)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        # ── Console ───────────────────────────────────────────────────────────
        self._console = QPlainTextEdit(central)
        self._console.setReadOnly(True)
        self._console.setStyleSheet(console_style())
        layout.addWidget(self._console)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom_row = QHBoxLayout()
        copy_btn = QPushButton(t("log.copy_all"), central)
        copy_btn.clicked.connect(self._copy_all)
        close_btn = QPushButton(t("common.close"), central)
        close_btn.clicked.connect(self.close)
        bottom_row.addStretch()
        bottom_row.addWidget(copy_btn)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        self._rerender()

    def retheme(self) -> None:
        """Repaint the console, and the lines already in it, under a new theme.

        This window holds its own copy of the entries, so re-inking them is the
        same redraw the level filters already do. See :mod:`decoui.ui.retheme`.
        """
        self._console.setStyleSheet(console_style())
        self._rerender()

    def _select_all_levels(self):
        """Enable every level filter."""
        self._active_levels = set(_ALL_LEVELS)
        for btn in self._level_btns.values():
            btn.setChecked(True)
        self._rerender()

    def _clear_all_levels(self) -> None:
        """Clear all active level filters and hide every log entry."""
        self._active_levels.clear()
        for btn in self._level_btns.values():
            btn.setChecked(False)
        self._rerender()

    def _toggle_level(self, level: str, checked: bool):
        """Show or hide one log level.

        Args:
            level: The level whose button was clicked.
            checked: Its new state.
        """
        if checked:
            self._active_levels.add(level)
        else:
            self._active_levels.discard(level)
        self._rerender()

    def _rerender(self):
        """Redraw the console from the entries the active filters allow."""
        query = self._search.text().lower()
        self._console.clear()
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        inks = level_inks()
        fallback = default_color()
        stamp = timestamp_color()
        for log in self._logs:
            if log.level not in self._active_levels:
                continue
            if query and query not in log.message.lower():
                continue
            insert_log_line(cursor, log.level, log.message, inks, fallback, stamp)
        self._console.setTextCursor(cursor)

    def _copy_all(self):
        """Copy the currently visible lines to the clipboard."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._console.toPlainText())
