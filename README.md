# decoui

Decorator-driven GUI framework for Python. Annotate your methods — decoui generates a full PySide6 desktop app automatically.

![preview](docs/preview.png)

---

## Features

- **Zero UI code** — decorate a class and its methods, call `gui_main()`
- **Native type mapping** — `str`, `int`, `float`, `bool`, `list`, `dict`, `Enum` → widgets automatically
- **Form assist** — autocomplete, cascading fill, and lazily evaluated defaults
- **Async execution** — every tool runs in a thread; stdout and `logging` are captured in real time
- **Execution history** — every run is persisted to SQLite with parameters, logs, and status
- **Parallel tool tabs** — keep multiple tool pages open and switch between running tasks
- **Persistent layout** — sidebar width is restored from the application database
- **Replay** — restore any past run's parameters with one click
- **Settings store** — `store("ns")[key] = value`, namespaced and persisted in the same database
- **Help panel** — a reference built from the docstrings the tools already carry, with cross-references, tabs and back/forward
- **Themes** — four built in, any number as JSON files; changed from Settings without a restart
- **Translatable interface** — decoui's own text ships as one JSON catalogue per language

---

## Installation

```bash
pip install decoui
```

Requires Python 3.10+.

decoui depends on **`PySide6-Essentials`** (6.6+), not the full `PySide6` metapackage.
It only ever imports `QtCore`, `QtGui`, `QtWidgets` and `QtTest`, all of which live in
Essentials — so the extra `PySide6-Addons` payload (Charts, Multimedia, WebEngine,
Qt3D, …) is skipped. Measured on Windows / PySide6 6.11: **637 MB → 202 MB**.

If your own tool methods need an Addons module, depend on it explicitly:

```bash
pip install decoui PySide6-Addons   # or simply: pip install decoui PySide6
```

Both coexist with decoui — `PySide6` is just `PySide6-Essentials` + `PySide6-Addons`.

> **Upgrading an existing environment** — all three distributions unpack into the same
> `PySide6/` directory, so uninstalling `PySide6` / `PySide6-Addons` also deletes shared
> libraries that Essentials still needs, leaving `ImportError: DLL load failed while
> importing QtWidgets`. Force a clean reinstall rather than relying on the uninstall:
>
> ```bash
> pip install --force-reinstall PySide6-Essentials
> # uv: uv sync --reinstall-package pyside6-essentials
> ```
>
> Fresh installs are unaffected.

---

## Quick Start

```python
import logging
from decoui import tool, toolset, gui_main

@toolset(label="Text Tools", tags=["text"])
class TextTools:

    @tool(label="Count Characters",
          description="Count chars, words and lines.",
          placeholders={"content": "Paste text here…"})
    def count(self, content: str = "") -> str:
        words = len(content.split())
        logging.info("words=%d", words)
        return f"{len(content)} chars / {words} words"

if __name__ == "__main__":
    gui_main(title="My Tools")
```

`gui_main()` auto-discovers every `@toolset` class in the caller's global scope — no explicit registration needed.

---

## API Reference

### `@toolset`

Applied to a class. Groups its `@tool` methods under one sidebar entry.

```python
@toolset(
    label="CSV Tools",           # required — sidebar display name
    tags=["file", "batch"],      # optional — used by the tag filter bar
    description="...",           # optional — tooltip on hover in the sidebar
)
class CsvTools:
    ...
```

| Parameter | Type | Description |
|---|---|---|
| `label` | `str` | Required. Display name in the sidebar. |
| `tags` | `list[str]` | Tag filter bar labels. Multiple tags = AND filter. |
| `description` | `str` | Shown as a tooltip when hovering the toolset in the nav tree. |

### `@tool`

Applied to a method inside a `@toolset` class.

```python
@tool(
    label="Merge Files",
    description="Merge multiple files into one.",
    placeholders={"files": "one path per line"},
    confirm=True,     # show confirmation dialog before running
    timeout=120,      # cancel after N seconds (None = unlimited)
)
def merge(self, files: list, output: str = "out.txt") -> str:
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `label` | `str` | required | Tool display name. |
| `description` | `str` | `""` | Shown in a bordered box below the title. |
| `placeholders` | `dict[str,str]` | `{}` | Placeholder text per parameter name. |
| `labels` | `dict[str,str]` | `{}` | Form label per parameter name. Defaults to the parameter name. |
| `confirm` | `bool` | `False` | Show a Yes/No confirmation dialog before running. |
| `timeout` | `int\|None` | `None` | Execution timeout in seconds. |
| `completions` | `dict[str,list\|callable\|str]` | `{}` | Autocomplete candidates per parameter. See [Form Assist](#form-assist). |
| `cascade` | `dict[str,callable\|str]` | `{}` | Fill other parameters when this one changes. |
| `defaults` | `dict\|callable\|str` | `None` | Initial form values, evaluated when the page opens. |
| `completion_debounce_ms` | `int` | `250` | Idle time before a dynamic completions callback runs. |
| `on_cancel` | `callable\|str` | `None` | Cleanup to run when the tool is cancelled. See [Cancellation](#cancellation). |

Every key in `placeholders`, `labels`, `completions`, `cascade` and `defaults` must name a real parameter of the method, and `placeholders`/`labels` values must be strings. A mistake raises at startup, when the toolset tree is built, naming the tool and listing the parameters it does have.

### `gui_main`

```python
gui_main(title="My App", db_path="~/.myapp/history.db", on_startup=connect_backend)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | `"decoui"` | Window title. |
| `db_path` | `str\|Path\|None` | `~/.decoui/history.db` | SQLite database path for execution history and application settings. |
| `on_startup` | `callable\|None` | `None` | Application-wide setup, run once before any toolset is created and before the window appears. See [Startup](#startup). |
| `toolsets` | `Sequence[type]\|None` | `None` | The `@toolset` classes to load. When omitted, every one visible in the calling namespace is discovered. |
| `theme` | `str\|None` | `None` | Default theme id. A theme the user picked in Settings wins over it. See [Themes](#themes). |
| `theme_dir` | `str\|Path\|None` | `~/.decoui/themes` | Directory scanned for user-supplied theme files. |
| `language` | `str\|None` | `None` | Code for the language decoui's **own** interface is drawn in — Run, Stop, the history columns. A language the user picked in Settings wins over it. A tool's own label, description and docstring are never translated. Defaults to English. |

By default `gui_main()` scans the caller's namespace, so a toolset has to be imported *and* look used:

```python
from mytools.restore import RestoreTools  # noqa: F401 -- discovered by gui_main()

gui_main(title="My App")
```

Naming them explicitly drops the pragma and the comment that has to explain it:

```python
from mytools.restore import RestoreTools

gui_main(title="My App", toolsets=[RestoreTools])
```

The list controls *what* loads, not the order it appears in: the sidebar is always sorted by label.

### Startup

> Full guide: [docs/startup-lifecycle.md](docs/startup-lifecycle.md) — read it before loading anything at startup.

Startup runs in a fixed order, so anything loaded early is available later:

1. `db_path` is applied and the database is initialised
2. the toolset tree is built and validated
3. `gui_main(on_startup=...)` runs — application-wide work
4. **every `@toolset` class is instantiated**
5. **each instance's own `on_startup()` method runs**, if it defines one
6. the window is shown and the event loop starts

The recommended pattern is to **declare state in `__init__` and load it in `on_startup()`**:

```python
@toolset(label="Deploy Tools")
class DeployTools:

    def __init__(self):
        self.config = {"env": "staging"}          # declare, with fallbacks

    def on_startup(self):
        self.config = json.loads(                  # load, before the UI is live
            CONFIG_PATH.read_text(encoding="utf-8")
        )

    @tool(label="Deploy", defaults="load_defaults")
    def deploy(self, env: str = "") -> None:
        ...

    def load_defaults(self) -> dict:
        return {"env": self.config["env"]}         # reads self at call time
```

Splitting the two matters when loading fails: `__init__` still succeeded, so the toolset opens with its declared fallbacks instead of disappearing.

Use the `gui_main(on_startup=...)` argument for work that belongs to no single toolset — a shared connection, an auth token, a warm cache. It runs *before* any instance exists, so it cannot write to `self`; give the toolset its own `on_startup()` method for that. The application hook always runs before every toolset hook.

#### Two rules for both hooks

- **The event loop is not running yet.** `QTimer` does not fire, queued signals are not delivered, and `QThreadPool` results never arrive — waiting on a background thread here deadlocks startup. To report a problem, just `raise`; decoui shows it in a dialog once the window is up.
- **They block the window.** Both run synchronously before `show()`, so however long they take is time the user spends looking at nothing. Anything slow belongs in the tool body, where it gets a thread, a progress bar, and a Stop button.

#### Can the decorator see `self`?

Decorator **arguments** are evaluated at import time, when no instance exists — so this is impossible:

```python
@tool(label="Deploy", defaults={"env": self.config["env"]})   # NameError: self
```

Pass a **method name** instead. decoui resolves it to a bound method when the tool page is built, and the method reads `self` at call time — after `__init__` and `on_startup()` have run:

```python
@tool(label="Deploy",
      defaults="load_defaults",          # self.config is available inside
      completions={"service": "search_services"},
      cascade={"service": "describe_service"})
```

This works for `defaults`, `completions`, and `cascade` alike.

#### When startup fails

A failure in step 3, 4, or 5 **does not stop the application**. Every failure is collected and reported in one dialog over the main window, listing what failed with the full traceback behind the Details button, and everything that did load stays usable.

The one exception is step 4: a class whose `__init__` raises produces no object, so that toolset is skipped and its tools do not appear. That is the practical reason to keep `__init__` trivial and do the real loading in `on_startup()`.

---

## Type → Widget Mapping

| Python annotation | Widget | Notes |
|---|---|---|
| `str` | `QLineEdit` | Single-line text. |
| `int` | `QSpinBox` | Integer, full int range. |
| `float` | `QDoubleSpinBox` | 4 decimal places. |
| `bool` | `QCheckBox` | Checked / unchecked. |
| `list` | `QTextEdit` | One item per line or comma-separated. |
| `dict` | `QTextEdit` | JSON input; parsed with `json.loads` then `ast.literal_eval`. Raises on invalid input. |
| `Enum` subclass | `QComboBox` | Dropdown of enum members. |
| `pathlib.Path` | `QLineEdit` + buttons | Text field with **File...** (file picker) and **Folder...** (directory picker) buttons. The selected path is passed as a `pathlib.Path` to the method. |

- Required parameters (no default) are marked with a red `*` in the form label.
- `Optional[X]` is unwrapped to `X`.
- `Annotated[X, ...]` maps on `X`; the metadata does not affect widget choice.
- Default values are pre-filled into widgets automatically.

### Field metadata with `Annotated`

`F` attaches a label and placeholder to the type itself, so a field shared across
tools carries its wording with it instead of repeating it in every `@tool`:

```python
from pathlib import Path
from typing import Annotated
from decoui import F, tool, toolset

DumpFile = Annotated[Path, F(label="Dump file", placeholder="Pick a .dump / .tar")]

@toolset(label="Backup")
class Backup:

    @tool(label="Restore")
    def restore(self, archive: DumpFile) -> None: ...

    # One tool can reword the shared field; the decorator wins.
    @tool(label="Verify", labels={"archive": "Archive to check"})
    def verify(self, archive: DumpFile) -> None: ...
```

Resolution order for both label and placeholder:

`@tool(labels=…)` / `@tool(placeholders=…)` → `Annotated[…, F(…)]` → parameter name (label) or empty (placeholder)

Adding `F` to an annotation is purely additive: widget selection, required-field
marking and value conversion all read the bare type underneath, so existing code
keeps working unchanged.

> **Note** — with `from __future__ import annotations`, annotations are strings at
> runtime and decoui resolves them with `typing.get_type_hints()`. An alias like
> `DumpFile` must therefore be importable at runtime; putting the import under
> `if TYPE_CHECKING:` makes resolution fail, and decoui falls back to the raw
> strings, losing the `F` metadata along with the type mapping.

### `pathlib.Path` example

```python
import pathlib
from decoui import tool, toolset

@toolset(label="File Tools")
class FileTools:

    @tool(label="File Info", placeholders={"path": "Select a file or folder…"})
    def file_info(self, path: pathlib.Path) -> None:
        import logging
        p = pathlib.Path(path)
        logging.info("size: %d bytes", p.stat().st_size)
        logging.info("resolved: %s", p.resolve())
```

---

## Form Assist

Three opt-in `@tool` arguments make the parameter form react to what the user types.

```python
_CATALOG = {
    "web-frontend": {"version": "2.4.1", "owner": "frontend-team"},
    "auth-service": {"version": "3.0.2", "owner": "identity-team"},
}

@toolset(label="Deploy Tools")
class DeployTools:

    @tool(
        label="Deploy Service",
        completions={
            "env": ["production", "staging", "development"],   # static list
            "service": "search_services",                       # method on this class
        },
        cascade={"service": "describe_service"},                # fill other fields
        defaults={"env": "staging"},                            # initial values
    )
    def deploy(self, service: str = "", env: str = "",
               version: str = "", owner: str = "") -> None:
        ...

    def search_services(self, text: str) -> list[str]:
        return [name for name in _CATALOG if text.casefold() in name]

    def describe_service(self, value: str, form: dict) -> dict:
        return dict(_CATALOG.get(value, {"version": "", "owner": ""}))
```

### `completions` — autocomplete

| Value | Behaviour |
|---|---|
| `list[str]` | Fixed candidates, filtered by Qt (case-insensitive, substring match). |
| callable | Re-evaluated as the user types, debounced. The returned list replaces the popup contents; your callback controls matching and ordering. |
| `str` | Name of a method on the toolset class, so the callback can use `self`. |

Clicking into the field opens the popup right away, before anything is typed — a static list shows every option, and a callback is called with an empty `text` so it can return its default set. The list is not narrowed by a value already in the field, since re-entering one is usually a prelude to changing it.

Supported on `str` and `pathlib.Path` parameters only. Declaring it elsewhere raises at startup.

### `cascade` — fill other fields

Keyed by the **source** parameter. The callback returns `{target_name: value}`, or `None` to change nothing. It fires when the source is **committed** (focus loss, Enter, picking a candidate, toggling a checkbox), not on every keystroke, and is skipped when the value did not actually change.

Targets are always overwritten, including fields the user typed into — the callback receives `form` with every current value, so it can return one unchanged to preserve it. A written target may itself be a cascade source; chains are capped at 5 levels and cycles terminate after one round. **Replay never triggers cascades**, so restored parameters survive.

### `defaults` — lazy initial values

Signature defaults (`def deploy(self, env: str = "staging")`) are evaluated at **import** time. Use `defaults=` when the initial value must be read after the application has started — for example from `~/.decoui/history.db`, which does not exist until `gui_main()` runs.

```python
@tool(label="Deploy", defaults=lambda: {"env": get_setting("deploy.env", "staging")})
```

Accepts a dict, a callable taking nothing or the current `form`, or a method name. Runs once per tool page.

### Callback rules

- **Completion and cascade callbacks run on a background thread.** They must not touch Qt objects. Keep them to a lookup: query, return data.
- Callbacks may take 0, 1, or 2 positional arguments — `(text, form)` for completions, `(value, form)` for cascade.
- Any exception is caught, reported as a `WARNING` in the output console, and never aborts the form.
- Results from superseded requests are discarded, so a slow lookup cannot overwrite a newer one.

---

## Output & Logging

Tool methods can use `print()` and the standard `logging` module. Both are captured and rendered in the output console with colour coding:

| Source | Colour |
|---|---|
| `print` / stdout | White |
| `logging.DEBUG` | Gray |
| `logging.INFO` | Phosphor Green |
| `logging.WARNING` | Yellow |
| `logging.ERROR` | Red |
| `logging.CRITICAL` | Bold Red |

Return values from tool methods are **not** displayed in the GUI. Use `logging` or `print` for any output you want users to see.

### `run_process` — calling an external program

```python
from decoui import run_process

result = run_process(["pg_dump", "-d", "app"], check=True)
```

Runs the program, streams its output into the console line by line, and lets
Stop kill it — and everything it spawned — without the tool declaring anything.
Plain `subprocess` does neither. See [Cancellation](#cancellation).

### Progress

Long, quiet work looks indistinguishable from a hang. `progress()` drives the page's progress bar and the status text next to it:

```python
from decoui import progress, tool, toolset

@tool(label="Dump")
def dump(self, schema: str) -> None:
    for index, table in enumerate(tables):
        progress(index, len(tables), f"dumping {table}")
        dump_table(table)
    progress(len(tables), len(tables), "done")
```

| Argument | Meaning |
|---|---|
| `done` | Units completed so far. |
| `total` | Total units, or `0` when unknown — the bar stays indeterminate and only the message updates. |
| `message` | Short status text. Replaces "Running…" while set. |

Calls closer than 100 ms apart are dropped so a tight loop cannot flood the GUI; the final call (`done >= total`) is always delivered.

Outside a running tool — when you instantiate the toolset and call the method directly, as in a test — `progress()` does nothing at all. It prints nothing and raises nothing, so a tool stays callable as a plain method.

---

## Tool Page Buttons

| Button | Action |
|---|---|
| **Run** | Type-coerce parameters, run the method in a background thread. |
| **Reset** | Expand the parameter panel and clear the output console. Parameters are kept. |
| **Stop** | Request cancellation of the running task. |
| **Replay** | Open the History panel pre-filtered to this tool's past runs. |
| **Copy** | Copy current console output to clipboard. |
| **View Log** | Open the current console output in a resizable log viewer window. |

---

## Cancellation

Stop is the hardest promise decoui makes, because Python cannot keep it on its own.

Cancellation works by injecting an exception into the worker thread, and CPython raises it **at the
next bytecode boundary**. A thread parked in a C call never reaches one. `proc.wait()`,
`socket.recv()`, a long `time.sleep()` — the exception stays pending until that call returns by
itself, and the tool's `finally` does not run either.

So whatever is holding the thread has to be released *from outside*. Everything below follows from
that one fact.

### If your tool shells out, use `run_process`

```python
from decoui import run_process, tool, toolset

@toolset(label="Database")
class RestoreTools:

    @tool(label="Restore")
    def restore(self, archive: Path) -> str:
        result = run_process(["pg_restore", str(archive)])
        if result.cancelled:
            return "Stopped."
        return f"pg_restore exited {result.returncode}."
```

No handle to keep, no `on_cancel` to declare. `run_process` registers the child with the running
tool, so Stop kills it **and everything it spawned**.

It also streams the child's output into the page console line by line, which plain `subprocess`
cannot: decoui replaces `sys.stdout` with an object that has no `fileno()`, so a child left to
inherit stdout writes past the console rather than into it.

| | |
|---|---|
| `result.returncode` | the child's exit status |
| `result.output` | everything it wrote, already printed |
| `result.cancelled` | True only when decoui killed it |
| `check=True` | raise `ProcessError` if the program fails — a *cancelled* run never raises, because that status is decoui's doing |
| `shell=True` | refused: a shell is what leaves an unkillable grandchild behind. Pass a list |

**`subprocess.run()` cannot be made stoppable**, with or without a hook — it keeps its handle to
itself, so there is nothing for a hook to terminate. That is the shape a real incident had: Stop
appeared to work and the dump kept running.

> Measured, not assumed: every claim here is a test in
> [tests/test_stop_external_process.py](tests/test_stop_external_process.py), driving the real engine
> against a real child process. Full matrix in
> [docs/cancelling-a-run.md](docs/cancelling-a-run.md).

### If your tool blocks on something else, declare `on_cancel`

For a socket read, a database driver, a lock — anything `run_process` cannot reach — the hook is
still the only way. It runs on the GUI thread, *before* the interrupt is injected, while the worker
is still blocked:

```python
@tool(label="Query", on_cancel="stop")
def query(self) -> None:
    self.conn = driver.connect(...)
    self.conn.execute(long_query)

def stop(self) -> None:
    conn = getattr(self, "conn", None)
    if conn is not None:
        conn.cancel()
```

Three properties the hook must have:

- **Idempotent.** A Stop that arrives before the tool has assigned the state the hook reads does
  nothing, and a second Stop is the user's only way out of that — hence `getattr(self, "conn", None)`
  rather than `self.conn`.
- **Fast.** It blocks the GUI. Slow cleanup belongs in the tool's own `finally`.
- **Concurrent with your tool.** It is on the GUI thread while the body is still on the worker
  thread, so do not touch state the body is writing.

A hook that raises is reported as an `ERROR` line in that run's log; cancellation still completes.

### What else to know

**`except Exception` does not catch it.** The injected `_WorkerCancelled` derives from
`BaseException`, so an ordinary handler lets it pass straight through. That is deliberate — cleanup
written as `except Exception` must not be able to swallow a cancellation and carry on.

**A cancelled run is recorded as `cancelled`, never `success`,** and the return value is dropped. A
tool that returns normally after Stop was pressed is still recorded as cancelled: the user asked for
it to stop, and a partial result must not look like a whole one.

**Do not trust `proc.returncode` after a cancellation** if you manage a child yourself. The injection
can land between `waitpid()` returning and `Popen` recording the status, so it may stay `None` even
though the child is gone. Ask the OS.

`timeout=` uses this same path — from the tool's side a timeout and a Stop press are the same event.

---

## Themes

A theme sets colours, corner radii, border widths and fonts -- per part, not
per application: the sidebar, the tool list inside it, input fields, buttons,
tabs, tables and the output console each have their own tokens, so a theme can
put a dark panel behind the tool list while the rest of the window stays light.
It cannot add or move widgets.

| id | Name | Look |
|---|---|---|
| `light` | Light | The default. Rounded, blue accent. |
| `cockpit` | Cockpit Panel | Military instrument panel: olive-grey chassis, green accent, hard edges. |
| `nasa` | Mission Control | Warm off-white console: square corners, deep green accent, monospace. |
| `jp-industrial` | Industrial 1980s | Japanese workstation: beige chassis, burnt-orange accent, square. |

The three panel themes are recolours and re-geometries of the same interface,
not replicas of a hardware console: decoui has no header band, status lamps or
bezel screws to dress, and a theme cannot add any.

```python
gui_main(title="Ops", theme="light", theme_dir="~/.decoui/themes")
```

| Parameter | Meaning |
|---|---|
| `theme` | The application's **default** theme id. A theme the user picks in Settings wins over it. |
| `theme_dir` | Where user themes are read from. Defaults to `~/.decoui/themes`. A missing directory is fine and is never created. |

### Writing one

Drop a `.json` file into the theme directory. Nothing needs rebuilding, and the
new theme appears the next time the application starts.

```json
{
  "version": 1,
  "id": "brand",
  "name": "Brand",
  "extends": "light",
  "colors": {
    "accent": "#0f766e",
    "accent.soft": "#ccfbf1",
    "bg.tree": "#0d1a0b",
    "text.on_sidebar": "#cfd8c3"
  },
  "shape": { "shape.radius_control": 2 },
  "font": { "mono_family": ["JetBrains Mono", "monospace"], "small_size_pt": 8 }
}
```

The token groups:

| Group | Count | Covers |
|---|---|---|
| `bg.*` | 21 | every surface separately -- app, page, top bar, tabs, sidebar, tool list, fields, buttons, table, console |
| `text.*` | 16 | one ink per place text sits, including `text.on_sidebar` (a dark tool list), `text.on_topbar` (a dark top bar), and `text.on_running` / `on_success` / `on_danger` / `on_neutral` so a bright Run button can take dark text while Stop stays dark and takes light text |
| `border.*` | 10 | panels, fields, buttons, tabs, the cap on the current tab, focus, and the console's frame |
| `console.*` | 12 | a formatted line is inked in three parts -- `console.timestamp`, then `console.tag.<level>` for the level itself and `console.body.<level>` for the message. `console.plain` covers a line that carries no level at all, such as raw `print()` output. Set a level's tag and body to one value to tint the whole line |
| `accent` · `running` · `success` · `danger` · `neutral` · `scrollbar.*` | 11 | selections and the semantic fills. `running` is separate from `accent` because `accent` also fills every checked button: a theme that wants its toggles and its Run button in one colour would otherwise get a Running badge identical to the Done one |
| `shape.*` | 14 | six corner radii, and border widths and styles grouped the way the colours are -- `_panel` / `_control` / `_field`, plus `_emphasis` and `_focus` -- so a theme can bevel its buttons without bevelling its tables. Qt's `outset` / `inset` / `ridge` / `groove` draw a bevel from the border colour, which is as close to a raised panel as a flat format gets; `double` needs a width of at least 3 before two lines fit. Set the radii to `0` to square everything off. |
| `font.*` | 8 | `family` / `size_pt` / `letter_spacing`, `mono_family` / `mono_size_pt` for the console, `title_size_px` / `small_size_pt` for headings and secondary controls, and `uppercase` to render tags, tabs and buttons in capitals |

Font families are **stacks**: Qt falls through them in order, so end every one with
a generic family (`monospace`, `sans-serif`) or the theme lands on Qt's default
wherever its preferred face is missing.

* `id` is the stable key — it is what gets saved when the user selects the
  theme, so **renaming `name` never loses their choice**.
* `extends` starts from a built-in theme and overrides only the keys you list.
  Without it, every token must be present.
* `extends` always resolves against the theme decoui ships, even if another
  file has taken over that id — so one theme can never quietly re-base another.
* Giving your theme the `id` of a built-in **replaces** it, with no warning —
  that is how you re-skin `light` or `nasa`. Two of your *own* files claiming
  one id is reported instead, because one of them silently loses.
* Colours are `#rrggbb` only. There are no gradients: every token is one flat
  colour, so metallic and bevelled looks are out of reach.
* Setting the `shape.radius_*` tokens to `0` squares the whole interface off.
* `font.uppercase` changes only how labels are drawn -- the underlying strings
  are untouched, so a tab's title still matches its tool id.

Run `python -c "import decoui.theme as t; print(sorted(t.COLOR_TOKENS))"` for
the full token list.

### When a theme is broken

A theme is presentation, so a bad one never stops the application:

| Situation | What happens |
|---|---|
| One file is invalid | It is skipped; every other theme still loads |
| The selected theme is invalid or missing | The light theme is used instead |
| Either of the above | The application starts, and reports it in the startup dialog |

A selected theme that has gone missing is **not** un-selected — the file may be
absent only on this machine, and the choice takes effect again once it returns.

### Changing theme

The gear button at the top right opens **Settings**, which lists every theme
available -- built-in and user-supplied alike -- and starts on the one currently
in effect.

A new theme is applied as soon as the dialog closes, to every window that is
open. Nothing is rebuilt: a tool that is running goes on running, the forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The one thing that is lost is the console's scroll position, which
returns to the newest line.

The **interface language**, chosen in the same dialog, is the exception: it
takes effect on the next launch. Text is read as each widget is built, in far
more places than colour is, and there is no equivalent of the application
stylesheet to catch the rest. The dialog says which is which before you choose.

---

## Help Panel

The **?** button in the top bar opens a reference for everything loaded in the
session. Nothing has to be declared for it: a tool's page is built from the
docstring the method already carries — its summary, the prose under it, and the
`Args:`, `Returns:` and `Raises:` sections of Google style.

Write the docstring for the person **using** the tool, not for the person
reading the file. Notes about which annotation produces which widget belong in
`#` comments above the method; comments are not collected, so the two audiences
stay separated.

Alongside the tools, the panel carries decoui's own guide — how history works,
what Replay actually replays, how to change theme. That part ships with decoui
and is translated with the rest of the interface.

Each page opens in its own tab, the way the main window opens a tool, and the
arrows above the tabs walk back and forward through the pages visited.

### Writing help

Docstrings and guide pages are Markdown: headings, fenced code blocks, tables,
ordered and nested lists, blockquotes. Two departures, because the source is
sometimes a Python docstring:

- ` ``literals`` ` in double backticks are accepted alongside single, since that
  is what reST — and therefore a Python docstring — uses;
- indented code blocks are **not** recognised. A docstring's indentation is an
  artefact of where it sits in the file. Fence code instead.

**Cross-references have their own syntax, `[[key]]`,** deliberately not
Markdown's link syntax:

```
[[MyTools.encode]]                one tool
[[MyTools]]                       a whole toolset
[[guide.themes]]                  one of decoui's own pages
[[guide.themes|the theme page]]   with your own text
```

The target is a **key**, never a title or a file name:

| Key | Page |
|---|---|
| `guide` | decoui's own contents page |
| `guide.<slug>` | one of decoui's guide pages |
| `ClassName` | a toolset |
| `ClassName.method` | a tool |

Keys do not change when a page is translated, so one written link works in every
language. A reference that does not resolve — a tool the application did not
load, a typo — renders as its own text with no link on it. Which tools exist is
up to the application, so help cannot be written against a fixed set, and a dead
link is worse than the sentence without it.

Keeping references out of `[text](target)` is what lets that form mean what it
means everywhere else: **`[text](https://…)` is an ordinary link** and opens in
the reader's browser. Only `http`, `https` and `mailto` are followed.

Link colour comes from the theme's `text.link` token.

### Help in a file

When a tool's help outgrows its docstring, or wants translating, point at a
Markdown file:

```python
@tool(label="Deploy", help="doc/deploy.md")
def deploy(self, service: str = "web") -> str:
    ...
```

The path is relative to the module the toolset class is defined in, and decoui
inserts a language directory into it — `doc/<language>/deploy.md`, falling back
to `doc/en/deploy.md` and then `doc/deploy.md`.

The file replaces the **prose** and nothing else: the summary, the parameter
table and Returns still come from the docstring, because they describe the
signature and a file beside the module cannot be checked against it.

> Full reference: [docs/help-authoring.md](docs/help-authoring.md).

---

## Remembering Things Between Runs

A tool often has one thing worth keeping — the environment last deployed to,
the folder last exported into, whether the verbose flag was on. `store()` gives
you a namespaced key/value store, persisted in the same SQLite database as the
run history.

```python
from decoui import store, tool, toolset

@toolset(label="Deploy")
class DeployTools:

    def load_defaults(self) -> dict:
        return {"env": store("deploy").get("last_env", "staging")}

    @tool(label="Deploy Service", defaults="load_defaults")
    def deploy(self, service: str, env: str) -> None:
        """Deploy a service.

        Args:
            service: What to deploy.
            env: Where to deploy it.
        """
        store("deploy")["last_env"] = env      # inserted if new, replaced if not
```

It behaves as a mapping:

| | |
|---|---|
| `s[key] = value` / `s.set(key, value)` | write; there is nothing to register first |
| `s[key]` | read, `KeyError` when absent |
| `s.get(key, default)` | read with a fallback |
| `del s[key]` / `s.delete(key)` | remove; removing what was never there is fine |
| `key in s`, `len(s)`, `list(s)` | the usual |
| `s.keys()`, `s.items()` | everything in this namespace, sorted |

### The namespace

`store("deploy")` and `store("deploy")` anywhere else in the application reach
the same rows — that is how a setting shared by every tool is shared. Omit the
name and you get `app`, for an application that only needs one.

`ui` and `decoui` are refused: they hold the chosen theme, the interface
language and the sidebar width. An application writing there would be changing
the user's settings rather than its own.

A namespace may not contain a dot, because the dot is what separates it from
the key. Keys may contain anything.

### Values

Anything JSON can carry — `str`, `int`, `float`, `bool`, `None`, and lists and
dicts of those — and it comes back as the type it went in as. A value JSON
cannot carry raises `TypeError` where you wrote it, rather than being coerced
to a string that fails somewhere else later.

`None` is a stored value, not an absence: `key in store` still reports `True`.

Tuples come back as lists. JSON has no tuple.

### What it is not

A settings store, not an application database: small values, one at a time, no
queries and no relations. A tool with real data of its own should open its own
file.

Reads and writes go straight to the database — there is no cache — and every
call opens and closes its own connection, so this is safe to use from a tool
body, which runs on a worker thread.

Clearing the run history does **not** clear these: `clear_all_records()` leaves
the settings table alone.

---

## Execution History

Every run is stored in SQLite. The History panel (sidebar button) shows:

- Timestamp, tool name, status badge, duration
- Per-row checkboxes with **Select All / Deselect All / Delete Selected**
- Filter by tool, status, and time range
- Click any row to see the parameter snapshot
- **Replay Params** — restores that run's parameters to the tool's form
- **View Full Log** — opens the full log in a resizable window with level filters and search
- **DB size readout** — the current on-disk size of the history database, next to the filters
- **Clear History** — drops every record, parameter, and log, then vacuums the database to reclaim
  the space. Application settings are preserved.

History is stored at `~/.decoui/history.db` by default. Override with `db_path` in `gui_main()`.

---

## Example

See [`src/decoui/example.py`](src/decoui/example.py) for a complete demo covering all supported widget types.

Two tools there are worth reading as a pair before writing anything that runs for a while:

| Tool | Shows |
|---|---|
| **Demo Tools → Slow Task** | `progress()` driving the bar, `confirm=True`, and what a failed run looks like. Cancellable on its own, because it only sleeps. |
| **Demo Tools → Run Child Process** | `on_cancel` around a real subprocess. Press **Stop** while it runs: the hook is what actually kills the child, and the `with Popen(...)` block is what reaps it. |

Run it with:

```bash
uv run python main.py
# or
python main.py
```
