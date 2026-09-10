"""Shared resizable log viewer window (used by HistoryPage and ToolPage)."""
from __future__ import annotations

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

#: Log level -> the theme colour token that paints it.
_LEVEL_TOKENS = {
    "stdout":   "console.stdout",
    "DEBUG":    "console.debug",
    "INFO":     "console.info",
    "WARNING":  "console.warning",
    "ERROR":    "console.error",
    "CRITICAL": "console.critical",
}


def level_colors() -> dict[str, str]:
    """Return the foreground colour for each log level under the active theme.

    Shared by the live console and this viewer, so a line keeps its colour when
    it is reopened in the log window.

    Returns:
        Level name to ``#rrggbb``. ``stdout`` reads apart from INFO on purpose:
        raw ``print()`` output should not look like a logged message.
    """
    colors = active_theme().colors
    return {level: colors[token] for level, token in _LEVEL_TOKENS.items()}


def default_color() -> str:
    """Return the colour for a level the theme does not name.

    Returns:
        The ``stdout`` colour, which is the theme's plain console foreground.
    """
    return active_theme().colors["console.stdout"]


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
        f"color:{colors['console.stdout']};"
        f"border:{shape['shape.border_width']:g}px solid {colors['border.console']};"
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
        colors = level_colors()
        fallback = default_color()
        for log in self._logs:
            if log.level not in self._active_levels:
                continue
            if query and query not in log.message.lower():
                continue
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors.get(log.level, fallback)))
            if log.level == "CRITICAL":
                fmt.setFontWeight(700)
            cursor.insertText(log.message + "\n", fmt)
        self._console.setTextCursor(cursor)

    def _copy_all(self):
        """Copy the currently visible lines to the clipboard."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._console.toPlainText())
