"""Execution history list with detail expand and replay."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..storage.db import (
    clear_all_records,
    delete_records,
    get_db_size,
    query_logs,
    query_params,
    query_records,
)
from ..i18n import t
from ..storage.models import ExecutionRecord
from .log_window import LogWindow

_COL_CHECK = 0
_COL_TIME  = 1
_COL_TOOL  = 2
_COL_STAT  = 3
_COL_DUR   = 4
_COL_RES   = 5


def _format_size(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string.

    Args:
        num_bytes: Size in bytes.

    Returns:
        The size with a unit suffix, e.g. ``'1.2 MB'``.
    """
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class HistoryPage(QWidget):
    """Browsable record of every run: filters, detail, replay, log, cleanup.

    This page is why a decoui application can answer "what exactly did that run
    do" after the fact -- which tool, which arguments, what it printed, how it
    ended. Replay reads the recorded arguments back into a tool page rather than
    re-running anything, so nothing is executed without the user pressing Run.
    """
    replay_requested = Signal(str, dict)  # (tool_id, param_map)
    close_requested = Signal()           # leave the history view

    def __init__(self, tool_labels: dict[str, str], parent=None):
        """Build the history table and its filter row.

        Args:
            tool_labels: Tool id to display label, used to populate the tool
                filter. Ids missing from it still appear in rows, labelled from
                the record itself.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._tool_labels = tool_labels   # {tool_id: "ToolSet: Tool"}
        self._records: list[ExecutionRecord] = []
        self._build_ui()
        self.refresh()

    def _control_strip(self, row: QHBoxLayout) -> QScrollArea:
        """Wrap a row of controls so it scrolls instead of being clipped.

        These rows do not shrink: their buttons are as wide as their labels, and
        a theme that renders in capitals with extra tracking makes them wider
        still. Left in a plain layout the row is simply cut off at the content
        area's edge, which puts Refresh and Clear History out of reach. Scrolling
        keeps every control reachable at any width.

        Args:
            row: The populated row layout.

        Returns:
            A borderless, transparent scroll area holding that row.
        """
        container = QWidget(self)
        container.setLayout(row)
        container.setStyleSheet("background: transparent;")

        scroll = QScrollArea(self)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Room for the horizontal bar, which only appears when it is needed.
        scroll.setFixedHeight(container.sizeHint().height() + 12)
        return scroll

    def _build_ui(self):
        """Assemble the filter row, the table and the detail strip."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # The page fills the whole content area, so it needs a way out of its
        # own: opening History with no tool tab open used to leave the window
        # with no route back at all.
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel(f"<b>{t('history.heading')}</b>"))
        header_row.addStretch()
        close_btn = QPushButton(t("history.close"), self)
        close_btn.setToolTip(t("history.close_tooltip"))
        close_btn.clicked.connect(self.close_requested)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)

        # ── Filter bar ────────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        self._tool_filter = QComboBox(self)
        # Sized from a fixed character count rather than from its longest entry.
        # Tool labels are written by the application, so left to itself this
        # combo grows without limit and drags the whole page's minimum width
        # along with it. The popup still shows every label in full.
        self._tool_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._tool_filter.setMinimumContentsLength(14)
        self._tool_filter.addItem(t("history.all_tools"), None)
        for tid, label in self._tool_labels.items():
            self._tool_filter.addItem(label, tid)
        self._tool_filter.currentIndexChanged.connect(self.refresh)

        self._status_filter = QComboBox(self)
        # The stored status value is the key, not the label: translating the
        # label must not change what the query filters on.
        self._status_filter.addItem(t("history.all_status"), None)
        for value in ("success", "error", "running", "cancelled"):
            self._status_filter.addItem(t(f"history.status.{value}"), value)
        self._status_filter.currentIndexChanged.connect(self.refresh)

        self._range_filter = QComboBox(self)
        for key, days in [("all", 0), ("today", 1), ("week", 7), ("month", 30)]:
            self._range_filter.addItem(t(f"history.range.{key}"), days)
        self._range_filter.currentIndexChanged.connect(self.refresh)

        refresh_btn = QPushButton(t("history.refresh"), self)
        refresh_btn.clicked.connect(self.refresh)

        self._db_size_label = QLabel("", self)
        self._db_size_label.setToolTip(t("history.db_size_tooltip"))

        self._clear_db_btn = QPushButton(t("history.clear"), self)
        self._clear_db_btn.setToolTip(t("history.clear_tooltip"))
        self._clear_db_btn.clicked.connect(self._clear_database)

        filter_row.addWidget(QLabel(t("history.filter"), self))
        filter_row.addWidget(self._tool_filter)
        filter_row.addWidget(self._status_filter)
        filter_row.addWidget(self._range_filter)
        filter_row.addStretch()
        filter_row.addWidget(self._db_size_label)
        filter_row.addWidget(self._clear_db_btn)
        filter_row.addWidget(refresh_btn)
        layout.addWidget(self._control_strip(filter_row))

        # ── Selection action bar ──────────────────────────────────────────────
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton(t("history.select_all"), self)
        sel_none_btn = QPushButton(t("history.deselect_all"), self)
        self._delete_sel_btn = QPushButton(t("history.delete_selected"), self)
        self._delete_sel_btn.setEnabled(False)
        sel_all_btn.clicked.connect(self._select_all)
        sel_none_btn.clicked.connect(self._deselect_all)
        self._delete_sel_btn.clicked.connect(self._delete_selected)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(sel_none_btn)
        sel_row.addStretch()
        sel_row.addWidget(self._delete_sel_btn)
        layout.addWidget(self._control_strip(sel_row))

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels([
            "",
            t("history.column.timestamp"),
            t("history.column.tool"),
            t("history.column.status"),
            t("history.column.duration"),
            t("history.column.result"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CHECK, 32)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemClicked.connect(self._on_item_clicked)
        self._table.currentCellChanged.connect(self._on_current_cell_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self._table)

        # ── Detail panel ──────────────────────────────────────────────────────
        self._detail = QWidget(self)
        det_layout = QVBoxLayout(self._detail)
        det_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_label = QLabel("", self._detail)
        self._detail_label.setWordWrap(True)
        det_layout.addWidget(self._detail_label)
        det_btn_row = QHBoxLayout()
        self._replay_btn = QPushButton(t("history.replay_params"), self._detail)
        self._replay_btn.clicked.connect(self._do_replay)
        self._log_btn = QPushButton(t("history.view_full_log"), self._detail)
        self._log_btn.clicked.connect(self._view_log)
        det_btn_row.addWidget(self._replay_btn)
        det_btn_row.addWidget(self._log_btn)
        det_btn_row.addStretch()
        det_layout.addLayout(det_btn_row)
        self._detail.setVisible(False)
        layout.addWidget(self._detail)

        self._selected_record: ExecutionRecord | None = None
        self._open_log_windows: list = []

    # ── Refresh ───────────────────────────────────────────────────────────────

    def show_for_tool(self, tool_id: str):
        """Filter the page to one tool, as the Replay button does.

        Args:
            tool_id: ``'ClassName.method_name'``. An id with no matching filter
                entry falls back to an unfiltered refresh.
        """
        for i in range(self._tool_filter.count()):
            if self._tool_filter.itemData(i) == tool_id:
                self._tool_filter.setCurrentIndex(i)
                return
        self.refresh()

    def refresh(self):
        """Re-query the database with the current filters and redraw the table.

        Called after every mutation, so the table never shows deleted rows.
        """
        tool_id = self._tool_filter.currentData()
        status  = self._status_filter.currentData()
        days    = self._range_filter.currentData() or 0
        since   = (datetime.now() - timedelta(days=days)) if days else None

        self._records = query_records(tool_id=tool_id, status=status, since=since)
        self._table.setRowCount(len(self._records))

        for row, rec in enumerate(self._records):
            duration = ""
            if rec.finished_at and rec.started_at:
                secs = (rec.finished_at - rec.started_at).total_seconds()
                duration = f"{secs:.1f}s"

            status_icon = {"success": "✅", "error": "❌", "running": "▶", "cancelled": "⛔"}.get(rec.status, "?")

            # Checkbox cell
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, _COL_CHECK, chk)

            self._table.setItem(row, _COL_TIME, QTableWidgetItem(rec.started_at.strftime("%Y-%m-%d %H:%M:%S")))
            self._table.setItem(row, _COL_TOOL, QTableWidgetItem(rec.tool_label))
            self._table.setItem(row, _COL_STAT, QTableWidgetItem(f"{status_icon} {t(f'history.status.{rec.status}')}"))
            self._table.setItem(row, _COL_DUR,  QTableWidgetItem(duration))

            result_preview = ""
            if rec.result_json:
                try:
                    result_preview = str(json.loads(rec.result_json))[:60]
                except Exception:
                    result_preview = rec.result_json[:60]
            self._table.setItem(row, _COL_RES, QTableWidgetItem(result_preview))

        self._detail.setVisible(False)
        self._update_delete_btn()
        self._update_db_size()

    # ── Database size ─────────────────────────────────────────────────────────

    def _update_db_size(self) -> None:
        """Refresh the size readout from the database's current disk usage."""
        size = get_db_size()
        self._db_size_label.setText(t("history.db_size", size=_format_size(size)))
        self._clear_db_btn.setEnabled(size > 0)

    def _clear_database(self) -> None:
        """Drop every execution record after the user confirms."""
        answer = QMessageBox.warning(
            self,
            "Clear History",
            "Delete all execution records, parameters and logs?\n"
            "This cannot be undone. Application settings are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        clear_all_records()
        self.refresh()

    # ── Checkbox helpers ──────────────────────────────────────────────────────

    def _checked_rows(self) -> list[int]:
        """Return the row indexes whose checkbox is ticked.

        Returns:
            Table row indexes, not record ids.
        """
        return [
            r for r in range(self._table.rowCount())
            if self._table.item(r, _COL_CHECK) and
               self._table.item(r, _COL_CHECK).checkState() == Qt.CheckState.Checked
        ]

    def _select_all(self):
        """Tick every checkbox currently in the table."""
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _COL_CHECK)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self._update_delete_btn()

    def _deselect_all(self):
        """Clear every checkbox in the table."""
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _COL_CHECK)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._update_delete_btn()

    def _update_delete_btn(self):
        """Enable the delete button only while something is ticked."""
        self._delete_sel_btn.setEnabled(len(self._checked_rows()) > 0)

    def _delete_selected(self):
        """Delete the ticked runs, cascading to their params and logs.

        Irreversible, and deliberately without a confirmation dialog -- the
        checkboxes are the confirmation. Disk space is not reclaimed here; only
        Clear History vacuums.
        """
        rows = self._checked_rows()
        ids = [self._records[r].id for r in rows if r < len(self._records)]
        delete_records(ids)
        self.refresh()

    # ── Row click ─────────────────────────────────────────────────────────────

    def _on_current_cell_changed(self, row: int, col: int, prev_row: int, _prev_col: int):
        """Show the detail strip when keyboard navigation changes rows.

        Args:
            row: The newly current row.
            col: The newly current column, unused.
            prev_row: The previously current row.
            _prev_col: The previous column, unused.
        """
        if row != prev_row and row >= 0:
            item = self._table.item(row, _COL_TOOL)
            if item:
                self._on_item_clicked(item)

    def _on_item_clicked(self, item: QTableWidgetItem):
        """Select a run and show its recorded arguments.

        Args:
            item: The clicked cell. A click in the checkbox column only updates
                the delete button; it does not change the selected run.
        """
        row = item.row()
        if row >= len(self._records):
            return

        # Toggle checkbox when clicking the checkbox column
        if item.column() == _COL_CHECK:
            self._update_delete_btn()
            return

        rec = self._records[row]
        self._selected_record = rec
        params = query_params(rec.id)
        param_text = ", ".join(f"{p.param_name}={p.param_value}" for p in params) or "(none)"
        self._detail_label.setText(f"<b>{t('history.params')}</b> {param_text}")
        self._detail.setVisible(True)

    # ── Detail actions ────────────────────────────────────────────────────────

    def _do_replay(self):
        """Emit the selected run's arguments for a tool page to restore.

        Values are read back with ``json.loads`` and fall back to the raw stored
        string when that fails -- the snapshot is lossy, so a Path replays as
        its string form and is re-coerced when the tool is run again.
        """
        if not self._selected_record:
            return
        params = query_params(self._selected_record.id)
        param_map: dict[str, object] = {}
        for p in params:
            try:
                param_map[p.param_name] = json.loads(p.param_value) if p.param_value else None
            except Exception:
                param_map[p.param_name] = p.param_value
        self.replay_requested.emit(self._selected_record.tool_id, param_map)

    def _view_log(self):
        """Open the selected run's stored console output in a log window."""
        if not self._selected_record:
            return
        logs = query_logs(self._selected_record.id)
        dlg = LogWindow(self._selected_record.tool_label, logs)
        dlg.show()
        self._open_log_windows.append(dlg)

    def _context_menu(self, pos):
        """Offer row deletion for the current table selection.

        Args:
            pos: Click position in table viewport coordinates.
        """
        rows = list({idx.row() for idx in self._table.selectedIndexes()})
        if not rows:
            return
        menu = QMenu(self)
        del_act = menu.addAction(t("history.delete_selected_rows"))
        del_act.triggered.connect(lambda: self._delete_rows(rows))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _delete_rows(self, rows: list[int]):
        """Delete runs by table row index.

        Args:
            rows: Row indexes to remove; they are mapped to record ids here.
        """
        ids = [self._records[r].id for r in rows if r < len(self._records)]
        delete_records(ids)
        self.refresh()


