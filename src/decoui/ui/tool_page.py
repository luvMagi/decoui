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
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
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
from ..engine.executor import ExecutionEngine, render_result
from ..registry import ToolInfo
from ..i18n import t
from ..theme import active_theme, apply_label_case
from ..widget_builder import (
    build_widget,
    coerce_params,
    completion_target,
    get_value,
    set_value,
)
from .icons import theme_icon
from .log_window import (
    LogEntry,
    LogWindow,
    console_style,
    default_color,
    insert_log_line,
    level_inks,
    timestamp_color,
)

#: How much of a rendered return value the result buttons show in their
#: tooltip. Generous next to history's 60-character column preview, because a
#: tooltip has the room and this is the only place the value is legible at all.
_RESULT_PREVIEW_CHARS = 200

#: Half the rule drawn around the word on the console's result banner, written
#: on both sides of it. A fixed length rather than padding to a total width:
#: the translated word is not as long as "Result", and stretching the rule to
#: hide that would make the banner a different shape in every language.
_RESULT_RULE = "=" * 10

#: Status badge -> the theme colour token that inks it.
_STATUS_INK = {
    "running": "text.on_running",
    "success": "text.on_success",
    "error": "text.on_danger",
    "cancelled": "text.on_neutral",
}

#: Status badge -> the theme colour token that fills it.
_STATUS_TOKENS = {
    "running": "running",
    "success": "success",
    "error": "danger",
    "cancelled": "neutral",
}


def _small_button_style(theme) -> str:
    """Return the stylesheet for the console's compact buttons.

    Args:
        theme: The active theme.

    Returns:
        A stylesheet setting only padding and the theme's small text size; the
        colours still come from the application stylesheet's QPushButton rules.
    """
    return f"padding: 0 10px; font-size: {theme.font.small_size_pt:g}pt;"


def _status_style(status: str) -> str:
    """Build the pill stylesheet for one run status.

    Read from the theme at call time rather than baked into a module constant,
    so the badge follows whichever theme the application started under.

    Args:
        status: One of the keys of :data:`_STATUS_TOKENS`.

    Returns:
        A stylesheet for the status label.
    """
    theme = active_theme()
    fill = theme.colors[_STATUS_TOKENS[status]]
    # Each badge sits on its own fill, and each fill has its own ink: a theme
    # may make Done a bright colour that needs dark text while Error stays dark.
    ink = _STATUS_INK[status]
    return (
        f"color:{theme.colors[ink]}; background:{fill}; "
        f"border-radius:{theme.shape['shape.radius_pill']:g}px; padding:2px 10px;"
    )


class ToolPage(QWidget):
    """One tool rendered as a page: parameter form, run controls, console.

    This is what a ``@tool`` method turns into. The layout is derived entirely
    from the tool's metadata -- there is no place for a tool author to inject
    widgets, and none is needed.

    What the user gets, and where it comes from:

    ==============================  =========================================
    Form fields                     parameter annotations, via widget_builder
    Field labels / placeholders      ``labels`` / ``placeholders`` / ``F``
    Red asterisk                     parameter has no default
    Confirmation dialog              ``@tool(confirm=True)``
    Progress bar                     :func:`decoui.progress`
    Console                          the tool's ``print`` and ``logging``
    Stop button                      cancels; runs ``on_cancel`` first
    Replay                           the run history for this tool
    ==============================  =========================================

    The tool's return value is never drawn into the page's own furniture -- it
    is made actionable instead. Copy Result puts it on the clipboard and Send
    Result hands it to another tool's field; both carry a preview in their
    tooltip, because a button for something invisible is worth explaining.
    Under ``print_result`` it also reaches the console, but as one more line of
    output rather than as a widget of its own.

    Attributes:
        history_requested: Emitted with the tool id when Replay is pressed, so
            the main window can open the History page filtered to this tool.
        send_requested: ``(target_tool_id, param_name, value)`` when Send Result
            is used. The page does not know how to reach another page, so the
            main window does the routing -- the same division as Replay.
    """

    history_requested = Signal(str)   # emits tool_id
    send_requested = Signal(str, str, object)   # (tool_id, param_name, value)

    def __init__(
        self,
        tool_info: ToolInfo,
        instance,
        parent=None,
        assist_runner=None,
        send_targets: list[tuple[str, str, str]] | None = None,
        app_print_result: bool = False,
    ):
        """Build the page for one tool and wire it to its own execution engine.

        Args:
            tool_info: The tool to render.
            instance: The toolset instance its method is called on. The same
                instance is used for every assist callback and for on_cancel.
            parent: Qt parent widget.
            assist_runner: Strategy used to run completion callbacks. Defaults
                to the standard runner; tests substitute a synchronous one.
            send_targets: Where this tool's return value may be sent, as
                ``(target_tool_id, "ToolSet: Tool", param_name)``. Worked out by
                the main window from the registry's field index. Empty or None
                means no Send Result button is built at all -- a disabled one
                would promise a destination that does not exist.
            app_print_result: The application's ``gui_main(print_result=...)``.
                Used only where this tool declares nothing of its own.

        Note:
            Each page owns a private ExecutionEngine, so pages run
            independently. Two pages can therefore run tools at the same time --
            see :mod:`decoui.engine.worker` for what that means for stdout.
        """
        super().__init__(parent)
        self._tool = tool_info
        self._instance = instance
        self._engine = ExecutionEngine(self)
        self._start_time: float = 0.0
        self._widgets: dict[str, QWidget] = {}
        self._log_records: list[LogEntry] = []
        self._open_log_windows: list = []
        self._send_targets = list(send_targets or ())
        # The live object, not its rendering: Send hands the real value to a
        # field declared for the same type, which is the whole reason the two
        # ends are matched by type rather than by name. Holding it costs the
        # memory of whatever the tool returned, so it is dropped the moment the
        # next run starts -- see _on_run.
        self._result: Any = None
        # Resolved once, here: the tool's own answer wins, and None means it
        # gave none -- which is why this is not `tool_info.print_result or ...`.
        self._print_result = (
            tool_info.print_result
            if tool_info.print_result is not None
            else app_print_result
        )
        # The badge stops on whatever the last run ended as, and its colours are
        # written into it at that moment. Kept so a re-theme can re-ink the badge
        # that is on screen instead of leaving the old theme's fill there.
        self._status: str | None = None
        # Labels carrying the required-field asterisk, with the text it prefixes.
        # The asterisk is inked inside rich text, which no stylesheet reaches.
        self._required_labels: list[tuple[QLabel, str]] = []
        # Read once, here: _append_log runs per output line, and rebuilding the
        # ink mapping there put a file read and a full theme validation on the
        # GUI thread for every line the tool printed. A re-theme refreshes both
        # -- see retheme() -- rather than moving the lookup back onto that path.
        self._level_inks = level_inks()
        self._default_color = default_color()
        self._timestamp_color = timestamp_color()
        self._assist_runner = assist_runner or AssistRunner()
        self._completions: dict[str, CompletionController] = {}
        self._cascade: CascadeController | None = None

        self._build_ui()
        self._apply_defaults()
        self._setup_assist()
        self._engine.log_line.connect(self._append_log)
        self._engine.finished.connect(self._on_finished)
        self._engine.progress.connect(self._on_progress)
        # Pages are built after the window, so they need their own pass.
        apply_label_case(self)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        """Assemble the header, parameter form, controls and console.

        Colours are not written here. Everything this page inks itself is set by
        :meth:`_apply_styles`, called at the end, so that a re-theme runs the
        same code rather than a second copy of it.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Separates the page from the tab row above it. It lives here rather
        # than in the stylesheet because the tab widget runs in document mode,
        # where Qt draws neither QTabWidget::pane's border nor one on the tab
        # bar -- the page is the only part of that boundary we control.
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        root.addWidget(separator)
        self._separator = separator

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(8)
        root.addLayout(body)
        root = body

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(f"<b>{self._tool.label}</b>", self)
        self._title = title
        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet("background: transparent;")
        self._param_toggle_btn = QPushButton(t("tool.parameters_expanded"), self)
        self._param_toggle_btn.setCheckable(True)
        self._param_toggle_btn.setChecked(True)
        self._param_toggle_btn.clicked.connect(self._toggle_params)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._status_label)
        header.addWidget(self._param_toggle_btn)
        root.addLayout(header)

        # ── Description ───────────────────────────────────────────────────────
        self._desc: QLabel | None = None
        if self._tool.description:
            desc = QLabel(self._tool.description, self)
            desc.setWordWrap(True)
            root.addWidget(desc)
            self._desc = desc

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
            lbl = QLabel(f'{text}:', self._param_panel)
            if not param.has_default:
                self._required_labels.append((lbl, text))
            form_layout.addRow(lbl, w)

        root.addWidget(self._param_panel)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._run_btn = QPushButton(t("tool.run"), self)
        self._run_btn.setObjectName("run_btn")
        self._run_btn.setDefault(True)
        self._run_btn.clicked.connect(self._on_run)
        self._reset_btn = QPushButton(t("tool.reset"), self)
        self._reset_btn.clicked.connect(self._reset_params)
        self._reset_btn.setIcon(
            theme_icon("reset", ratio=self.devicePixelRatioF())
        )
        self._stop_btn = QPushButton(t("tool.stop"), self)
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._engine.cancel)
        self._replay_btn = QPushButton(t("tool.replay"), self)
        self._replay_btn.clicked.connect(
            lambda: self.history_requested.emit(self._tool.tool_id)
        )
        # Everything to the right of the stretch is "what to do now the run is
        # over"; everything left of it acts on the run itself. Copy and Send
        # belong on that side with Replay, and they belong in this row rather
        # than under the console: the row is always on screen, while a long log
        # would push anything below it out of view exactly when it is wanted.
        self._copy_result_btn = QPushButton(t("tool.copy_result"), self)
        self._copy_result_btn.clicked.connect(self._copy_result)

        self._send_result_btn: QPushButton | None = None
        if self._send_targets:
            self._send_result_btn = QPushButton(t("tool.send_result"), self)
            if len(self._send_targets) == 1:
                self._send_result_btn.clicked.connect(self._send_result_to_only)
            else:
                self._send_result_btn.setMenu(self._build_send_menu())

        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._copy_result_btn)
        if self._send_result_btn is not None:
            btn_row.addWidget(self._send_result_btn)
        btn_row.addWidget(self._replay_btn)
        root.addLayout(btn_row)

        self._refresh_result_buttons()

        # ── Output section header ─────────────────────────────────────────────
        out_hdr = QHBoxLayout()
        out_hdr.setContentsMargins(0, 4, 0, 0)
        out_lbl = QLabel(t("tool.output"), self)
        self._out_lbl = out_lbl
        out_hdr.addWidget(out_lbl)
        out_hdr.addStretch()
        self._copy_btn = QPushButton(t("tool.copy"), self)
        self._copy_btn.setFixedHeight(24)
        self._copy_btn.clicked.connect(self._copy_console)
        self._expand_btn = QPushButton(t("tool.view_log"), self)
        self._expand_btn.setFixedHeight(24)
        self._expand_btn.clicked.connect(self._expand_console)
        out_hdr.addWidget(self._copy_btn)
        out_hdr.addWidget(self._expand_btn)
        root.addLayout(out_hdr)

        # ── Output console ────────────────────────────────────────────────────
        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setMinimumHeight(120)
        self._console.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._console)

        self._apply_styles()

    # ── Theming ───────────────────────────────────────────────────────────────

    def _apply_styles(self) -> None:
        """Write every colour this page inks itself, from the active theme.

        These are the parts the application stylesheet cannot reach: a frame
        used as a hairline, rich text carrying its own colour, and the console,
        which is meant to read as a terminal rather than as part of the page.
        """
        theme = active_theme()
        colors, shape, font = theme.colors, theme.shape, theme.font

        self._separator.setStyleSheet(
            f"background: {colors['border.panel']}; border: none;"
        )
        self._title.setStyleSheet(
            f"font-size: {font.title_size_px:g}px; color: {colors['text.primary']};"
        )
        if self._desc is not None:
            self._desc.setStyleSheet(
                f"color: {colors['text.muted']};"
                f"border: {shape['shape.border_width_panel']:g}px "
                f"{shape['shape.border_style_panel']} {colors['border.subtle']};"
                f"border-radius: {shape['shape.radius_panel']:g}px;"
                "padding: 8px 12px;"
                f"background: {colors['bg.header']};"
            )
        self._out_lbl.setStyleSheet(
            f"font-weight: bold; color: {colors['text.muted']}; "
            f"font-size: {font.small_size_pt:g}pt; background: transparent;"
        )
        self._copy_btn.setStyleSheet(_small_button_style(theme))
        self._expand_btn.setStyleSheet(_small_button_style(theme))
        # Redrawn rather than restyled: an icon is a pixmap, and no stylesheet
        # reaches inside one.
        self._reset_btn.setIcon(theme_icon("reset", ratio=self.devicePixelRatioF()))
        self._console.setStyleSheet(console_style())

        # Labels may come from user metadata, so they are escaped before going
        # into the rich text that draws the required-field marker.
        required = colors["text.required"]
        for label, text in self._required_labels:
            label.setText(f'<span style="color:{required}">*</span>{text}:')

        # The badge is written when a run changes state, so nothing else would
        # repaint it until the next run -- which may be never.
        if self._status is not None:
            self._status_label.setStyleSheet(_status_style(self._status))

    def retheme(self) -> None:
        """Repaint the page, and its console, under the new active theme.

        The run is not touched: no widget is replaced, the form keeps its
        values, and a tool that is running goes on running. What changes is
        colour -- including the colour of output already printed, which is
        re-inked from the records the page keeps, the same way the log window
        re-inks its own copy.

        Note:
            The console is rebuilt, so its scroll position is lost and the view
            returns to the newest line. Known and accepted: re-inking text in
            place would mean walking the document per line, and a theme change
            is a deliberate act, not something that happens mid-read.
        """
        self._level_inks = level_inks()
        self._default_color = default_color()
        self._timestamp_color = timestamp_color()
        self._apply_styles()
        self._rerender_console()

    def _rerender_console(self) -> None:
        """Redraw every line the page has kept, in the active theme's colours."""
        self._console.clear()
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for record in self._log_records:
            insert_log_line(
                cursor, record.level, record.message,
                self._level_inks, self._default_color, self._timestamp_color,
            )
        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()

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
        """Animate the parameter panel shut, as happens when a run starts."""
        self._anim = QPropertyAnimation(self._param_panel, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.setStartValue(self._param_panel.sizeHint().height())
        self._anim.setEndValue(0)
        self._anim.start()
        self._param_toggle_btn.setChecked(False)
        self._param_toggle_btn.setText(t("tool.parameters_collapsed"))

    def _expand_params(self):
        """Animate the parameter panel open again."""
        self._anim = QPropertyAnimation(self._param_panel, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.setStartValue(0)
        self._anim.setEndValue(self._param_panel.sizeHint().height() or 400)
        self._anim.start()
        self._param_toggle_btn.setChecked(True)
        self._param_toggle_btn.setText(t("tool.parameters_expanded"))

    def _toggle_params(self):
        """Open or close the parameter panel to match the toggle button."""
        if self._param_toggle_btn.isChecked():
            self._expand_params()
        else:
            self._collapse_params()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_run(self):
        """Confirm, read and coerce the form, then start the run.

        Nothing starts if coercion fails: the errors are printed to the console
        as ERROR entries and the form stays editable. This is the only place a
        parameter type mismatch is reported -- the tool body never sees a value
        it did not ask for.
        """
        if self._tool.confirm:
            reply = QMessageBox.question(
                self, t("tool.confirm_title"),
                t("tool.confirm_body", tool=self._tool.label),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        raw = {name: get_value(w) for name, w in self._widgets.items()}
        params, errors = coerce_params(self._tool, raw)

        self._console.clear()
        self._log_records.clear()
        # Dropped here rather than when the next run ends: a tool that returned
        # something large would otherwise stay held for the whole of the next
        # run as well, for no benefit -- the buttons are already disabled.
        self._result = None
        self._refresh_result_buttons()

        if errors:
            for tb in errors:
                self._append_log("ERROR", tb)
            return

        self._start_time = time.monotonic()
        self._run_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._progress.setVisible(True)
        self._set_status("running", t("tool.running"))
        self._set_params_readonly(True)
        self._collapse_params()

        self._engine.run(self._tool, self._instance, params)

    def _on_progress(self, done: int, total: int, message: str) -> None:
        """Show progress reported by the running tool.

        Args:
            done: Units completed so far.
            total: Total units, or 0 when unknown. 0 returns the bar to its
                indeterminate sweep, so a tool that finishes a counted phase and
                moves on to an unbounded one does not leave the bar frozen at
                the last percentage.
            message: Status text, shown in place of "Running…" when non-empty.
        """
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        else:
            self._progress.setRange(0, 0)
        if message:
            self._status_label.setText(message)

    def _on_finished(self, result: Any, status: str):
        """Restore the idle state and show how the run ended.

        Args:
            result: The tool's return value. Held -- as the object, not as
                text -- so Copy Result and Send Result have something to act
                on. Still not drawn anywhere on the page.
            status: ``'success'``, ``'error'`` or ``'cancelled'``.
        """
        # Only a successful run has a return value. An error's is None because
        # the tool never reached its return statement, and a cancelled one's is
        # None because the exception was injected before it did.
        self._result = result if status == "success" else None
        self._refresh_result_buttons()

        elapsed = time.monotonic() - self._start_time
        self._progress.setVisible(False)
        # Back to indeterminate, so the next run does not start from the last
        # run's percentage.
        self._progress.setRange(0, 0)
        self._run_btn.setVisible(True)
        self._run_btn.setText(t("tool.run_again"))
        self._stop_btn.setVisible(False)
        self._set_params_readonly(False)

        if status == "success":
            self._set_status("success", t("tool.done", elapsed=f"{elapsed:.1f}"))
            self._print_result_lines()
        elif status == "error":
            self._set_status("error", t("tool.error", elapsed=f"{elapsed:.1f}"))
        else:
            self._set_status("cancelled", t("tool.cancelled"))

    def _print_result_lines(self) -> None:
        """Write the finished run's return value to the console, if asked to.

        Three lines rather than one: a blank one so the value does not read as
        the continuation of whatever the tool last printed, the banner that
        names what follows, and the value itself. They are appended as ordinary
        stdout lines, which is what makes them stored with the run, re-openable
        from history, and reachable by the log window's filter and search.

        The text is :func:`render_result`'s, the same renderer the history
        record and Copy Result use, so one run cannot read two ways.
        """
        if not self._print_result:
            return
        text = render_result(self._result)
        # None is "the tool returned nothing" -- printing the word None would
        # be decoui inventing output the run did not have.
        if text is None:
            return
        rule = _RESULT_RULE
        self._append_log("stdout", "")
        self._append_log("stdout", f"{rule} {t('tool.result_banner')} {rule}")
        self._append_log("stdout", text)

    def _set_status(self, status: str, text: str) -> None:
        """Show one run state on the badge, and record which one it is.

        The badge is the only part of the page whose colour depends on
        something other than the theme, so it is the only one a re-theme cannot
        work out for itself. Recording the state here is what lets
        :meth:`_apply_styles` re-ink it later.

        Args:
            status: One of the keys of :data:`_STATUS_TOKENS`.
            text: The label to show, already translated.
        """
        self._status = status
        self._status_label.setText(text)
        self._status_label.setStyleSheet(_status_style(status))

    def _append_log(self, level: str, message: str):
        """Append one coloured line to the console.

        Args:
            level: ``'stdout'`` or a logging level name; selects the colour.
            message: The line text.
        """
        self._log_records.append(LogEntry(level, message))

        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        insert_log_line(
            cursor, level, message,
            self._level_inks, self._default_color, self._timestamp_color,
        )
        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()

    # ── The return value ──────────────────────────────────────────────────────

    def _build_send_menu(self) -> QMenu:
        """Build the destination menu for a value with more than one target.

        Returns:
            A menu with one entry per destination, reading
            ``ToolSet: Tool → field``. Entries follow the registry's order, so
            the menu reads in the same order as the sidebar.
        """
        menu = QMenu(self)
        for tool_id, display, param_name in self._send_targets:
            action = menu.addAction(f"{display} → {param_name}")
            action.triggered.connect(
                lambda _checked=False, tid=tool_id, pname=param_name:
                self.send_requested.emit(tid, pname, self._result)
            )
        return menu

    def _send_result_to_only(self) -> None:
        """Send the result to the single destination it has.

        A one-entry menu would be a click and a decision for something with no
        alternative, so the button acts directly instead.
        """
        tool_id, _display, param_name = self._send_targets[0]
        self.send_requested.emit(tool_id, param_name, self._result)

    def _copy_result(self) -> None:
        """Put the run's return value on the clipboard.

        Uses the same rendering the history record stores, so a value copied
        from here and the same value read back out of history are the same text.
        """
        text = render_result(self._result)
        if text is not None:
            QApplication.clipboard().setText(text)

    def _refresh_result_buttons(self) -> None:
        """Enable, disable and re-label the two result buttons.

        Called after every run and whenever the held value is dropped. The
        tooltip is where the preview lives: the value is not drawn on the page,
        so without it the buttons would be two controls for something the user
        cannot see at all.
        """
        text = render_result(self._result)
        if text is None:
            tooltip = t("tool.result_none")
        else:
            tooltip = text if len(text) <= _RESULT_PREVIEW_CHARS else (
                text[:_RESULT_PREVIEW_CHARS] + "…"
            )

        for button in (self._copy_result_btn, self._send_result_btn):
            if button is None:
                continue
            button.setEnabled(text is not None)
            button.setToolTip(tooltip)

    def _copy_console(self):
        """Copy the whole console to the clipboard."""
        QApplication.clipboard().setText(self._console.toPlainText())

    def _expand_console(self):
        """Open the current output in a separate, filterable log window."""
        win = LogWindow(self._tool.label, list(self._log_records))
        win.show()
        self._open_log_windows.append(win)

    def _reset_params(self):
        """Clear the console and reopen the form.

        Parameter values are kept: Reset undoes the run, not the input.
        """
        self._console.clear()
        self._log_records.clear()
        self._expand_params()

    def _set_params_readonly(self, readonly: bool):
        """Lock or unlock the form while a run is in flight.

        Args:
            readonly: True disables the panel and suspends assist callbacks, so
                a cascade cannot fire against a form the user cannot see.
        """
        self._param_panel.setEnabled(not readonly)
        self._set_assist_suspended(readonly)

    def set_param(self, name: str, value: Any) -> None:
        """Write one field, as if the user had just filled it in.

        Used by Send Result. Deliberately different from :meth:`restore_params`
        in one respect: the cascade is **told**, rather than suspended. That
        method restores a whole set at once, where a cascade would overwrite the
        very values being replayed; this one writes a single field, and a
        cascade firing from it is the point -- setting an artifact id should
        still bring its version along, exactly as typing the id would.

        The notification has to be explicit. ``set_value`` writes through
        ``setText`` and friends, which emit no commit signal, so leaving the
        cascade merely un-suspended would have left it silent.

        Args:
            name: Parameter name. An unknown one is ignored, so a tool whose
                signature changed cannot break the sender.
            value: The value to write. Coerced by the widget; one it refuses is
                skipped rather than raised, matching replay's tolerance.
        """
        widget = self._widgets.get(name)
        if widget is None:
            return
        try:
            set_value(widget, value)
        except Exception:
            # Same policy as restore_params: a value that will not fit is not
            # worth failing a transfer the user asked for, and the field simply
            # keeps what it had.
            return
        if self._cascade is not None:
            self._cascade.notify_commit(name)

    def restore_params(self, param_map: dict[str, Any]):
        """Refill the form from a past run, for Replay.

        Args:
            param_map: Parameter name to value, as recovered from history.
                Unknown names are ignored and a value the widget rejects is
                skipped, so a replay never fails outright after a signature
                change -- it just restores what still fits.
        """
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
