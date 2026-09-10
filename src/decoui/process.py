"""Run an external program so that Stop can actually stop it.

A tool that shells out is the case decoui is worst at cancelling, and the reason
is structural rather than accidental. Cancellation works by injecting an
exception into the worker thread, and CPython raises that exception at the next
bytecode boundary -- which a thread parked inside ``subprocess.run()`` does not
reach until the child exits on its own. The child has to be killed from outside
before the worker can return at all.

Doing that by hand takes three things, and every one of them is easy to leave
out:

1. keep the ``Popen`` handle somewhere the GUI thread can reach,
2. declare ``@tool(on_cancel=...)`` and terminate the child from it,
3. remember that ``terminate()`` kills one process and not the tree under it,
   so a client that forks a worker -- or anything run through a shell -- leaves
   the grandchild holding the connection open.

``subprocess.run()``, which is what everyone writes first, cannot do step 1 at
all: it keeps its handle to itself, so a hook has nothing to terminate even when
one is declared.

:func:`run_process` does all three. It registers the child with the running
worker, so Stop kills it -- and everything it spawned -- without the tool
declaring anything. It also streams the child's output into the page console
line by line, which plain ``subprocess`` does not: decoui replaces ``sys.stdout``
with an object that has no ``fileno()``, so a child left to inherit stdout writes
past the console rather than into it.

Example:
    @tool(label="Dump")
    def dump(self, database: str = "app") -> str:
        result = run_process(["pg_dump", "-d", database, "-f", "dump.sql"])
        return f"pg_dump exited {result.returncode}"
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import IO, Any, Sequence

from .engine.worker import current_worker

#: How long a child is given to exit after being asked politely, before it is
#: killed outright. Short enough that Stop feels immediate, long enough for a
#: database client to close its connection rather than leaving it to time out
#: server-side.
_GRACE_SECONDS = 3.0


@dataclass(frozen=True)
class ProcessResult:
    """What an external program left behind.

    Attributes:
        returncode: The child's exit status. Negative on POSIX when it was
            killed by a signal, as ``subprocess`` reports it.
        output: Everything the child wrote to stdout and stderr, interleaved in
            the order it arrived. Already printed to the console line by line;
            this is the collected copy, for a tool that wants to parse it.
        cancelled: True when decoui killed the child because the run was
            stopped, rather than the child exiting on its own.
    """

    returncode: int
    output: str
    cancelled: bool


class ProcessError(RuntimeError):
    """Raised by :func:`run_process` when ``check=True`` and the child failed.

    Attributes:
        result: The full result, so a caller that catches this can still read
            the output the child produced before it failed.
    """

    def __init__(self, argv: Sequence[str], result: ProcessResult) -> None:
        """Describe the failure in terms of what was run.

        Args:
            argv: The command line, for the message.
            result: The completed result.
        """
        super().__init__(
            f"{argv[0] if argv else '<command>'} exited {result.returncode}"
        )
        self.result = result


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a child process and everything it spawned.

    Runs on a throwaway thread, because it is called from the GUI thread during
    Stop and the polite phase takes seconds. Blocking there would freeze the
    window for exactly as long as the child took to think about it.

    Args:
        proc: The child to kill. Already-exited children are left alone.

    Note:
        The tree is walked while the parent is **still alive**. On Windows
        ``taskkill /T`` finds descendants through their parent pid, and once the
        parent has gone an orphan can no longer be traced back to it; on POSIX
        the group id is inherited, which is why the child is started in a
        session of its own. Kill the parent first and the grandchildren survive,
        which is the bug this function exists to avoid.
    """
    if proc.poll() is not None:
        return

    if sys.platform == "win32":
        # /T for the tree, /F because a console process has no message loop to
        # receive a polite request through -- there is no graceful phase to
        # offer it. Output is swallowed: taskkill reports "process not found"
        # on a child that exited a moment ago, which is not an error here.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return

    # POSIX: the child leads its own process group (start_new_session below),
    # so one signal reaches every descendant that has not left the group.
    try:
        group = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError):
        return

    for sig, wait in ((signal.SIGTERM, _GRACE_SECONDS), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(group, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def _pump(stream: IO[str], collected: list[str]) -> None:
    """Read a child's output and print it, one line at a time.

    Args:
        stream: The child's merged stdout/stderr pipe.
        collected: List each line is appended to, for the returned result.

    Note:
        ``print`` is what reaches the page console: the worker has replaced
        ``sys.stdout`` for the duration of the run. Reading line by line rather
        than with ``communicate()`` is what makes a long-running program's
        output appear as it happens instead of all at once at the end.
    """
    try:
        for line in stream:
            line = line.rstrip("\r\n")
            collected.append(line)
            print(line)
    except (OSError, ValueError):
        # The pipe was closed under us, which is what killing the child does.
        pass


def run_process(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    encoding: str = "utf-8",
    errors: str = "replace",
    **popen_kwargs: Any,
) -> ProcessResult:
    """Run an external program, streaming its output, and let Stop kill it.

    Args:
        argv: The command and its arguments. A list, not a string: ``shell=True``
            is not offered, because a shell is one more process between decoui
            and the program, it is the thing that makes quoting a security
            question, and on Windows it is what leaves an unkillable grandchild.
        cwd: Working directory for the child.
        env: Environment for the child, or None to inherit this process's.
        check: Raise :class:`ProcessError` when the child exits non-zero. A run
            that was **cancelled** never raises -- the non-zero status is
            decoui's doing, not the program's.
        encoding: How to decode the child's output.
        errors: Decoding error policy. Defaults to ``"replace"`` so that a
            program emitting one bad byte cannot fail the tool.
        **popen_kwargs: Passed through to ``subprocess.Popen``. ``stdout``,
            ``stderr`` and ``stdin`` are not accepted: the pipes are how output
            reaches the console.

    Returns:
        The child's status and collected output.

    Raises:
        ProcessError: If ``check`` is set and the child failed on its own.
        ValueError: If a stream is passed through ``popen_kwargs``, or if
            ``shell=True`` is requested.

    Note:
        Called outside a decoui worker -- from a test, or from a tool invoked
        directly -- it still runs the program and still streams the output. Only
        the cancellation registration is skipped, because there is nothing to
        register with.
    """
    for reserved in ("stdout", "stderr", "stdin"):
        if reserved in popen_kwargs:
            raise ValueError(
                f"run_process() manages {reserved} itself; it is how the "
                f"program's output reaches the console."
            )
    if popen_kwargs.get("shell"):
        raise ValueError(
            "run_process() does not run a shell. Pass the program and its "
            "arguments as a list: a shell is an extra process between decoui "
            "and the program, and on Windows it is what a killed tree leaves "
            "behind still holding the connection open."
        )

    if sys.platform != "win32":
        # Its own process group, so one signal reaches everything it spawns.
        popen_kwargs.setdefault("start_new_session", True)

    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        encoding=encoding,
        errors=errors,
        bufsize=1,
        **popen_kwargs,
    )

    worker = current_worker()
    if worker is not None:
        worker.register_process(proc)

    collected: list[str] = []
    try:
        if proc.stdout is not None:
            _pump(proc.stdout, collected)
        proc.wait()
    finally:
        if worker is not None:
            worker.forget_process(proc)
        if proc.stdout is not None:
            proc.stdout.close()

    cancelled = bool(worker is not None and worker.killed(proc))
    result = ProcessResult(
        returncode=proc.returncode,
        output="\n".join(collected),
        cancelled=cancelled,
    )
    if check and result.returncode != 0 and not cancelled:
        raise ProcessError(list(argv), result)
    return result


def _kill_tree_async(proc: subprocess.Popen) -> None:
    """Kill a process tree without blocking the caller.

    Args:
        proc: The child to kill.
    """
    threading.Thread(
        target=_kill_tree, args=(proc,), name="decoui-kill", daemon=True
    ).start()
