"""Example toolset classes — covers every supported widget type and feature."""
from __future__ import annotations

import enum
import logging
import time

from decoui import tool, toolset


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
        description="Join a list of items into one string. Demonstrates list parameter.",
        placeholders={"items": "one item per line, or comma-separated"},
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
