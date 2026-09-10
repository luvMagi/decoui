"""gui_main() entry point.

One call starts the whole application: it finds the toolsets, validates their
declarations, builds the tree, creates one instance of each, runs the startup
hooks and shows the window. It does not return -- it ends in ``sys.exit()``.

The startup order is fixed and documented on :func:`gui_main`; the important
consequence is that ``__init__`` and ``on_startup()`` both run **before** the
event loop starts, so neither may wait on a timer, a signal or a worker thread.
See ``docs/startup-lifecycle.md``.

Failures during startup are collected rather than fatal: a toolset that cannot
be constructed is dropped, everything else stays usable, and all the failures
are reported together in one dialog over the window.
"""
from __future__ import annotations

import inspect
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Callable

from .decorators import _TOOL_ATTR, _TOOLSET_ATTR
from .registry import build_tree
from .storage.db import init_db, set_db_path


def gui_main(
    title: str = "decoui",
    db_path: str | Path | None = None,
    on_startup: Callable[[], None] | None = None,
    toolsets: Sequence[type] | None = None,
) -> None:
    """Launch the decoui GUI application.

    Auto-discovers all @toolset classes visible in the caller's global scope,
    unless ``toolsets`` names them explicitly.

    Startup runs in a fixed order, so anything loaded early is available later:

      1. ``db_path`` is applied and the database is initialised
      2. the toolset tree is built and validated
      3. ``on_startup()`` runs                     <- application hook
      4. every toolset class is instantiated       <- ``self`` exists from here
      5. each instance's own ``on_startup()`` method runs, if it defines one
      6. the window is shown and the event loop starts

    Failures in steps 3-5 do not stop the application: they are collected and
    reported in one dialog over the main window, and everything that did load
    stays usable.

    Both hooks run on the GUI thread before the event loop starts. See
    docs/startup-lifecycle.md for what that rules out.

    Args:
        title:   Window title.
        db_path: Path to the SQLite history and settings database. Defaults to
            ~/.decoui/history.db.
        on_startup: Called once at step 3, for application-wide work: opening a
            shared connection, fetching a token, warming a cache. It runs
            before any toolset instance exists, so it cannot write to ``self``
            -- to load data a single toolset owns, give that class its own
            ``on_startup()`` method instead.
        toolsets: The @toolset classes to load. When given, the calling
            namespace is not scanned at all, so imports exist only for the
            classes named here and need no ``# noqa: F401``. When omitted,
            every @toolset class visible to the caller is discovered.

            The list order does not reach the navigation tree: build_tree()
            sorts toolsets and tools by label. Pass an explicit list to
            control *what* loads, not what order it appears in.

    Raises:
        RuntimeError: If no @toolset class is visible in the calling namespace,
            or if ``toolsets`` is an empty sequence.
        TypeError: If ``toolsets`` holds anything that is not a @toolset class.
    """
    if db_path is not None:
        set_db_path(Path(db_path))

    if toolsets is None:
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
    else:
        toolset_classes = _check_explicit_toolsets(toolsets)

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_icon_path())))
    _apply_fonts(app)
    _apply_theme(app)

    init_db()
    tree = build_tree(*toolset_classes)

    # Startup hooks run here, before show(): whatever they cost is time the
    # user spends looking at nothing. Nothing below starts the event loop, so
    # neither hook may wait on a timer or a worker thread.
    problems = _run_startup_hook(on_startup)
    instances, init_problems = _create_instances(tree)
    problems += init_problems
    problems += _run_toolset_hooks(instances)

    # Toolsets that failed to construct have no instance to build pages from.
    tree = [ts for ts in tree if ts.cls in instances]

    from .ui.main_window import MainWindow
    window = MainWindow(tree, title=title, instances=instances)
    window.show()
    _show_startup_problems(problems, window)

    sys.exit(app.exec())


def _check_explicit_toolsets(toolsets: Sequence[type]) -> list[type]:
    """Validate the explicit toolsets list handed to gui_main().

    Args:
        toolsets: The sequence passed as ``gui_main(toolsets=...)``.

    Returns:
        The same classes as a list, in the caller's order.

    Raises:
        RuntimeError: If the sequence is empty. This is kept distinct from the
            auto-discovery failure so the message can say which one happened.
        TypeError: If an entry is not a class decorated with @toolset.
    """
    toolset_classes = list(toolsets)
    if not toolset_classes:
        raise RuntimeError(
            "gui_main(toolsets=[]) was given an empty list. Pass the @toolset "
            "classes to load, or omit the argument to discover them from the "
            "calling namespace."
        )

    for candidate in toolset_classes:
        if not (isinstance(candidate, type) and hasattr(candidate, _TOOLSET_ATTR)):
            name = getattr(candidate, "__name__", repr(candidate))
            raise TypeError(
                f"gui_main(toolsets=...) got {name}, which is not decorated "
                f"with @toolset"
            )
    return toolset_classes


@dataclass(frozen=True)
class StartupProblem:
    """One failure recorded while starting the application.

    Attributes:
        source: What failed, in user-facing terms.
        summary: One-line reason, shown in the dialog body.
        detail: Full traceback, shown behind the dialog's Details button.
    """

    source: str
    summary: str
    detail: str


def _run_startup_hook(on_startup: Callable[[], None] | None) -> list[StartupProblem]:
    """Run the application startup hook, if one was given.

    Called at step 3: QApplication exists, the database is initialised, but no
    toolset instance exists and the event loop has not started. Two consequences
    the hook author has to live with, documented in docs/startup-lifecycle.md:

      * No ``self`` to write to -- that is what ToolSet.on_startup() is for.
      * No event loop -- timers do not fire and QThreadPool results never
        arrive, so waiting on a background thread here deadlocks startup.

    A failure is reported but never fatal: the rest of the application is still
    usable, and a dialog is a better diagnosis than a window that refuses to
    open.

    Args:
        on_startup: Zero-argument callable, or None.

    Returns:
        One problem if the hook raised, otherwise an empty list.
    """
    if on_startup is None:
        return []
    try:
        on_startup()
    except Exception as exc:
        return [StartupProblem(
            source=f"on_startup={_callable_name(on_startup)}",
            summary=f"{type(exc).__name__}: {exc}",
            detail=traceback.format_exc(),
        )]
    return []


def _create_instances(tree: list) -> tuple[dict[type, object], list[StartupProblem]]:
    """Instantiate every registered toolset class before the window appears.

    Creating them eagerly makes ``__init__`` a reliable place to declare state:
    it runs once, after on_startup, and always before the event loop starts.

    A class whose ``__init__`` raises is skipped — there is no object to hang a
    tool page on — but the other toolsets still load.

    Args:
        tree: The toolset tree returned by build_tree().

    Returns:
        A mapping of toolset class to its shared instance, and the failures.
    """
    instances: dict[type, object] = {}
    problems: list[StartupProblem] = []
    for toolset_info in tree:
        try:
            instances[toolset_info.cls] = toolset_info.cls()
        except Exception as exc:
            problems.append(StartupProblem(
                source=f"@toolset('{toolset_info.label}')",
                summary=f"{toolset_info.cls.__name__}.__init__ raised "
                        f"{type(exc).__name__}: {exc}",
                detail=traceback.format_exc(),
            ))
    return instances, problems


def _run_toolset_hooks(instances: dict[type, object]) -> list[StartupProblem]:
    """Call ``on_startup()`` on every toolset instance that defines one.

    Called at step 5, after construction and after the application hook, so a
    toolset can declare its attributes in ``__init__`` and fill them here. A
    failure leaves the instance in place with whatever ``__init__`` declared, so
    its tools still open with fallback values -- which is the whole reason to
    keep ``__init__`` trivial.

    Order between toolsets follows build_tree()'s alphabetical sort and must not
    be relied on; cross-toolset setup belongs in the application hook.

    Args:
        instances: Toolset instances created by _create_instances().

    Returns:
        One problem per hook that raised.
    """
    problems: list[StartupProblem] = []
    for cls, instance in instances.items():
        hook = getattr(instance, "on_startup", None)
        if not callable(hook) or hasattr(hook, _TOOL_ATTR):
            continue
        try:
            hook()
        except Exception as exc:
            problems.append(StartupProblem(
                source=f"{cls.__name__}.on_startup()",
                summary=f"{type(exc).__name__}: {exc}",
                detail=traceback.format_exc(),
            ))
    return problems


def _show_startup_problems(problems: list[StartupProblem], parent=None) -> None:
    """Report startup failures in a modal dialog over the main window.

    Args:
        problems: Failures collected during startup; nothing is shown if empty.
        parent: Widget the dialog is modal to.
    """
    if not problems:
        return

    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Startup problems")
    box.setText(
        f"{len(problems)} startup step(s) failed.\n"
        f"The application is running without them."
    )
    box.setInformativeText(
        "\n".join(f"• {problem.source}\n    {problem.summary}" for problem in problems)
    )
    box.setDetailedText(
        "\n\n".join(f"--- {problem.source} ---\n{problem.detail}" for problem in problems)
    )
    box.exec()


def _callable_name(target: Callable) -> str:
    """Return a readable name for a callback, for use in error messages.

    Args:
        target: Any callable.

    Returns:
        Its qualified name, or its repr when it has none.
    """
    return getattr(target, "__qualname__", None) or repr(target)


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
/* Tabs */
QTabWidget::pane {
    border: none;
    border-top: 1px solid #e4e7ef;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #eef1f7;
    border: 1px solid #d9deea;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 12px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #3b5bdb;
}
/* Close affordance installed by MainWindow; Qt's built-in one is unusable here
   because styling QTabBar::tab stops it being painted on the selected tab and
   its position cannot be nudged in from the tab edge. */
QToolButton#tabCloseButton {
    background-color: transparent;
    border: none;
    border-radius: 3px;
}
QToolButton#tabCloseButton:hover {
    background-color: #e4e7ef;
}
QToolButton#tabCloseButton:pressed {
    background-color: #d0d5e0;
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
    """Set the application font to the first available CJK-capable UI face.

    The families are tried in order and Qt falls back through them, so the same
    stylesheet renders on Windows, macOS and Linux without per-platform code.

    Args:
        app: The QApplication to configure.
    """
    from PySide6.QtGui import QFont
    ui_font = QFont()
    ui_font.setFamilies(["Microsoft YaHei", "Meiryo", "Segoe UI", "sans-serif"])
    ui_font.setPointSize(10)
    app.setFont(ui_font)


def _apply_theme(app) -> None:
    """Install the light stylesheet shared by every decoui window.

    Args:
        app: The QApplication to configure.
    """
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
