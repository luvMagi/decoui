"""QRunnable worker with stdout/logging capture."""
from __future__ import annotations

import io
import logging
import sys
import threading
import traceback
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    log_line = Signal(str, str)      # (level, message)
    finished = Signal(object, str)   # (result, status: 'success'|'error'|'cancelled')
    error = Signal(str)              # error message


class _StreamRedirect(io.TextIOBase):
    """Thread-safe stdout redirector that emits signals."""

    def __init__(self, signals: WorkerSignals, original: io.TextIOBase):
        super().__init__()
        self._signals = signals
        self._original = original
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._signals.log_line.emit("stdout", line)
        return len(text)

    def flush(self):
        if self._buffer:
            self._signals.log_line.emit("stdout", self._buffer)
            self._buffer = ""


class _SignalHandler(logging.Handler):
    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self._signals = signals

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._signals.log_line.emit(record.levelname, msg)
        except Exception:
            pass


_thread_local = threading.local()


class ToolWorker(QRunnable):
    def __init__(self, tool_info, instance, params: dict, timeout: int | None = None):
        super().__init__()
        self.tool_info = tool_info
        self.instance = instance
        self.params = params
        self.timeout = timeout
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        original_stdout = sys.stdout
        redirect = _StreamRedirect(self.signals, original_stdout)
        handler = _SignalHandler(self.signals)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%H:%M:%S"))

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        sys.stdout = redirect

        try:
            import inspect as _inspect
            first = next(iter(_inspect.signature(self.tool_info.method).parameters), None)
            if first != "self":
                raise TypeError(
                    f"{self.tool_info.method.__qualname__}() is missing 'self' as the first parameter. "
                    f"All @tool methods must be instance methods."
                )
            result = self.tool_info.method(self.instance, **self.params)
            redirect.flush()
            if self._cancelled:
                self.signals.finished.emit(None, "cancelled")
            else:
                self.signals.finished.emit(result, "success")
        except Exception as exc:
            redirect.flush()
            msg = traceback.format_exc()
            self.signals.log_line.emit("ERROR", msg)
            self.signals.finished.emit(None, "error")
            self.signals.error.emit(str(exc))
        finally:
            sys.stdout = original_stdout
            root_logger.removeHandler(handler)
