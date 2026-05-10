"""Execution scheduling and ExecutionRecord lifecycle."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ..registry import ToolInfo
from ..storage.db import init_db, insert_record, update_record, insert_logs
from ..storage.models import ExecutionLog, ExecutionParam, ExecutionRecord
from .worker import ToolWorker


class ExecutionEngine(QObject):
    log_line = Signal(str, str)           # (level, message)
    finished = Signal(object, str)        # (result, status)
    record_created = Signal(int)          # record_id

    def __init__(self, parent=None):
        super().__init__(parent)
        init_db()
        self._worker: ToolWorker | None = None
        self._record_id: int = 0
        self._log_buffer: list[ExecutionLog] = []
        self._log_seq = 0
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(1000)
        self._flush_timer.timeout.connect(self._flush_logs)

    def run(self, tool_info: ToolInfo, instance, params: dict):
        now = datetime.now()
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

        self._flush_timer.start()
        QThreadPool.globalInstance().start(self._worker)

        if tool_info.timeout:
            QTimer.singleShot(tool_info.timeout * 1000, self._on_timeout)

    def cancel(self):
        if self._worker:
            self._worker.cancel()

    def _on_log_line(self, level: str, message: str):
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
        self._flush_timer.stop()
        self._flush_logs()
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
        if self._worker:
            self._worker.cancel()
            self._on_log_line("WARNING", "Execution timed out.")

    def _flush_logs(self):
        if self._log_buffer:
            insert_logs(self._log_buffer)
            self._log_buffer.clear()

    @staticmethod
    def _serialize_params(tool_info: ToolInfo, params: dict) -> list[ExecutionParam]:
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
