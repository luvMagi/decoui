"""@toolset and @tool decorator definitions."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from .assist import DEFAULT_DEBOUNCE_MS

_TOOLSET_ATTR = "__decoui_toolset__"
_TOOL_ATTR = "__decoui_tool__"

_Fn = TypeVar("_Fn", bound=Callable)


def toolset(
    label: str,
    tags: list[str] | None = None,
    icon: str | None = None,
    description: str = "",
) -> Callable:
    """Class decorator that marks a class as a decoui ToolSet."""
    def decorator(cls):
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
) -> Callable[[_Fn], _Fn]:
    """Method decorator that marks a method as a runnable tool.

    Args:
        label: Tool display name.
        description: Shown in a bordered box below the title.
        icon: Reserved for a future icon lookup.
        confirm: Show a Yes/No dialog before running.
        timeout: Execution timeout in seconds, or None for unlimited.
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

    Returns:
        The original function, tagged with decoui tool metadata.

    Note:
        Every argument here is evaluated at import time, when no toolset
        instance exists -- ``defaults={"env": self.config["env"]}`` cannot work.
        Pass the name of a method instead: decoui binds it to the instance when
        the tool page is built, so the method body reads ``self`` at call time,
        after __init__ and on_startup() have run. This applies to
        ``completions``, ``cascade`` and ``defaults`` alike.
        See docs/startup-lifecycle.md.
    """
    def decorator(fn: _Fn) -> _Fn:
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
        })
        return fn
    return decorator
