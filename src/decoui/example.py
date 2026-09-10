"""Example toolset classes -- covers every supported widget type and feature.

This module doubles as the reference for writing tools: every pattern decoui
supports appears here at least once, in working form. Copy from it rather than
from prose.

What each toolset demonstrates::

    TextTools     str, int, bool, list; a static completions list
    NumberTools   int, float; parsing failures reported through logging
    DemoTools     Enum (dropdown), dict (JSON field), pathlib.Path with dynamic
                  path completion, every log level, confirm=True, progress()
                  reporting, and on_cancel cleanup around a child process
    AssistTools   completions / cascade / defaults driven by instance state
                  loaded in on_startup()
    FontTools     a tool with no parameters at all, whose output is meant to be
                  looked at rather than read: sample text in every script the
                  interface ships a language for; also the one tool whose Help
                  page comes from a Markdown file rather than from its docstring

Note:
    **A tool's docstring is written for the person using the tool**, not for the
    person reading this file. It is the source the Help panel collects: the
    summary line, the paragraphs under it and the ``Args:`` entries all reach
    the screen. So they say what the field is for, never which Qt widget the
    annotation happens to produce.

    Notes aimed at whoever is copying this code -- which annotation builds which
    widget, why a check is written the way it is -- live in ``#`` comments above
    the method instead. Comments are not collected, so the two audiences stay
    separated without either losing anything.

    **Logging needs a level set by the application.** decoui attaches its
    console handler to the root logger but does not change that logger's level,
    and an unconfigured root logger filters everything below WARNING. Several
    tools here log at INFO and DEBUG, so their output only reaches the console
    when the entry point has called ``logging.basicConfig(level=...)`` -- see
    ``main.py``. This module deliberately does not call it itself: configuring
    logging is the application's job, not an importable module's.

    Every tool here is an ordinary method with ordinary arguments, and every one
    of them can be called directly -- ``TextTools().count("abc")`` works with no
    GUI involved. That is the property to preserve when writing new tools.

    Tools return strings for convenience, but decoui does **not** display return
    values. Everything the user sees here comes from ``print()`` or ``logging``.
"""
from __future__ import annotations

import enum
import logging
import pathlib
import subprocess
import sys
import time

from decoui import progress, run_process, tool, toolset
from decoui import store


# ── Shared enums ──────────────────────────────────────────────────────────────

class LogLevel(enum.Enum):
    """Log levels offered as a dropdown.

    Any Enum subclass used as an annotation becomes a QComboBox, and the tool
    receives the member itself -- not its name or value.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Encoding(enum.Enum):
    """Text encodings offered as a dropdown.

    The member *name* is what the combo box shows; ``member.value`` is what the
    tool body passes to ``str.encode``.
    """

    UTF8 = "utf-8"
    GBK = "gbk"
    Latin1 = "latin-1"


class SortOrder(enum.Enum):
    """Sort direction offered as a dropdown."""

    Ascending = "asc"
    Descending = "desc"


# ── ToolSet 1: Text — str, int, bool, list ───────────────────────────────────

@toolset(
    label="Text Tools",
    tags=["text", "basic"],
    description="String and text processing utilities.\nCovers: str, int, bool, list parameters.",
)
class TextTools:
    """String utilities: str, int, bool and list parameters."""

    @tool(
        label="Count Characters",
        description="Count characters, words and lines. Demonstrates str + logging output.",
        placeholders={"content": "Paste your text here…"},
    )
    def count(self, content: str = "") -> str:
        """Count characters, words and lines.

        Demonstrates a plain ``str`` parameter (single-line field) and output
        through ``logging`` at two levels.

        # This is H1
        | Source | Where it comes from | What it becomes |
        |--------|--------------------|-----------------|
        | Tool docstring | `@tool`-decorated method | Summary, prose, parameter table, Returns, Raises |
        | Toolset docstring | `@toolset`-decorated class | The group's page |
        | Markdown file | `@tool(help="...")` | Replaces the tool's **prose** only |
        Args:
            content: Text to measure.

        Returns:
            A one-line summary. Recorded in history; not shown in the GUI.
        """
        words = len(content.split())
        lines = len(content.splitlines())
        logging.debug("raw input length: %d", len(content))
        logging.info("words=%d  lines=%d", words, lines)
        return f"{len(content)} chars / {words} words / {lines} lines"

    @tool(
        label="Repeat Text",
        description="Repeat a string N times. Demonstrates str + int + bool.",
        placeholders={"text": "Text to repeat", "separator": "e.g.  |  or a space"},
    )
    def repeat(
        self,
        text: str = "hello",
        times: int = 3,
        separator: str = " ",
        strip: bool = False,
    ) -> str:
        """Repeat a string, joined by a separator.

        Demonstrates ``int`` (spin box) and ``bool`` (check box) alongside text.

        Args:
            text: The string to repeat.
            times: How many copies.
            separator: Placed between copies.
            strip: Strip the joined result.

        Returns:
            The repeated text.
        """
        result = separator.join(text for _ in range(times))
        return result.strip() if strip else result

    @tool(
        label="Join Lines",
        description="Join a list of items into one string. Demonstrates list + a static completions list.",
        placeholders={"items": "one item per line, or comma-separated"},
        completions={"separator": [", ", " | ", " - ", " / ", " → ", "\t"]},
    )
    def join_lines(
        self,
        items: list = None,
        separator: str = ", ",
        uppercase: bool = False,
    ) -> str:
        """Join list items into one string.

        Demonstrates a ``list`` parameter (multi-line field, split on newlines
        and commas) plus a static ``completions`` list on a text field.

        Args:
            items: The items to join. None becomes an empty list -- a list field
                is never passed as None by the GUI, but a direct call may.
            separator: Placed between items.
            uppercase: Upper-case each item first.

        Returns:
            The joined string.
        """
        items = items or []
        if uppercase:
            items = [s.upper() for s in items]
        return separator.join(items)

    @tool(
        label="Sort Lines",
        description="Sort a list of strings. Demonstrates list + Enum (SortOrder).",
        placeholders={"lines": "one item per line"},
    )
    def sort_lines(
        self,
        lines: list = None,
        order: SortOrder = SortOrder.Ascending,
        deduplicate: bool = False,
    ) -> list:
        """Sort list items, optionally removing duplicates.

        Demonstrates a ``list`` parameter combined with an Enum dropdown.

        Args:
            lines: Items to sort.
            order: Sort direction; received as the Enum member.
            deduplicate: Drop repeats, keeping first occurrence.

        Returns:
            The sorted items.
        """
        items = lines or []
        if deduplicate:
            seen: set = set()
            unique = []
            for x in items:
                if x not in seen:
                    seen.add(x)
                    unique.append(x)
            items = unique
        return sorted(items, reverse=(order == SortOrder.Descending))


# ── ToolSet 2: Numbers — int, float, bool ────────────────────────────────────

@toolset(
    label="Number Tools",
    tags=["math", "basic"],
    description="Numeric calculation utilities.\nCovers: int, float, bool parameters.",
)
class NumberTools:
    """Numeric utilities: int, float and bool parameters."""

    @tool(
        label="Sum List",
        description="Sum a list of numbers. Shows print output + error handling.",
        placeholders={"numbers": "e.g. 1, 2, 3\n4, 5"},
    )
    def sum_list(self, numbers: list = None, absolute: bool = False) -> str:
        """Sum a list of integers entered as text.

        Demonstrates handling bad input *inside* the tool: the list field hands
        over strings, so conversion is the tool's job, and the failure is
        reported through ``logging.error`` rather than by raising -- which keeps
        the run recorded as a success with a readable message.

        Args:
            numbers: Values as strings.
            absolute: Sum absolute values.

        Returns:
            The total, or the parse error message.
        """
        numbers = numbers or []
        try:
            vals = [int(x) for x in numbers]
        except ValueError as e:
            logging.error("Parse error: %s", e)
            return f"Parse error: {e}"
        if absolute:
            vals = [abs(v) for v in vals]
        total = sum(vals)
        print(f"Summed {len(vals)} values → {total}")
        return f"Sum = {total}  (count={len(vals)})"

    @tool(
        label="Power",
        description="Compute base ^ exponent. Demonstrates float + bool.",
    )
    def power(
        self,
        base: float = 2.0,
        exponent: float = 10.0,
        round_result: bool = True,
    ) -> str:
        """Raise base to exponent.

        Demonstrates ``float`` parameters, which render as spin boxes with four
        decimal places.

        Args:
            base: The base.
            exponent: The exponent.
            round_result: Round to six decimals.

        Returns:
            The result as a string.
        """
        result = base ** exponent
        return str(round(result, 6) if round_result else result)

    @tool(
        label="Range Stats",
        description="Min / max / avg of a range. Demonstrates multiple int + bool.",
    )
    def range_stats(
        self,
        start: int = 1,
        end: int = 100,
        step: int = 1,
        include_end: bool = True,
    ) -> str:
        """Report count, min, max and average over a range.

        Demonstrates several ``int`` parameters on one form.

        Args:
            start: First value.
            end: Last value.
            step: Increment.
            include_end: Treat ``end`` as inclusive.

        Returns:
            A one-line summary, or a note that the range is empty.
        """
        stop = end + 1 if include_end else end
        nums = list(range(start, stop, step))
        if not nums:
            return "Empty range."
        return (
            f"Count={len(nums)}  Min={min(nums)}  "
            f"Max={max(nums)}  Avg={sum(nums) / len(nums):.2f}"
        )


# ── ToolSet 3: Demo — Enum, dict, all log levels, slow task ──────────────────

@toolset(
    label="Demo Tools",
    tags=["demo"],
    description="Showcases: Enum (QComboBox), dict (JSON input), all log levels, slow/failing tasks.",
)
class DemoTools:
    """Enum, dict and Path parameters, log levels, progress and cancellation.

    The last two tools are the pair worth reading together: ``slow_task`` shows
    what cancellation does for free, and ``run_child_process`` shows the case
    where it is not enough.
    """

    def __init__(self) -> None:
        """Declare the child-process slot the cancel hook reads.

        Initialising it here means :meth:`stop_child` can read ``self._child``
        directly. A tool that assigns such state only inside the tool body must
        read it defensively instead -- ``getattr(self, "_child", None)`` -- since
        Stop can be pressed before the assignment happens.
        """
        self._child: subprocess.Popen | None = None

    @tool(
        label="All Log Levels",
        description="Emit one line at every log level. Use View Full Log to see level filtering.",
        placeholders={"message": "Base message text"},
    )
    def all_log_levels(self, message: str = "test message") -> str:
        """Emit one line at every level, including raw stdout.

        Useful for seeing the console colours and the level filter in the log
        window. ``print`` output arrives as level ``'stdout'``.

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

    @tool(
        label="Log Demo",
        description="Emit messages at a chosen level N times. Demonstrates Enum + list + int.",
        placeholders={"messages": "One message per line"},
    )
    def log_demo(
        self,
        messages: list = None,
        level: LogLevel = LogLevel.INFO,
        repeat: int = 1,
    ) -> str:
        """Emit chosen messages at a chosen level, repeatedly.

        Demonstrates dispatching on an Enum member received from a dropdown.

        Args:
            messages: Lines to emit.
            level: Which logging function to use.
            repeat: How many passes.

        Returns:
            A count of what was emitted.
        """
        messages = messages or ["Hello from decoui!"]
        log_fn = {
            LogLevel.DEBUG:    logging.debug,
            LogLevel.INFO:     logging.info,
            LogLevel.WARNING:  logging.warning,
            LogLevel.ERROR:    logging.error,
            LogLevel.CRITICAL: logging.critical,
        }[level]
        for _ in range(repeat):
            for msg in messages:
                log_fn("%s", msg)
        return f"Emitted {len(messages) * repeat} line(s) at {level.value}"

    @tool(
        label="Encode Text",
        description="Show byte encoding of text. Demonstrates str + Enum + bool.",
        placeholders={"text": "Text to encode"},
    )
    def encode_text(
        self,
        text: str = "Hello",
        encoding: Encoding = Encoding.UTF8,
        show_hex: bool = True,
    ) -> str:
        """Show the byte encoding of some text.

        Demonstrates using ``member.value`` from an Enum parameter.

        Args:
            text: Text to encode.
            encoding: Codec to use.
            show_hex: Show spaced hex instead of a bytes repr.

        Returns:
            The encoded bytes as text.
        """
        raw = text.encode(encoding.value)
        return raw.hex(" ").upper() if show_hex else repr(raw)

    @tool(
        label="Dict Inspector",
        description="Print dict contents. Demonstrates dict (JSON) parameter.",
        placeholders={"data": '{"key": "value", "count": 42}'},
    )
    def dict_inspector(
        self,
        data: dict,
        pretty: bool = True,
    ) -> str:
        """Print the contents of a dict.

        Demonstrates a ``dict`` parameter: a multi-line field parsed as JSON,
        falling back to a Python literal. Invalid input is rejected before the
        tool runs, so the body always receives a real dict.

        Note that ``data`` has no default, which is what draws the red asterisk
        on the form.

        Args:
            data: The parsed object.
            pretty: Indent the returned JSON.

        Returns:
            The dict re-serialised as JSON.
        """
        import json
        data = data or {}
        logging.info("received %d key(s)", len(data))
        for k, v in data.items():
            print(f"  {k}: {v!r}")
        return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)

    @tool(
        label="File Info",
        description=(
            "Show basic info about a file or folder. Demonstrates pathlib.Path plus "
            "shell-style path completion — start typing a path to get a popup."
        ),
        placeholders={"path": "Type a path, or use the buttons…"},
        completions={"path": "complete_path"},
    )
    def file_info(self, path: pathlib.Path = pathlib.Path()) -> str:
        """Report the type, resolved path and size of a filesystem entry.

        Demonstrates ``pathlib.Path``, which is the only annotation that builds
        the field with **File...** and **Folder...** buttons, and dynamic
        completion through a method named in ``completions``.

        Args:
            path: The entry to inspect. An empty field arrives as ``Path()``,
                i.e. the current directory -- never None -- which is why the
                emptiness check below looks the way it does.

        Returns:
            A short report, or an explanation of why there is none.
        """
        if not path or not str(path):
            return "No path provided."
        p = pathlib.Path(path)
        if not p.exists():
            return f"Path does not exist: {p}"
        stat = p.stat()
        kind = "directory" if p.is_dir() else "file"
        logging.info("inspecting %s: %s", kind, p)
        return (
            f"Type : {kind}\n"
            f"Path : {p.resolve()}\n"
            f"Size : {stat.st_size:,} bytes"
        )

    def complete_path(self, text: str) -> list[str]:
        """Return filesystem entries matching a partially typed path.

        Runs on a worker thread, so touching a slow or offline drive cannot
        freeze the window.

        Args:
            text: The path fragment typed so far.

        Returns:
            Up to 200 matching paths, directories first.
        """
        raw = text.strip()
        if not raw:
            base, prefix = pathlib.Path.home(), ""
        else:
            typed = pathlib.Path(raw).expanduser()
            if raw.endswith(("/", "\\")) and typed.is_dir():
                base, prefix = typed, ""
            else:
                base, prefix = typed.parent, typed.name.casefold()

        try:
            entries = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.casefold()))
        except OSError:
            # Unreadable or non-existent directory: offer nothing rather than fail.
            return []

        matches = [p for p in entries if p.name.casefold().startswith(prefix)]
        return [str(p) for p in matches[:200]]

    @tool(
        label="Slow Task",
        description=(
            "Simulated long-running task driving the progress bar. "
            "Try fail_on_step > 0 to see a failed run."
        ),
        confirm=True,
    )
    def slow_task(
        self,
        steps: int = 5,
        delay: float = 0.4,
        fail_on_step: int = 0,
    ) -> str:
        """Simulate a long task, reporting progress and optionally failing.

        Demonstrates three things:

        * ``confirm=True`` -- a Yes/No dialog before anything runs.
        * :func:`decoui.progress` -- passing a known ``total`` switches the bar
          from its indeterminate sweep to a real percentage, and the message
          replaces "Running..." beside it. Reports closer together than 100 ms
          are dropped, so calling it every iteration of a tight loop is fine.
        * A raised exception: the traceback is logged and the run is recorded
          with status ``'error'``.

        Because it only sleeps, this tool is interruptible by Stop on its own --
        the injected exception lands at a bytecode boundary between steps. See
        :meth:`run_child_process` for the case where that is not enough.

        Calling this method directly still works: outside the GUI
        :func:`decoui.progress` is a no-op, so nothing here needs decoui to be
        running.

        Args:
            steps: How many steps to run.
            delay: Seconds per step.
            fail_on_step: Raise at this step; 0 never fails.

        Returns:
            A completion message.

        Raises:
            RuntimeError: When ``fail_on_step`` is reached.
        """
        for i in range(1, steps + 1):
            if fail_on_step and i == fail_on_step:
                raise RuntimeError(f"Simulated failure at step {i}")
            # Reported before the work, so the bar shows what is starting.
            progress(i - 1, steps, f"step {i} of {steps}")
            logging.info("Step %d / %d", i, steps)
            time.sleep(delay)
        # The final report is never throttled away, so the bar reaches 100%.
        progress(steps, steps, "done")
        return f"Completed {steps} steps."

    # ── Copy this one when your tool shells out ──────────────────────────
    #
    # run_process() is the supported way to run an external program, and the
    # reason is cancellation. Stop works by injecting an exception into the
    # worker thread, and CPython raises it at the next bytecode boundary -- a
    # thread parked inside subprocess.run() does not reach one until the child
    # exits by itself. The child has to be killed from outside first.
    #
    # Doing that by hand needs three things, and the obvious way to write this
    # gets none of them:
    #
    #   1. keep the Popen handle where the GUI thread can reach it. This is the
    #      one subprocess.run() cannot do at all -- it keeps its handle to
    #      itself, so declaring on_cancel does not help. That is the shape a
    #      real incident had: Stop appeared to work and pg_dump kept running.
    #   2. declare @tool(on_cancel=...) and terminate the child from it.
    #   3. remember terminate() kills one process and not the tree under it, so
    #      anything the child forked -- or a shell in between -- survives it.
    #
    # run_process does all three. See run_child_process below for what steps 1
    # and 2 look like written out, and docs/cancelling-a-run.md for the
    # measurements behind these claims.
    #
    # Two more things it handles that plain subprocess does not:
    #
    #   * Output. decoui replaces sys.stdout with an object that has no
    #     fileno(), so a child left to inherit stdout writes *past* the console.
    #     run_process reads the pipe and prints line by line, so the output
    #     appears as it happens.
    #   * Telling failure from cancellation. result.cancelled is True only when
    #     decoui killed the child. Pass check=True and a program that fails on
    #     its own raises ProcessError, while a cancelled one never does -- a
    #     Stop must not be recorded as an error.
    #
    # shell=True is refused: a shell is an extra process in between, it is what
    # makes quoting a security question, and it is what leaves a grandchild
    # holding the connection open after the shell is killed. Pass a list.
    @tool(
        label="Run External Tool",
        description=(
            "Shell out through decoui's own runner. Press Stop while it runs: "
            "nothing here declares a cleanup hook, and it still stops."
        ),
    )
    def run_external(self, seconds: int = 30) -> str:
        """Run an external program and show its output as it arrives.

        Press Stop at any point: the program is ended, along with anything it
        started, and the run is recorded as cancelled rather than as a failure.

        Args:
            seconds: How long the program should run. It prints one line a
                second, so this is also how many lines to expect.

        Returns:
            How the program ended.
        """
        script = (
            "import sys, time\n"
            "for i in range(int(sys.argv[1])):\n"
            "    print(f'child tick {i + 1}', flush=True)\n"
            "    time.sleep(1)\n"
        )
        # A list, never a string: see the note above about shell=True. -u stops
        # the child buffering its output for the whole run, which would defeat
        # the streaming.
        result = run_process([sys.executable, "-u", "-c", script, str(seconds)])
        # Distinguishing the two is the caller's job -- run_process reports it
        # rather than guessing what a non-zero status meant.
        if result.cancelled:
            return "Stopped, and the child went with it."
        return f"Child exited {result.returncode}."

    @tool(
        label="Run Child Process",
        description=(
            "Start a child process and wait for it. Press Stop while it runs: "
            "the on_cancel hook is what actually kills the child."
        ),
        on_cancel="stop_child",
        timeout=120,
    )
    def run_child_process(
        self,
        seconds: int = 30,
        encoding: Encoding = Encoding.UTF8,
    ) -> str:
        """Run a chatty child process and stream its output to the console.

        This is the long way round, kept because it shows what
        ``run_process`` does on your behalf. To actually write a tool that
        shells out, copy [[DemoTools.run_external]] instead: it is four lines
        and it kills the whole process tree, which the hook below does not.

        Pressing Stop injects an exception into the worker thread, but this
        thread spends nearly all its time inside a C call -- reading the child's
        pipe -- where that exception cannot be raised. Without ``on_cancel`` the
        Stop button would appear to work, the page would go back to idle, and
        the child would keep running in the background. A ``try/finally`` around
        this body would not help either: it would not run until the child exited
        on its own, which is exactly what needs to be prevented.

        ``@tool(on_cancel="stop_child")`` closes that gap by running
        :meth:`stop_child` on the GUI thread, while this thread is still
        blocked. ``timeout=120`` uses the same path, so an overrunning child is
        cleaned up identically.

        Args:
            seconds: How long the child should run, one line of output a second.
            encoding: Codec used to decode the child's output. Getting this
                wrong is how console output turns to mojibake on a non-UTF-8
                system, so it is a parameter rather than a hidden default.

        Returns:
            A summary of how the child ended. Not reached when cancelled.
        """
        script = (
            "import sys, time\n"
            "for i in range(int(sys.argv[1])):\n"
            "    print(f'child tick {i + 1}', flush=True)\n"
            "    time.sleep(1)\n"
        )
        # The `with` matters on the cancelled path: Popen.__exit__ closes the
        # pipes and waits, which is what reaps the child the hook terminated.
        # Without it the child dies but lingers as a zombie, because the
        # injected exception interrupts this method before it can wait().
        # -u keeps the child from buffering its output for the whole run.
        with subprocess.Popen(
            [sys.executable, "-u", "-c", script, str(seconds)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=encoding.value,
        ) as child:
            # Published on self so the cancel hook, which runs on the GUI
            # thread, can reach it while this thread is blocked below.
            self._child = child
            logging.info("Started child process %d", child.pid)

            ticks = 0
            # Blocked in here between lines: this is where Stop cannot reach.
            for line in child.stdout:
                print(line.rstrip())
                ticks += 1
                progress(ticks, seconds, f"tick {ticks} of {seconds}")

            returncode = child.wait()

        # Cleared so the next run's "not started yet" case stays distinguishable
        # from this run's "already finished" one. Leaving the exited Popen here
        # would let a Stop pressed early in the next run inspect the wrong
        # process, find it dead, and terminate nothing.
        self._child = None
        return f"Child exited with {returncode} after {ticks} tick(s)."

    def stop_child(self) -> None:
        """Terminate the child process when the run is cancelled.

        Runs on the GUI thread, concurrently with :meth:`run_child_process`, so
        it does only one idempotent thing and returns immediately -- anything
        slower here would freeze the window.

        Reading ``self._child`` directly is safe only because ``__init__``
        creates the attribute. A tool that assigns its state inside the tool
        body must use ``getattr(self, "_child", None)``: Stop can be pressed in
        the moment before the assignment runs.
        """
        child = self._child
        if child is not None and child.poll() is None:
            logging.warning("Cancelled: terminating child process %d", child.pid)
            child.terminate()


# ── ToolSet 4: Form assist — completions, cascade, defaults ──────────────────

# Stand-in for a real data source (a database, an HTTP API, a config file).
_SERVICE_CATALOG = {
    "web-frontend":  {"version": "2.4.1", "owner": "frontend-team", "region": "eu-west-1"},
    "web-gateway":   {"version": "1.9.0", "owner": "platform-team", "region": "eu-west-1"},
    "auth-service":  {"version": "3.0.2", "owner": "identity-team", "region": "us-east-1"},
    "billing-api":   {"version": "0.8.7", "owner": "payments-team", "region": "us-east-1"},
    "report-worker": {"version": "1.2.0", "owner": "data-team",     "region": "ap-northeast-1"},
}


@toolset(
    label="Assist Demo",
    tags=["demo", "form"],
    description="Autocomplete, cascading fill and lazy defaults.\nType in Service to see the popup.",
)
class AssistTools:
    """Form assist: completions, cascading fill, and lazily loaded defaults.

    The pattern to copy here is the indirection: ``completions`` / ``cascade`` /
    ``defaults`` are given *method names*, not values. Decorator arguments are
    evaluated at import time, when no instance exists, so anything that depends
    on ``self`` has to be named and bound later.
    """

    def __init__(self) -> None:
        """Declare state, without loading it yet.

        Keeping __init__ trivial means the object always exists: if loading
        fails, decoui reports it in a dialog and this toolset still opens with
        the fallbacks declared here. A toolset whose __init__ raises disappears
        from the sidebar entirely.
        """
        self.preferences: dict = {"env": "staging", "dry_run": True}

    def on_startup(self) -> None:
        """Load persisted state before the window appears.

        decoui calls this once during startup, after every toolset has been
        constructed and before the event loop starts. A real tool would read a
        config file or query a service here; whatever lands on self is
        reachable from the defaults, completions and cascade callbacks below,
        because those name a method rather than capturing a value.

        Reading the settings table is safe here but would not be in a signature
        default: init_db() has run by now, and had not at import time.

        Two limits apply, see docs/startup-lifecycle.md:
          * this blocks the window from appearing, so keep it quick
          * the event loop is not running, so no timers and no worker threads
        """
        stored = store("example").get("deploy_env")
        if stored:
            self.preferences["env"] = stored

    @tool(
        label="Deploy Service",
        description=(
            "Type in 'service' to get a filtered popup; picking one fills version, "
            "owner and region automatically. 'env' offers a fixed list."
        ),
        placeholders={"service": "start typing: web, auth, billing…"},
        completions={
            "env": ["production", "staging", "development"],
            "service": "search_services",
        },
        cascade={"service": "describe_service"},
        defaults="load_defaults",
    )
    def deploy(
        self,
        service: str = "",
        env: str = "",
        version: str = "",
        owner: str = "",
        region: str = "",
        dry_run: bool = True,
    ) -> str:
        """Pretend to deploy a service, driven by the assist callbacks above.

        All three assist mechanisms are wired here at once:

        * ``completions["env"]`` is a static list -- no callback needed.
        * ``completions["service"]`` names :meth:`search_services`, which is
          called as the user types and runs on a worker thread.
        * ``cascade={"service": ...}`` names :meth:`describe_service`, which
          fills ``version``, ``owner`` and ``region`` once a service is chosen.
        * ``defaults="load_defaults"`` seeds the form when the page opens, from
          state ``on_startup()`` loaded -- not from anything evaluated at import.

        Args:
            service: Service name; drives the cascade.
            env: Target environment.
            version: Filled by the cascade.
            owner: Filled by the cascade.
            region: Filled by the cascade.
            dry_run: Defaults to True so the destructive path is opt-in.

        Returns:
            A one-line summary of what would have been deployed.
        """
        logging.info("Deploying %s %s to %s (%s)", service, version, env, region)
        if dry_run:
            logging.warning("dry_run is on — nothing was actually deployed.")
        # Remember the choice; on_startup() reads it back on the next launch.
        # store() is the public way to persist a preference -- it namespaces the
        # key, so nothing here can reach decoui's own settings.
        store("example")["deploy_env"] = env
        return f"{service} {version} → {env}"

    def search_services(self, text: str) -> list[str]:
        """Return catalog entries matching the typed text.

        Args:
            text: Whatever the user has typed so far.

        Returns:
            Matching service names, or the full catalog when nothing is typed.
        """
        if not text:
            return list(_SERVICE_CATALOG)
        needle = text.casefold()
        return [name for name in _SERVICE_CATALOG if needle in name.casefold()]

    def describe_service(self, value: str, form: dict) -> dict:
        """Derive the metadata fields for the chosen service.

        Args:
            value: The committed service name.
            form: Snapshot of the current form values.

        Returns:
            Values for the version, owner and region fields.
        """
        meta = _SERVICE_CATALOG.get(value)
        if meta is None:
            return {"version": "", "owner": "", "region": ""}
        return dict(meta)

    def load_defaults(self) -> dict:
        """Seed the form from state loaded during startup.

        Returns:
            Initial values for the form.
        """
        return dict(self.preferences)


# ── Language samples ──────────────────────────────────────────────────────────

# Three lines per language, in the order the locale files are shipped in.
#
# Line 1 is prose: it shows whether the face has the script at all, and how its
# letterforms sit next to the Latin tag in front of them. Line 2 is fixed-width
# bait -- digits, box drawing and, for the CJK entries, half- and full-width
# forms of the same characters -- because a console only reads as a console if
# those columns line up. Line 3 is the punctuation and diacritics that fall
# through to a fallback face first, which is where a stack shows its seams.
#
# The tags are deliberately ASCII: they are the fixed point the eye measures the
# rest of the line against.
_LANGUAGE_SAMPLES: list[tuple[str, str, tuple[str, str, str]]] = [
    ("en", "English", (
        "The quick brown fox jumps over the lazy dog.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "Curly \u201cquotes\u201d, an em\u2014dash, ellipsis\u2026 and a fraction \u00bd.",
    )),
    ("de-DE", "Deutsch", (
        "Falsches \u00dcben von Xylophonmusik qu\u00e4lt jeden gr\u00f6\u00dferen Zwerg.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "\u00c4\u00d6\u00dc \u00e4\u00f6\u00fc \u00df \u2014 \u201eGro\u00dfschreibung\u201c heute \u00fcblich.",
    )),
    ("es", "Espa\u00f1ol", (
        "El veloz murci\u00e9lago hind\u00fa com\u00eda feliz cardillo y kiwi.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "\u00bfQu\u00e9 a\u00f1o? \u00a1Ninguno! \u2014 \u00e1\u00e9\u00ed\u00f3\u00fa \u00fc \u00f1 \u00ab comillas \u00bb",
    )),
    ("fr-FR", "Fran\u00e7ais", (
        "Portez ce vieux whisky au juge blond qui fume.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "\u00e0\u00e2\u00e6\u00e7\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u0153\u00f9\u00fb\u00fc\u00ff \u2014 \u00ab espace fine \u00bb ; oui !",
    )),
    ("id-ID", "Bahasa Indonesia", (
        "Muharjo seorang xenofobia universal yang takut pada warga Qatar.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "Riwayat dijalankan \u2014 \u201ctanda kutip\u201d, titik\u2026 dan tanda hubung-.",
    )),
    ("ja-JP", "\u65e5\u672c\u8a9e", (
        "\u5b9f\u884c\u5c65\u6b74\u3092\u66f4\u65b0\u3057\u307e\u3057\u305f\u3002\u30c4\u30fc\u30eb\u3092\u691c\u7d22\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "0123456789  \uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19  \uff8a\uff9d\uff76\uff9e\uff78 / \u5168\u89d2  ──────",
        "\u6f22\u5b57\u30fb\u3072\u3089\u304c\u306a\u30fb\u30ab\u30bf\u30ab\u30ca\u3001\u300c\u62ec\u5f27\u300d\u3068\u9577\u97f3\u30fc\u3002",
    )),
    ("ko-KR", "\ud55c\uad6d\uc5b4", (
        "\ub2e4\ub78c\uc950 \ud4e8\uc988\ub97c \ub9c8\uc2dc\uba70 \uc2e4\ud589 \uae30\ub85d\uc744 \uc0c8\ub85c \uace0\uce68\ub2c8\ub2e4.",
        "0123456789  \uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19  \uac00\ub098\ub2e4\ub77c  ──────",
        "\ud55c\uae00\u00b7\u6f22\u5b57 \ud63c\uc6a9, \u300c\uad04\ud638\u300d\uc640 \ub9c8\uce68\ud45c.",
    )),
    ("pt-BR", "Portugu\u00eas", (
        "Zebras caolhas de Java querem passar fax para moscovita.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "\u00e1\u00e2\u00e3\u00e0\u00e7\u00e9\u00ea\u00ed\u00f3\u00f4\u00f5\u00fa \u2014 execu\u00e7\u00e3o conclu\u00edda, n\u00e3o?",
    )),
    ("ru-RU", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439", (
        "\u0421\u044a\u0435\u0448\u044c \u0436\u0435 \u0435\u0449\u0451 \u044d\u0442\u0438\u0445 \u043c\u044f\u0433\u043a\u0438\u0445 \u0444\u0440\u0430\u043d\u0446\u0443\u0437\u0441\u043a\u0438\u0445 \u0431\u0443\u043b\u043e\u043a.",
        "0123456789  \u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422  \u0430\u0432\u0435\u043a\u043c\u043d\u043e\u0440\u0441\u0442  ──────",
        "\u0401\u0451 \u0429\u0449 \u042a\u044a \u042c\u044c \u2014 \u00ab\u0451\u043b\u043e\u0447\u043a\u0438\u00bb \u0438 \u0442\u0438\u0440\u0435.",
    )),
    ("tr-TR", "T\u00fcrk\u00e7e", (
        "Pijamal\u0131 hasta ya\u011f\u0131z \u015fof\u00f6re \u00e7abucak g\u00fcvendi.",
        "0123456789  ILil1 O0o  \u0130i \u0049\u0131  ──────  [{(<>)}]",
        "\u00c7\u011e\u0130\u00d6\u015e\u00dc \u00e7\u011f\u0131\u00f6\u015f\u00fc \u2014 dotted \u0130 vs dotless \u0131.",
    )),
    ("zh-CN", "\u7b80\u4f53\u4e2d\u6587", (
        "\u5df2\u5237\u65b0\u8fd0\u884c\u5386\u53f2\uff0c\u8bf7\u5728\u4e0a\u65b9\u641c\u7d22\u5de5\u5177\u3002",
        "0123456789  \uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19  \u4e00\u4e8c\u4e09\u56db  ──────",
        "\u5168\u89d2\u6807\u70b9\uff1a\uff0c\u3002\uff1b\uff1a\u201c\u201d\u2018\u2019\uff08\uff09\u3010\u3011\u2014\u2014",
    )),
    ("zh-TW", "\u7e41\u9ad4\u4e2d\u6587", (
        "\u5df2\u91cd\u65b0\u6574\u7406\u57f7\u884c\u6b77\u53f2\uff0c\u8acb\u5728\u4e0a\u65b9\u641c\u5c0b\u5de5\u5177\u3002",
        "0123456789  \uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19  \u58f9\u8cb3\u53c3\u8086  ──────",
        "\u5168\u5f62\u6a19\u9ede\uff1a\uff0c\u3002\uff1b\uff1a\u300c\u300d\u300e\u300f\uff08\uff09\u3010\u3011\u2500\u2500",
    )),
]


@toolset(
    label="Font Tools",
    tags=["demo", "text"],
    description="Prints multilingual sample text, for judging a theme's font stack.",
)
class FontTools:
    """Sample text in every language decoui's interface ships in.

    Written for looking at, not for parsing: a font stack is only as good as the
    scripts it actually covers, and the way to find a hole in one is to put the
    scripts side by side and look. The console is the place to do it because it
    draws in ``mono_family``, which is the stack most likely to be missing a
    script -- code faces often ship Latin and nothing else.
    """

    # help= points at a Markdown file instead of leaving the whole explanation
    # in the docstring below. The file supplies the prose on the Help page; the
    # summary, the parameter table and Returns still come from the docstring,
    # so the two cannot drift apart from the signature.
    #
    # The path is relative to this module's directory, and decoui inserts a
    # language directory into it when one exists -- tool_help/ja-JP/... would be
    # picked up automatically under a Japanese interface.
    @tool(
        label="Language Samples",
        description="Print three lines in each of decoui's interface languages.",
        help="tool_help/language-samples.md",
    )
    def language_samples(self) -> str:
        """Print three lines of sample text for every interface language.

        The lines go to the console through ``print``, so they are drawn in the
        theme's monospaced face. To judge the interface face instead, read the
        same scripts in the sidebar and the buttons after switching language in
        Settings.

        What to look for, per language: whether every character has a glyph at
        all, whether the digits and box-drawing line up into columns, and
        whether any run of characters is visibly a different face from the text
        around it -- that last one is the stack falling through, and it is only
        a fault if it looks like one.

        Returns:
            A count of what was printed.
        """
        for code, name, lines in _LANGUAGE_SAMPLES:
            print(f"[{code}] {name}")
            for line in lines:
                print(f"  {line}")
            print()

        return f"Printed {len(_LANGUAGE_SAMPLES)} languages, 3 lines each."
