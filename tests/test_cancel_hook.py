"""Tests for the on_cancel cleanup hook and the cancellation contract."""

from __future__ import annotations

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

    @tool(label="Timed", timeout=60, on_cancel="stop")
    def timed(self) -> None:
        """Placeholder body for the timeout-timer tests."""

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


def _tool_of(cls: type, method_name: str):
    """Look one tool up by method name.

    Args:
        cls: The @toolset class to scan.
        method_name: The attribute name of the wanted tool.

    Returns:
        Its ToolInfo.
    """
    return next(t for t in build_tree(cls)[0].tools if t.method_name == method_name)


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
    engine._tool_info = _tool_of(_CancelTools, method_name)
    engine._instance = instance
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


def test_a_second_stop_retries_the_hook(tmp_path: Path) -> None:
    """Verify repeated Stop presses each get a fresh attempt at cleanup.

    A Stop that arrives before the tool has assigned the state its hook reads
    does nothing, and the worker is still blocked in the call only the hook can
    release. Suppressing the retry would leave the page wedged for the rest of
    the child's life, so the hook is contractually idempotent instead.
    """
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())

    engine.cancel()
    engine.cancel()

    assert order == ["hook", "interrupt", "hook", "interrupt"]


def test_the_hook_does_not_fire_once_the_run_has_ended(tmp_path: Path) -> None:
    """Verify cleanup is bounded by the run, not by a once-only flag.

    ``_on_finished`` drops the worker, which is what closes the window: a Stop
    pressed afterwards must not run cleanup against work that already completed.
    """
    engine, order = _armed(tmp_path, "with_hook", _CancelTools())

    engine._on_finished(None, "success")
    engine.cancel()

    assert order == []


def test_a_finished_run_disarms_its_timeout(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Verify the timeout timer does not outlive the run that armed it."""
    engine = _engine(tmp_path)

    engine.run(_tool_of(_CancelTools, "timed"), _CancelTools(), {})
    assert engine._timeout_timer.isActive()

    assert QThreadPool.globalInstance().waitForDone(10_000)
    qt_app.processEvents()

    assert not engine._timeout_timer.isActive()


def test_a_later_run_is_not_cut_short_by_an_earlier_timeout(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Verify a run inherits no timeout from the run before it.

    A fire-and-forget QTimer.singleShot cannot be recalled, so a timer armed by
    a finished run would fire against whatever is running when its deadline
    arrives -- cancelling it, writing a bogus timeout warning into its record,
    and invoking its on_cancel hook.
    """
    engine = _engine(tmp_path)
    instance = _CancelTools()

    engine.run(_tool_of(_CancelTools, "timed"), instance, {})
    assert QThreadPool.globalInstance().waitForDone(10_000)
    qt_app.processEvents()

    # 'No hook' declares no timeout at all, so nothing may be armed for it.
    engine.run(_tool_of(_CancelTools, "without_hook"), instance, {})
    assert not engine._timeout_timer.isActive()

    assert QThreadPool.globalInstance().waitForDone(10_000)
    qt_app.processEvents()
    assert instance.order == []


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

    # Popen.returncode is still None. The injected exception is raised at the
    # first bytecode boundary after the wait syscall returns, which falls inside
    # Popen._wait, before it records the status -- so the cached attribute never
    # gets written. Read the child's state, do not trust this attribute.
    assert instance.proc.returncode is None

    # Asking the OS is what actually proves the child is gone. poll() is the
    # portable way to do it: on Windows it reads the exit code through the
    # handle Popen still holds, and on POSIX it either reaps the child itself or
    # gets ECHILD because the worker's wait already did. Both give a non-None
    # answer only once the child has really ended.
    #
    # os.kill(pid, 0) does not work here: on Windows the pid stays openable for
    # as long as Popen holds a handle to the exited process, so it succeeds for
    # a dead child instead of raising ProcessLookupError.
    assert instance.proc.poll() is not None
    qt_app.processEvents()
