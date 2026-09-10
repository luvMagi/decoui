# Startup Lifecycle — Where to Load Data

> [Project README](../README.md) · [Complete reference](reference.md)

> Guide for tool authors · Applies to decoui `0.2.0`+ · theme step added in `0.4.0` · language step added in `0.5.0`

Reading initial values from a config file, a database, or a service is the common case, not an edge case. decoui gives you three places to do it and they are **not** interchangeable. This page says which one to use and what each guarantees.

If you only read one thing: **declare state in `__init__`, load it in `on_startup()`, and reference it from a decorator by method name.**

---

## 1. The full order

```
── import time ─────────────────────────────────────────────
    @toolset / @tool decorators execute
    signature defaults are evaluated here      def deploy(self, env="staging")

── gui_main() ──────────────────────────────────────────────
 1  set_db_path()               db location fixed
 2  toolsets resolved           explicit list, or a scan of caller globals;
                                @toolset CLASSES, not instances
 3  QApplication created        ← the app object exists from here
 4  init_db()                   tables created; get_setting() and store() usable
 5  language applied            stored choice > gui_main(language=) > English.
                                Before the theme: the theme's own failure dialog
                                is written in the interface language
 6  theme resolved + applied    stored choice > gui_main(theme=) > light;
                                a broken theme falls back, never stops startup
 7  build_tree()                annotation scan + assist validation
 8  on_startup()                ← APPLICATION hook
 9  cls() for every toolset     ← `self` exists from here
10  ToolSet.on_startup()        ← PER-TOOLSET hook
11  MainWindow built            sidebar only; no ToolPage yet
12  window.show()               the window appears
13  problem dialog, if any      theme problems are reported here too
14  app.exec()                  ← the event loop starts

── later, when the user clicks a tool ──────────────────────
    ToolPage.__init__ → defaults / completions / cascade become live
```

---

## 2. Three places, three guarantees

| Where | Runs | `self` | Database | Use it for |
|---|---|---|---|---|
| Signature default<br>`def deploy(self, env="staging")` | Import time, before step 1 | No | **No** — no tables, `db_path` not applied | Constants, and data your own code already read at import |
| `gui_main(on_startup=...)` | Step 6 | **No** — no instance exists yet | Yes | Application-wide setup: a shared connection, an auth token, a warm cache |
| `ToolSet.on_startup(self)` | Step 8 | **Yes** | Yes | Everything one toolset owns |

A fourth exists for form values specifically: `@tool(defaults=...)`, evaluated when the tool page is opened. It is for values that must be recomputed each time the page opens; for load-once data, prefer `on_startup()` plus a method-name spec.

---

## 3. Three things that surprise people

### 3.1 The event loop is not running yet

`QApplication` exists at step 3, but `app.exec()` is at step 13. Inside either hook:

- **`QTimer` does not fire**, queued signals are not delivered, and `QThreadPool` results never arrive. Starting a background thread and waiting for its result deadlocks your startup.
- **There is no main window**, so a dialog you open yourself has no parent and blocks startup behind a frame the user did not expect. To report a problem, just `raise` — decoui collects it and shows one dialog after the window appears (step 11).

### 3.2 Both hooks block the window

They run synchronously on the GUI thread, before `show()`. However long they take is time the user spends looking at nothing. A 10-second HTTP call means 10 seconds of blank screen.

That is the deal you are making by loading before the event loop. Keep it to what the form genuinely needs at open time; anything slow belongs in the tool body, where it gets a thread, a progress bar, and a Stop button.

### 3.3 The two hooks share a name but not a scope

This is the one that causes real confusion:

```python
def connect() -> None: ...                    # free function → step 6, no self
gui_main(on_startup=connect)

class DeployTools:
    def on_startup(self) -> None: ...         # method → step 8, has self
```

The application hook runs at step 6, *before any instance exists*, so it physically cannot write to `self`. That is exactly why the per-toolset hook exists.

The ordering between them is guaranteed: **the application hook always runs before every toolset hook.** That is the intended division of labour.

---

## 4. The recommended pattern

Declare in `__init__` with fallbacks, load in `on_startup()`, expose by method name:

```python
_CLIENT: Client | None = None


def connect() -> None:
    """Application-wide setup: belongs to no single toolset."""
    global _CLIENT
    _CLIENT = Client.connect(SERVICE_URL)


@toolset(label="Deploy Tools")
class DeployTools:

    def __init__(self) -> None:
        # Cheap and always succeeds. These are the values the form falls back
        # to if loading fails.
        self.services: list[str] = []
        self.config = {"env": "staging"}

    def on_startup(self) -> None:
        # Runs after connect(), before the window. May fail; see §5.
        self.services = _CLIENT.list_services()
        self.config["env"] = store("deploy").get("env", "staging")

    @tool(
        label="Deploy",
        defaults="load_defaults",
        completions={"service": "search_services"},
    )
    def deploy(self, service: str = "", env: str = "") -> None:
        store("deploy")["env"] = env            # remember for next launch

    def load_defaults(self) -> dict:
        return {"env": self.config["env"]}      # reads self at call time

    def search_services(self, text: str) -> list[str]:
        return [s for s in self.services if text.casefold() in s.casefold()]
```

### Why split `__init__` and `on_startup()`?

Because of what happens when loading fails — see the table in §5. A failing `__init__` makes the toolset **disappear**; a failing `on_startup()` only makes it **degrade**. Keeping `__init__` trivial is what buys you the second outcome.

### Can a decorator argument see `self`?

**Not directly.** Decorator arguments are evaluated at import time, when no instance exists:

```python
@tool(label="Deploy", defaults={"env": self.config["env"]})    # NameError: self
```

**Pass a method name instead.** decoui resolves it to a bound method when the tool page is built, and the method body reads `self` at call time — long after `__init__` and `on_startup()` have run:

```python
@tool(
    label="Deploy",
    defaults="load_defaults",
    completions={"service": "search_services"},
    cascade={"service": "describe_service"},
)
```

All three of `defaults`, `completions`, and `cascade` accept a method name this way.

---

## 5. When loading fails

No startup failure stops the application. Every failure is collected and shown in **one dialog over the main window**, with the full traceback behind the Details button. Whatever loaded successfully stays usable.

| Failure | Result |
|---|---|
| `gui_main(on_startup=...)` raises | Reported. Everything else loads normally. |
| `ToolSet.__init__` raises | Reported. **That toolset is skipped** and its tools do not appear — there is no object to build a page from. |
| `ToolSet.on_startup()` raises | Reported. **The instance survives**, holding whatever `__init__` declared, so its tools still open with fallback values. |
| `@tool(defaults=...)` raises | Reported as a `WARNING` in that tool's output console. The form keeps its signature defaults. |

Do not catch and swallow errors inside a hook just to keep the app quiet. Raising is how the problem reaches the user; a hook that silently leaves `self.services` empty produces an autocomplete popup that is simply always blank, with nothing to explain why.

---

## 5.1 Why the language and the theme come before anything is built

The database comes first because both choices live in it. The language is
applied before the theme because the theme's own failure dialog is written in
the interface language: by the time there is a problem to report, the language
has to be settled.

Both are applied before the first widget exists, because widgets read their
text and the colours they set on themselves as they are constructed.

They differ in what happens afterwards. **The theme can be changed in place**
(since `0.5.0`): most colour lives in the application stylesheet, and the
handful of widgets that ink themselves are told to redo it —
`ui/retheme.py`. **The language cannot**: text is read at build time in far
more places than colour is, and there is no equivalent of the stylesheet to
catch what a walk would miss. Changing language still means restarting, and the
settings dialog says which is which.

A theme is presentation, so nothing about it is fatal: an unreadable file is
skipped, an unresolvable selection falls back to the built-in light theme, and
both are reported in the same dialog as hook failures at step 13.

---

## 6. Gotchas worth knowing

- **Order between toolsets is alphabetical**, because `build_tree()` sorts by label. Do not depend on it. If toolset A needs something toolset B produced, that something belongs in the application hook.
- **The hooks are a `gui_main()` guarantee.** Constructing `MainWindow(tree)` directly — as the tests do — falls back to lazy instantiation, and `on_startup()` methods are never called.
- **A `@tool` named `on_startup` stays a tool.** decoui checks for the tool marker first, so it is never called as a hook.
- **Logging needs a level.** decoui attaches its console handler to the root
  logger but does not change that logger's level, and an unconfigured root
  logger filters everything below WARNING. A tool that calls `logging.info()`
  produces nothing until the application has called `logging.basicConfig()`.
- **Eager instantiation is observable.** A toolset `__init__` with side effects (writing a file, printing) now runs at startup rather than on first click. This changed in `0.2.0`.
- **`store()` is safe in a hook, not in a signature default.** `init_db()` runs at step 4, before both hooks, but long after import time.

---

## 7. Decision table

| I want to… | Use |
|---|---|
| Hard-code a constant | Signature default |
| Use a value my module already read at import | Signature default |
| Open a connection every toolset needs | `gui_main(on_startup=...)` |
| Load a config file this toolset owns | `ToolSet.on_startup()` |
| Remember what the user picked last time | `ToolSet.on_startup()` + `store("ns").get(...)`, write back with `store("ns")[key] = ...` in the tool body |
| Recompute a form value every time the page opens | `@tool(defaults=...)` |
| Fetch something slow | Neither — put it in the tool body, where it gets a thread and a Stop button |
