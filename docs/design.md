# decoui — Framework Design Specification v0.1

> Decorator-Driven GUI Framework for Python · `pip install decoui`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Decorator Design](#3-decorator-design)
4. [Type Annotation → Widget Mapping](#4-type-annotation--widget-mapping)
5. [UI Layout Design](#5-ui-layout-design)
6. [Async Execution Engine](#6-async-execution-engine)
7. [Data Storage Design](#7-data-storage-design)
8. [History Page](#8-history-page)
9. [Usage Examples](#9-usage-examples)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Tech Stack](#11-tech-stack)

---

## 1. Project Overview

**decoui** is a Python framework that automatically generates PySide6 GUIs from decorator and type annotations. Developers annotate their classes and methods — decoui takes care of the rest: parameter input forms, async execution, real-time log output, and execution history.

### Design Principles

- **Annotation-first** — focus on business logic, write zero UI code
- **Type = Widget** — `str` → `QLineEdit`, `Text` → `QTextEdit`, automatically
- **Transparent execution** — every tool run is automatically async, logged, and persisted
- **Zero-config startup** — `gui_main(MyToolClass)` launches the full GUI app

### Target Users

| User | Use Case |
|---|---|
| SI / enterprise developers | GUI wrapper for internal tools and batch scripts |
| Data engineers | CSV/Excel/DB processing tools with a UI |
| Automation engineers | Add a GUI front-end to existing automation scripts |
| OSS library authors | Ship a lightweight GUI alongside a CLI tool |

---

## 2. Architecture

### 2.1 Overall Structure

```
┌─────────────────────────────────────────────────────┐
│                  User Application                    │
│  @toolset('CSV Tools')                               │
│  class CsvTools:                                     │
│      @tool(label='Merge', tags=['file', 'batch'])    │
│      def merge(self, files: list[Path]) -> str: ...  │
└──────────────────┬──────────────────────────────────┘
                   │  gui_main(CsvTools)
                   ▼
┌─────────────────────────────────────────────────────┐
│                   decoui Core                        │
│  ┌────────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ decorators │  │ registry │  │ widget_builder │  │
│  └────────────┘  └──────────┘  └────────────────┘  │
│  ┌────────────┐  ┌──────────┐  ┌────────────────┐  │
│  │   engine   │  │ storage  │  │      ui/       │  │
│  │ (executor) │  │ (SQLite) │  │   (PySide6)    │  │
│  └────────────┘  └──────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 2.2 Module Layout

```
decoui/
├── decorators.py        # @toolset / @tool decorator definitions
├── types.py             # Marker types: Text, FilePath, Choice, ...
├── registry.py          # Annotation scanning, ToolTree construction
├── widget_builder.py    # Type annotation → Widget conversion logic
├── engine/
│   ├── worker.py        # QRunnable + stdout/logging capture
│   └── executor.py      # Execution scheduling, record lifecycle
├── storage/
│   ├── models.py        # ExecutionRecord dataclass definitions
│   └── db.py            # SQLite CRUD operations
├── ui/
│   ├── main_window.py   # Main window + QSplitter layout
│   ├── nav_tree.py      # Left sidebar (ToolSet/Tool tree)
│   ├── tag_bar.py       # Tag filter bar
│   ├── tool_page.py     # Right panel (form + console)
│   ├── history_page.py  # Execution history list + detail view
│   └── widgets/         # Custom per-type widget implementations
└── runner.py            # gui_main() entry point
```

| Module | Responsibility |
|---|---|
| `decorators.py` | Define `@toolset` and `@tool` decorators |
| `types.py` | Marker type definitions (`Text`, `FilePath`, `Choice`, ...) |
| `registry.py` | Scan annotations, build the two-layer ToolTree |
| `widget_builder.py` | Map type annotations to PySide6 widgets |
| `engine/worker.py` | `QRunnable` worker with stdout/logging capture |
| `engine/executor.py` | Schedule runs, create and update `ExecutionRecord` |
| `storage/db.py` | SQLite init, insert, query, delete |
| `storage/models.py` | `ExecutionRecord`, `ExecutionParam`, `ExecutionLog` dataclasses |
| `ui/main_window.py` | Main window, splitter, stacked widget |
| `ui/nav_tree.py` | Left sidebar tree |
| `ui/tag_bar.py` | Tag filter buttons |
| `ui/tool_page.py` | Parameter form + collapsible panel + output console |
| `ui/history_page.py` | History list, detail expand, replay |
| `runner.py` | `gui_main()` entry point |

---

## 3. Decorator Design

### 3.1 `@toolset` — Class Level

Groups related tools under one sidebar entry.

```python
@toolset(
    label="CSV Tools",
    icon="table.png",          # optional: sidebar icon path
    description="Tools for CSV file processing",  # optional
)
class CsvTools:
    ...
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `label` | `str` | ✅ | Display name in the sidebar |
| `icon` | `str` | — | Icon file path |
| `description` | `str` | — | Tooltip / toolset description |

### 3.2 `@tool` — Method Level

Defines an individual tool. Applied to methods inside a `@toolset` class.

```python
@tool(
    label="Merge CSV",
    tags=["file", "batch", "common"],   # multiple tags supported
    description="Merge multiple CSV files into one",
    icon="merge.png",
    confirm=True,      # show confirmation dialog before running
    timeout=300,       # timeout in seconds (None = unlimited)
)
def merge(self, files: list[Path], output: FilePath) -> str:
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `label` | `str` | ✅ required | Tool display name |
| `tags` | `list[str]` | `[]` | Tags for filtering; multiple allowed |
| `description` | `str` | `""` | Tool description shown in the UI |
| `icon` | `str` | `None` | Icon file path |
| `confirm` | `bool` | `False` | Show confirmation dialog before execution |
| `timeout` | `int\|None` | `None` | Execution timeout in seconds |

---

## 4. Type Annotation → Widget Mapping

### 4.1 Built-in Type Mapping

| Python Type Annotation | Generated Widget | Notes |
|---|---|---|
| `str` | `QLineEdit` | Single-line text input |
| `Text` | `QTextEdit` | Multi-line text input (decoui marker type) |
| `int` | `QSpinBox` | Integer input; range via `Annotated` |
| `float` | `QDoubleSpinBox` | Float input |
| `bool` | `QCheckBox` | Checkbox |
| `list[str]` | `QListWidget` + add/remove buttons | Editable string list |
| `list[Path]` | `QListWidget` + file picker button | Multi-file selection |
| `Path` / `FilePath` | `QLineEdit` + file picker button | Single file / directory |
| `Choice` / `Enum` | `QComboBox` | Dropdown selection |
| `datetime` | `QDateTimeEdit` | Date and time picker |
| `Optional[X]` | Widget for `X` + enable/disable toggle | Nullable input |

### 4.2 Custom Marker Types

```python
# decoui/types.py

class Text(str):
    """Maps to QTextEdit (multi-line text area)."""
    pass

class FilePath(str):
    """Maps to QLineEdit with a file-picker button."""
    pass

class DirPath(str):
    """Maps to QLineEdit with a directory-picker button."""
    pass

# Constraint annotations via Annotated
from typing import Annotated
Age  = Annotated[int,   {"min": 0,   "max": 150}]
Rate = Annotated[float, {"min": 0.0, "max": 1.0, "step": 0.01}]
```

### 4.3 Default Values

Method default arguments are automatically used as widget initial values.

```python
@tool(label="Text Processing")
def process(
    self,
    name:    str   = "John Doe",   # QLineEdit pre-filled with "John Doe"
    count:   int   = 10,           # QSpinBox initial value: 10
    verbose: bool  = False,        # QCheckBox: unchecked
) -> str: ...
```

### 4.4 Return Type Display

| Return Type | Display After Execution |
|---|---|
| `str` | Appended to console as result text |
| `list[str]` | Rendered as a list in the console |
| `dict` | Pretty-printed JSON in the console |
| `None` | Completion message only |
| `Path` | Clickable file link in the console |

---

## 5. UI Layout Design

### 5.1 Main Window

```
┌────────────────────────────────────────────────────────────────┐
│  decoui — [App Title]                          [─]  [□]  [×]  │
├────────────────────────────────────────────────────────────────┤
│  🔍 [Search tools...]                                          │
│  Tags:  [All ▼]  [file]  [batch]  [common]  [db]  [convert]  │
├───────────────────┬────────────────────────────────────────────┤
│  Sidebar          │  Main Area  (QStackedWidget)               │
│  (QTreeWidget)    │                                            │
│                   │                                            │
│  ▼ CSV Tools      │                                            │
│    > Merge CSV    │      ← ToolPage / HistoryPage              │
│    > Convert      │                                            │
│  ▶ Excel Tools    │                                            │
│  ▶ DB Tools       │                                            │
│                   │                                            │
│  [History] [⚙]   │                                            │
└───────────────────┴────────────────────────────────────────────┘
```

### 5.2 Sidebar (NavigationTree)

Two-layer tree: **ToolSet → Tool**.

| Element | Spec |
|---|---|
| ToolSet node | Bold text, click to expand/collapse, icon support |
| Tool node (leaf) | Click to switch the right panel to that ToolPage |
| Search box | Real-time partial-match filtering on tool labels |
| Tag bar | Click tags to filter the tree; multi-select = AND condition |
| History button | Navigate to the global execution history page |

### 5.3 ToolPage — Default State (Before Execution)

```
┌────────────────────────────────────────────────────────────┐
│  📋 Merge CSV                                               │
│  Merge multiple CSV files into one.             [History ▼] │
├────────────────────────────────────────────────────────────┤
│  Parameter Form  (QFormLayout)                              │
│                                                             │
│  Input files:   [file1.csv          ]  [+ Add]  [− Remove] │
│                 [file2.csv          ]                       │
│  Output file:   [output.csv         ]  [📁 Browse]         │
│  Delimiter:     [,                  ]                       │
│  Header:        ● Use first row  ○ Each file                │
│                                                             │
├────────────────────────────────────────────────────────────┤
│                  [▶ Run]       [↺ Reset]                    │
├────────────────────────────────────────────────────────────┤
│  Output Console  (QPlainTextEdit, read-only, minimal height) │
│  Previous run output shown here if available                │
└────────────────────────────────────────────────────────────┘
```

### 5.4 ToolPage — Running State (Parameters Collapsed)

After clicking **Run**, the parameter area collapses and the console expands to fill the space.

```
┌────────────────────────────────────────────────────────────┐
│  📋 Merge CSV                              [▼ Parameters]  │
│  ▶ Running...  [━━━━━━━━━░░░░░░░░]         [■ Stop]        │
├────────────────────────────────────────────────────────────┤
│  Output Console  (maximized)                                │
│                                                             │
│  [10:23:01] INFO   Starting process                         │
│  [10:23:01] INFO   Reading file1.csv...                     │
│  [10:23:02] INFO   Reading file2.csv...                     │
│  [10:23:03] INFO   Merging rows (1,240 total)               │
│  > Custom print output here                                 │
│  ...                                                        │
│                                                             │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### 5.5 ToolPage — Completed State

```
┌────────────────────────────────────────────────────────────┐
│  📋 Merge CSV         ✅ Done (2.3s)       [▼ Parameters]  │
├────────────────────────────────────────────────────────────┤
│  Output Console                                             │
│  ...                                                        │
│  [10:23:05] INFO   Written to output.csv                    │
│  ─────────────────────────────────────────────────         │
│  ✅ Result: output.csv  (3,500 rows · 128 KB)               │
│  ─────────────────────────────────────────────────         │
├────────────────────────────────────────────────────────────┤
│  [▶ Run Again]   [↺ Reset Params]   [📋 Copy Result]       │
└────────────────────────────────────────────────────────────┘
```

> **Note:** The `[▼ Parameters]` button in the header lets users manually toggle the parameter panel at any time.

### 5.6 Parameter Panel Collapse — Animation Spec

| Item | Spec |
|---|---|
| Trigger | Auto-collapse when **Run** is clicked |
| Animation | `QPropertyAnimation` on `maximumHeight`: current → 0 (200 ms, `EaseInOut`) |
| Expand | `[▼ Parameters]` button in header toggles visibility |
| During execution | Panel can be expanded, but inputs are read-only |
| On re-run | Collapses again when Run is clicked |

---

## 6. Async Execution Engine

### 6.1 Execution Flow

```
User clicks "Run"
        │
        ▼
ExecutionEngine.run(tool, params)
        │
        ├── Create ExecutionRecord (status=running) → write to SQLite
        ├── Snapshot parameters → execution_params table
        ├── Create ToolWorker(QRunnable)
        │         │
        │         ├── Redirect sys.stdout  → LogSignal
        │         ├── Attach logging.Handler → LogSignal
        │         ├── Call tool.method(**params)
        │         │
        │         │   [each print / logging call]
        │         │     └── emit log_line(level, message)
        │         │               └── UI thread: append to console
        │         │                              batch insert to execution_log
        │         │
        │         └── emit finished(result, status)
        │
        └── QThreadPool.globalInstance().start(worker)

On finished signal:
        ├── Update ExecutionRecord (status=success|error, result)
        ├── Display result in console
        └── Update UI status indicators
```

### 6.2 Worker Implementation

| Item | Spec |
|---|---|
| Base class | `QRunnable` (managed by `QThreadPool`) |
| Signal bus | Separate `WorkerSignals(QObject)` class to carry Qt signals |
| stdout capture | Replace `sys.stdout` with `StreamRedirect` (thread-local safe) |
| logging capture | Attach `SignalHandler` to root logger; detach on completion |
| Thread safety | Signals are automatically queued to the Qt main thread |
| Cancellation | `QThread.requestInterruption()` + periodic checks inside the tool method |
| Timeout | Timer fires cancel signal after `@tool(timeout=N)` seconds |

### 6.3 Log Level Color Coding

| Source / Level | Console Color |
|---|---|
| `print` (stdout) | White `#FFFFFF` |
| `logging.DEBUG` | Gray `#A0A0A0` |
| `logging.INFO` | Cyan `#00BFFF` |
| `logging.WARNING` | Yellow `#FFD700` |
| `logging.ERROR` | Red `#FF6B6B` |
| `logging.CRITICAL` | Bold Red `#FF0000` |
| Return value (result) | Green `#90EE90` |

---

## 7. Data Storage Design

### 7.1 SQLite Schema

```sql
-- Main execution record
CREATE TABLE execution_record (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id      TEXT    NOT NULL,   -- 'ClassName.method_name'
    tool_label   TEXT    NOT NULL,   -- display name snapshot
    started_at   DATETIME NOT NULL,
    finished_at  DATETIME,
    status       TEXT    NOT NULL,   -- 'running' | 'success' | 'error' | 'cancelled'
    result_json  TEXT,               -- JSON-serialized return value
    error_msg    TEXT                -- exception message on error
);

-- Parameter snapshot (enables replay)
CREATE TABLE execution_params (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id),
    param_name   TEXT    NOT NULL,
    param_value  TEXT,               -- JSON-serialized value
    param_type   TEXT    NOT NULL    -- type name string (for deserialization)
);

-- Execution log (per line)
CREATE TABLE execution_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id),
    seq          INTEGER NOT NULL,   -- line order guarantee
    level        TEXT    NOT NULL,   -- 'stdout' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
    message      TEXT    NOT NULL,
    logged_at    DATETIME NOT NULL
);

CREATE INDEX idx_log_record ON execution_log(record_id, seq);
```

### 7.2 `tool_id` Design

`tool_id` is a dot-separated path that uniquely identifies a tool.

```python
# Format: '{ClassName}.{method_name}'
tool_id = "CsvTools.merge"
tool_id = "ExcelTools.read_sheet"
```

> **Note:** The `label` may change over time, so the stable class name + method name is used as the ID. The label at time of execution is snapshotted in `tool_label`.

### 7.3 Parameter Replay

| Step | Detail |
|---|---|
| Serialization | JSON for standard types; `Path` → string; `list` → JSON array |
| Deserialization | Use `param_type` to reconstruct the correct Python type |
| UI restore | `widget_builder` calls `setValue` / `setText` etc. on each widget |
| Partial restore | If a parameter type has changed, restore what's possible; skip the rest silently |

### 7.4 Log Batch Writing

Writing one `INSERT` per log line is too slow under high output volume.

Strategy:
- Buffer log lines in memory (up to **50 lines** or **1 second**, whichever comes first)
- Flush with `executemany` (batch `INSERT`)
- Force-flush all remaining lines when execution completes

---

## 8. History Page

### 8.1 Layout

```
┌────────────────────────────────────────────────────────────┐
│  📜 Execution History                                       │
│  Filter: [All Tools ▼]  [All Status ▼]  [Last 7 days ▼]   │
├────────────────────────────────────────────────────────────┤
│  Timestamp           │ Tool          │ Status   │ Duration  │
├────────────────────────────────────────────────────────────┤
│  2024-01-15 10:23   │ Merge CSV     │ ✅ OK    │   2.3s   │
│  2024-01-15 09:50   │ Convert       │ ❌ Error  │   0.5s   │
│  2024-01-14 17:30   │ Merge CSV     │ ✅ OK    │   5.1s   │
├────────────────────────────────────────────────────────────┤
│  ▼ Detail (click row to expand)                            │
│    Params: files=['a.csv','b.csv'], output='out.csv'       │
│    [↩ Replay Params]   [📄 View Full Log]                  │
└────────────────────────────────────────────────────────────┘
```

### 8.2 Feature Spec

| Feature | Detail |
|---|---|
| Filtering | Filter by tool name, status, and time range (today / 7d / 30d / all) |
| Sorting | By timestamp (default: descending) or duration |
| Detail expand | Click row to inline-expand params + log summary |
| Param replay | "↩ Replay" opens the ToolPage and restores the parameter values |
| Full log view | Separate dialog showing all log lines, with search and copy support |
| Delete | Right-click context menu for single or bulk delete |

---

## 9. Usage Examples

### 9.1 Minimal Setup

```python
from decoui import toolset, tool, gui_main
from decoui.types import Text

@toolset(label="Text Tools")
class TextTools:

    @tool(label="Count Characters", tags=["text"])
    def count(self, content: Text) -> str:
        lines = content.splitlines()
        return f"{len(content)} chars / {len(lines)} lines"


if __name__ == "__main__":
    gui_main(TextTools)
```

### 9.2 Multiple ToolSets

```python
from decoui import toolset, tool, gui_main
from decoui.types import FilePath
from pathlib import Path
import logging

@toolset(label="CSV Tools", icon="csv.png")
class CsvTools:

    @tool(label="Merge CSV", tags=["file", "batch"])
    def merge(self, files: list[Path], output: FilePath) -> str:
        logging.info(f"Merging {len(files)} files...")
        # ... processing ...
        print(f"Done: {output}")
        return str(output)


@toolset(label="Excel Tools", icon="excel.png")
class ExcelTools:

    @tool(label="List Sheets", tags=["excel", "info"])
    def list_sheets(self, file: FilePath) -> list[str]:
        import openpyxl
        wb = openpyxl.load_workbook(file, read_only=True)
        return wb.sheetnames


if __name__ == "__main__":
    gui_main(CsvTools, ExcelTools, title="Internal Tools")
```

---

## 10. Implementation Roadmap

### Phase 1 — Core Skeleton (MVP)

| Priority | Task |
|---|---|
| P0 | `decorators.py`: implement `@toolset` / `@tool` |
| P0 | `types.py`: define `Text`, `FilePath`, `DirPath`, `Choice` |
| P0 | `registry.py`: annotation scanning, ToolTree construction |
| P0 | `widget_builder.py`: basic type mapping (`str`, `int`, `bool`, `Path`, `Text`) |
| P0 | `engine/worker.py`: `QRunnable` + stdout/logging capture |
| P0 | `ui/tool_page.py`: form generation, Run button, output console (no collapse yet) |
| P0 | `runner.py`: `gui_main()` entry point |

### Phase 2 — Execution Management

| Priority | Task |
|---|---|
| P1 | `storage/db.py`: SQLite init and CRUD |
| P1 | `engine/executor.py`: `ExecutionRecord` lifecycle, log batch writing |
| P1 | `ui/tool_page.py`: parameter panel collapse animation |
| P1 | `ui/nav_tree.py`: two-layer ToolSet/Tool tree |
| P1 | `ui/tag_bar.py`: tag filtering |

### Phase 3 — History & Extensions

| Priority | Task |
|---|---|
| P2 | `ui/history_page.py`: history list + detail expand |
| P2 | Parameter replay feature |
| P2 | `list[Path]` and `list[str]` widgets |
| P2 | `Enum` / `Choice` → `QComboBox` mapping |
| P2 | `@tool(timeout=N)` timeout enforcement |
| P2 | PyPI packaging (`pyproject.toml`) |

### Phase 4 — Quality & Distribution

| Priority | Task |
|---|---|
| P3 | `Optional[X]` type support |
| P3 | `Annotated` constraints (`min` / `max` / `step`) |
| P3 | Dark / light theme support |
| P3 | Documentation and example projects |
| P3 | GitHub Actions for automated PyPI releases |

---

## 11. Tech Stack

| Area | Technology |
|---|---|
| GUI framework | PySide6 (Qt 6) |
| Persistence | SQLite (stdlib `sqlite3`) |
| Packaging | `pyproject.toml` + `uv` / `pip` |
| Type introspection | `inspect`, `typing` (`get_args`, `get_origin`, `get_annotations`) |
| Async execution | `QRunnable` + `QThreadPool` (integrated with Qt event loop) |
| Log capture | `sys.stdout` redirect + `logging.Handler` |
| Minimum Python | Python 3.10+ |