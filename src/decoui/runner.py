"""gui_main() entry point."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

from .decorators import _TOOLSET_ATTR
from .registry import build_tree
from .storage.db import init_db, set_db_path


def gui_main(title: str = "decoui", db_path: str | Path | None = None) -> None:
    """Launch the decoui GUI application.

    Auto-discovers all @toolset classes visible in the caller's global scope.

    Args:
        title:   Window title.
        db_path: Path to the SQLite history database. Defaults to ~/.decoui/history.db.
    """
    if db_path is not None:
        set_db_path(Path(db_path))

    # Walk up the call stack to find the first frame outside this module,
    # then collect every class decorated with @toolset from that namespace.
    caller_globals = _caller_globals()
    toolset_classes = [
        obj
        for obj in caller_globals.values()
        if isinstance(obj, type) and hasattr(obj, _TOOLSET_ATTR)
    ]

    if not toolset_classes:
        raise RuntimeError(
            "gui_main() found no @toolset classes in the calling namespace. "
            "Make sure to import them before calling gui_main()."
        )

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_icon_path())))
    _apply_fonts(app)
    _apply_theme(app)

    init_db()
    tree = build_tree(*toolset_classes)

    from .ui.main_window import MainWindow
    window = MainWindow(tree, title=title)
    window.show()

    sys.exit(app.exec())


_APP_STYLESHEET = """
QWidget {
    background-color: #f5f6fa;
    color: #1e2128;
}
QMainWindow > QWidget,
QStackedWidget > QWidget {
    background-color: #ffffff;
}
/* Sidebar */
QWidget#sidebar {
    background-color: #f8faff;
    border-right: 1px solid #e4e7ef;
}
QWidget#sidebar QLineEdit {
    background-color: #ffffff;
}
/* Tree */
QTreeWidget {
    background-color: #f8faff;
    border: none;
    outline: none;
    padding: 2px;
}
QTreeWidget::item {
    padding: 4px 6px;
    border-radius: 5px;
}
QTreeWidget::item:hover {
    background-color: #edf0fb;
}
QTreeWidget::item:selected {
    background-color: #dbe4ff;
    color: #1e2128;
}
/* Splitter */
QSplitter::handle:horizontal {
    background-color: #e4e7ef;
    width: 1px;
}
/* Buttons */
QPushButton {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    border-radius: 6px;
    padding: 4px 14px;
    color: #344054;
    min-height: 26px;
}
QPushButton:hover {
    background-color: #f0f4ff;
    border-color: #7c90cc;
}
QPushButton:pressed {
    background-color: #e0e8ff;
}
QPushButton:checked {
    background-color: #3b5bdb;
    color: #ffffff;
    border-color: #3b5bdb;
}
QPushButton:disabled {
    color: #aab0bf;
    border-color: #e4e7ef;
    background-color: #f8f9fc;
}
QPushButton#run_btn {
    background-color: #2b9348;
    color: #ffffff;
    border-color: #2b9348;
    font-weight: bold;
}
QPushButton#run_btn:hover {
    background-color: #218838;
    border-color: #218838;
}
QPushButton#stop_btn {
    background-color: #dc3545;
    color: #ffffff;
    border-color: #dc3545;
}
QPushButton#stop_btn:hover {
    background-color: #c82333;
    border-color: #c82333;
}
/* Inputs */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}
QLineEdit:focus {
    border-color: #3b5bdb;
}
QTextEdit {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    border-radius: 6px;
    padding: 4px 8px;
}
QTextEdit:focus {
    border-color: #3b5bdb;
}
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    border-radius: 6px;
    padding: 3px 8px 3px 8px;
    min-height: 26px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #3b5bdb;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 0;
    border: none;
    background: none;
}
QComboBox {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    border-radius: 6px;
    padding: 3px 8px;
    min-height: 26px;
}
QComboBox:focus {
    border-color: #3b5bdb;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #d0d5e0;
    selection-background-color: #dbe4ff;
    selection-color: #1e2128;
    outline: none;
}
QCheckBox {
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1.5px solid #d0d5e0;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #3b5bdb;
    border-color: #3b5bdb;
}
/* Progress */
QProgressBar {
    border: none;
    border-radius: 2px;
    background-color: #e4e7ef;
}
QProgressBar::chunk {
    background-color: #3b5bdb;
    border-radius: 2px;
}
/* Table */
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e4e7ef;
    border-radius: 8px;
    gridline-color: #f0f2f8;
    outline: none;
}
QHeaderView::section {
    background-color: #f8f9fc;
    border: none;
    border-bottom: 1px solid #e4e7ef;
    padding: 6px 8px;
    font-weight: bold;
    color: #667085;
}
QTableWidget::item {
    padding: 4px 8px;
}
QTableWidget::item:selected {
    background-color: #dbe4ff;
    color: #1e2128;
}
/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #c0c8d8;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #8a96b0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #c0c8d8;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


def _apply_fonts(app) -> None:
    from PySide6.QtGui import QFont
    ui_font = QFont()
    ui_font.setFamilies(["Microsoft YaHei", "Meiryo", "Segoe UI", "sans-serif"])
    ui_font.setPointSize(10)
    app.setFont(ui_font)


def _apply_theme(app) -> None:
    app.setStyleSheet(_APP_STYLESHEET)


def _icon_path() -> Path:
    """Resolve icon.png whether running from source or installed wheel."""
    from importlib.resources import files
    try:
        ref = files("decoui") / "icon.png"
        # as_file gives a real Path even inside a zip/wheel
        from importlib.resources import as_file
        from contextlib import ExitStack
        _stack = ExitStack()
        return Path(str(_stack.enter_context(as_file(ref))))
    except Exception:
        return Path(__file__).parent / "icon.png"


def _caller_globals() -> dict:
    """Return the global namespace of the first frame outside decoui itself."""
    this_pkg = __name__.split(".")[0]
    for frame_info in inspect.stack():
        module = frame_info.frame.f_globals.get("__name__", "")
        if not module.startswith(this_pkg):
            return frame_info.frame.f_globals
    return {}
