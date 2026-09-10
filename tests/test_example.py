"""Tests for the bundled example application.

The example is the reference a tool author copies from, so these check that the
patterns it demonstrates actually work -- not merely that the module imports.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from decoui.decorators import _TOOLSET_ATTR
from decoui.engine import worker as worker_module
from decoui.engine.executor import ExecutionEngine
from decoui.example import DemoTools, Encoding
from decoui.registry import ToolInfo, build_tree
from decoui.storage.db import set_db_path


class _Recorder:
    """Stand-in for WorkerSignals that records progress reports.

    Attributes:
        calls: One (done, total, message) tuple per report that got through.
    """

    def __init__(self) -> None:
        """Start with an empty call log and act as our own progress signal."""
        self.calls: list[tuple[int, int, str]] = []
        self.progress = self

    def emit(self, done: int, total: int, message: str) -> None:
        """Record one report.

        Args:
            done: Units completed.
            total: Total units.
            message: Status text.
        """
        self.calls.append((done, total, message))


@pytest.fixture()
def recorder() -> Iterator[_Recorder]:
    """Make progress() reportable without starting a worker.

    Yields:
        The recorder collecting what progress() lets through.
    """
    rec = _Recorder()
    worker_module._thread_local.signals = rec
    worker_module._thread_local.progress_at = 0.0
    yield rec
    worker_module._thread_local.signals = None


def _demo_tool(label: str) -> ToolInfo:
    """Look up one tool of DemoTools by its display label.

    Args:
        label: The tool's ``@tool(label=...)``.

    Returns:
        Its ToolInfo.
    """
    return next(t for t in build_tree(DemoTools)[0].tools if t.label == label)


def test_example_tree_builds() -> None:
    """Verify every declaration in the example passes startup validation.

    build_tree() is where a wrong key or a missing callback method is caught, so
    this covers the whole example at once.
    """
    import decoui.example as example

    classes = [
        obj
        for obj in vars(example).values()
        if isinstance(obj, type) and hasattr(obj, _TOOLSET_ATTR)
    ]
    tree = build_tree(*classes)

    assert len(tree) == 5
    assert sum(len(ts.tools) for ts in tree) == 17


def test_slow_task_reports_progress(recorder: _Recorder) -> None:
    """Verify the progress demo drives the bar and always reaches 100%."""
    result = DemoTools().slow_task(steps=3, delay=0.0)

    assert result == "Completed 3 steps."
    assert recorder.calls[-1] == (3, 3, "done")


def test_slow_task_runs_without_a_gui() -> None:
    """Verify calling the tool directly still works, progress() included.

    This is the property the whole framework is built around: a tool is a plain
    method. Outside a worker, progress() must be a silent no-op.
    """
    worker_module._thread_local.signals = None

    assert DemoTools().slow_task(steps=2, delay=0.0) == "Completed 2 steps."


def test_child_process_tool_declares_its_cleanup() -> None:
    """Verify the cancellation demo is actually wired to its hook."""
    info = _demo_tool("Run Child Process")

    assert info.on_cancel == "stop_child"
    assert info.timeout == 120


def test_cancelling_the_child_process_tool_kills_the_child(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Verify the demo does what its docstring claims Stop cannot do alone.

    The worker is blocked reading the child's pipe, so only the on_cancel hook
    can end the child -- and the ``with`` block is what reaps it afterwards.
    """
    set_db_path(tmp_path / "history.db")
    engine = ExecutionEngine()
    instance = DemoTools()

    started = time.monotonic()
    engine.run(
        _demo_tool("Run Child Process"),
        instance,
        {"seconds": 30, "encoding": Encoding.UTF8},
    )
    deadline = time.monotonic() + 5.0
    while instance._child is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert instance._child is not None
    child = instance._child

    engine.cancel()

    assert QThreadPool.globalInstance().waitForDone(10_000)
    assert time.monotonic() - started < 20.0
    # The child really ended, rather than the worker merely giving up on it.
    # poll() is the portable check -- see test_cancel_hook for why os.kill(pid, 0)
    # cannot tell a dead child from a live one on Windows.
    assert child.poll() is not None
    qt_app.processEvents()
