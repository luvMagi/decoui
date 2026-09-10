"""Does Stop actually stop an external program? One test per way of calling one.

Written after a tool that shelled out to a database client could not be stopped.
:mod:`tests.test_cancel_hook` already covers the mechanism -- the hook runs
before the thread interrupt, on the GUI thread. This module asks the question
the accident actually posed: given the ways people really invoke an external
tool, which of them can decoui stop?

Every test here drives the real :class:`~decoui.engine.executor.ExecutionEngine`
against a real child process, and reads liveness from the heartbeat file
``tests/heavy_background_task.py`` writes rather than from a pid or from
``Popen.returncode``. A stopped process stops writing; that is the only signal
that means the same thing on every platform.

Several of these assert a **limitation**, not a success. They are here so the
limitation is visible and cannot regress silently.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from decoui import run_process, tool, toolset
from decoui.engine.executor import ExecutionEngine
from decoui.registry import build_tree
from decoui.storage.db import set_db_path

_TASK = Path(__file__).resolve().parent / "heavy_background_task.py"

#: How long a spawned child would run if nothing stopped it. Comfortably longer
#: than _STOP_GRACE_S, so a child finishing on its own is never mistaken for one
#: that was stopped -- and no longer than that, because the tests which prove a
#: child *cannot* be stopped have to sit out its whole life before the pool
#: drains, and that wait is most of this module's runtime.
_CHILD_SECONDS = 12.0

#: How long to allow for a stop to take effect before calling it a failure.
_STOP_GRACE_S = 6.0


def _command(heartbeat: Path, **flags: object) -> list[str]:
    """Build a command line for the heavy task.

    Args:
        heartbeat: File the child should beat into.
        **flags: Extra switches; ``spawn_child=True`` becomes ``--spawn-child``.

    Returns:
        The argv list.
    """
    argv = [
        sys.executable, str(_TASK),
        "--seconds", str(_CHILD_SECONDS),
        "--heartbeat", str(heartbeat),
    ]
    for name, value in flags.items():
        switch = "--" + name.replace("_", "-")
        if value is True:
            argv.append(switch)
        elif value is not False and value is not None:
            argv += [switch, str(value)]
    return argv


def _wait_for_beat(path: Path, timeout: float = 10.0) -> None:
    """Block until the heartbeat file exists, so the child is known to be up.

    Args:
        path: The heartbeat file.
        timeout: Seconds to wait before failing the test.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return
        time.sleep(0.02)
    pytest.fail(f"child never started: {path} was never written")


def _is_beating(path: Path, window: float = 2.0) -> bool:
    """Report whether something is still writing to a heartbeat file.

    Args:
        path: The heartbeat file.
        window: How long to keep watching before concluding it is dead.

    Returns:
        True as soon as the contents change, i.e. the process behind them is
        still running; False if nothing changed for the whole window.

    Note:
        Polled rather than sampled once at each end of the window. A single
        sample says "not beating" for a live child that happened to be starved
        of CPU for that one second -- and this module runs alongside a dozen
        other processes, so that is not hypothetical. Polling makes the positive
        answer arrive as fast as the child can produce it, and only the negative
        answer pay the full window.
    """
    try:
        before = path.read_text(encoding="utf-8")
    except OSError:
        return False
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        time.sleep(0.05)
        try:
            if path.read_text(encoding="utf-8") != before:
                return True
        except OSError:
            return False
    return False


def _engine(tmp_path: Path) -> ExecutionEngine:
    """Build an engine backed by a throwaway database.

    Args:
        tmp_path: pytest's per-test directory.

    Returns:
        A fresh ExecutionEngine.
    """
    set_db_path(tmp_path / "history.db")
    return ExecutionEngine()


def _run_and_stop(
    engine: ExecutionEngine, info, instance, heartbeat: Path
) -> tuple[bool, float]:
    """Start a tool, wait for its child, press Stop, and see what happens.

    Args:
        engine: The engine to run on.
        info: The ToolInfo to run.
        instance: The toolset instance.
        heartbeat: The child's heartbeat file.

    Returns:
        ``(worker_returned, seconds_taken)``. ``worker_returned`` is False when
        the worker thread was still parked when the grace period expired, which
        is the wedged-page symptom the accident showed.
    """
    engine.run(info, instance, {})
    _wait_for_beat(heartbeat)
    # Cancelling before the worker is parked inside the call proves nothing:
    # the injected exception would land at an ordinary bytecode boundary.
    time.sleep(0.3)

    started = time.monotonic()
    engine.cancel()
    returned = QThreadPool.globalInstance().waitForDone(int(_STOP_GRACE_S * 1000))
    return returned, time.monotonic() - started


# ── The ways people actually call an external tool ────────────────────────────


@toolset(label="External")
class _External:
    """One tool per calling convention, each shelling out for real.

    Attributes:
        proc: The child, for the tools that keep a handle on it.
        argv: Command line, injected by the test.
    """

    def __init__(self) -> None:
        """Start with nothing running."""
        self.proc: subprocess.Popen | None = None
        self.argv: list[str] = []

    # subprocess.run() is the first thing anyone reaches for, and it keeps no
    # handle the tool could hand to a hook.
    @tool(label="run, no hook")
    def run_no_hook(self) -> None:
        """Block in subprocess.run with nothing declared."""
        subprocess.run(self.argv)

    @tool(label="run, with hook", on_cancel="stop")
    def run_with_hook(self) -> None:
        """Block in subprocess.run, having declared a hook that has no handle."""
        subprocess.run(self.argv)

    @tool(label="popen wait", on_cancel="stop")
    def popen_wait(self) -> None:
        """Keep the handle, then block in wait()."""
        self.proc = subprocess.Popen(self.argv)
        self.proc.wait()

    @tool(label="popen communicate", on_cancel="stop")
    def popen_communicate(self) -> None:
        """Keep the handle, then block reading the child's pipes."""
        self.proc = subprocess.Popen(
            self.argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        self.proc.communicate()

    # The supported way. No handle to keep, no hook to declare, and the child's
    # whole tree goes down with it.
    @tool(label="run_process")
    def helper(self) -> None:
        """Shell out through decoui's own runner."""
        run_process(self.argv)

    @tool(label="run_process tree")
    def helper_tree(self) -> None:
        """Shell out through decoui's runner, to something that forks."""
        run_process(self.argv)

    def stop(self) -> None:
        """Terminate the child, if this tool kept a handle on one."""
        proc = getattr(self, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()


def _tool_of(name: str):
    """Look one tool up by method name.

    Args:
        name: The attribute name of the wanted tool.

    Returns:
        Its ToolInfo.
    """
    return next(t for t in build_tree(_External)[0].tools if t.method_name == name)


@pytest.fixture(autouse=True)
def _drain_pool() -> None:
    """Make sure a test never inherits a worker left running by the one before.

    Yields:
        Nothing; the drain happens on the way out.
    """
    yield
    QThreadPool.globalInstance().waitForDone(int((_CHILD_SECONDS + 5) * 1000))


def test_popen_and_wait_is_stoppable(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """The supported shape: keep the handle, terminate it from the hook."""
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    returned, taken = _run_and_stop(
        engine, _tool_of("popen_wait"), instance, heartbeat
    )

    assert returned, "the worker thread was still parked after Stop"
    assert taken < _STOP_GRACE_S
    assert not _is_beating(heartbeat), "the child was still running after Stop"
    qt_app.processEvents()


def test_popen_and_communicate_is_stoppable(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Blocking on the child's pipes rather than on its exit status.

    ``communicate()`` waits for the pipes to close as well as for the process,
    so it is a strictly harder case than ``wait()``.
    """
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    returned, taken = _run_and_stop(
        engine, _tool_of("popen_communicate"), instance, heartbeat
    )

    assert returned, "the worker thread was still parked after Stop"
    assert taken < _STOP_GRACE_S
    assert not _is_beating(heartbeat), "the child was still running after Stop"
    qt_app.processEvents()


def test_subprocess_run_without_a_hook_cannot_be_stopped(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """**Limitation.** ``subprocess.run()`` with no hook is not stoppable.

    This is the shape the reported accident had. ``run()`` keeps its handle to
    itself, so there is nothing for a hook to terminate even if one is declared,
    and the worker is parked in a C call where the injected exception cannot be
    raised. Stop does everything it can and the child runs to completion.

    Asserted rather than fixed because it cannot be fixed from decoui's side:
    the tool never gave anyone the handle. It is written down here so that the
    day it stops being true, somebody notices.
    """
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    returned, _ = _run_and_stop(
        engine, _tool_of("run_no_hook"), instance, heartbeat
    )

    assert not returned, "unexpectedly stoppable -- has the contract changed?"
    assert _is_beating(heartbeat), "the child died, but nothing should have killed it"
    qt_app.processEvents()


def test_subprocess_run_with_a_hook_is_still_not_stoppable(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """**Limitation.** Declaring ``on_cancel`` does not rescue ``run()``.

    Worth its own test because it is the fix a reader would reach for first:
    the hook fires, finds ``self.proc`` still None, and has nothing to do.
    Declaring a hook is necessary but not sufficient -- the tool has to keep the
    handle too.
    """
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    returned, _ = _run_and_stop(
        engine, _tool_of("run_with_hook"), instance, heartbeat
    )

    assert not returned, "unexpectedly stoppable -- has the contract changed?"
    assert _is_beating(heartbeat)
    qt_app.processEvents()


def test_a_child_that_refuses_sigterm(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """What ``terminate()`` is worth against a process that declines it.

    On POSIX ``terminate()`` is SIGTERM, which a process may ignore -- and a
    client parked in a network read often behaves as though it does. On Windows
    it is ``TerminateProcess``, which cannot be declined. The assertion is
    therefore platform-dependent, which is itself the thing worth knowing.
    """
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat, ignore_term=True)

    returned, _ = _run_and_stop(
        engine, _tool_of("popen_wait"), instance, heartbeat
    )

    if sys.platform == "win32":
        assert returned, "TerminateProcess cannot be declined"
        assert not _is_beating(heartbeat)
    else:
        assert not returned, "SIGTERM was ignored, so the child should live on"
        assert _is_beating(heartbeat)
    qt_app.processEvents()


def test_a_grandchild_survives_terminating_its_parent(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """**Limitation.** ``terminate()`` kills one process, not a process tree.

    This is the case that bites when a tool runs its client through a shell, or
    when the client forks a worker of its own: the parent dies, Stop looks like
    it worked, and the grandchild keeps the connection open.
    """
    heartbeat = tmp_path / "beat.txt"
    grandchild = tmp_path / "grandchild.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(
        heartbeat, spawn_child=True, grandchild_heartbeat=grandchild
    )

    returned, _ = _run_and_stop(
        engine, _tool_of("popen_wait"), instance, heartbeat
    )

    assert returned, "the worker thread was still parked after Stop"
    assert not _is_beating(heartbeat), "the direct child should be gone"
    assert _is_beating(grandchild), (
        "the grandchild died -- if this is now handled, update the docs"
    )
    qt_app.processEvents()


def test_a_wedged_run_does_not_block_the_next_one(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """A tool that cannot be stopped must not take the application with it.

    Workers share ``QThreadPool.globalInstance()``. If an unstoppable run held
    a pool thread and the pool had only one, every other tool would queue behind
    it and the whole application would appear frozen -- a far worse outcome than
    one stuck tab.
    """
    heartbeat = tmp_path / "beat.txt"
    stuck = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    stuck.run(_tool_of("run_no_hook"), instance, {})
    _wait_for_beat(heartbeat)
    stuck.cancel()

    # A second, ordinary run on its own engine must still complete promptly.
    other = _engine(tmp_path)
    done: list[str] = []
    other.finished.connect(lambda _result, status: done.append(status))

    quick = _External()
    quick.argv = [sys.executable, "-c", "print('quick')"]
    other.run(_tool_of("popen_wait"), quick, {})

    deadline = time.monotonic() + 15.0
    while not done and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.02)

    assert done == ["success"], (
        f"a second run did not finish while one was wedged: {done!r}; "
        f"pool max={QThreadPool.globalInstance().maxThreadCount()}"
    )


# ── The supported way: decoui.run_process ─────────────────────────────────────


def test_run_process_is_stoppable_without_declaring_anything(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """The point of the helper: no ``on_cancel``, no kept handle, still stops.

    Compare with ``test_subprocess_run_without_a_hook_cannot_be_stopped``, which
    is the same tool written the obvious way and cannot be stopped at all.
    """
    heartbeat = tmp_path / "beat.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(heartbeat)

    returned, taken = _run_and_stop(engine, _tool_of("helper"), instance, heartbeat)

    assert returned, "the worker thread was still parked after Stop"
    assert taken < _STOP_GRACE_S
    assert not _is_beating(heartbeat), "the child was still running after Stop"
    qt_app.processEvents()


def test_run_process_takes_the_grandchild_with_it(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """The tree, not just the child.

    ``terminate()`` on the direct child leaves the grandchild holding the
    connection open -- see
    ``test_a_grandchild_survives_terminating_its_parent``. This is that case
    with the same program, run through the helper instead.
    """
    heartbeat = tmp_path / "beat.txt"
    grandchild = tmp_path / "grandchild.txt"
    engine = _engine(tmp_path)
    instance = _External()
    instance.argv = _command(
        heartbeat, spawn_child=True, grandchild_heartbeat=grandchild
    )

    returned, _ = _run_and_stop(
        engine, _tool_of("helper_tree"), instance, heartbeat
    )

    assert returned, "the worker thread was still parked after Stop"
    assert not _is_beating(heartbeat), "the direct child survived"
    assert not _is_beating(grandchild), "the grandchild survived"
    qt_app.processEvents()


def test_run_process_streams_output_to_the_console(
    qt_app: QApplication, tmp_path: Path
) -> None:
    """Output reaches the page console, which plain subprocess cannot manage.

    The worker replaces ``sys.stdout`` with an object that has no ``fileno()``,
    so a child left to inherit stdout writes past the console rather than into
    it. The helper reads the pipe and prints, which is what puts the lines in
    front of the user.
    """
    engine = _engine(tmp_path)
    lines: list[tuple[str, str]] = []
    engine.log_line.connect(lambda level, message: lines.append((level, message)))

    instance = _External()
    instance.argv = [
        sys.executable, "-c",
        "print('first'); print('second'); import sys; print('third', file=sys.stderr)",
    ]
    done: list[str] = []
    engine.finished.connect(lambda _r, status: done.append(status))
    engine.run(_tool_of("helper"), instance, {})

    deadline = time.monotonic() + 15.0
    while not done and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.02)

    assert done == ["success"]
    printed = [message for level, message in lines if level == "stdout"]
    # stderr is merged into stdout, so a program's diagnostics are not lost.
    assert "first" in printed and "second" in printed and "third" in printed


def test_run_process_reports_a_failure_but_not_a_cancellation(
    tmp_path: Path
) -> None:
    """``check=True`` distinguishes the program failing from decoui killing it.

    A cancelled child exits non-zero because decoui killed it. Raising for that
    would turn every Stop into an error in the history, which is the opposite of
    what the user just asked for.
    """
    from decoui import ProcessError

    failing = [sys.executable, "-c", "raise SystemExit(3)"]

    result = run_process(failing)
    assert result.returncode == 3
    assert not result.cancelled

    with pytest.raises(ProcessError) as caught:
        run_process(failing, check=True)
    assert caught.value.result.returncode == 3


def test_run_process_refuses_a_shell() -> None:
    """A shell is the thing that leaves an unkillable grandchild behind."""
    with pytest.raises(ValueError, match="does not run a shell"):
        run_process(["echo", "hi"], shell=True)


def test_run_process_refuses_to_have_its_streams_taken(tmp_path: Path) -> None:
    """The pipes are how output reaches the console; they are not negotiable."""
    with pytest.raises(ValueError, match="stdout"):
        run_process([sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL)
