"""Form assist: autocomplete candidates, cascading fill, and lazy defaults.

Three opt-in features declared on ``@tool``:

  completions  parameter -> candidate list or lookup callback (QCompleter popup)
  cascade      parameter -> callback returning values for other parameters
  defaults     lazily evaluated initial form values

Lookup and cascade callbacks run on a dedicated background thread pool so a slow
data source can never freeze the GUI or delay an actual tool run. Callbacks are
plain synchronous user code and must not touch Qt objects.

Writing the callbacks
---------------------

Each of the three accepts a **method name** (a string), a callable, or -- for
``completions`` -- a plain list. Prefer the method name: decorator arguments are
evaluated at import time, so a callable defined there cannot see ``self``, while
a named method is bound to the live instance when the page is built.

Arity is adapted, so declare only the arguments actually needed::

    completions / cascade   () | (value) | (value, form)
    defaults                () | (form)

``value`` is the parameter's current text; ``form`` is a snapshot of every
field as ``{name: value}``. A cascade returns ``{other_param: new_value}`` and
may name any subset of the form -- unknown names are reported as a warning
rather than raising.

Constraints worth knowing:

* Callbacks run **off the GUI thread**. Never create or touch a widget in one,
  and do not rely on their ordering relative to a tool run.
* Completion candidates are normalised: non-strings are coerced, blanks and
  duplicates dropped, and the list is truncated. Returning thousands of entries
  is safe but pointless.
* Completions only attach to text-like fields. Declaring them on a number,
  check box or dropdown is rejected when the application starts.
* A callback that raises does not break the form: the failure surfaces as a
  warning and the field is simply left alone.
* Cascades are suspended while a run is in progress and while history replay
  restores values, so they cannot overwrite what is being replayed.
"""
from __future__ import annotations

import inspect
import time
import traceback
from collections import OrderedDict
from typing import Any, Callable, Iterable

from PySide6.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    QStringListModel,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from .widget_builder import get_value, set_value, supports_completion

# ── Tunables ──────────────────────────────────────────────────────────────────

MAX_COMPLETION_ITEMS = 1000
MAX_CASCADE_DEPTH = 5
DEFAULT_DEBOUNCE_MS = 250
SLOW_CALLBACK_SECONDS = 5.0
WARNING_COOLDOWN_SECONDS = 10.0
_CACHE_SIZE = 32
_POOL_THREADS = 4

Form = dict[str, Any]
LookupCallback = Callable[[Any, Form], Any]

_pool: QThreadPool | None = None


def assist_pool() -> QThreadPool:
    """Return the thread pool used for assist callbacks, creating it on demand.

    The pool is deliberately separate from the global pool that runs tools, so a
    slow lookup cannot starve or delay an execution.

    Returns:
        A process-wide QThreadPool with a bounded thread count.
    """
    global _pool
    if _pool is None:
        _pool = QThreadPool()
        _pool.setMaxThreadCount(_POOL_THREADS)
    return _pool


# ── Task dispatch ─────────────────────────────────────────────────────────────

class _AssistSignals(QObject):
    """Signal carrier for _AssistTask (QRunnable cannot define signals)."""

    finished = Signal(int, object, float)   # (seq, result, elapsed seconds)
    failed = Signal(int, str)               # (seq, traceback text)


class _AssistTask(QRunnable):
    """Run one adapted assist callback and report the outcome by signal.

    Attributes:
        signals: Emitted from the worker thread; queued to the owning thread.
    """

    def __init__(self, callback: LookupCallback, value: Any, form: Form, seq: int) -> None:
        """Prepare a callback invocation.

        Args:
            callback: Two-argument callable produced by _adapt_lookup.
            value: Current text (completion) or committed value (cascade).
            form: Snapshot of every parameter's current widget value.
            seq: Request sequence number used to discard stale results.
        """
        super().__init__()
        self._callback = callback
        self._value = value
        self._form = form
        self._seq = seq
        self.signals = _AssistSignals()

    def run(self) -> None:
        """Invoke the callback, timing it and converting exceptions to a signal."""
        started = time.monotonic()
        try:
            result = self._callback(self._value, self._form)
        except Exception:
            self.signals.failed.emit(self._seq, traceback.format_exc())
            return
        self.signals.finished.emit(self._seq, result, time.monotonic() - started)


class AssistRunner:
    """Dispatch assist tasks to the shared background thread pool."""

    def submit(self, task: _AssistTask) -> None:
        """Queue a task for execution on a worker thread.

        Args:
            task: The prepared callback invocation.
        """
        assist_pool().start(task)


class InlineRunner(AssistRunner):
    """Run assist tasks synchronously on the calling thread.

    Used by tests to make completion and cascade behaviour deterministic without
    waiting on a real thread pool.
    """

    def submit(self, task: _AssistTask) -> None:
        """Execute the task immediately.

        Args:
            task: The prepared callback invocation.
        """
        task.run()


# ── Callback resolution ───────────────────────────────────────────────────────

def _positional_count(callback: Callable[..., Any]) -> int | None:
    """Return how many positional arguments a callable accepts.

    Args:
        callback: Any callable; bound methods do not count ``self``.

    Returns:
        The positional argument count, or None when the callable accepts a
        variable number and should be given the full argument list.
    """
    try:
        params = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        # Builtins and C extensions often have no introspectable signature.
        return None

    kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params.values()):
        return None
    return len([p for p in params.values() if p.kind in kinds])


def _adapt_lookup(callback: Callable[..., Any]) -> LookupCallback:
    """Wrap a 0-, 1-, or 2-argument lookup callback into a uniform call.

    Args:
        callback: A completion or cascade callback.

    Returns:
        A callable taking ``(value, form)`` regardless of the original arity.
    """
    count = _positional_count(callback)
    if count == 0:
        return lambda value, form: callback()
    if count == 1:
        return lambda value, form: callback(value)
    return lambda value, form: callback(value, form)


def _adapt_defaults(callback: Callable[..., Any]) -> Callable[[Form], Any]:
    """Wrap a 0- or 1-argument defaults callback into a uniform call.

    Args:
        callback: A callable returning a param name -> value mapping.

    Returns:
        A callable taking the current form snapshot.
    """
    count = _positional_count(callback)
    if count == 0:
        return lambda form: callback()
    return lambda form: callback(form)


def resolve_callback(spec: Any, instance: Any) -> LookupCallback:
    """Turn a callback spec into a bound two-argument callable.

    Args:
        spec: A callable, or the name of a method on the toolset class.
        instance: The live toolset instance, used to bind method names.

    Returns:
        A callable taking ``(value, form)``.

    Raises:
        AttributeError: If a method name does not exist on the instance.
        TypeError: If the resolved attribute is not callable.
    """
    target = getattr(instance, spec) if isinstance(spec, str) else spec
    if not callable(target):
        raise TypeError(f"Assist callback {spec!r} is not callable")
    return _adapt_lookup(target)


# ── Value helpers ─────────────────────────────────────────────────────────────

def read_form(widgets: dict[str, QWidget]) -> Form:
    """Snapshot every widget's current value.

    Args:
        widgets: Mapping of parameter name to its input widget.

    Returns:
        A plain dict copy; parameters whose value cannot be read (for example a
        dict field holding invalid JSON) map to None.
    """
    return {name: safe_get_value(widget) for name, widget in widgets.items()}


def safe_get_value(widget: QWidget) -> Any:
    """Read a widget value, returning None instead of raising.

    Args:
        widget: The input widget to read.

    Returns:
        The widget value, or None if parsing it failed.
    """
    try:
        return get_value(widget)
    except Exception:
        # A half-typed dict field raises while the user is still editing;
        # an unreadable value is reported as None rather than aborting.
        return None


def _values_equal(left: Any, right: Any) -> bool:
    """Compare two widget values, treating incomparable values as different.

    Args:
        left: Previously committed value.
        right: Current value.

    Returns:
        True when the values are equal.
    """
    try:
        return bool(left == right)
    except Exception:
        return False


def normalize_candidates(raw: Any) -> list[str]:
    """Convert a completion callback result into a clean candidate list.

    Non-string items are stringified, duplicates are dropped keeping first-seen
    order, and the result is truncated to MAX_COMPLETION_ITEMS.

    Args:
        raw: Whatever the callback returned.

    Returns:
        A de-duplicated list of candidate strings.

    Raises:
        TypeError: If the result is not iterable.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        # A bare string is a single candidate, not a sequence of characters.
        return [raw]
    if not isinstance(raw, Iterable):
        raise TypeError(f"completions callback returned {type(raw).__name__}, expected an iterable")

    seen: dict[str, None] = {}
    for item in raw:
        seen.setdefault(item if isinstance(item, str) else str(item), None)
        if len(seen) >= MAX_COMPLETION_ITEMS:
            break
    return list(seen)


# ── Warning throttle ──────────────────────────────────────────────────────────

class _WarningThrottle:
    """Collapse repeated warnings from the same source into one per window."""

    def __init__(self, cooldown: float = WARNING_COOLDOWN_SECONDS) -> None:
        """Create a throttle.

        Args:
            cooldown: Minimum seconds between two warnings sharing a key.
        """
        self._cooldown = cooldown
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        """Report whether a warning for this key should be emitted now.

        Args:
            key: Stable identifier for the warning source.

        Returns:
            True when the cooldown for this key has elapsed.
        """
        now = time.monotonic()
        previous = self._last.get(key)
        if previous is not None and now - previous < self._cooldown:
            return False
        self._last[key] = now
        return True


# ── Focus tracking ────────────────────────────────────────────────────────────

class _FocusFilter(QObject):
    """Report focus changes for widgets that need explicit focus handling."""

    focus_in = Signal(object)   # Qt.FocusReason
    focus_lost = Signal()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Emit focus signals, never consuming the event.

        Args:
            watched: The widget the filter is installed on.
            event: The intercepted event.

        Returns:
            Always False, so the widget still handles the event.
        """
        if event.type() == QEvent.Type.FocusIn:
            self.focus_in.emit(event.reason())
        elif event.type() == QEvent.Type.FocusOut:
            self.focus_lost.emit()
        return False


# Focus arriving for these reasons is not the user entering the field: the first
# is the completer popup itself opening or closing, which would otherwise make
# the popup reopen forever; the second is the whole window regaining focus.
_IGNORED_FOCUS_REASONS = frozenset({
    Qt.FocusReason.PopupFocusReason,
    Qt.FocusReason.ActiveWindowFocusReason,
})


# ── Completion ────────────────────────────────────────────────────────────────

class CompletionController(QObject):
    """Drive one parameter's completion popup from a static list or a callback.

    A static list is filtered by Qt itself. A callback is debounced, dispatched
    to a worker thread, and its result replaces the candidate model wholesale.
    """

    candidate_chosen = Signal(str)   # parameter name whose candidate was picked
    failed = Signal(str)             # warning message for the output console

    def __init__(
        self,
        param_name: str,
        line_edit: QLineEdit,
        spec: Any,
        instance: Any,
        form_reader: Callable[[], Form],
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        runner: AssistRunner | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Attach a completer to one line edit.

        Args:
            param_name: Name of the parameter this widget edits.
            line_edit: The line edit that receives the completer.
            spec: A static list/tuple, a callable, or a toolset method name.
            instance: Live toolset instance, used to bind method names.
            form_reader: Returns a snapshot of the whole form, called on the
                GUI thread before each dispatch.
            debounce_ms: Idle time before a dynamic lookup is dispatched.
            runner: Task dispatcher; defaults to the shared thread pool.
            parent: Qt parent object; defaults to the line edit, so the
                controller and its event filter live as long as the widget.
        """
        super().__init__(parent if parent is not None else line_edit)
        self._name = param_name
        self._line_edit = line_edit
        self._form_reader = form_reader
        self._runner = runner or AssistRunner()
        self._suspended = False
        self._seq = 0
        self._pending: dict[int, str] = {}
        self._cache: OrderedDict[str, list[str]] = OrderedDict()
        self._throttle = _WarningThrottle()

        self._model = QStringListModel([], self)
        self._completer = QCompleter(self._model, line_edit)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.activated.connect(self._on_activated)
        line_edit.setCompleter(self._completer)

        # Entering the field is itself a request for candidates, so the popup
        # opens without the user having to type first.
        self._focus_filter = _FocusFilter(self)
        self._focus_filter.focus_in.connect(self._on_focus_in)
        line_edit.installEventFilter(self._focus_filter)

        self._lookup: LookupCallback | None = None
        if isinstance(spec, (list, tuple)):
            self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            self._model.setStringList(normalize_candidates(spec))
        else:
            # The callback owns matching and ordering, so Qt must not filter.
            self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
            self._lookup = resolve_callback(spec, instance)
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(max(0, debounce_ms))
            self._timer.timeout.connect(self._dispatch)
            line_edit.textEdited.connect(self._on_text_edited)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def param_name(self) -> str:
        """Name of the parameter this controller completes."""
        return self._name

    @property
    def is_dynamic(self) -> bool:
        """True when candidates come from a callback rather than a static list."""
        return self._lookup is not None

    def candidates(self) -> list[str]:
        """Return the candidate list currently offered by the popup."""
        return list(self._model.stringList())

    def invalidate_cache(self) -> None:
        """Drop cached candidates because another parameter changed."""
        self._cache.clear()

    def set_suspended(self, suspended: bool) -> None:
        """Enable or disable lookups, e.g. while the tool is running.

        Args:
            suspended: True to ignore edits and cancel a pending dispatch.
        """
        self._suspended = suspended
        if suspended and self._lookup is not None:
            self._timer.stop()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _on_activated(self, _text: str) -> None:
        """Report that the user picked a candidate from the popup."""
        self.candidate_chosen.emit(self._name)

    def _on_focus_in(self, reason: Qt.FocusReason) -> None:
        """Offer the full candidate list as soon as the user enters the field.

        The list is deliberately unfiltered even when the field already holds a
        value: someone clicking into a filled field is usually there to pick a
        different value, and typing narrows the list again immediately.

        Args:
            reason: Why the widget received focus.
        """
        if self._suspended or reason in _IGNORED_FOCUS_REASONS:
            return
        if self._lookup is None:
            self.show_popup()
        else:
            self._dispatch(text="")

    def show_popup(self, prefix: str = "") -> None:
        """Open the completion popup.

        Args:
            prefix: Text to filter a static candidate list by. Ignored for a
                dynamic list, whose callback already decided what to offer.
        """
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount():
            self._completer.complete()

    def _on_text_edited(self, _text: str) -> None:
        """Restart the debounce timer after a keystroke."""
        if self._suspended:
            return
        if self._timer.interval() == 0:
            self._dispatch()
        else:
            self._timer.start()

    def _dispatch(self, text: str | None = None) -> None:
        """Serve a query from cache, or submit a lookup task.

        Args:
            text: Query text; defaults to whatever the field currently holds.
        """
        if self._suspended or self._lookup is None:
            return

        if text is None:
            text = self._line_edit.text()
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)
            self._apply(cached)
            return

        self._seq += 1
        self._pending[self._seq] = text
        task = _AssistTask(self._lookup, text, self._form_reader(), self._seq)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        self._runner.submit(task)

    def _on_finished(self, seq: int, result: Any, elapsed: float) -> None:
        """Apply a lookup result unless a newer request has superseded it.

        Args:
            seq: Sequence number of the completed request.
            result: Raw callback return value.
            elapsed: Callback duration in seconds.
        """
        text = self._pending.pop(seq, None)
        if text is None or seq != self._seq:
            return  # A newer keystroke already replaced this request.

        if elapsed > SLOW_CALLBACK_SECONDS and self._throttle.allow(f"slow:{self._name}"):
            self.failed.emit(
                f"completions['{self._name}'] took {elapsed:.1f}s; "
                f"consider narrowing the candidate set."
            )

        try:
            items = normalize_candidates(result)
        except TypeError as exc:
            self._warn(f"completions['{self._name}'] returned an invalid result: {exc}")
            return

        self._cache[text] = items
        self._cache.move_to_end(text)
        while len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)
        self._apply(items)

    def _on_failed(self, seq: int, message: str) -> None:
        """Report a raised lookup callback without touching the popup.

        Args:
            seq: Sequence number of the failed request.
            message: Formatted traceback.
        """
        self._pending.pop(seq, None)
        self._warn(f"completions['{self._name}'] raised:\n{message}")

    def _apply(self, items: list[str]) -> None:
        """Replace the candidate model and show or hide the popup.

        Args:
            items: Normalized candidate strings.
        """
        self._model.setStringList(items)
        if not items:
            self._completer.popup().hide()
            return
        if self._line_edit.hasFocus():
            self.show_popup()

    def _warn(self, message: str) -> None:
        """Emit a throttled warning for the output console.

        Args:
            message: Human-readable warning text.
        """
        if self._throttle.allow(f"error:{self._name}"):
            self.failed.emit(message)


# ── Cascade ───────────────────────────────────────────────────────────────────

class CascadeController(QObject):
    """Detect parameter commits and apply cascading fill for a whole form.

    Commit detection is wired for every widget, because the form snapshot passed
    to lookup callbacks becomes stale on any change. Only parameters declared in
    ``cascade`` dispatch a callback.
    """

    committed = Signal(str)          # parameter name whose value was committed
    applied = Signal(str, list)      # (source name, target names written)
    failed = Signal(str)             # warning message for the output console

    def __init__(
        self,
        tool_info: Any,
        widgets: dict[str, QWidget],
        instance: Any,
        runner: AssistRunner | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Wire commit detection and resolve cascade callbacks.

        Args:
            tool_info: The ToolInfo whose ``cascade`` map is used.
            widgets: Mapping of parameter name to its input widget.
            instance: Live toolset instance, used to bind method names.
            runner: Task dispatcher; defaults to the shared thread pool.
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._widgets = widgets
        self._runner = runner or AssistRunner()
        self._sources = {
            name: resolve_callback(spec, instance)
            for name, spec in tool_info.cascade.items()
            if name in widgets
        }
        self._last = read_form(widgets)
        self._suspended = False
        self._applying = False
        self._seq = 0
        self._latest: dict[str, int] = {}
        self._pending: dict[int, tuple[str, int, frozenset[str]]] = {}
        self._filters: list[_FocusFilter] = []
        self._throttle = _WarningThrottle()
        self._wire()

    # ── Public API ────────────────────────────────────────────────────────────

    def notify_commit(self, name: str) -> None:
        """Handle a committed parameter value, dispatching a cascade if declared.

        Does nothing when the value is unchanged since the last commit, so
        tabbing through an untouched field never triggers a lookup.

        Args:
            name: Parameter name whose widget was committed.
        """
        if self._suspended or self._applying:
            return
        widget = self._widgets.get(name)
        if widget is None:
            return

        value = safe_get_value(widget)
        if _values_equal(value, self._last.get(name)):
            return

        self._last[name] = value
        self.committed.emit(name)
        self._dispatch(name, value, depth=0, visited=frozenset())

    def sync_values(self) -> None:
        """Re-read every widget as the new commit baseline.

        Called after a programmatic bulk write (Replay, defaults) so the restored
        values are not mistaken for user edits later.
        """
        self._last = read_form(self._widgets)

    def set_suspended(self, suspended: bool) -> None:
        """Enable or disable cascade propagation.

        Args:
            suspended: True while the tool runs or a bulk restore is in progress.
        """
        self._suspended = suspended

    # ── Wiring ────────────────────────────────────────────────────────────────

    def _wire(self) -> None:
        """Connect a commit signal for every widget in the form."""
        for name, widget in self._widgets.items():
            self._connect_commit(name, widget)

    def _connect_commit(self, name: str, widget: QWidget) -> None:
        """Connect the commit signal appropriate for one widget type.

        Args:
            name: Parameter name.
            widget: The parameter's input widget.
        """
        def on_commit(*_args: Any) -> None:
            """Forward a widget commit, discarding whatever the signal carried.

            Args:
                *_args: Signal payload; ignored because the parameter name is
                    captured from the enclosing scope and the current value is
                    read back from the form.
            """
            self.notify_commit(name)

        # _PathWidget exposes an explicit commit signal covering both the inner
        # line edit and the file/folder dialogs.
        committed_signal = getattr(widget, "committed", None)
        if committed_signal is not None and hasattr(committed_signal, "connect"):
            committed_signal.connect(on_commit)
            return

        if isinstance(widget, QLineEdit):
            widget.editingFinished.connect(on_commit)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(on_commit)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(on_commit)
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.editingFinished.connect(on_commit)
        elif isinstance(widget, QTextEdit):
            focus_filter = _FocusFilter(self)
            focus_filter.focus_lost.connect(on_commit)
            widget.installEventFilter(focus_filter)
            self._filters.append(focus_filter)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, name: str, value: Any, depth: int, visited: frozenset[str]) -> None:
        """Submit the cascade callback for one source parameter.

        Args:
            name: Source parameter name.
            value: Its committed value.
            depth: Propagation depth, 0 for a user-initiated commit.
            visited: Sources already handled in this propagation pass.
        """
        callback = self._sources.get(name)
        if callback is None:
            return

        self._seq += 1
        self._latest[name] = self._seq
        self._pending[self._seq] = (name, depth, visited | {name})
        task = _AssistTask(callback, value, read_form(self._widgets), self._seq)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        self._runner.submit(task)

    def _on_finished(self, seq: int, result: Any, elapsed: float) -> None:
        """Apply a cascade result unless a newer commit has superseded it.

        Args:
            seq: Sequence number of the completed request.
            result: Raw callback return value.
            elapsed: Callback duration in seconds.
        """
        context = self._pending.pop(seq, None)
        if context is None:
            return
        name, depth, visited = context
        if self._latest.get(name) != seq:
            return  # A newer commit on the same source already won.

        if elapsed > SLOW_CALLBACK_SECONDS and self._throttle.allow(f"slow:{name}"):
            self.failed.emit(
                f"cascade['{name}'] took {elapsed:.1f}s; a cascade should be a fast lookup."
            )

        self._apply(name, result, depth, visited)

    def _on_failed(self, seq: int, message: str) -> None:
        """Report a raised cascade callback without writing any target.

        Args:
            seq: Sequence number of the failed request.
            message: Formatted traceback.
        """
        context = self._pending.pop(seq, None)
        name = context[0] if context is not None else "?"
        self._warn(name, f"cascade['{name}'] raised:\n{message}")

    def _apply(self, source: str, updates: Any, depth: int, visited: frozenset[str]) -> None:
        """Write cascade targets and continue the propagation chain.

        Args:
            source: Parameter that triggered this cascade.
            updates: Raw callback result, expected to be a param -> value dict.
            depth: Propagation depth of this cascade.
            visited: Sources already handled in this propagation pass.
        """
        if updates is None:
            return
        if not isinstance(updates, dict):
            self._warn(
                source,
                f"cascade['{source}'] returned {type(updates).__name__}, expected a dict.",
            )
            return

        written = self._write_targets(source, updates)
        if written:
            self.applied.emit(source, written)

        chained = [name for name in written if name in self._sources and name not in visited]
        if not chained:
            return
        if depth + 1 >= MAX_CASCADE_DEPTH:
            self._warn(
                source,
                f"cascade chain from '{source}' exceeded {MAX_CASCADE_DEPTH} levels; "
                f"stopped before {', '.join(chained)}.",
            )
            return
        for name in chained:
            self._dispatch(name, self._last[name], depth + 1, visited)

    def _write_targets(self, source: str, updates: dict[str, Any]) -> list[str]:
        """Write each target value into its widget.

        Widget signals are suppressed during the write, so chaining is driven
        explicitly rather than by programmatic value changes.

        Args:
            source: Parameter that triggered this cascade.
            updates: Mapping of target parameter name to new value.

        Returns:
            Names of the targets that were written successfully.
        """
        written: list[str] = []
        self._applying = True
        try:
            for target, value in updates.items():
                if target == source:
                    continue  # A cascade never re-triggers itself.
                widget = self._widgets.get(target)
                if widget is None:
                    self._warn(
                        source,
                        f"cascade['{source}'] returned unknown parameter '{target}'; ignored.",
                    )
                    continue
                try:
                    set_value(widget, value)
                except Exception as exc:
                    self._warn(
                        source,
                        f"cascade['{source}'] could not set '{target}' to {value!r}: {exc}",
                    )
                    continue
                self._last[target] = safe_get_value(widget)
                written.append(target)
        finally:
            self._applying = False
        return written

    def _warn(self, key: str, message: str) -> None:
        """Emit a throttled warning for the output console.

        Args:
            key: Source parameter name, used as the throttle key.
            message: Human-readable warning text.
        """
        if self._throttle.allow(f"error:{key}"):
            self.failed.emit(message)


# ── Defaults ──────────────────────────────────────────────────────────────────

def resolve_defaults(spec: Any, instance: Any, form: Form) -> Form:
    """Evaluate a tool's ``defaults`` spec into a parameter -> value mapping.

    Args:
        spec: A dict, a callable returning a dict, or a toolset method name.
        instance: Live toolset instance, used to bind method names.
        form: Snapshot of the form as built from signature defaults.

    Returns:
        The mapping to apply, empty when the spec yields nothing.

    Raises:
        TypeError: If the spec or its result is not a mapping.
        AttributeError: If a method name does not exist on the instance.
    """
    if not spec:
        return {}
    if isinstance(spec, dict):
        return dict(spec)

    target = getattr(instance, spec) if isinstance(spec, str) else spec
    if not callable(target):
        raise TypeError(f"defaults spec {spec!r} is neither a dict nor callable")

    result = _adapt_defaults(target)(form)
    if result is None:
        return {}
    if not isinstance(result, dict):
        raise TypeError(f"defaults callable returned {type(result).__name__}, expected a dict")
    return result


def apply_defaults(widgets: dict[str, QWidget], values: Form) -> list[str]:
    """Write default values into the form, skipping unknown parameters.

    Args:
        widgets: Mapping of parameter name to its input widget.
        values: Parameter name -> value mapping to apply.

    Returns:
        Names of parameters that could not be applied.
    """
    problems: list[str] = []
    for name, value in values.items():
        widget = widgets.get(name)
        if widget is None:
            problems.append(f"unknown parameter '{name}'")
            continue
        try:
            set_value(widget, value)
        except Exception as exc:
            problems.append(f"'{name}' = {value!r} ({exc})")
    return problems


# ── Startup validation ────────────────────────────────────────────────────────

def validate_assist_config(
    tool_label: str,
    cls: type,
    params: list[Any],
    *,
    placeholders: dict[str, str],
    labels: dict[str, str],
    completions: dict[str, Any],
    cascade: dict[str, Any],
    defaults: Any,
    on_cancel: Any = None,
) -> None:
    """Validate assist declarations against a tool's signature.

    Args:
        tool_label: The tool's display label, used in error messages.
        cls: The toolset class, used to check method-name specs.
        params: The tool's ParamInfo list.
        placeholders: The declared placeholder text map.
        labels: The declared form label map.
        completions: The declared completions map.
        cascade: The declared cascade map.
        defaults: The declared defaults spec.
        on_cancel: The declared cancel-cleanup spec, if any.

    Raises:
        ValueError: If a key does not name a parameter of the tool.
        TypeError: If a spec has an unsupported type, targets an unsupported
            widget, or a placeholder/label value is not a str.
        AttributeError: If a method-name spec does not exist on the class.
    """
    known = {param.name: param for param in params}
    available = ", ".join(known) or "(none)"

    # Text maps first: a mistyped key here used to fail silently, which is the
    # one failure mode a form author cannot see.
    for where, texts in (("placeholders", placeholders), ("labels", labels)):
        for name, text in texts.items():
            if name not in known:
                raise ValueError(
                    f"@tool('{tool_label}') {where} references unknown parameter "
                    f"'{name}'; available: {available}"
                )
            if not isinstance(text, str):
                raise TypeError(
                    f"@tool('{tool_label}') {where}['{name}'] must be str, "
                    f"got {type(text).__name__}"
                )

    for name, spec in completions.items():
        if name not in known:
            raise ValueError(
                f"@tool('{tool_label}') completions references unknown parameter "
                f"'{name}'; available: {available}"
            )
        if not supports_completion(known[name].annotation):
            raise TypeError(
                f"@tool('{tool_label}') completions['{name}'] targets a "
                f"{_annotation_name(known[name].annotation)} parameter; completions "
                f"support str and pathlib.Path only"
            )
        if isinstance(spec, (list, tuple)):
            continue
        _check_callable_spec(
            tool_label, cls, f"completions['{name}']", spec,
            allowed="a list, a callable, or a method name",
        )

    for name, spec in cascade.items():
        if name not in known:
            raise ValueError(
                f"@tool('{tool_label}') cascade references unknown parameter "
                f"'{name}'; available: {available}"
            )
        _check_callable_spec(tool_label, cls, f"cascade['{name}']", spec)

    if on_cancel is not None:
        _check_callable_spec(tool_label, cls, "on_cancel", on_cancel)

    if not defaults:
        return
    if isinstance(defaults, dict):
        for name in defaults:
            if name not in known:
                raise ValueError(
                    f"@tool('{tool_label}') defaults references unknown parameter "
                    f"'{name}'; available: {available}"
                )
        return
    _check_callable_spec(
        tool_label, cls, "defaults", defaults,
        allowed="a dict, a callable, or a method name",
    )


def _check_callable_spec(
    tool_label: str, cls: type, where: str, spec: Any, allowed: str = "a callable or a method name"
) -> None:
    """Verify that a callback spec is callable or names a class method.

    Args:
        tool_label: The tool's display label, used in error messages.
        cls: The toolset class the method name is looked up on.
        where: Human-readable location, e.g. ``cascade['service']``.
        spec: The declared spec.
        allowed: What the caller accepts, quoted back in the TypeError. Only
            ``completions`` also takes a plain list, so the default omits it.

    Raises:
        TypeError: If the spec is neither a string nor callable.
        AttributeError: If the named method does not exist on the class.
    """
    if isinstance(spec, str):
        target = getattr(cls, spec, None)
        if target is None:
            raise AttributeError(
                f"@tool('{tool_label}') {where} names method '{spec}', "
                f"which does not exist on {cls.__name__}"
            )
        if not callable(target):
            raise TypeError(
                f"@tool('{tool_label}') {where} names '{spec}' on {cls.__name__}, "
                f"which is not callable"
            )
        return
    if not callable(spec):
        raise TypeError(
            f"@tool('{tool_label}') {where} must be {allowed}; "
            f"got {type(spec).__name__}"
        )


def _annotation_name(annotation: Any) -> str:
    """Return a short readable name for a type annotation.

    Args:
        annotation: The parameter annotation.

    Returns:
        The type name, or the repr for non-class annotations.
    """
    return getattr(annotation, "__name__", None) or repr(annotation)
