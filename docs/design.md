# decoui — Design & Implementation Reference

> Decorator-Driven GUI Framework for Python · `pip install decoui`

**Related documents**

| Document | Covers |
|---|---|
| [startup-lifecycle.md](startup-lifecycle.md) | Where to load persisted data: signature defaults vs. the two `on_startup` hooks vs. `@tool(defaults=...)`. Read before loading anything at startup. |
| [v0.2.0/design.md](v0.2.0/design.md) | Form assist — autocomplete, cascading fill, lazy defaults, and the startup sequence that supports them. |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Decorator Design](#3-decorator-design)
4. [Type Annotation → Widget Mapping](#4-type-annotation--widget-mapping)
5. [UI Layout](#5-ui-layout)
6. [Async Execution Engine](#6-async-execution-engine)
7. [Data Storage](#7-data-storage)
8. [History Page](#8-history-page)
9. [Theme & Styling](#9-theme--styling)
10. [Usage Examples](#10-usage-examples)
11. [Tech Stack](#11-tech-stack)

---

## 1. Project Overview

**decoui** is a Python framework that automatically generates PySide6 GUIs from decorator and type annotations. Developers annotate their classes and methods — decoui handles the rest: parameter input forms, async execution, real-time log output, and execution history.

### Design Principles

- **Annotation-first** — focus on business logic, write zero UI code
- **Native types only** — no custom marker types; use standard Python (`str`, `int`, `list`, `Enum`, ...)
- **Transparent execution** — every run is async, logged, and persisted automatically
- **Zero-config startup** — `gui_main()` auto-discovers `@toolset` classes in the caller's namespace

---

## 2. Architecture

### 2.1 Module Layout

```
decoui/
├── decorators.py        # @toolset / @tool decorator definitions
├── registry.py          # Annotation scanning, ToolTree construction
├── widget_builder.py    # Type annotation → Widget mapping
├── engine/
│   ├── worker.py        # QRunnable + stdout/logging capture
│   └── executor.py      # Execution scheduling, record lifecycle
├── storage/
│   ├── models.py        # Dataclass definitions
│   └── db.py            # SQLite CRUD operations
├── ui/
│   ├── main_window.py   # Main window + QSplitter layout
│   ├── nav_tree.py      # Left sidebar (ToolSet/Tool tree)
│   ├── tag_bar.py       # Tag filter pill buttons
│   ├── tool_page.py     # Parameter form + output console
│   ├── history_page.py  # Execution history list + detail view
│   └── log_window.py    # Shared resizable log viewer window
├── icon.png             # Application icon (bundled in wheel)
└── runner.py            # gui_main() entry point + theme stylesheet
```

| Module | Responsibility |
|---|---|
| `decorators.py` | `@toolset` and `@tool` decorators |
| `registry.py` | Scan annotations with `get_type_hints()`, split `Annotated` metadata, build ToolTree |
| `widget_builder.py` | Map type annotations to PySide6 widgets; `_DictTextEdit` marker subclass |
| `engine/worker.py` | `QRunnable` with `sys.stdout` redirect and `logging.Handler` attachment |
| `engine/executor.py` | Schedule runs; `ExecutionRecord` lifecycle; log batch writing |
| `storage/db.py` | SQLite history CRUD and key-value application settings; WAL mode |
| `storage/models.py` | `ExecutionRecord`, `ExecutionParam`, `ExecutionLog` dataclasses |
| `ui/main_window.py` | QSplitter layout; persistent sidebar; stacked history/tool-tab views; signal wiring |
| `ui/nav_tree.py` | Two-layer tree; search; tag filtering; keyboard navigation |
| `ui/tag_bar.py` | Pill-style checkable tag buttons |
| `ui/tool_page.py` | Form generation; collapse animation; output console; Replay button |
| `ui/history_page.py` | History table; filtering; checkboxes; detail panel; replay |
| `ui/log_window.py` | Shared `LogWindow(QMainWindow)` + `LogEntry` namedtuple |
| `runner.py` | `gui_main()` entry; font config; global QSS theme |

---

## 3. Decorator Design

### 3.1 `@toolset` — Class Level

```python
@toolset(
    label="CSV Tools",
    tags=["file", "batch"],           # used by the tag filter bar
    description="CSV processing tools",
)
class CsvTools:
    ...
```

| Parameter | Type | Description |
|---|---|---|
| `label` | `str` | Required. Sidebar display name. |
| `tags` | `list[str]` | Tag filter labels. Tag bar hides the entire toolset if tags don't match. |
| `description` | `str` | Tooltip shown on hover over the toolset node in the nav tree. |

### 3.2 `@tool` — Method Level

```python
@tool(
    label="Merge CSV",
    description="Merge multiple CSV files into one.",
    placeholders={"files": "one path per line", "output": "e.g. out.csv"},
    confirm=True,
    timeout=300,
)
def merge(self, files: list, output: str = "out.csv") -> str:
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `label` | `str` | required | Tool display name. |
| `description` | `str` | `""` | Shown in a rounded-border box below the title. |
| `placeholders` | `dict[str,str]` | `{}` | Placeholder text for named parameters. |
| `labels` | `dict[str,str]` | `{}` | Form label for named parameters. Defaults to the parameter name. |
| `confirm` | `bool` | `False` | Show Yes/No dialog before executing. |
| `timeout` | `int\|None` | `None` | Execution timeout in seconds. |
| `on_cancel` | `callable\|str` | `None` | Cleanup run on the GUI thread when the tool is cancelled. See [6.2](#62-cancellation). |

Keys in `placeholders`, `labels`, `completions`, `cascade` and `defaults` are validated against the
method signature in `build_tree()`, not in the decorator — a tool called directly, without a GUI,
must not be blocked by form-text validation.

**Return values** from tool methods are intentionally ignored by the GUI. Use `print()` or `logging` for any output.

---

## 4. Type Annotation → Widget Mapping

Only native Python types are supported. No custom marker types.

| Annotation | Widget | Behaviour |
|---|---|---|
| `str` | `QLineEdit` | Single-line text. |
| `int` | `QSpinBox` (no arrows) | Full int range; user types or uses keyboard. |
| `float` | `QDoubleSpinBox` (no arrows) | 4 decimal places. |
| `bool` | `QCheckBox` | Checked / unchecked. |
| `list` / `list[X]` | `QTextEdit` | Items split by newline or comma. |
| `dict` | `_DictTextEdit` (QTextEdit subclass) | JSON input. Parsed with `json.loads`, then `ast.literal_eval` fallback. Raises on failure. |
| `Enum` subclass | `QComboBox` | Dropdown; `currentData()` returns the Enum member directly. |
| `Optional[X]` | Widget for `X` | Unwrapped silently. |

### Label convention

Parameters without a default value are marked with a red `*` prefix in the form label, indicating they are required.

### Default values

Method default arguments pre-fill widgets automatically. `inspect.Parameter.empty` is used to detect the absence of a default.

### Type coercion

Before calling the tool method, `coerce_params()` casts widget values to their declared types. Any `Exception` is caught, formatted as a traceback, and shown in the output console as an `ERROR` line. The run is aborted.

### Annotation evaluation

`typing.get_type_hints(method)` is used (not `method.__annotations__`) to correctly evaluate stringified annotations under PEP 563 / Python 3.14 lazy evaluation.

`registry._resolve_hints()` runs that call twice: once stripped, and once with `include_extras=True`. The stripped pass is what `ParamInfo.annotation` stores, so widget selection and value coercion keep seeing bare runtime types at any nesting depth — `Optional[Annotated[Path, F(...)]]` still arrives as `Path | None`. The `include_extras` pass is read only by `_find_field_meta()`, which walks the annotation tree for the first `F` instance and feeds `ParamInfo.label` / `ParamInfo.placeholder`.

Keeping the two passes separate is what makes `Annotated` support purely additive: nothing downstream of the registry ever sees an `Annotated` object, so no type-mapping table needed changing.

Non-`F` metadata is ignored, so pre-existing aliases such as `Age = Annotated[int, {"min": 0, "max": 150}]` behave exactly as before.

When annotations cannot be resolved (an alias only imported under `TYPE_CHECKING`), both passes fail together and the registry falls back to the raw `__annotations__` strings. Field metadata is unavailable on that path, matching the pre-existing loss of type mapping.

---

## 5. UI Layout

### 5.1 Main Window

```
┌─────────────────────────────────────────────────────────────────┐
│  Tags:  [All]  [basic]  [demo]  [math]  [text]                 │
├──────────────────┬──────────────────────────────────────────────┤
│  Sidebar         │  QStackedWidget (main area)                  │
│                  │ ┌──────────┬──────────┬──────────┐           │
│  🔍 Search…      │ │ Tool A × │ Tool B × │ Tool C × │           │
│                  │ └──────────┴──────────┴──────────┘           │
│                  │                                              │
│  ▼ Text Tools    │                                              │
│    Count Chars   │                                              │
│    Repeat Text   │                                              │
│  ▼ Number Tools  │                                              │
│    Power         │                                              │
│                  │                                              │
│  [History]       │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

- The sidebar has a light blue-gray tint (`#f8faff`).
- A 1 px separator line is provided by the `QSplitter` handle.
- Default splitter ratio: 220 px sidebar / 880 px content.
- The sidebar width is restored from `ui.sidebar.width` in `app_setting`.
- Tool pages open in movable, closable tabs. Closing a tab hides it without destroying its page or interrupting a running task; selecting the tool again restores the same page.
- Right-clicking a tab opens **Close Tab**, **Close Others**, and **Close All** actions. **Close Others** keeps and activates the right-clicked tab, and is disabled when only one tab is open. **Close All** returns to the welcome page without destroying tool pages or interrupting running tasks.
- History and the tabbed tool workspace remain separate pages in the outer `QStackedWidget`.

### 5.2 Sidebar (NavTree)

- Two-layer tree: **ToolSet (bold)** → Tool (half of the platform-default indentation).
- Search box filters tool labels in real time (hides tools that don't match, removes toolsets with zero visible tools).
- Tag filter hides the **entire toolset** if its tags don't include all active tags.
- Toolset description shown as a tooltip on hover.
- Both mouse click and **arrow key navigation** emit `tool_selected`.

### 5.3 Tag Bar

- Pill-shaped checkable buttons (`border-radius: 12px`).
- **All** = clear all active tags (show everything).
- Other tags: multi-select, AND semantics.
- Fixed height 42 px to prevent layout stretch.

### 5.4 ToolPage

```
┌───────────────────────────────────────────────────────┐
│  Tool Label                  [Running…]  [▼ Parameters]│
│ ┌─────────────────────────────────────────────────┐   │
│ │ Description (rounded border, light bg)          │   │
│ └─────────────────────────────────────────────────┘   │
│ ████ progress (4 px, hidden until run)                 │
│                                                        │
│  ▼ Parameter Panel (collapsible, QPropertyAnimation)   │
│  *name:   [widget]                                     │
│   option: [widget]                                     │
│                                                        │
│  [▶ Run]  [↺ Reset]  [■ Stop]          [Replay]        │
│                                                        │
│  Output                           [Copy]  [View Log]   │
│ ┌─────────────────────────────────────────────────┐   │
│ │ dark console (QPlainTextEdit, read-only)         │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

**Buttons:**

| Button | Behaviour |
|---|---|
| **Run** | Coerce params → start background thread → collapse params panel. |
| **Reset** | Clear console + log records; expand params panel. Does not change param values. |
| **Stop** | Request cancellation. |
| **Replay** | Emit `history_requested(tool_id)` → MainWindow shows History filtered to this tool. |
| **Copy** | Copy console text to clipboard. |
| **View Log** | Open current log records in a `LogWindow` (same as History's View Full Log). |

**Status badge** (pill label, top-right of header):

| State | Colour |
|---|---|
| Running… | Blue `#3b5bdb` |
| Done (Ns) | Green `#2b9348` |
| Error (Ns) | Red `#dc3545` |
| Cancelled | Gray `#6c757d` |

**Parameter collapse animation:** `QPropertyAnimation` on `maximumHeight`, 200 ms, `InOutQuad`. Parameters become read-only (disabled) during execution. Auto-collapses on Run; auto-expands on Reset or when `restore_params()` is called.

### 5.5 Log Viewer (LogWindow)

Shared by ToolPage ("View Log") and HistoryPage ("View Full Log"). Implemented in `ui/log_window.py`.

- Independent `QMainWindow`, resizable, `WA_DeleteOnClose`.
- Level filter buttons: **All**, **None**, stdout, DEBUG, INFO, WARNING, ERROR, CRITICAL.
- Search bar: real-time substring filter.
- Coloured text matching the console colour scheme.
- **Copy All** copies filtered text to clipboard.

---

## 6. Async Execution Engine

### 6.1 Flow

```
User clicks Run
      │
      ▼
ExecutionEngine.run(tool, instance, params)
      ├── INSERT ExecutionRecord (status=running)
      ├── INSERT ExecutionParams snapshot
      ├── ToolWorker(QRunnable)
      │       ├── redirect sys.stdout → _StreamRedirect → log_line signal
      │       ├── attach _SignalHandler to root logger → log_line signal
      │       ├── publish signals on worker._thread_local → progress() finds them
      │       ├── call tool.method(instance, **params)
      │       ├── clear _thread_local (finally; QThreadPool reuses threads)
      │       └── emit finished(result, status)
      └── QThreadPool.globalInstance().start(worker)

On finished:
      ├── UPDATE ExecutionRecord (status, finished_at)
      ├── flush remaining log buffer
      ├── drop the worker reference (closes the late-cancel window)
      └── update UI (status badge, buttons)
```

### 6.2 Cancellation

```
User clicks Stop (or timeout fires)
      │
      ▼  GUI thread
ExecutionEngine.cancel()
      ├── _run_cancel_hook()          ← tool's on_cancel, on every attempt
      │       └── errors → ERROR log line; cancellation continues
      └── ToolWorker.cancel()
              └── PyThreadState_SetAsyncExc(_WorkerCancelled)
```

The order is the design. `PyThreadState_SetAsyncExc` schedules an exception that
CPython raises at the next bytecode boundary — a worker parked inside a C call
(`proc.wait()`, `socket.recv()`) reaches no such boundary until that call returns
on its own, and neither does its `finally`. Running the hook first, on the GUI
thread, while the worker is still blocked, is the only point at which the thing
holding the worker can be released.

Two consequences worth knowing:

- The hook runs **concurrently** with the tool body. It is contractually limited
  to idempotent interruption, must tolerate not-yet-assigned state, and must be
  fast — it is on the GUI thread.
- The injection can land between `waitpid()` returning and `Popen` recording the
  status, so a cancelled tool's `Popen.returncode` may stay `None` even though
  the child is reaped. Do not read a child's fate through `Popen` after a cancel.

The hook fires on **every** cancellation attempt, not once per execution. This is
deliberate: a Stop that arrives before the tool has assigned the state its hook
reads does nothing, and the worker is still blocked in the call only the hook can
release — a second Stop has to be able to retry. Idempotence is what makes that
safe, which is why it is part of the hook's contract rather than an optimisation.

What bounds the hook instead is the run's own lifetime. `cancel()` returns early
when `_worker` is None, and `_on_finished` both drops `_worker` and stops the
timeout timer, so nothing can invoke cleanup for work that already completed. The
timeout timer is owned by the engine and re-armed per run, rather than a
fire-and-forget `QTimer.singleShot`: a single-shot armed by a finished run cannot
be recalled, and would cancel whichever run happened to be in flight when it
eventually fired.

### 6.3 Progress

`decoui.progress(done, total, message)` is a module-level function, not a method
on a base class: tools are verified by instantiating the toolset and calling the
method directly, so nothing may require framework state to exist.

It reads `worker._thread_local.signals`, which `ToolWorker.run()` publishes for
the duration of the call. Outside a worker that lookup returns `None` and the
call is a no-op — no output, no warning.

Reports closer than `_PROGRESS_MIN_INTERVAL_S` (100 ms) are dropped, since a
queued cross-thread signal per loop iteration would outrun the GUI. A final
report (`done >= total > 0`) is never dropped, so the bar always lands on 100%.

Progress is transient UI state: `ExecutionEngine` re-emits it and **does not**
write it to `execution_log`.

### 6.4 Log Batch Writing

- Buffer up to **50 lines** or **1 second** (whichever comes first), then `executemany` INSERT.
- Force-flush on `finished` signal before updating the record.

### 6.5 Log Level Colours

| Source / Level | Console Colour |
|---|---|
| `print` / stdout | White `#FFFFFF` |
| `logging.DEBUG` | Gray `#A0A0A0` |
| `logging.INFO` | Phosphor Green `#39FF14` |
| `logging.WARNING` | Yellow `#FFD700` |
| `logging.ERROR` | Red `#FF6B6B` |
| `logging.CRITICAL` | Bold Red `#FF0000` |

---

## 7. Data Storage

### 7.1 SQLite Schema

```sql
CREATE TABLE execution_record (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id      TEXT    NOT NULL,   -- 'ClassName.method_name'
    tool_label   TEXT    NOT NULL,   -- display label snapshot
    started_at   DATETIME NOT NULL,
    finished_at  DATETIME,
    status       TEXT    NOT NULL,   -- 'running'|'success'|'error'|'cancelled'
    result_json  TEXT,
    error_msg    TEXT
);

CREATE TABLE execution_params (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id),
    param_name   TEXT    NOT NULL,
    param_value  TEXT,               -- JSON (ensure_ascii=False)
    param_type   TEXT    NOT NULL
);

CREATE TABLE execution_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id),
    seq          INTEGER NOT NULL,
    level        TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    logged_at    DATETIME NOT NULL
);

CREATE TABLE app_setting (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX idx_log_record ON execution_log(record_id, seq);
```

- WAL mode enabled for better concurrent read performance.
- `sqlite3.DETECT_TYPES` is not used (removed for Python 3.14 compatibility).
- `datetime` fields stored/retrieved as ISO strings and parsed manually.
- Parameter values serialized with `json.dumps(..., ensure_ascii=False)` to preserve CJK characters.
- Application settings use stable dotted keys and string values. Writes use an upsert so callers can add settings without schema changes.

### 7.2 Default DB Path

`~/.decoui/history.db` — stores execution history and application settings; overridable via `gui_main(db_path=...)`.

### 7.3 Parameter Replay

1. `query_params(record_id)` → list of `ExecutionParam`.
2. Each `param_value` (JSON string) is decoded with `json.loads`; fallback to raw string on failure.
3. `HistoryPage.replay_requested` signal emits `(tool_id, param_map)`.
4. `MainWindow._replay()` calls `ToolPage.restore_params(param_map)` → `set_value()` per widget → `_expand_params()`.

### 7.4 Application Settings

- `get_setting(key, default)` reads a value from `app_setting`.
- `set_setting(key, value)` inserts or updates a value and its timestamp.
- `ui.sidebar.width` stores the first `QSplitter` pane width in pixels.
- Splitter writes are debounced by 250 ms and flushed again when the main window closes.
- Invalid or missing sidebar values fall back to 220 px.

---

## 8. History Page

### 8.1 Layout

```
📜 Execution History

Filter: [All Tools ▼]  [All Status ▼]  [All time ▼]   [🔄 Refresh]
[Select All]  [Deselect All]                    [🗑 Delete Selected]

 ☐ │ Timestamp           │ Tool             │ Status    │ Duration │ Result
───┼─────────────────────┼──────────────────┼───────────┼──────────┼────────
 ☐ │ 2025-05-11 14:23:01 │ All Log Levels   │ ✅ success│   0.1s   │ …
 ☐ │ 2025-05-11 14:22:45 │ Slow Task        │ ⛔ canc.  │   1.2s   │

▼ Detail (click row or navigate with ↑↓)
  Params: message=test
  [↩ Replay Params]  [📄 View Full Log]
```

### 8.2 Features

| Feature | Detail |
|---|---|
| Tool filter | Dropdown shows `"ToolSet Label: Tool Label"` entries, sorted alphabetically. |
| Status filter | success / error / running / cancelled |
| Time filter | Today / Last 7 days / Last 30 days / All time |
| Keyboard nav | Arrow keys change row and update the detail panel. |
| Checkboxes | Per-row checkboxes; Select All / Deselect All operate on current filtered set. |
| Delete | Checkbox-selected or right-click context menu. |
| Replay | Restores params and switches to the tool's page. |
| View Full Log | Opens `LogWindow` with level filters and search. |
| show_for_tool | Called by ToolPage's Replay button to pre-filter history to the current tool. |

---

## 9. Theme & Styling

The global QSS stylesheet is applied in `runner._apply_theme()`.

| Element | Style |
|---|---|
| App background | `#f5f6fa` |
| Sidebar | `#f8faff` with 1 px right border |
| White surfaces (inputs, table, tree) | `#ffffff` |
| Accent / selection | `#3b5bdb` (blue) |
| Run button | `#2b9348` (green) |
| Stop button | `#dc3545` (red) |
| Tag bar pills | `border-radius: 12px`; checked = accent fill |
| Console | `#1e1e1e` background — inline style overrides global QSS |
| Scrollbars | 8 px, rounded handles, no arrow buttons |
| SpinBox arrows | Hidden (`width: 0`) — users type values directly |

Font stack (set via `QFont.setFamilies`): **Consolas**, **Microsoft YaHei**, **Meiryo**, Segoe UI, sans-serif.

---

## 10. Usage Examples

### Minimal

```python
from decoui import tool, toolset, gui_main

@toolset(label="Text Tools", tags=["text"])
class TextTools:

    @tool(label="Count Characters",
          placeholders={"content": "Paste text here…"})
    def count(self, content: str = "") -> str:
        import logging
        words = len(content.split())
        logging.info("words=%d", words)
        return f"{len(content)} chars / {words} words"

if __name__ == "__main__":
    gui_main(title="My Tools")
```

### Multiple ToolSets + Enum

```python
import enum
import logging
from decoui import tool, toolset, gui_main

class Format(enum.Enum):
    JSON = "json"
    CSV  = "csv"
    TSV  = "tsv"

@toolset(label="Export Tools", tags=["export"])
class ExportTools:

    @tool(label="Export Data",
          description="Export data to the chosen format.",
          confirm=True)
    def export(
        self,
        data: dict = None,
        fmt: Format = Format.JSON,
        pretty: bool = True,
    ) -> None:
        logging.info("Exporting as %s", fmt.value)
        print("done")

@toolset(label="Text Tools", tags=["text"])
class TextTools:

    @tool(label="Join Lines",
          placeholders={"items": "one item per line"})
    def join(self, items: list = None, sep: str = ", ") -> None:
        items = items or []
        print(sep.join(items))

if __name__ == "__main__":
    gui_main(title="Internal Tools", db_path="./runs.db")
```

---

## 11. Tech Stack

| Area | Technology |
|---|---|
| GUI framework | `PySide6-Essentials` (Qt 6.6+) — only `QtCore` / `QtGui` / `QtWidgets` / `QtTest` are imported, so `PySide6-Addons` is not a dependency |
| Persistence | SQLite via stdlib `sqlite3`, WAL mode |
| Packaging | `pyproject.toml` + `uv` / `pip`; icon bundled via `force-include` |
| Type introspection | `inspect`, `typing.get_type_hints`, `get_args`, `get_origin` |
| Async execution | `QRunnable` + `QThreadPool` |
| Log capture | `sys.stdout` redirect + `logging.Handler` |
| Minimum Python | 3.10+ |
