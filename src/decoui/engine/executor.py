"""Execution scheduling and ExecutionRecord lifecycle.

One engine belongs to one tool page and owns one run at a time. It writes the
history record, streams log lines into it, drives cancellation, and re-emits
what the page needs to display.

What a run leaves behind
------------------------

Every press of Run inserts a record *before* the tool starts, so a run that
crashes the process is still visible in the history afterwards. The record holds
the tool id and label, the parameter snapshot, the status, both timestamps and
the serialised return value; the console lines are stored separately and in
batches.

Serialisation is deliberately lossy and never fails: the return value goes
through ``json.dumps(..., default=str)``, and anything that still refuses is
stored as ``str(result)``. Do not treat ``result_json`` as a round-trippable
value.

Progress reports are the exception -- they are re-emitted for the UI and never
written to the log table, because they are transient state, not output.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ..registry import ToolInfo
from ..storage.db import init_db, insert_record, update_record, insert_logs
from ..storage.models import ExecutionLog, ExecutionParam, ExecutionRecord
from .worker import ToolWorker


class ExecutionEngine(QObject):
    """Owns one tool's execution: history record, worker, cancellation.

    Attributes:
        log_line: Console lines, forwarded from the worker.
        finished: ``(result, status)`` once the run ends.
        record_created: The new history record id, emitted before the tool
            starts so the page can link to it immediately.
        progress: ``(done, total, message)``, forwarded from the worker and not
            persisted.
    """

    log_line = Signal(str, str)           # (level, message)
    finished = Signal(object, str)        # (result, status)
    record_created = Signal(int)          # record_id
    progress = Signal(int, int, str)      # (done, total, message)

    def __init__(self, parent=None):
        """Prepare the engine and make sure the history database exists.

        Args:
            parent: Qt parent object.
        """
        super().__init__(parent)
        init_db()
        self._worker: ToolWorker | None = None
        self._tool_info: ToolInfo | None = None
        self._instance: Any = None
        self._cancel_hook_fired: bool = False
        self._record_id: int = 0
        self._log_buffer: list[ExecutionLog] = []
        self._log_seq = 0
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(1000)
        self._flush_timer.timeout.connect(self._flush_logs)

    def run(self, tool_info: ToolInfo, instance, params: dict):
        """Record the run, start the worker, and arm the timeout.

        Args:
            tool_info: The tool to execute.
            instance: The toolset instance to call it on.
            params: Already-coerced keyword arguments, as produced by
                :func:`decoui.widget_builder.coerce_params`.

        Note:
            The record is inserted with ``status='running'`` before the thread
            starts, so an interrupted run is still visible afterwards. Nothing
            here prevents a second call while a run is in flight -- the page's
            buttons are what enforce one run at a time.
        """
        now = datetime.now()
        self._tool_info = tool_info
        self._instance = instance
        self._cancel_hook_fired = False
        serialized_params = self._serialize_params(tool_info, params)
        rec = ExecutionRecord(
            tool_id=tool_info.tool_id,
            tool_label=tool_info.label,
            started_at=now,
            status="running",
            params=serialized_params,
        )
        self._record_id = insert_record(rec)
        self._log_buffer.clear()
        self._log_seq = 0
        self.record_created.emit(self._record_id)

        self._worker = ToolWorker(tool_info, instance, params, tool_info.timeout)
        self._worker.signals.log_line.connect(self._on_log_line)
        self._worker.signals.finished.connect(self._on_finished)
        # Forwarded as-is: progress is transient UI state and is not recorded.
        self._worker.signals.progress.connect(self.progress)

        self._flush_timer.start()
        QThreadPool.globalInstance().start(self._worker)

        if tool_info.timeout:
            QTimer.singleShot(tool_info.timeout * 1000, self._on_timeout)

    def cancel(self):
        """Stop the running tool, giving it a chance to clean up first.

        The hook runs before the interrupt, and on this thread. Cancellation
        injects an exception into the worker thread, but that exception is only
        raised at a Python bytecode boundary -- a worker blocked in proc.wait()
        never reaches one until the child exits, and its finally block does not
        run either. Terminating that child from here is what lets the worker
        return at all, so the order matters.
        """
        if not self._worker:
            return
        self._run_cancel_hook()
        self._worker.cancel()

    def _run_cancel_hook(self):
        """Run the tool's on_cancel declaration, at most once per execution.

        A hook that raises is reported into the run's own log: cancellation has
        to complete either way, and the Stop button is not a place to surface a
        traceback.
        """
        if self._cancel_hook_fired or self._tool_info is None:
            return
        spec = self._tool_info.on_cancel
        if spec is None:
            return

        self._cancel_hook_fired = True
        target = getattr(self._instance, spec) if isinstance(spec, str) else spec
        try:
            target()
        except Exception:
            self._on_log_line(
                "ERROR",
                f"on_cancel hook for '{self._tool_info.label}' failed:\n"
                f"{traceback.format_exc()}",
            )

    def _on_log_line(self, level: str, message: str):
        """Forward one console line and queue it for the database.

        Args:
            level: ``'stdout'`` or a logging level name.
            message: The line text.
        """
        self.log_line.emit(level, message)
        log_entry = ExecutionLog(
            record_id=self._record_id,
            seq=self._log_seq,
            level=level,
            message=message,
            logged_at=datetime.now(),
        )
        self._log_buffer.append(log_entry)
        self._log_seq += 1
        if len(self._log_buffer) >= 50:
            self._flush_logs()

    def _on_finished(self, result, status: str):
        """Close out the run: flush logs, finalise the record, forward the result.

        Args:
            result: The tool's return value, or None when it failed or was
                cancelled.
            status: ``'success'``, ``'error'`` or ``'cancelled'``.
        """
        self._flush_timer.stop()
        self._flush_logs()
        # Dropping the worker closes the window in which a late timeout, or a
        # second Stop, could fire the cancel hook after the tool already ended.
        self._worker = None
        result_json = None
        if result is not None:
            try:
                result_json = json.dumps(result, default=str, ensure_ascii=False)
            except Exception:
                result_json = json.dumps(str(result), ensure_ascii=False)
        update_record(
            self._record_id,
            status=status,
            finished_at=datetime.now(),
            result_json=result_json,
        )
        self.finished.emit(result, status)

    def _on_timeout(self):
        """Cancel the run when its declared timeout expires.

        Goes through :meth:`cancel`, so a timeout runs the tool's ``on_cancel``
        hook exactly as pressing Stop does. Does nothing once the run has ended,
        because the worker reference is dropped in :meth:`_on_finished`.
        """
        if self._worker:
            self.cancel()
            self._on_log_line("WARNING", "Execution timed out.")

    def _flush_logs(self):
        """Write the buffered console lines to the database in one statement."""
        if self._log_buffer:
            insert_logs(self._log_buffer)
            self._log_buffer.clear()

    @staticmethod
    def _serialize_params(tool_info: ToolInfo, params: dict) -> list[ExecutionParam]:
        """Snapshot the parameters of a run so it can be replayed later.

        Args:
            tool_info: The tool being run, which fixes the parameter order.
            params: The coerced arguments.

        Returns:
            One ExecutionParam per declared parameter, in signature order. A
            parameter missing from ``params`` is recorded as None rather than
            skipped, so replay always sees the full set.
        """
        result = []
        for p in tool_info.params:
            val = params.get(p.name)
            try:
                serialized = json.dumps(val, default=str, ensure_ascii=False)
            except Exception:
                serialized = str(val)
            type_name = type(val).__name__ if val is not None else "NoneType"
            result.append(ExecutionParam(
                record_id=0,
                param_name=p.name,
                param_value=serialized,
                param_type=type_name,
            ))
        return result
