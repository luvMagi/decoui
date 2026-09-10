"""A deliberately hard-to-kill child process, for testing that Stop works.

This is not a test. It is the program the cancellation tests spawn, standing in
for the ``pg_dump`` that could not be stopped: something long-running, noisy on
stdout, and -- with the right flags -- as stubborn as a real database client.

Run it directly to watch it behave::

    python tests/heavy_background_task.py --seconds 5 --heartbeat beat.txt

Liveness is reported through a **heartbeat file** rather than through a pid.
A pid is not a reliable liveness check across platforms: on Windows a pid stays
openable for as long as any handle to the exited process is held, so a dead
child still answers. A file whose contents stop advancing is unambiguous, needs
no third-party dependency, and works the same for a grandchild that the test has
no handle to at all.

Flags exist for one failure mode each:

``--ignore-term``
    Install a SIGTERM handler that refuses to die. This is what a client
    blocked in a network read can look like: ``Popen.terminate()`` asks
    politely on POSIX, and a process is free to decline. On Windows
    ``terminate()`` is ``TerminateProcess``, which cannot be declined, so this
    flag is a no-op there -- which is itself worth knowing.

``--spawn-child``
    Start a grandchild that outlives this process. Killing a shell, or a client
    that forks a worker, leaves the grandchild holding the connection open.
    This is the case a naive ``terminate()`` does not cover.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _beat(path: Path | None, tag: str, count: int) -> None:
    """Write one heartbeat, so a watcher can tell this process is still alive.

    Args:
        path: File to write, or None to skip.
        tag: Which process is beating -- ``"child"`` or ``"grandchild"``.
        count: Monotonically increasing tick.
    """
    if path is None:
        return
    try:
        path.write_text(f"{tag} {count} {time.time():.3f}\n", encoding="utf-8")
    except OSError:
        # A watcher deleting the file mid-run is not this program's problem.
        pass


def _ignore_term() -> None:
    """Refuse SIGTERM, the way a client parked in a syscall can appear to.

    Note:
        SIGINT is left alone. A process that ignored every signal would be
        untestable rather than realistic.
    """
    def handler(_signum: int, _frame: object) -> None:
        print("child: ignoring SIGTERM", flush=True)

    for name in ("SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            try:
                signal.signal(signum, handler)
            except (OSError, ValueError, RuntimeError):
                # Not every signal is settable on every platform or thread.
                pass


def _spawn_grandchild(seconds: float, heartbeat: Path | None) -> subprocess.Popen:
    """Start a copy of this program that outlives us.

    Args:
        seconds: How long the grandchild should run.
        heartbeat: The grandchild's own heartbeat file, or None.

    Returns:
        The grandchild process.
    """
    argv = [
        sys.executable, os.path.abspath(__file__),
        "--seconds", str(seconds),
        "--tag", "grandchild",
    ]
    if heartbeat is not None:
        argv += ["--heartbeat", str(heartbeat)]
    return subprocess.Popen(argv)


def main(argv: list[str] | None = None) -> int:
    """Run until told to stop, or until the clock runs out.

    Args:
        argv: Command line, or None to read ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--heartbeat", type=Path, default=None)
    parser.add_argument("--grandchild-heartbeat", type=Path, default=None)
    parser.add_argument("--ignore-term", action="store_true")
    parser.add_argument("--spawn-child", action="store_true")
    parser.add_argument("--tag", default="child")
    args = parser.parse_args(argv)

    if args.ignore_term:
        _ignore_term()

    grandchild = None
    if args.spawn_child:
        grandchild = _spawn_grandchild(args.seconds, args.grandchild_heartbeat)
        print(f"child: spawned grandchild pid={grandchild.pid}", flush=True)

    print(f"{args.tag}: started pid={os.getpid()}", flush=True)
    deadline = time.monotonic() + args.seconds
    count = 0
    try:
        while time.monotonic() < deadline:
            _beat(args.heartbeat, args.tag, count)
            # Short sleeps rather than one long one: the point is to keep
            # beating, not to be unresponsive for reasons of our own.
            time.sleep(0.05)
            count += 1
    finally:
        print(f"{args.tag}: exiting after {count} ticks", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
