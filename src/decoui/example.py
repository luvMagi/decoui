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

from decoui import progress, tool, toolset
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

        This is the tool to copy when writing anything that shells out.

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
