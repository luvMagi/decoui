# decoui v0.2.0 — Form Assist: Autocomplete & Cascading Fill

> Status: **Implemented** · Version: `0.2.0` · Previous: `0.1.4`

---

## Table of Contents

1. [Scope](#1-scope)
2. [Motivation](#2-motivation)
3. [Public API](#3-public-api)
   - [`completions`](#31-completions) · [`cascade`](#32-cascade) · [`defaults`](#33-defaults) · [`completion_debounce_ms`](#34-completion_debounce_ms)
4. [Callback Contract](#4-callback-contract)
5. [Widget Support Matrix](#5-widget-support-matrix)
6. [Execution Model](#6-execution-model)
7. [Internal Design](#7-internal-design)
8. [Behaviour Rules](#8-behaviour-rules)
9. [Error Handling](#9-error-handling)
10. [Validation](#10-validation)
11. [Backward Compatibility](#11-backward-compatibility)
12. [Tests](#12-tests)
13. [Out of Scope](#13-out-of-scope)
14. [Startup Sequence](#14-startup-sequence)

---

## 1. Scope

Four related additions, three to the parameter form and one to application startup:

| Feature | Meaning |
|---|---|
| **Autocomplete** (`completions`) | A parameter's input widget offers a candidate dropdown while typing. Candidates come from a static list or from a callback re-evaluated as the user types. |
| **Cascading fill** (`cascade`) | When a parameter's value is committed, a callback computes values for *other* parameters and writes them into the form. |
| **Lazy defaults** (`defaults`) | Initial form values evaluated when the tool page is opened, rather than at import time when a signature default is bound. |
| **Startup sequence** (`on_startup`) | Defined points at which to load persisted data, before the event loop starts: one application-wide, one per toolset. |

The first three are opt-in, declared on `@tool`. The completion and cascade callbacks run off the GUI thread; `defaults` runs synchronously once per page. The startup sequence is not opt-in: toolset instantiation moves from lazy to eager (see [§14](#14-startup-sequence)).

Nothing about the existing execution engine, history, or type→widget mapping changes.

---

## 2. Motivation

As of `0.1.4` the parameter form is fully static. `widget_builder.build_widget()` produces a widget from the annotation and default, `ToolPage._build_ui()` puts it in a `QFormLayout`, and no widget ever observes another. There is no hook on `@tool` where a lookup could be attached — the decorator metadata is `label / description / icon / confirm / timeout / placeholders`.

This forces three bad patterns on tool authors:

- Users retype identifiers (service names, table names, ticket ids) that the tool could look up.
- Fields that are derivable from another field (a service's owner, a dataset's schema, a host's region) must either be typed by hand or silently recomputed inside the tool body, where the user cannot see or override them.
- Initial values can only come from signature defaults, which Python evaluates at **import** time. That rules out any source which is not ready until the app has started — most notably decoui's own settings table, since `init_db()` and `set_db_path()` both run inside `gui_main()`.

`completions` fixes the first. `cascade` fixes the second while keeping the derived values visible and editable before the run. `defaults` fixes the third.

Note that a plain module-level variable remains the right answer whenever the data *is* available at import time:

```python
LAST = json.loads(Path("~/.myapp.json").expanduser().read_text())

class DeployTools:
    @tool(label="Deploy")
    def deploy(self, env: str = LAST["env"]) -> None: ...
```

`defaults` exists for the cases that pattern cannot reach, not to replace it.

---

## 3. Public API

Four new keyword arguments on `@tool`. `completions` and `cascade` follow the shape of the existing `placeholders`: a dict keyed by parameter name.

```python
@tool(
    label="Deploy",
    placeholders={"env": "prod / staging"},
    completions={
        "env": ["prod", "staging", "dev"],          # static list
        "service": lambda text, form: search(text),  # dynamic callback
        "region": "complete_region",                 # method on the toolset class
    },
    cascade={
        # when 'service' is committed, fill 'version' and 'owner'
        "service": lambda value, form: {
            "version": latest_version(value),
            "owner": owner_of(value),
        },
    },
    completion_debounce_ms=250,   # optional, per-tool override
)
def deploy(self, env: str, service: str,
           version: str = "", owner: str = "", region: str = "") -> None:
    ...
```

### 3.1 `completions`

`dict[str, list[str] | Callable | str]`, default `{}`.

| Value form | Behaviour |
|---|---|
| `list[str]` / `tuple[str, ...]` | Fixed candidate set. Filtering is done by Qt (`QCompleter` default `PopupCompletion`, case-insensitive, `MatchContains`). No callback runs. |
| `Callable` | Re-evaluated as the user types (debounced). The returned iterable **replaces** the candidate model wholesale; Qt-side filtering is disabled (`UnfilteredPopupCompletion`) so the callback has full control over matching and ordering. |
| `str` | Name of a method on the `@toolset` class. Resolved and bound to the live instance when the `ToolPage` is created, so the callback can use `self`. Same call contract as `Callable`. |

### 3.2 `cascade`

`dict[str, Callable | str]`, default `{}`.

The key is the **source** parameter. The callback returns a `dict[str, Any]` mapping **target** parameter names to values, or `None` / `{}` for "change nothing". Targets are written with the existing `widget_builder.set_value()`, so any value type that `set_value` accepts is accepted here.

`str` values resolve to a bound method of the toolset class, exactly as in `completions`.

### 3.3 `defaults`

`dict[str, Any] | Callable | str`, default `None`.

Evaluated once, on the GUI thread, when the `ToolPage` is constructed — after `init_db()`, after `on_startup()`, and after the toolset's `__init__` ([§14](#14-startup-sequence)) — so a callback may read the settings table or anything the toolset loaded onto `self`. Values are written with `set_value()`, exactly like a cascade target.

Applied **before** any assist controller exists, so seeding the form never triggers a cascade. A callable receives the form as built from signature defaults, and may take it or take nothing:

```python
defaults=lambda: {"env": get_setting("deploy.env", "staging")}
defaults=lambda form: {"name": form["name"].upper()}
defaults="load_defaults"       # method on the toolset class
```

Unlike the other two, this callback is **not** dispatched to a thread: the form must be populated before the user sees it, and a page that opens with a half-filled form would be worse than one that opens slightly later. A raising callback logs a `WARNING` and leaves the signature defaults in place.

### 3.4 `completion_debounce_ms`

`int`, default `250`. Idle time after the last keystroke before a dynamic completion callback is dispatched. Ignored for static lists. `0` disables debouncing (dispatch on every keystroke) — not recommended for network-backed sources.

Cascade callbacks are **not** debounced; they fire on commit, not per keystroke (see [§8.1](#81-when-a-cascade-fires)).

---

## 4. Callback Contract

### 4.1 Signatures

Both callback kinds accept 0, 1, or 2 positional parameters. Arity is inspected once at `ToolPage` construction with `inspect.signature()` and the call is adapted; a bound method's `self` does not count.

```python
# completions
def complete(text: str, form: dict[str, Any]) -> Iterable[str]: ...
def complete(text: str) -> Iterable[str]: ...
def complete() -> Iterable[str]: ...

# cascade
def on_change(value: Any, form: dict[str, Any]) -> dict[str, Any] | None: ...
def on_change(value: Any) -> dict[str, Any] | None: ...
def on_change() -> dict[str, Any] | None: ...
```

| Argument | Type | Meaning |
|---|---|---|
| `text` | `str` | Current raw text of the source widget, exactly as typed. May be empty. |
| `value` | `Any` | Committed value of the source parameter, already read through `widget_builder.get_value()` (so an `Enum` parameter yields the member, an `int` parameter yields an `int`). Not type-coerced through `coerce_params`. |
| `form` | `dict[str, Any]` | Snapshot of every parameter's current widget value, taken on the GUI thread before dispatch. A plain dict copy — mutating it has no effect. |

Return values are normalised: for `completions`, non-`str` items are passed through `str()`, duplicates are dropped keeping first-seen order, and the result is truncated to `MAX_COMPLETION_ITEMS = 1000`. For `cascade`, keys that are not parameters of this tool are dropped with a warning.

### 4.2 Threading rule

> **Callbacks run on a worker thread. They must not touch Qt objects.**

This is a hard contract, stated in the README and raised as a warning in the log if a callback is detected to have taken longer than 5 s. Callbacks should be pure lookups: query, return data. All widget mutation happens back on the GUI thread inside the controllers.

---

## 5. Widget Support Matrix

| Annotation | Widget | `completions` | `cascade` source | `cascade` target |
|---|---|---|---|---|
| `str` | `QLineEdit` | ✅ | ✅ | ✅ |
| `pathlib.Path` | `_PathWidget` | ✅ (on the inner `QLineEdit`) | ✅ | ✅ |
| `Enum` | `QComboBox` | ❌ (candidate set is the enum) | ✅ | ✅ |
| `int` / `float` | `QSpinBox` / `QDoubleSpinBox` | ❌ | ✅ | ✅ |
| `bool` | `QCheckBox` | ❌ | ✅ | ✅ |
| `list` | `QTextEdit` | ❌ (see [§13](#13-out-of-scope)) | ✅ | ✅ |
| `dict` | `_DictTextEdit` | ❌ | ✅ | ✅ |

Declaring `completions` for a parameter whose widget does not support it is a startup error ([§10](#10-validation)), not a silent no-op.

---

## 6. Execution Model

Both features share one dispatch mechanism, modelled on `engine/worker.py`: a `QRunnable` submitted to a `QThreadPool`, results delivered back to the GUI thread through a `Signal`.

A dedicated `QThreadPool` with `maxThreadCount = 4` is used, **separate from the global pool that runs tools**, so that a slow lookup can never starve or delay an actual tool run.

### 6.1 Completion request lifecycle

```
keystroke → restart debounce timer (completion_debounce_ms)
          → timer fires
          → seq += 1; snapshot form on GUI thread
          → submit _AssistTask(callback, text, form, seq) to pool
          → worker thread calls the callback
          → finished(seq, items) signal → GUI thread
          → if seq < latest_seq for this widget: DROP (stale)
          → else: replace QStringListModel, show popup if the widget still has focus
```

Staleness is the only concurrency control — requests are never cancelled mid-flight (the callback is user code and cannot be interrupted), their results are simply discarded. A widget holds at most one pending sequence number; older results always lose.

### 6.2 Caching

Results are cached per widget in an LRU of 32 entries keyed by the request text. The whole cache for a tool page is invalidated whenever any parameter is committed, because `form` is part of the callback input and a stale `form` would produce wrong candidates.

The `completions` design assumes a candidate set of **under ~1000 items** per query. Above that, the popup is the bottleneck, not the lookup; authors should return a narrowed set from the callback rather than relying on Qt to filter.

### 6.3 Cascade lifecycle

```
source widget commits → read value via get_value()
                      → snapshot form
                      → submit _AssistTask to the same pool
                      → worker thread calls the callback
                      → finished(seq, updates) → GUI thread
                      → drop if stale
                      → apply set_value() to each target
                      → each written target may itself be a cascade source
                        (see §8.2 for depth and cycle limits)
```

While a cascade is in flight the source widget stays editable — the result is simply dropped if the user has moved on. No modal blocking, no spinner: a cascade that takes long enough to need one is a design smell and is documented as such.

---

## 7. Internal Design

### 7.1 New module

```
src/decoui/assist.py     # completion + cascade controllers and the shared task runner
```

Placed at the top level next to `widget_builder.py` rather than under `ui/`, matching the existing split: `widget_builder.py` already imports Qt widgets and is not considered a UI page.

| Symbol | Kind | Responsibility |
|---|---|---|
| `AssistPool` | module-level `QThreadPool` | Dedicated 4-thread pool for assist callbacks. |
| `_AssistTask(QRunnable)` | class | Calls one adapted callback, emits `finished(seq, result)` or `failed(seq, message)`. |
| `AssistRunner` / `InlineRunner` | class | Task dispatchers. `InlineRunner` runs tasks synchronously and is injected by tests. |
| `_FocusFilter` | class | Event filter reporting `FocusIn` (with its reason) and `FocusOut`. |
| `_adapt_lookup` / `_adapt_defaults` | function | Inspect arity once and return a fixed-signature closure. |
| `CompletionController` | class | Owns one widget's `QCompleter`, `QStringListModel`, debounce `QTimer`, sequence counter, and LRU cache. |
| `CascadeController` | class | Owns the source→callback map for a whole page; performs propagation with depth and cycle limits. |
| `resolve_callback(spec, instance)` | function | Turns a `str` / `Callable` spec into a concrete callable bound to `instance`. |
| `resolve_defaults` / `apply_defaults` | function | Evaluate the `defaults` spec and write the result into the form. |
| `validate_assist_config(...)` | function | Startup validation, called from `build_tree()`. |
| `_WarningThrottle` | class | Collapses repeated warnings from one callback into one per 10 s. |

`CascadeController` wires commit detection for **every** widget, not only for declared sources. Two things need it: the completion cache, which is keyed on a form snapshot and goes stale when any field changes, and the "value actually changed" check. Only declared sources dispatch a callback.

### 7.2 Changes to existing modules

**`decorators.py`** — `tool()` gains `completions`, `cascade`, `defaults`, `completion_debounce_ms`; they are stored in the `__decoui_tool__` metadata dict alongside `placeholders`.

**`registry.py`** — `ToolInfo` gains four fields, all with defaults so existing construction sites keep working:

```python
completions: dict[str, Any] = field(default_factory=dict)   # param -> list | Callable | str
cascade: dict[str, Any] = field(default_factory=dict)       # param -> Callable | str
defaults: Any = None
completion_debounce_ms: int = DEFAULT_DEBOUNCE_MS
```

`build_tree()` copies them from the metadata and runs the startup validation in [§10](#10-validation). `ParamInfo` is unchanged — assist specs are a property of the tool, not of an individual parameter, and keeping them on `ToolInfo` avoids touching the `ParamInfo` constructor used throughout the widget layer.

**`widget_builder.py`** — two new public helpers plus one signal:

```python
def completion_target(widget: QWidget) -> QLineEdit | None:
    """Return the QLineEdit a completer should attach to, or None if unsupported."""

def supports_completion(annotation: Any) -> bool:
    """Report whether an annotation maps to a completable widget."""
```

`completion_target` returns the widget itself for a bare `QLineEdit`, `widget._edit` for a `_PathWidget`, and `None` otherwise, keeping `_PathWidget`'s internals private to the module where they already live. `supports_completion` backs the startup check in [§10](#10-validation) and mirrors the branches in `_build_for_type()`.

`_PathWidget` gains a `committed` signal, emitted both when its inner line edit finishes editing and when a file/folder dialog is accepted. Without it a path chosen from the dialog would set the text programmatically and never register as a commit.

**`ui/tool_page.py`** — `__init__` gains an optional `assist_runner` argument (tests inject `InlineRunner`), and calls two new steps after `_build_ui()`:

```python
self._build_ui()
self._apply_defaults()    # before controllers exist -> cannot trigger a cascade
self._setup_assist()
```

`_set_params_readonly()` additionally suspends both controllers, so no lookup fires while a tool is running. `restore_params()` (used by Replay) suspends propagation for the duration of the restore and then calls `CascadeController.sync_values()` — see [§8.3](#83-overwriting-user-input).

### 7.3 Signal wiring per widget type

| Widget | Completion trigger | Cascade commit trigger |
|---|---|---|
| `QLineEdit` | `textEdited`, and `FocusIn` | `editingFinished`, and `QCompleter.activated` |
| `_PathWidget` | inner `textEdited` | `committed` (inner `editingFinished` + dialog acceptance) |
| `QComboBox` | — | `currentIndexChanged` |
| `QCheckBox` | — | `toggled` |
| `QSpinBox` / `QDoubleSpinBox` | — | `editingFinished` |
| `QTextEdit` / `_DictTextEdit` | — | `focusOut` (via an event filter) |

`textEdited` rather than `textChanged` is deliberate: it is not emitted by programmatic `setText()`, so a cascade writing into a field never triggers that field's completion popup.

---

## 8. Behaviour Rules

### 8.1 When a cascade fires

On **commit**, not on every keystroke — `editingFinished` for text and numeric fields, selection for combo boxes, `focusOut` for text areas. Typing `prod` character by character produces one cascade, not four.

A cascade is skipped when the committed value is equal to the value at the previous commit. `editingFinished` fires on every focus loss, including when the user tabs through a field without touching it; that must not trigger a lookup.

### 8.2 Chained cascades

A field written by a cascade may itself be a cascade source. Propagation is bounded:

- **Depth limit** `MAX_CASCADE_DEPTH = 5`. Exceeding it stops propagation and logs a `WARNING` naming the chain.
- **Cycle detection**: a set of already-visited source names is carried through one propagation pass. Re-entering a source is skipped silently — `a → b → a` settles after one round instead of looping.
- A cascade never triggers itself, even if its own name appears among the targets it returns.

### 8.3 Overwriting user input

**Cascade targets are always overwritten**, including fields the user has already typed into. The alternative — tracking a per-field "dirty" flag and skipping dirty targets — makes the form's behaviour depend on invisible state and is harder to reason about than "picking a service resets its derived fields".

Authors who need to preserve a user edit have the escape hatch built into the contract: `form` carries the current value of every field, so the callback can return it unchanged.

**Replay** is the one exception. `restore_params()` writes a complete parameter set from history; running cascades over it would overwrite the restored values with freshly computed ones and defeat the purpose. Cascade propagation is therefore suspended for the whole restore and re-enabled afterwards.

### 8.4 Empty input and focus

Entering a completable field opens the popup immediately, before anything is typed — the field is otherwise indistinguishable from a plain text box, and the candidates are the whole point of declaring them.

The list shown on focus is **unfiltered**, even when the field already holds a value: a static list shows every option, and a dynamic callback is called with an empty `text` so it can return its default set. Someone clicking into a filled field is usually there to pick a *different* value, and typing narrows the list again immediately. This is also why the callback contract guarantees `text` may be empty.

Two focus reasons are ignored, both via `QFocusEvent.reason()`:

| Reason | Why |
|---|---|
| `PopupFocusReason` | Showing the popup hands focus back to the line edit. Acting on it would reopen the popup forever. |
| `ActiveWindowFocusReason` | Alt-tabbing back into the window is not the user entering the field. |

Cascades are **not** fired for an empty commit unless the previous committed value was non-empty — clearing a field is a real change and should be allowed to clear derived fields.

---

## 9. Error Handling

An exception inside any assist callback must never abort the form or the application.

| Failure | Result |
|---|---|
| Completion callback raises | Candidate model left unchanged, popup not shown. One `WARNING` line with the traceback in the tool's output console. |
| Cascade callback raises | No target is written. One `WARNING` line with the traceback. |
| Cascade returns a non-dict | Ignored, `WARNING` naming the source and the returned type. |
| Cascade returns unknown target names | Known targets are still applied; unknown ones dropped with a `WARNING`. |
| `set_value()` raises on one target | That target is skipped, remaining targets are still applied, `WARNING` per failure. |
| Callback exceeds 5 s | Result still applied if not stale; one `WARNING` suggesting the callback be made faster or the candidate set narrowed. |
| `defaults` raises or returns a non-dict | Form keeps its signature defaults, one `WARNING` with the traceback. |
| `defaults` names an unknown parameter at runtime | That entry is skipped, the rest are applied, one `WARNING` per entry. |

Warnings go through the existing `ToolPage._append_log()`, so they land in the console and the log window with the standard yellow `WARNING` colour. They are **not** persisted to history — assist activity is form interaction, not execution, and `ExecutionRecord` is created only on Run.

Repeated identical warnings from the same callback are collapsed: at most one per callback per 10 s window, so a broken lookup on a fast typist does not flood the console.

---

## 10. Validation

`build_tree()` fails loudly at startup — a misspelled parameter name should not turn into a silently dead feature.

| Condition | Error |
|---|---|
| `completions` / `cascade` key is not a parameter of the tool | `ValueError: @tool('Deploy') completions references unknown parameter 'servcie'; available: env, service, version` |
| `completions` value is not a list/tuple/callable/str | `TypeError` naming the parameter and the received type |
| `completions` declared for an unsupported widget type | `TypeError: @tool('Deploy') completions['count'] targets an int parameter; completions support str and pathlib.Path only` |
| `str` spec names a method that does not exist on the toolset class | `AttributeError` naming both the class and the method |
| `str` spec names a non-callable class attribute | `TypeError` |
| `defaults` is a dict with a key that is not a parameter | `ValueError` naming the key and the available parameters |
| `defaults` is neither a dict, a callable, nor a method name | `TypeError` |

A `defaults` **callable** can only be checked at runtime, since its result does not exist until the page opens; unknown keys there are warnings, not errors ([§9](#9-error-handling)).

Method-name resolution happens in two stages: existence is checked in `build_tree()` (class is available), binding to the instance happens in `ToolPage.__init__` (instance is available).

---

## 11. Backward Compatibility

Fully additive. All four `@tool` arguments default to empty/`None`/`250`, and a tool that declares none of them builds exactly the widget tree `0.1.4` builds — `_setup_assist()` returns immediately, no completer is attached, no signal is connected, and no thread pool is created (the pool is lazily instantiated on first use).

No storage schema change: `ExecutionRecord`, `ExecutionParam`, and `ExecutionLog` are untouched, so existing `history.db` files open unchanged and Replay keeps working against runs recorded by `0.1.x`.

Version bump to `0.2.0` rather than `0.1.5` because the public decorator surface grows.

---

## 12. Tests

Under `tests/`, using the existing offscreen `qt_app` fixture from `conftest.py`. 46 tests across three files; the suite as a whole is 54 and passes.

**`test_assist_registry.py`** (20) — metadata plumbing and startup validation:
- `completions` / `cascade` / `defaults` / `completion_debounce_ms` survive the decorator into `ToolInfo`, and a plain tool declares none of them
- every validation case in [§10](#10-validation) raises with the offending parameter name in the message
- a method-name spec binds to the live instance, so the callback can use `self`
- `_adapt_lookup` / `_adapt_defaults` handle every supported arity
- `normalize_candidates` de-duplicates, stringifies, truncates at 1000, and rejects scalars

**`test_completion.py`** (15):
- a static list installs a Qt-filtered completer; a callback installs an unfiltered one
- the callback receives the typed text and the form snapshot
- entering a field offers candidates with nothing typed, and is not narrowed by an existing value
- `PopupFocusReason` and `ActiveWindowFocusReason` trigger no lookup, so the popup cannot reopen itself
- a suspended controller ignores focus as well as keystrokes
- three fast keystrokes produce one call after the debounce interval elapses
- repeated text is served from cache; `invalidate_cache()` forces a fresh lookup
- a late result whose sequence number was superseded never reaches the model
- a raising callback keeps the previous candidates and warns exactly once
- a non-iterable result warns instead of corrupting the model
- a suspended controller performs no lookup

**`test_cascade.py`** (16) — driven through a real `ToolPage`:
- committing a source writes every returned target; a checkbox is a valid source
- an unchanged commit fires nothing; clearing a field does fire
- a 6-link chain propagates 5 levels and stops with one warning; `a → b → a` settles after one round
- unknown targets are dropped while known ones still apply; a non-dict result and a raising callback both warn and write nothing
- `restore_params()` triggers no cascade and resets the commit baseline
- the form is inert while `_set_params_readonly(True)`
- `defaults` applies dicts and callables, is evaluated once per page, receives the signature defaults, survives a raising callback, and does not trigger cascades

**`test_startup.py`** (12) — the sequence in [§14](#14-startup-sequence):
- `on_startup` runs once; omitting it is not an error
- a raising application hook is reported as a problem carrying source, summary and traceback, and does not abort startup
- a raising `__init__` is reported and skips only that toolset; unrelated ones still load
- `ToolSet.on_startup()` runs after construction and can fill attributes declared in `__init__`; when it raises, the instance survives with those declarations intact
- a `@tool` named `on_startup` is not called as a hook
- every toolset is constructed eagerly, exactly once, and the window reuses those instances rather than building new ones
- data loaded at startup reaches the form through `defaults`
- a `MainWindow` built without an `instances` map still creates them lazily

Threading is made deterministic by injecting `InlineRunner` into the controllers, rather than waiting on a real `QThreadPool`. One caveat worth recording: `QTest.qWait()` starves worker threads of the GIL, so any end-to-end check against the real pool must run under `app.exec()` with `QTimer.singleShot` steps.

---

## 13. Out of Scope

Deliberately excluded from `0.2.0`:

- **Multi-value completion in `list` fields** (per-line candidates in a `QTextEdit`). Needs a custom completer prefix strategy; revisit if asked for.
- **Editable `QComboBox` for `str` parameters** — a "choose from these, or type your own" widget. `completions` on a `QLineEdit` already covers most of that need.
- **Validation callbacks** (`@tool(validate={...})`) marking a field red before Run. Related and likely next, but a separate feature with its own visual language.
- **Async/`await` callbacks.** Callbacks are plain sync functions run in a thread; an `asyncio` bridge is not worth the dependency yet.
- **Cross-tool sharing** of candidate sources. Each tool declares its own; deduplicate with an ordinary module-level function.
- **A built-in key-value store** (`decoui.store`) wrapping the `app_setting` table, and **`@tool(remember=True)`** to auto-save and restore the last used parameters. Both were considered alongside [§14](#14-startup-sequence); the startup sequence is the prerequisite, and these can be layered on later without changing it.

---

## 14. Startup Sequence

> This section records *why* the sequence is shaped this way. Tool authors who
> just need to know where to load data should read
> [../startup-lifecycle.md](../startup-lifecycle.md) instead.

### 14.1 The gap

Reading initial values from a persisted file is expected to be the common case, not an edge case. Before `0.2.0` there was no correct place to do it:

| Moment | Problem |
|---|---|
| Import time (signature defaults) | Runs before `gui_main()`, so `db_path` is unset and the database has no tables. Fine for the user's own files, useless for decoui's storage. |
| Toolset `__init__` | Lazy: `MainWindow._get_instance()` constructed a class the first time one of its tools was clicked. Load time was unpredictable, blocked the click, and never happened at all for a tool the user did not open. |
| `ToolPage` construction (`defaults`) | Already inside the event loop, and once per page rather than once per application. |

### 14.2 Defined order

`gui_main()` now runs a fixed sequence:

1. `set_db_path()` if `db_path` was given, then `init_db()`
2. `build_tree()` — annotation scan and assist validation ([§10](#10-validation))
3. `_run_startup_hook(on_startup)` — the application-wide hook
4. `_create_instances(tree)` — **every** toolset class is instantiated
5. `_run_toolset_hooks(instances)` — each instance's own `on_startup()` method
6. `MainWindow(..., instances=...)`, `show()`, then the problem dialog, then `app.exec()`

Step 4 is the substantive change: instantiation moves from lazy to eager.

### 14.3 Two hooks, two scopes

| Hook | Scope | Runs | Can write to `self` |
|---|---|---|---|
| `gui_main(on_startup=...)` | Application | Before any instance exists | No — there is no instance yet |
| `ToolSet.on_startup()` | One toolset | After that instance is constructed | Yes |

The second exists because of that "no" in the first row. The natural request — "load in `on_startup` and store it on `self`" — is impossible for the `gui_main` argument by construction: it runs at step 3, and instances do not exist until step 4. Rather than reorder the sequence or pass the instance map into a free function, a toolset that owns its data gets its own hook.

The recommended split is **declare in `__init__`, load in `on_startup()`**:

```python
def __init__(self):
    self.config = {"env": "staging"}     # cheap, always succeeds
def on_startup(self):
    self.config = load_from_disk()       # may fail; see §14.4
```

A `@tool`-decorated method named `on_startup` is never called as a hook — the `_TOOL_ATTR` marker is checked first, so a tool that happens to share the name keeps behaving like a tool.

### 14.4 Failure is reported, not fatal

A failure in steps 3-5 does not stop the application. Each one is collected as a `StartupProblem` (source, one-line summary, full traceback) and all of them are shown in a single `QMessageBox` over the main window, with the tracebacks behind the Details button.

This is a deliberate reversal of the first draft of this design, which made startup failures fatal on the grounds that a half-initialised tool is worse than one that never opened. That reasoning was wrong about the blast radius: one unreachable backend would have blocked every unrelated tool in the application, and a stack trace on stderr is not visible to someone running a packaged GUI.

The split between `__init__` and `on_startup()` is what makes non-fatal handling coherent:

| Failure | Result |
|---|---|
| `gui_main(on_startup=...)` raises | Reported; everything else loads. |
| `ToolSet.__init__` raises | Reported; that toolset is **skipped** and its tools do not appear — there is no object to build a page from. |
| `ToolSet.on_startup()` raises | Reported; the instance stays, holding whatever `__init__` declared, so its tools still open with fallback values. |

Keeping `__init__` trivial therefore has a concrete payoff: it moves a toolset from the "disappears" row to the "degrades" row.

### 14.5 Compatibility

`MainWindow.__init__` gains an optional `instances` mapping. Classes absent from it are still instantiated on first use by `_get_instance()`, so constructing a `MainWindow` directly — as the existing tests do — keeps working unchanged.

Eager instantiation is observable in one more way: a toolset `__init__` with side effects (writing a file, printing) now runs at startup rather than on first click.
