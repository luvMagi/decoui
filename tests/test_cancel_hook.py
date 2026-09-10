"""Tests for the on_cancel cleanup hook and the cancellation contract."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from decoui import tool, toolset
from decoui.engine.executor import ExecutionEngine
from decoui.registry import build_tree
from decoui.storage.db import set_db_path


class _FakeWorker:
    """Stand-in for ToolWorker that records when it was interrupted.

    Attributes:
        order: Shared log the hook and this worker both append to.
    """

    def __init__(self, order: list[str]) -> None:
        """Store the shared call log.

        Args:
            order: List both the hook and cancel() append to, in call order.
        """
        self.order = order

    def cancel(self) -> None:
        """Record that the thread interrupt was requested."""
        self.order.append("interrupt")


@toolset(label="Cancel Tools")
class _CancelTools:
    """Toolset whose tools declare cleanup hooks."""

    def __init__(self) -> None:
        """Start with an empty call log and no recorded thread."""
        self.order: list[str] = []
        self.hook_thread: str = ""

    @tool(label="With hook", on_cancel="stop")
    def with_hook(self) -> None:
        """Placeholder body; these tests drive the engine directly."""

    @tool(label="No hook")
    def without_hook(self) -> None:
        """Placeholder body for the untouched path."""

    @tool(label="Broken hook", on_cancel="broken")
    def with_broken_hook(self) -> None:
        """Placeholder body for the failing-hook path."""

    def stop(self) -> None:
        """Record the hook call and the thread it ran on."""
        self.order.append("hook")
        self.hook_thread = threading.current_thread().name

    def broken(self) -> None:
        """Fail the way a real cleanup can.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("cleanup exploded")


def _engine(tmp_path: Path) -> ExecutionEngine:
    """Build an engine backed by a throwaway database.

    Args:
        tmp_path: pytest's per-test directory.

    Returns:
        A fresh ExecutionEngine.
    """
    set_db_path(tmp_path / "history.db")
    return ExecutionEngine()


def _armed(
    tmp_path: Path, method_name: str, instance: _CancelTools
) -> tuple[ExecutionEngine, list[str]]:
    """Put an engine into the state run() leaves behind, without a thread.

    Args:
        tmp_path: pytest's per-test directory.
        method_name: Which tool of _CancelTools to arm.
        instance: The toolset instance the hook is looked up on.

    Returns:
        The engine and the shared call-order log.
    """
    engine = _engine(tmp_path)
    info = next(
        t for t in build_tree(_CancelTools)[0].tools if t.method_name == method_name
    )
    engine._tool_info = info
    engine._instance = instance
    engine._cancel_hook_fired = False
    engine._worker = _FakeWorker(instance.order)
    return engine, instance.order


def test_hook_runs_before_the_thread_is_interrupted(tmp_path: Path) -> None:
    """Verify cleanup happens first, which is the whole point of the hook.

    A worker blocked in a C call cannot see the injected exception until that
    call returns, so the hook has to run first to make it return.
    """
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())

    engine.cancel()

    assert order == ["hook", "interrupt"]


def test_hook_runs_on_the_calling_thread(tmp_path: Path) -> None:
    """Verify the hook runs on the GUI thread, not inside the worker."""
    instance = _CancelTools()
    engine, _ = _armed(tmp_path, "with_hook", instance)

    engine.cancel()

    assert instance.hook_thread == threading.current_thread().name


def test_hook_fires_once_for_repeated_cancels(tmp_path: Path) -> None:
    """Verify a second Stop press does not run cleanup twice."""
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())

    engine.cancel()
    engine.cancel()

    assert order.count("hook") == 1


def test_timeout_fires_the_hook(tmp_path: Path) -> None:
    """Verify a timeout is the same event as Stop from the tool's side."""
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())

    engine._on_timeout()

    assert order[0] == "hook"


def test_hook_failure_is_logged_and_cancel_still_completes(tmp_path: Path) -> None:
    """Verify a broken hook cannot leave the tool un-cancellable."""
    instance = _CancelTools()
    engine, order = _armed(tmp_path, "with_broken_hook", instance)
    logged: list[tuple[str, str]] = []
    engine.log_line.connect(lambda level, message: logged.append((level, message)))

    engine.cancel()

    assert order == ["interrupt"]
    assert logged[0][0] == "ERROR"
    assert "cleanup exploded" in logged[0][1]


def test_tool_without_a_hook_is_unaffected(tmp_path: Path) -> None:
    """Verify undeclared tools cancel exactly as they did before."""
    engine, order = _armed(tmp_path, "without_hook", _CancelTools())

    engine.cancel()

    assert order == ["interrupt"]


def test_cancel_after_the_run_finished_does_nothing(tmp_path: Path) -> None:
    """Verify a late timeout cannot clean up a run that already ended."""
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())
    engine._on_finished(None, "success")

    engine.cancel()
    engine._on_timeout()

    assert order == []


def test_unknown_hook_method_is_rejected() -> None:
    """Verify a misspelled on_cancel method name fails at startup."""

    @toolset(label="Broken")
    class BrokenTools:

        @tool(label="Deploy", on_cancel="does_not_exist")
        def deploy(self) -> None:
            pass

    with pytest.raises(AttributeError, match="does_not_exist"):
        build_tree(BrokenTools)


@toolset(label="Subprocess Tools")
class _SubprocessTools:
    """Toolset that blocks on a real child process, as the reported tool did.

    Attributes:
        proc: The child, once started.
        waiting: Set just before the worker blocks, so the test can cancel at
            the moment the accident actually happens.
    """

    def __init__(self) -> None:
        """Start with no child process."""
        self.proc: subprocess.Popen | None = None
        self.waiting: bool = False

    @tool(label="Sleep", on_cancel="stop")
    def sleep(self) -> None:
        """Start a long-running child and block until it exits."""
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            encoding="utf-8",
        )
        self.waiting = True
        self.proc.wait()

    def stop(self) -> None:
        """Terminate the child, tolerating a Stop that arrives too early."""
        proc = getattr(self, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()


def test_cancel_terminates_a_blocking_child_process(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Verify Stop kills the child, which plain cancellation cannot.

    This is the reported accident: the worker sits in proc.wait(), so the
    injected exception is never raised and the child keeps running. Without the
    hook this test would sit here for the child's full 30 seconds.
    """
    engine = _engine(tmp_path)
    info = build_tree(_SubprocessTools)[0].tools[0]
    instance = _SubprocessTools()

    started = time.monotonic()
    engine.run(info, instance, {})
    deadline = time.monotonic() + 5.0
    while not instance.waiting and time.monotonic() < deadline:
        time.sleep(0.01)
    assert instance.proc is not None
    # Cancelling before the worker reaches wait() proves nothing: the injected
    # exception would land at an ordinary bytecode boundary and the tool would
    # stop on its own. The accident needs the worker parked inside the C call.
    time.sleep(0.2)

    engine.cancel()

    # The worker returns rather than sitting out the child's full 30 seconds.
    assert QThreadPool.globalInstance().waitForDone(10_000)
    assert time.monotonic() - started < 20.0

    # The child is gone, and reaped: kill(pid, 0) still succeeds on a zombie,
    # so this also proves the worker's waitpid() collected it.
    with pytest.raises(ProcessLookupError):
        os.kill(instance.proc.pid, 0)

    # Popen.returncode stays None even so. The injected exception is raised at
    # the first bytecode boundary after waitpid() returns, which falls inside
    # Popen._wait, before it records the status. Cancellation leaves the Popen
    # object unusable -- read the child through the OS, not through Popen.
    assert instance.proc.returncode is None
    qt_app.processEvents()
