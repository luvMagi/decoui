"""Tool page: parameter form + animated collapse + output console."""
from __future__ import annotations

import time
import traceback
from html import escape
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..assist import (
    AssistRunner,
    CascadeController,
    CompletionController,
    apply_defaults,
    read_form,
    resolve_defaults,
)
from ..engine.executor import ExecutionEngine
from ..registry import ToolInfo
from ..widget_builder import (
    build_widget,
    coerce_params,
    completion_target,
    get_value,
    set_value,
)
from .log_window import LEVEL_COLORS, LogEntry, LogWindow

_STATUS_STYLES = {
    "running":   "color:#fff; background:#3b5bdb; border-radius:10px; padding:2px 10px;",
    "success":   "color:#fff; background:#2b9348; border-radius:10px; padding:2px 10px;",
    "error":     "color:#fff; background:#dc3545; border-radius:10px; padding:2px 10px;",
    "cancelled": "color:#fff; background:#6c757d; border-radius:10px; padding:2px 10px;",
}


class ToolPage(QWidget):
    history_requested = Signal(str)   # emits tool_id

    def __init__(self, tool_info: ToolInfo, instance, parent=None, assist_runner=None):
        super().__init__(parent)
        self._tool = tool_info
        self._instance = instance
        self._engine = ExecutionEngine(self)
        self._start_time: float = 0.0
        self._widgets: dict[str, QWidget] = {}
        self._log_records: list[LogEntry] = []
        self._open_log_windows: list = []
        self._assist_runner = assist_runner or AssistRunner()
        self._completions: dict[str, CompletionController] = {}
        self._cascade: CascadeController | None = None

        self._build_ui()
        self._apply_defaults()
        self._setup_assist()
        self._engine.log_line.connect(self._append_log)
        self._engine.finished.connect(self._on_finished)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(f"<b>{self._tool.label}</b>", self)
        title.setStyleSheet("font-size: 15px; color: #1e2128;")
        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet("background: transparent;")
        self._param_toggle_btn = QPushButton("▼ Parameters", self)
        self._param_toggle_btn.setCheckable(True)
        self._param_toggle_btn.setChecked(True)
        self._param_toggle_btn.clicked.connect(self._toggle_params)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._status_label)
        header.addWidget(self._param_toggle_btn)
        root.addLayout(header)

        # ── Description ───────────────────────────────────────────────────────
        if self._tool.description:
            desc = QLabel(self._tool.description, self)
            desc.setWordWrap(True)
            desc.setStyleSheet(
                "color: #5a6275;"
                "border: 1px solid #e0e3ea;"
                "border-radius: 8px;"
                "padding: 8px 12px;"
                "background: #f8f9fc;"
            )
            root.addWidget(desc)

        # ── Progress bar (hidden until run) ───────────────────────────────────
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # ── Parameter form (collapsible) ──────────────────────────────────────
        self._param_panel = QWidget(self)
        form_layout = QFormLayout(self._param_panel)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        for param in self._tool.params:
            w = build_widget(param, self._param_panel)
            self._widgets[param.name] = w
            # Labels may come from user metadata, so they are escaped before
            # going into the rich text that draws the required-field marker.
            text = escape(param.label or param.name)
            if not param.has_default:
                lbl = QLabel(f'<span style="color:#e05252">*</span>{text}:', self._param_panel)
            else:
                lbl = QLabel(f'{text}:', self._param_panel)
            form_layout.addRow(lbl, w)

        root.addWidget(self._param_panel)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._run_btn = QPushButton("▶  Run", self)
        self._run_btn.setObjectName("run_btn")
        self._run_btn.setDefault(True)
        self._run_btn.clicked.connect(self._on_run)
        self._reset_btn = QPushButton("↺  Reset", self)
        self._reset_btn.clicked.connect(self._reset_params)
        self._stop_btn = QPushButton("■  Stop", self)
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._engine.cancel)
        self._replay_btn = QPushButton("Replay", self)
        self._replay_btn.clicked.connect(
            lambda: self.history_requested.emit(self._tool.tool_id)
        )
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._replay_btn)
        root.addLayout(btn_row)

        # ── Output section header ─────────────────────────────────────────────
        out_hdr = QHBoxLayout()
        out_hdr.setContentsMargins(0, 4, 0, 0)
        out_lbl = QLabel("Output", self)
        out_lbl.setStyleSheet("font-weight: bold; color: #667085; font-size: 9pt; background: transparent;")
        out_hdr.addWidget(out_lbl)
        out_hdr.addStretch()
        self._copy_btn = QPushButton("Copy", self)
        self._copy_btn.setFixedHeight(24)
        self._copy_btn.setStyleSheet("padding: 0 10px; font-size: 9pt;")
        self._copy_btn.clicked.connect(self._copy_console)
        self._expand_btn = QPushButton("View Log", self)
        self._expand_btn.setFixedHeight(24)
        self._expand_btn.setStyleSheet("padding: 0 10px; font-size: 9pt;")
        self._expand_btn.clicked.connect(self._expand_console)
        out_hdr.addWidget(self._copy_btn)
        out_hdr.addWidget(self._expand_btn)
        root.addLayout(out_hdr)

        # ── Output console ────────────────────────────────────────────────────
        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setMinimumHeight(120)
        self._console.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._console.setStyleSheet(
            "background:#1e1e1e; color:#ffffff; border-radius:6px;"
            "font-family: Consolas, 'Microsoft YaHei', Meiryo, monospace;"
            "font-size: 10pt;"
        )
        root.addWidget(self._console)

    # ── Form assist ───────────────────────────────────────────────────────────

    def _apply_defaults(self) -> None:
        """Fill the form from the tool's `defaults` spec.

        Evaluated here rather than at import time, so the callback can read data
        that only becomes available once the application has started.
        """
        if not self._tool.defaults:
            return
        try:
            values = resolve_defaults(self._tool.defaults, self._instance, self._read_form())
        except Exception:
            self._append_log("WARNING", f"defaults failed:\n{traceback.format_exc()}")
            return

        for problem in apply_defaults(self._widgets, values):
            self._append_log("WARNING", f"defaults could not apply {problem}")

    def _setup_assist(self) -> None:
        """Attach completion popups and cascading fill handlers to the form."""
        if not self._tool.completions and not self._tool.cascade:
            return

        for name, spec in self._tool.completions.items():
            widget = self._widgets.get(name)
            target = completion_target(widget) if widget is not None else None
            if target is None:
                continue  # Rejected by validate_assist_config; guard anyway.
            controller = CompletionController(
                param_name=name,
                line_edit=target,
                spec=spec,
                instance=self._instance,
                form_reader=self._read_form,
                debounce_ms=self._tool.completion_debounce_ms,
                runner=self._assist_runner,
                parent=self,
            )
            controller.failed.connect(self._on_assist_warning)
            self._completions[name] = controller

        self._cascade = CascadeController(
            tool_info=self._tool,
            widgets=self._widgets,
            instance=self._instance,
            runner=self._assist_runner,
            parent=self,
        )
        self._cascade.failed.connect(self._on_assist_warning)
        self._cascade.committed.connect(self._on_param_committed)

        for controller in self._completions.values():
            controller.candidate_chosen.connect(self._cascade.notify_commit)

    def _read_form(self) -> dict[str, Any]:
        """Return a snapshot of every parameter's current widget value."""
        return read_form(self._widgets)

    def _on_param_committed(self, _name: str) -> None:
        """Drop cached candidates, since the form snapshot they used is stale."""
        for controller in self._completions.values():
            controller.invalidate_cache()

    def _on_assist_warning(self, message: str) -> None:
        """Show an assist failure in the output console.

        Args:
            message: Human-readable warning text.
        """
        self._append_log("WARNING", message)

    def _set_assist_suspended(self, suspended: bool) -> None:
        """Enable or disable all assist lookups for this page.

        Args:
            suspended: True while the tool runs or a bulk restore is in progress.
        """
        for controller in self._completions.values():
            controller.set_suspended(suspended)
        if self._cascade is not None:
            self._cascade.set_suspended(suspended)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _collapse_params(self):
        self._anim = QPropertyAnimation(self._param_panel, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.setStartValue(self._param_panel.sizeHint().height())
        self._anim.setEndValue(0)
        self._anim.start()
        self._param_toggle_btn.setChecked(False)
        self._param_toggle_btn.setText("▶ Parameters")

    def _expand_params(self):
        self._anim = QPropertyAnimation(self._param_panel, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.setStartValue(0)
        self._anim.setEndValue(self._param_panel.sizeHint().height() or 400)
        self._anim.start()
        self._param_toggle_btn.setChecked(True)
        self._param_toggle_btn.setText("▼ Parameters")

    def _toggle_params(self):
        if self._param_toggle_btn.isChecked():
            self._expand_params()
        else:
            self._collapse_params()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_run(self):
        if self._tool.confirm:
            reply = QMessageBox.question(
                self, "Confirm", f"Run '{self._tool.label}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        raw = {name: get_value(w) for name, w in self._widgets.items()}
        params, errors = coerce_params(self._tool, raw)

        self._console.clear()
        self._log_records.clear()

        if errors:
            for tb in errors:
                self._append_log("ERROR", tb)
            return

        self._start_time = time.monotonic()
        self._run_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._progress.setVisible(True)
        self._status_label.setText("Running…")
        self._status_label.setStyleSheet(_STATUS_STYLES["running"])
        self._set_params_readonly(True)
        self._collapse_params()

        self._engine.run(self._tool, self._instance, params)

    def _on_finished(self, _result: Any, status: str):
        elapsed = time.monotonic() - self._start_time
        self._progress.setVisible(False)
        self._run_btn.setVisible(True)
        self._run_btn.setText("▶  Run Again")
        self._stop_btn.setVisible(False)
        self._set_params_readonly(False)

        if status == "success":
            self._status_label.setText(f"Done ({elapsed:.1f}s)")
            self._status_label.setStyleSheet(_STATUS_STYLES["success"])
        elif status == "error":
            self._status_label.setText(f"Error ({elapsed:.1f}s)")
            self._status_label.setStyleSheet(_STATUS_STYLES["error"])
        else:
            self._status_label.setText("Cancelled")
            self._status_label.setStyleSheet(_STATUS_STYLES["cancelled"])

    def _append_log(self, level: str, message: str):
        self._log_records.append(LogEntry(level, message))

        color = LEVEL_COLORS.get(level, "#FFFFFF")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if level == "CRITICAL":
            fmt.setFontWeight(700)

        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)
        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()

    def _copy_console(self):
        QApplication.clipboard().setText(self._console.toPlainText())

    def _expand_console(self):
        win = LogWindow(self._tool.label, list(self._log_records))
        win.show()
        self._open_log_windows.append(win)

    def _reset_params(self):
        self._console.clear()
        self._log_records.clear()
        self._expand_params()

    def _set_params_readonly(self, readonly: bool):
        self._param_panel.setEnabled(not readonly)
        self._set_assist_suspended(readonly)

    def restore_params(self, param_map: dict[str, Any]):
        # Cascades stay suspended for the whole restore: recomputing derived
        # fields here would overwrite the very values being replayed.
        self._set_assist_suspended(True)
        try:
            for name, value in param_map.items():
                if name in self._widgets:
                    try:
                        set_value(self._widgets[name], value)
                    except Exception:
                        pass
        finally:
            if self._cascade is not None:
                self._cascade.sync_values()
            self._set_assist_suspended(False)
        self._expand_params()
