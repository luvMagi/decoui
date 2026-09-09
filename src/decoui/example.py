"""Example toolset classes — covers every supported widget type and feature."""
from __future__ import annotations

import enum
import logging
import pathlib
import time

from decoui import tool, toolset
from decoui.storage.db import get_setting, set_setting


# ── Shared enums ──────────────────────────────────────────────────────────────

class LogLevel(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Encoding(enum.Enum):
    UTF8 = "utf-8"
    GBK = "gbk"
    Latin1 = "latin-1"


class SortOrder(enum.Enum):
    Ascending = "asc"
    Descending = "desc"


# ── ToolSet 1: Text — str, int, bool, list ───────────────────────────────────

@toolset(
    label="Text Tools",
    tags=["text", "basic"],
    description="String and text processing utilities.\nCovers: str, int, bool, list parameters.",
)
class TextTools:

    @tool(
        label="Count Characters",
        description="Count characters, words and lines. Demonstrates str + logging output.",
        placeholders={"content": "Paste your text here…"},
    )
    def count(self, content: str = "") -> str:
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

    @tool(
        label="Sum List",
        description="Sum a list of numbers. Shows print output + error handling.",
        placeholders={"numbers": "e.g. 1, 2, 3\n4, 5"},
    )
    def sum_list(self, numbers: list = None, absolute: bool = False) -> str:
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

    @tool(
        label="All Log Levels",
        description="Emit one line at every log level. Use View Full Log to see level filtering.",
        placeholders={"message": "Base message text"},
    )
    def all_log_levels(self, message: str = "test message") -> str:
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
        description="Simulated long-running task with progress output. Try fail_on_step > 0.",
        confirm=True,
    )
    def slow_task(
        self,
        steps: int = 5,
        delay: float = 0.4,
        fail_on_step: int = 0,
    ) -> str:
        for i in range(1, steps + 1):
            if fail_on_step and i == fail_on_step:
                raise RuntimeError(f"Simulated failure at step {i}")
            logging.info("Step %d / %d", i, steps)
            print(f"  progress: {i}/{steps}")
            time.sleep(delay)
        return f"Completed {steps} steps."


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
        stored = get_setting("example.deploy.env")
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
        logging.info("Deploying %s %s to %s (%s)", service, version, env, region)
        if dry_run:
            logging.warning("dry_run is on — nothing was actually deployed.")
        # Remember the choice; on_startup() reads it back on the next launch.
        set_setting("example.deploy.env", env)
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
