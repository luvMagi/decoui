"""Tests for the progress reporting API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from decoui import progress, tool, toolset
from decoui.engine import worker as worker_module
from decoui.engine.worker import ToolWorker
from decoui.registry import ToolInfo, build_tree
from decoui.storage.db import set_db_path
from decoui.ui.tool_page import ToolPage


class _Recorder:
    """Stand-in for WorkerSignals that records what progress() emits.

    Attributes:
        calls: One (done, total, message) tuple per emission that got through.
    """

    def __init__(self) -> None:
        """Start with an empty call log and act as our own progress signal."""
        self.calls: list[tuple[int, int, str]] = []
        self.progress = self

    def emit(self, done: int, total: int, message: str) -> None:
        """Record one emission.

        Args:
            done: Units completed.
            total: Total units, or 0 when unknown.
            message: Status text.
        """
        self.calls.append((done, total, message))


@pytest.fixture()
def recorder() -> Iterator[_Recorder]:
    """Install a recording signals object on the worker thread local.

    Yields:
        The recorder collecting everything progress() lets through.
    """
    rec = _Recorder()
    worker_module._thread_local.signals = rec
    worker_module._thread_local.progress_at = 0.0
    yield rec
    worker_module._thread_local.signals = None


def _page(tmp_path: Path, info: ToolInfo, instance: object) -> ToolPage:
    """Build a ToolPage backed by a throwaway database.

    Args:
        tmp_path: pytest's per-test directory, used for the history database.
        info: The tool the page is built for.
        instance: The toolset instance the page runs against.

    Returns:
        A ToolPage ready for direct handler calls.
    """
    set_db_path(tmp_path / "history.db")
    return ToolPage(info, instance)


@toolset(label="Progress Tools")
class _ProgressTools:
    """Toolset whose tool reports progress while it runs."""

    @tool(label="Copy")
    def copy(self) -> str:
        """Report two steps and finish.

        Returns:
            A constant marker, so the caller can tell the body ran.
        """
        progress(1, 2, "half")
        progress(2, 2, "done")
        return "copied"


def test_progress_outside_a_worker_is_a_noop() -> None:
    """Verify a direct call reports nothing and raises nothing.

    Tools are verified by instantiating the toolset and calling the method, so
    progress() must stay silent when there is no worker around it.
    """
    worker_module._thread_local.signals = None

    assert progress(1, 10, "ignored") is None
    assert _ProgressTools().copy() == "copied"


def test_progress_reaches_the_signals(recorder: _Recorder) -> None:
    """Verify a reported step is forwarded verbatim."""
    progress(3, 10, "step")

    assert recorder.calls == [(3, 10, "step")]


def test_rapid_calls_are_throttled(recorder: _Recorder) -> None:
    """Verify a dense loop cannot flood the queued cross-thread signal."""
    for index in range(1000):
        progress(index, 0, "working")

    assert len(recorder.calls) == 1


def test_the_final_call_is_never_dropped(recorder: _Recorder) -> None:
    """Verify the last step survives throttling, so the bar reaches 100%."""
    progress(1, 10, "first")
    for index in range(2, 10):
        progress(index, 10, "middle")
    progress(10, 10, "last")

    assert recorder.calls[0] == (1, 10, "first")
    assert recorder.calls[-1] == (10, 10, "last")


def test_worker_clears_the_thread_local_after_running() -> None:
    """Verify a finished worker leaves no signals behind.

    QThreadPool reuses threads: a stale entry here would make the next tool
    report progress through the previous run's signals.
    """
    info = build_tree(_ProgressTools)[0].tools[0]
    worker = ToolWorker(info, _ProgressTools(), {})
    recorder = _Recorder()
    worker.signals.progress = recorder

    worker.run()

    assert recorder.calls[-1] == (2, 2, "done")
    assert getattr(worker_module._thread_local, "signals", None) is None


def test_page_switches_to_determinate(qt_app: QApplication, tmp_path: Path) -> None:
    """Verify a known total turns the indeterminate bar into a real one."""
    info = build_tree(_ProgressTools)[0].tools[0]
    page = _page(tmp_path, info, _ProgressTools())

    page._on_progress(3, 10, "dumping")

    assert page._progress.maximum() == 10
    assert page._progress.value() == 3
    assert page._status_label.text() == "dumping"

    page.close()


def test_unknown_total_keeps_the_bar_indeterminate(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Verify a message-only report does not pin the bar at zero."""
    info = build_tree(_ProgressTools)[0].tools[0]
    page = _page(tmp_path, info, _ProgressTools())

    page._on_progress(0, 0, "still working")

    assert page._progress.maximum() == 0
    assert page._status_label.text() == "still working"

    page.close()


def test_finishing_resets_the_bar(qt_app: QApplication, tmp_path: Path) -> None:
    """Verify the next run does not start at the previous run's percentage."""
    info = build_tree(_ProgressTools)[0].tools[0]
    page = _page(tmp_path, info, _ProgressTools())
    page._on_progress(10, 10, "done")

    page._on_finished(None, "success")

    assert page._progress.maximum() == 0

    page.close()
