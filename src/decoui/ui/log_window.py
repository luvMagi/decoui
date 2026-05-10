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

LogEntry = namedtuple("LogEntry", ["level", "message"])

_ALL_LEVELS = ["stdout", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_LEVEL_COLORS = {
    "stdout":   "#FFFFFF",
    "DEBUG":    "#A0A0A0",
    "INFO":     "#00BFFF",
    "WARNING":  "#FFD700",
    "ERROR":    "#FF6B6B",
    "CRITICAL": "#FF0000",
}


class LogWindow(QMainWindow):
    """Independent resizable log viewer with level filtering and search."""

    def __init__(self, title: str, logs):
        super().__init__(parent=None)
        self.setWindowTitle(f"Log — {title}")
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
        level_row.addWidget(QLabel("Level:", central))

        all_btn = QPushButton("All", central)
        all_btn.clicked.connect(self._select_all_levels)
        level_row.addWidget(all_btn)

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
        search_row.addWidget(QLabel("Search:", central))
        self._search = QLineEdit(central)
        self._search.setPlaceholderText("Filter log messages...")
        self._search.textChanged.connect(self._rerender)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        # ── Console ───────────────────────────────────────────────────────────
        self._console = QPlainTextEdit(central)
        self._console.setReadOnly(True)
        self._console.setStyleSheet(
            "background:#1e1e1e; color:#ffffff; border-radius:6px;"
            "font-family: Consolas, 'Microsoft YaHei', Meiryo, monospace;"
            "font-size: 10pt;"
        )
        layout.addWidget(self._console)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom_row = QHBoxLayout()
        copy_btn = QPushButton("Copy All", central)
        copy_btn.clicked.connect(self._copy_all)
        close_btn = QPushButton("Close", central)
        close_btn.clicked.connect(self.close)
        bottom_row.addStretch()
        bottom_row.addWidget(copy_btn)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        self._rerender()

    def _select_all_levels(self):
        self._active_levels = set(_ALL_LEVELS)
        for btn in self._level_btns.values():
            btn.setChecked(True)
        self._rerender()

    def _toggle_level(self, level: str, checked: bool):
        if checked:
            self._active_levels.add(level)
        else:
            self._active_levels.discard(level)
        self._rerender()

    def _rerender(self):
        query = self._search.text().lower()
        self._console.clear()
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for log in self._logs:
            if log.level not in self._active_levels:
                continue
            if query and query not in log.message.lower():
                continue
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(_LEVEL_COLORS.get(log.level, "#FFFFFF")))
            if log.level == "CRITICAL":
                fmt.setFontWeight(700)
            cursor.insertText(log.message + "\n", fmt)
        self._console.setTextCursor(cursor)

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._console.toPlainText())
