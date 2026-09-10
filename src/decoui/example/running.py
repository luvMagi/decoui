"""What happens between pressing Run and the run ending."""
from __future__ import annotations

import logging
import subprocess
import sys
import time

from decoui import progress, run_process, tool, toolset

from .samples import LANGUAGE_SAMPLES

#: The child program both cancellation tools run. One line a second, unbuffered,
#: so the streaming is visible rather than arriving all at once at the end.
_TICKER = (
    "import sys, time\n"
    "for i in range(int(sys.argv[1])):\n"
    "    print(f'child tick {i + 1}', flush=True)\n"
    "    time.sleep(1)\n"
)


@toolset(
    label="Running",
    tags=["run"],
    description="Output, progress, confirmation, timeouts and stopping.",
)
class RunTools:
    """What happens between pressing Run and the run ending.

    The two cancellation tools are the pair worth reading together:
    :meth:`external` is how to shell out, and :meth:`external_by_hand` is what
    that one is doing on your behalf.
    """

    def __init__(self) -> None:
        """Declare the child-process slot the cancel hook reads.

        Initialising it here means :meth:`stop_child` can read ``self._child``
        directly. A tool that assigns such state only inside the tool body must
        read it defensively instead -- ``getattr(self, "_child", None)`` -- since
        Stop can be pressed before the assignment happens.
        """
        self._child: subprocess.Popen | None = None

    @tool(label="Log Levels", description="One line at every level.")
    def log_levels(self, message: str = "test message") -> str:
        """Emit one line at every level, including raw stdout.

        Useful for seeing the console colours and the log window's level filter.
        ``print`` output arrives as level ``stdout``.

        Args:
            message: Text appended to each line.

        Returns:
            A confirmation string.
        """
        print(f"stdout: {message}")
        logging.debug("DEBUG: %s", message)
        logging.info("INFO: %s", message)
        logging.warning("WARNING: %s", message)
        logging.error("ERROR: %s", message)
        logging.critical("CRITICAL: %s", message)
        return "Emitted one line at each level."

    # timeout= cancels the run through exactly the path Stop uses, so a tool
    # that cleans up after Stop cleans up after a timeout too.
    @tool(
        label="Long Task",
        description="Reports progress. Press Stop, or let it time out.",
        timeout=60,
    )
    def long_task(self, steps: int = 10, fail_at: int = 0) -> str:
        """Work through a number of steps, reporting progress as it goes.

        Set **fail at** to a step number to see what an exception looks like:
        the traceback reaches the console and the run is recorded as an error.

        Args:
            steps: How many steps to work through.
            fail_at: Raise at this step. 0 never raises.

        Returns:
            A summary of the work done.

        Raises:
            RuntimeError: When the step named by ``fail_at`` is reached.
        """
        for index in range(steps):
            # progress(done, total, message). A total of 0 leaves the bar in its
            # indeterminate sweep and updates only the message. Reports are
            # throttled to ~10/s, except one that completes a known total.
            progress(index, steps, f"step {index + 1} of {steps}")
            if fail_at and index + 1 == fail_at:
                raise RuntimeError(f"asked to fail at step {fail_at}")
            # A plain sleep is interruptible: the worker is at a bytecode
            # boundary often enough for Stop's injected exception to land. That
            # is *not* true of a blocking C call -- see external_by_hand below.
            time.sleep(0.4)
        progress(steps, steps, "done")
        return f"Completed {steps} steps."

    # confirm=True puts a Yes/No dialog in front of the run. Declare it on
    # anything destructive: it is greppable, so `grep -r "confirm=True"` gives
    # an inventory of everything in an application that can do damage.
    @tool(
        label="Destructive",
        description="Asks for confirmation before it runs.",
        confirm=True,
    )
    def destructive(self, target: str = "staging") -> str:
        """Pretend to do something that cannot be undone.

        Args:
            target: What would have been destroyed.

        Returns:
            What did not actually happen.
        """
        logging.warning("pretending to wipe %s", target)
        return f"{target} was not really touched."

    # ── Copy this one when your tool shells out ───────────────────────────────
    #
    # run_process() is the supported way to run an external program, and the
    # reason is cancellation. Stop works by injecting an exception into the
    # worker thread, and CPython raises it at the next bytecode boundary -- a
    # thread parked inside subprocess.run() does not reach one until the child
    # exits by itself. The child has to be killed from outside first.
    #
    # Doing that by hand needs three things, and the obvious way to write it
    # gets none of them:
    #
    #   1. keep the Popen handle where the GUI thread can reach it. This is the
    #      one subprocess.run() cannot do at all -- it keeps its handle to
    #      itself, so declaring on_cancel does not help. That is the shape a
    #      real incident had: Stop appeared to work and the dump kept running.
    #   2. declare @tool(on_cancel=...) and terminate the child from it.
    #   3. remember terminate() kills one process and not the tree under it, so
    #      anything the child forked -- or a shell in between -- survives it.
    #
    # run_process does all three, and two more things plain subprocess does not:
    # it prints the child's output line by line as it arrives (decoui replaces
    # sys.stdout with an object that has no fileno(), so a child left to inherit
    # stdout writes *past* the console), and it reports whether a non-zero exit
    # was the program failing or decoui killing it.
    #
    # shell=True is refused: a shell is an extra process in between, it is what
    # makes quoting a security question, and it is what leaves a grandchild
    # holding the connection open after the shell is killed. Pass a list.
    #
    # See docs/cancelling-a-run.md for the measurements behind all of this.
    @tool(
        label="Run External Tool",
        description="Shell out through decoui's runner. Stop works with nothing declared.",
    )
    def external(self, seconds: int = 30) -> str:
        """Run an external program and show its output as it arrives.

        Press Stop at any point: the program is ended, along with anything it
        started, and the run is recorded as cancelled rather than as a failure.

        Args:
            seconds: How long the program should run. It prints one line a
                second, so this is also how many lines to expect.

        Returns:
            How the program ended.
        """
        result = run_process([sys.executable, "-u", "-c", _TICKER, str(seconds)])
        # Distinguishing the two is the caller's job -- run_process reports it
        # rather than guessing what a non-zero status meant.
        if result.cancelled:
            return "Stopped, and the child went with it."
        return f"Child exited {result.returncode}."

    # The long way round, kept because it shows what run_process is doing. Do
    # not copy this one; copy external() above. Note what it still does *not*
    # handle: terminate() reaches this child and nothing the child spawned.
    @tool(
        label="Run External By Hand",
        description="The same thing written out: kept handle, on_cancel, terminate.",
        on_cancel="stop_child",
        timeout=120,
    )
    def external_by_hand(self, seconds: int = 30) -> str:
        """Run an external program, managing the child process directly.

        Behaves like **Run External Tool** from the outside. The difference is
        only in how it is written.

        Args:
            seconds: How long the program should run.

        Returns:
            How the program ended.
        """
        # The `with` matters on the cancelled path: Popen.__exit__ closes the
        # pipes and waits, which is what reaps the child the hook terminated.
        # Without it the child dies but lingers as a zombie, because the
        # injected exception interrupts this method before it can wait().
        with subprocess.Popen(
            [sys.executable, "-u", "-c", _TICKER, str(seconds)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        ) as child:
            self._child = child
            for line in child.stdout:
                print(line.rstrip())
        return f"Child exited {child.returncode}."

    def stop_child(self) -> None:
        """End the child process when the run is cancelled.

        Runs on the GUI thread, before the worker is interrupted, while that
        worker is still blocked reading the child's pipe. Terminating the child
        is what lets that read return at all.

        ``getattr`` rather than ``self._child``: Stop can arrive before the tool
        has assigned it, and the hook has to survive that -- a second Stop is
        the user's only way out of the case where the first one was too early.
        """
        child = getattr(self, "_child", None)
        if child is not None and child.poll() is None:
            child.terminate()

    # A tool with no parameters at all, and the one whose Help page comes from
    # Markdown files rather than from its docstring.
    #
    # The path is relative to *this module's directory*, and decoui inserts a
    # language directory into it. help="help/language-samples.md" is looked for
    # in this order:
    #
    #   example/help/<interface language>/language-samples.md
    #   example/help/en/language-samples.md
    #   example/help/language-samples.md
    #
    # This package ships the first two, so the page is Japanese under a Japanese
    # interface and English under everything else. The file replaces the prose
    # only -- the summary, the parameter table and Returns still come from the
    # docstring below, because those describe the signature and a file sitting
    # beside the module cannot be checked against it.
    @tool(
        label="Language Samples",
        description="Print three lines in each of decoui's interface languages.",
        help="help/language-samples.md",
    )
    def language_samples(self) -> str:
        """Print three lines of sample text for every interface language.

        The lines go to the console, which is drawn in the theme's monospaced
        face -- the stack most likely to be missing a script. To judge the
        interface face instead, change language in Settings and read the sidebar.

        Returns:
            A count of what was printed.
        """
        for code, name, lines in LANGUAGE_SAMPLES:
            print(f"[{code}] {name}")
            for line in lines:
                print(f"  {line}")
            print()
        return f"Printed {len(LANGUAGE_SAMPLES)} languages, 3 lines each."
