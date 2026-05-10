"""@toolset and @tool decorator definitions."""
from __future__ import annotations

from typing import Callable, TypeVar

_TOOLSET_ATTR = "__decoui_toolset__"
_TOOL_ATTR = "__decoui_tool__"

F = TypeVar("F", bound=Callable)


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
) -> Callable[[F], F]:
    """Method decorator that marks a method as a runnable tool.

    placeholders: per-parameter placeholder text, e.g. {"name": "Enter your name..."}
    """
    def decorator(fn: F) -> F:
        setattr(fn, _TOOL_ATTR, {
            "label": label,
            "description": description,
            "icon": icon,
            "confirm": confirm,
            "timeout": timeout,
            "placeholders": placeholders or {},
        })
        return fn
    return decorator
