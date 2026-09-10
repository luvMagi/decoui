"""The two decorators that turn a plain class into a decoui application.

Both decorators are **non-invasive**: they call ``setattr`` on the class or the
function and hand the original object straight back. There is no wrapper, no
base class and no descriptor. Consequences worth relying on:

* ``DatabaseTools().restore(path)`` behaves exactly as it would without decoui,
  which is how tools are meant to be tested -- no Qt, no event loop, no GUI.
* ``@tool`` never changes the signature, so introspection tools, type checkers
  and other decorators stacked below it keep working.
* Nothing here validates anything. Every argument is checked later, in
  :func:`decoui.registry.build_tree`, when the application starts. That timing
  is deliberate: a mistyped ``placeholders`` key must not stop a direct call.

The one thing to keep in mind while writing tools: **everything passed to these
decorators is evaluated at import time**, when no instance exists yet. Anything
that needs ``self`` must be passed as a method *name* (a string), which decoui
binds to the instance once it has been created.
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from .assist import DEFAULT_DEBOUNCE_MS

# Attribute names the metadata is parked under. Private by convention; the
# registry is the only reader. A class or function is "a decoui thing" precisely
# when it carries one of these.
_TOOLSET_ATTR = "__decoui_toolset__"
_TOOL_ATTR = "__decoui_tool__"

_Fn = TypeVar("_Fn", bound=Callable)


def toolset(
    label: str,
    tags: list[str] | None = None,
    icon: str | None = None,
    description: str = "",
) -> Callable:
    """Class decorator that marks a class as a decoui ToolSet.

    One decorated class becomes one group in the sidebar, holding every ``@tool``
    method it defines. decoui instantiates it **once**, at startup, with no
    arguments -- so ``__init__`` must be callable as ``cls()``.

    Args:
        label: Group name shown in the sidebar.
        tags: Labels for the tag bar above the sidebar. Selecting tags hides
            every group that does not carry *all* of them (the filter is an
            AND, not an OR). Hiding is presentation only: the toolset is still
            instantiated and its tools still run from history replay.
        icon: Reserved. Nothing reads it yet.
        description: Free text. Currently unused for toolsets; the per-tool
            ``description`` is the one that reaches the screen.

    Returns:
        The same class, tagged with decoui toolset metadata.

    Example:
        @toolset(label="Database", tags=["ops"])
        class DatabaseTools:

            def __init__(self) -> None:
                self.dsn = os.environ["DSN"]

            def on_startup(self) -> None:
                # Optional. Runs after __init__, before the window appears.
                self.catalog = load_catalog()

    Note:
        Methods without ``@tool`` are ordinary methods: use them for helpers, and
        for the callbacks named by ``completions`` / ``cascade`` / ``defaults`` /
        ``on_cancel``.

        A failure in ``__init__`` or ``on_startup()`` does not abort startup. The
        application collects it, reports every failure in one dialog, and drops
        only the toolsets that could not be built. See
        :func:`decoui.runner.gui_main`.
    """
    def decorator(cls):
        """Attach the toolset metadata and return the class untouched.

        Args:
            cls: The class being decorated.

        Returns:
            The same class object -- no wrapper, no subclass.
        """
        setattr(cls, _TOOLSET_ATTR, {
            "label": label,
            "tags": tags or [],
            "icon": icon,
            "description": description,
        })
        return cls
    return decorator


def tool(
    label: str,
    description: str = "",
    icon: str | None = None,
    confirm: bool = False,
    timeout: int | None = None,
    placeholders: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    completions: dict[str, Any] | None = None,
    cascade: dict[str, Any] | None = None,
    defaults: Any = None,
    completion_debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    on_cancel: Any = None,
) -> Callable[[_Fn], _Fn]:
    """Method decorator that marks a method as a runnable tool.

    One decorated method becomes one page: a form built from the parameter
    annotations, a Run button, an output console and a history link. The method
    itself runs on a worker thread when Run is pressed.

    The method **must** be an instance method -- ``self`` first. A missing
    ``self`` is reported as a TypeError when the tool is run, not at import.

    Args:
        label: Tool display name, and the key used in every error message
            raised while validating the arguments below.
        description: Shown in a bordered box below the title.
        icon: Reserved for a future icon lookup. Nothing reads it yet.
        confirm: Show a Yes/No dialog before running. Declare it on anything
            destructive: it is greppable, so ``grep -r "confirm=True"`` gives an
            audit of the dangerous surface of an application.
        timeout: Execution timeout in seconds, or None for unlimited. On expiry
            decoui cancels the run exactly as the Stop button does -- including
            the ``on_cancel`` hook -- and logs a WARNING line.
        placeholders: Per-parameter placeholder text,
            e.g. ``{"name": "Enter your name..."}``. Overrides any placeholder
            carried by an ``Annotated[..., F(...)]`` annotation.
        labels: Per-parameter form label, e.g. ``{"archive": "Dump file"}``.
            Overrides any label carried by an ``Annotated[..., F(...)]``
            annotation. Falls back to the parameter name.
        completions: Per-parameter autocomplete source. Each value is a static
            list of candidates, a callable ``(text, form) -> Iterable[str]``, or
            the name of a method on the toolset class.
        cascade: Per-parameter change handler. Each value is a callable
            ``(value, form) -> dict`` mapping other parameter names to values,
            or the name of a method on the toolset class. Fires when the
            parameter's value is committed.
        defaults: Initial form values, evaluated when the tool page is opened
            rather than at import time. Either a dict, a callable returning one,
            or the name of a method on the toolset class. For data loaded once
            at startup, prefer a ToolSet.on_startup() method plus a method name
            here; see docs/startup-lifecycle.md.
        completion_debounce_ms: Idle time after the last keystroke before a
            dynamic completions callback runs. 0 dispatches on every keystroke.
        on_cancel: Cleanup to run when the user presses Stop or the timeout
            fires. Either a callable taking no arguments, or the name of a
            method on the toolset class.

            Declare this whenever the tool starts something the interpreter
            cannot interrupt -- a subprocess above all. Cancellation works by
            injecting an exception into the worker thread, and that exception
            is only raised at a Python bytecode boundary: a thread sitting in
            proc.wait() does not see it, and its finally block does not run,
            until the child exits on its own. The hook runs on the GUI thread
            while the worker is still blocked, which is the only moment
            anything can terminate that child.

            It therefore runs concurrently with the tool body. Keep it to
            idempotent interruption (terminate, close, cancel), keep it fast --
            it blocks the GUI -- and tolerate state that does not exist yet,
            since Stop may be pressed before the tool assigns it:
            ``proc = getattr(self, "_proc", None)``.

    Returns:
        The original function, tagged with decoui tool metadata.

    Example:
        @tool(
            label="Restore",
            description="Restore a dump into the target schema.",
            confirm=True,
            timeout=1800,
            labels={"archive": "Dump file"},
            completions={"schema": "list_schemas"},   # method name on the class
            on_cancel="stop",                         # method name on the class
        )
        def restore(self, archive: Path, schema: str, dry_run: bool = False) -> None:
            ...

    Note:
        Every argument here is evaluated at import time, when no toolset
        instance exists -- ``defaults={"env": self.config["env"]}`` cannot work.
        Pass the name of a method instead: decoui binds it to the instance when
        the tool page is built, so the method body reads ``self`` at call time,
        after __init__ and on_startup() have run. This applies to
        ``completions``, ``cascade``, ``defaults`` and ``on_cancel`` alike.
        See docs/startup-lifecycle.md.

        Keys in ``placeholders``, ``labels``, ``completions``, ``cascade`` and
        ``defaults`` must name real parameters of the method, and method names
        must exist on the class. Both are checked when the application starts,
        and a mistake raises there rather than failing silently. Nothing is
        checked at import time, so a direct call is never blocked by a typo in
        form text.

        The return value is **not** shown in the GUI. It is serialised into the
        run's history record, nothing more. Anything the user must see goes
        through ``print()``, ``logging`` or :func:`decoui.progress`.
    """
    def decorator(fn: _Fn) -> _Fn:
        """Attach the tool metadata and return the function untouched.

        Args:
            fn: The method being decorated.

        Returns:
            The same function object, so the method stays directly callable.
        """
        # Stored verbatim; the registry reads this dict and is the only place
        # any of it is interpreted or validated.
        setattr(fn, _TOOL_ATTR, {
            "label": label,
            "description": description,
            "icon": icon,
            "confirm": confirm,
            "timeout": timeout,
            "placeholders": placeholders or {},
            "labels": labels or {},
            "completions": completions or {},
            "cascade": cascade or {},
            "defaults": defaults,
            "completion_debounce_ms": completion_debounce_ms,
            "on_cancel": on_cancel,
        })
        return fn
    return decorator
