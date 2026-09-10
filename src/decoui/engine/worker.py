"""The worker thread a tool body actually runs on.

What a tool can rely on while it runs
-------------------------------------

* ``print()`` and the standard ``logging`` module both reach the page console,
  line by line, as they happen. Nothing needs to be flushed or configured.
* :func:`progress` drives the progress bar.
* Raising is fine: the traceback is logged and the run is recorded as ``error``.
* The return value is handed on but never displayed -- it is only serialised
  into the run's history record.

Caveats that matter when writing tools
--------------------------------------

* **The stdout redirect is process-global.** ``sys.stdout`` is replaced for the
  duration of the call, so while a tool runs, output printed by *any* thread --
  the GUI thread included -- lands in that tool's console. Two tools running at
  once in different tabs share one ``sys.stdout``, and the one that finishes
  first restores it, so late output from the other may escape to the real
  stdout. Use ``logging`` if a tool is expected to run alongside others.
* **The log handler is attached to the root logger**, so log records from every
  library in the process are captured too, not just the tool's own.
* **Cancellation cannot interrupt a blocking call.** See :meth:`ToolWorker.cancel`.
* Tools run on ``QThreadPool.globalInstance()``, whose threads are reused. Never
  leave thread-local state behind.
"""
from __future__ import annotations

import ctypes
import io
import logging
import sys
import threading
import time
import traceback
from datetime import datetime


from PySide6.QtCore import QObject, QRunnable, Signal


class _WorkerCancelled(BaseException):
    """Injected into the worker thread by cancel() to interrupt execution.

    It derives from ``BaseException`` deliberately, so an ordinary
    ``except Exception`` inside a tool cannot swallow a cancellation and keep
    running. The cost is that cleanup written as ``except Exception`` never sees
    it either -- which is what ``@tool(on_cancel=...)`` exists to solve.
    """


class WorkerSignals(QObject):
    """Everything a worker reports back to the GUI thread.

    A QRunnable cannot carry signals itself, so they live on this companion
    QObject. All of them cross threads and are therefore delivered as queued
    connections -- nothing here runs on the worker.

    Attributes:
        log_line: One console line, as ``(level, message)``. ``level`` is
            ``'stdout'`` for print output, otherwise a logging level name.
        finished: ``(result, status)`` where status is ``'success'``,
            ``'error'`` or ``'cancelled'``. ``result`` is None for the latter
            two -- a cancelled run's return value is dropped.
        error: The exception message. **Nothing connects to this**; failures are
            surfaced through the ERROR log line and the ``finished`` status.
        progress: ``(done, total, message)`` from :func:`progress`.
    """

    log_line = Signal(str, str)          # (level, message)
    finished = Signal(object, str)       # (result, status: 'success'|'error'|'cancelled')
    error = Signal(str)                  # error message
    progress = Signal(int, int, str)     # (done, total, message)


class _StreamRedirect(io.TextIOBase):
    """Thread-safe stdout redirector that emits signals.

    Buffers partial writes and emits one signal per completed line, so
    ``print("a", end="")`` followed by ``print("b")`` arrives as a single line.
    Anything still buffered when the tool ends is flushed as a final line.

    It is not a real file object: it has no ``fileno()``, so a subprocess
    launched with ``stdout=sys.stdout`` will fail. Leave subprocess stdout
    alone (it inherits the process's real handle) or capture it with a pipe.
    """

    def __init__(self, signals: WorkerSignals, original: io.TextIOBase):
        """Start with an empty line buffer.

        Args:
            signals: The running worker's signal object.
            original: The stdout being replaced. Kept for reference; output is
                sent to the console rather than mirrored to it.
        """
        super().__init__()
        self._signals = signals
        self._original = original
        self._buffer = ""

    def write(self, text: str) -> int:
        """Buffer text and emit each completed line.

        Args:
            text: The text written to stdout.

        Returns:
            The number of characters accepted, as a file object must.
        """
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._signals.log_line.emit("stdout", line)
        return len(text)

    def flush(self):
        """Emit whatever is buffered without a trailing newline."""
        if self._buffer:
            self._signals.log_line.emit("stdout", self._buffer)
            self._buffer = ""


class _SignalHandler(logging.Handler):
    """Logging handler that forwards formatted records to the console.

    Attached to the *root* logger for the duration of a run, so every library's
    log output is captured too, then removed again.
    """

    def __init__(self, signals: WorkerSignals):
        """Store the signals to forward through.

        Args:
            signals: The running worker's signal object.
        """
        super().__init__()
        self._signals = signals

    def emit(self, record: logging.LogRecord):
        """Forward one record as a console line, never raising.

        Args:
            record: The log record to format and emit.
        """
        try:
            msg = self.format(record)
            self._signals.log_line.emit(record.levelname, msg)
        except Exception:
            pass


_thread_local = threading.local()

# Progress calls can be far denser than the UI can repaint. Queued cross-thread
# signals would pile up, so anything closer than this to the previous report is
# dropped -- except the final one, which must never be lost.
_PROGRESS_MIN_INTERVAL_S = 0.1


def progress(done: int, total: int = 0, message: str = "") -> None:
    """Report progress from inside a running tool.

    Call this from a @tool method body to drive the page's progress bar. It is
    a no-op outside a decoui worker, so a tool called directly -- as when its
    toolset is instantiated in a test -- behaves exactly as it did before.

    Args:
        done: Units completed so far.
        total: Total units, or 0 when the amount of work is unknown. A total of
            0 leaves the progress bar in its indeterminate state and updates
            only the message.
        message: Short status text shown next to the progress bar.

    Example:
        for index, table in enumerate(tables):
            progress(index, len(tables), f"dumping {table}")
    """
    signals = getattr(_thread_local, "signals", None)
    if signals is None:
        return

    is_final = total > 0 and done >= total
    now = time.monotonic()
    if not is_final and now - getattr(_thread_local, "progress_at", 0.0) < _PROGRESS_MIN_INTERVAL_S:
        return

    _thread_local.progress_at = now
    signals.progress.emit(done, total, message)


class ToolWorker(QRunnable):
    """Runs one tool call on a pool thread, capturing its output.

    Attributes:
        signals: The WorkerSignals instance the GUI connects to. Created here,
            on the calling (GUI) thread, so the queued connections are set up
            before the run starts.
    """

    def __init__(self, tool_info, instance, params: dict, timeout: int | None = None):
        """Prepare a single run.

        Args:
            tool_info: The tool to call.
            instance: The toolset instance to call it on.
            params: Already-coerced keyword arguments.
            timeout: Recorded for reference; the timer that enforces it lives in
                ExecutionEngine, not here.
        """
        super().__init__()
        self.tool_info = tool_info
        self.instance = instance
        self.params = params
        self.timeout = timeout
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        """Ask the worker thread to stop by injecting an exception into it.

        Called from the GUI thread. ``PyThreadState_SetAsyncExc`` schedules
        :class:`_WorkerCancelled` in the worker, and CPython raises it at the
        next bytecode boundary.

        **A thread parked in a C call never reaches such a boundary.**
        ``proc.wait()``, ``socket.recv()``, a long ``time.sleep()`` -- the
        exception stays pending until the call returns on its own, and the
        tool's ``finally`` does not run either. Whatever is holding the thread
        must be released from outside, which is what
        :meth:`decoui.engine.executor.ExecutionEngine._run_cancel_hook` does
        immediately before calling this.

        Calling this before :meth:`run` has started is safe: there is no thread
        id yet, and the ``_cancelled`` flag makes run() report ``cancelled``
        once it finishes.
        """
        self._cancelled = True
        tid = getattr(self, "_thread_id", None)
        if tid is not None:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid),
                ctypes.py_object(_WorkerCancelled),
            )

    def run(self):
        """Execute the tool with stdout, logging and progress redirected.

        Runs on a pool thread. Never raises: every outcome is reported through
        ``signals.finished``, and the console/stdout state is restored in the
        finally block whatever happens.
        """
        self._thread_id = threading.current_thread().ident
        original_stdout = sys.stdout
        redirect = _StreamRedirect(self.signals, original_stdout)
        handler = _SignalHandler(self.signals)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%H:%M:%S"))

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        sys.stdout = redirect
        # progress() reads these; QThreadPool reuses threads, so they must be
        # cleared in the finally below or the next tool reports to dead signals.
        _thread_local.signals = self.signals
        _thread_local.progress_at = 0.0

        try:
            # Checked here rather than at decoration time so that @tool never
            # rejects anything at import; a staticmethod slips through the
            # registry but cannot be called with an instance.
            import inspect as _inspect
            first = next(iter(_inspect.signature(self.tool_info.method).parameters), None)
            if first != "self":
                raise TypeError(
                    f"{self.tool_info.method.__qualname__}() is missing 'self' as the first parameter. "
                    f"All @tool methods must be instance methods."
                )
            result = self.tool_info.method(self.instance, **self.params)
            redirect.flush()
            # A tool that returned normally after cancel() was requested is
            # still recorded as cancelled: the user asked for it to stop, and
            # a partially-completed result must not look like a success.
            if self._cancelled:
                self.signals.finished.emit(None, "cancelled")
            else:
                self.signals.finished.emit(result, "success")
        except _WorkerCancelled:
            redirect.flush()
            self.signals.finished.emit(None, "cancelled")
        except Exception as exc:
            redirect.flush()
            msg = traceback.format_exc()
            self.signals.log_line.emit("ERROR", msg)
            self.signals.finished.emit(None, "error")
            self.signals.error.emit(str(exc))
        finally:
            _thread_local.signals = None
            sys.stdout = original_stdout
            root_logger.removeHandler(handler)
