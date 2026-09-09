"""Annotation scanning and ToolTree construction."""
from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, TypeAlias

from .assist import DEFAULT_DEBOUNCE_MS, validate_assist_config
from .decorators import _TOOLSET_ATTR, _TOOL_ATTR
from .types import F

#: Parameter name -> resolved annotation, as returned by get_type_hints().
HintMap: TypeAlias = dict[str, Any]


@dataclass
class ToolInfo:
    tool_id: str          # 'ClassName.method_name'
    method_name: str
    method: Any           # unbound function
    label: str
    description: str
    icon: str | None
    confirm: bool
    timeout: int | None
    placeholders: dict[str, str]
    params: list[ParamInfo]
    return_annotation: Any
    completions: dict[str, Any] = field(default_factory=dict)
    cascade: dict[str, Any] = field(default_factory=dict)
    defaults: Any = None
    completion_debounce_ms: int = DEFAULT_DEBOUNCE_MS
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class ParamInfo:
    name: str
    annotation: Any       # Annotated metadata stripped; the bare runtime type
    default: Any          # inspect.Parameter.empty if no default
    has_default: bool
    placeholder: str = ""
    label: str | None = None   # None falls back to the parameter name


@dataclass
class ToolSetInfo:
    cls: type
    label: str
    tags: list[str]
    icon: str | None
    description: str
    tools: list[ToolInfo] = field(default_factory=list)


def _find_field_meta(annotation: Any) -> F | None:
    """Return the first F() attached anywhere inside an annotation.

    The search recurses so metadata is still found when Annotated sits under
    another construct, as in ``Optional[Annotated[Path, F(...)]]``.

    Args:
        annotation: A type annotation retrieved with include_extras=True.

    Returns:
        The field metadata, or None when the annotation carries none.
    """
    for meta in getattr(annotation, "__metadata__", ()):
        if isinstance(meta, F):
            return meta
    for arg in typing.get_args(annotation):
        found = _find_field_meta(arg)
        if found is not None:
            return found
    return None


def _resolve_hints(method: Callable[..., Any]) -> tuple[HintMap, HintMap]:
    """Resolve a method's annotations, both stripped and with metadata kept.

    Two passes are used deliberately. The stripped pass is what ParamInfo
    stores, so widget selection and value conversion keep seeing the same bare
    types they always have, at any nesting depth. The include_extras pass is
    read only to look up F() metadata.

    Args:
        method: The unbound tool function.

    Returns:
        A (stripped, annotated) pair of name -> annotation mappings. Both fall
        back to raw __annotations__ when evaluation fails, in which case the
        annotated mapping is empty and no metadata is picked up.
    """
    try:
        return (
            typing.get_type_hints(method),
            typing.get_type_hints(method, include_extras=True),
        )
    except Exception:
        # Unresolvable forward reference: PEP 563 leaves the strings in place.
        return getattr(method, "__annotations__", {}), {}


def build_tree(*toolset_classes) -> list[ToolSetInfo]:
    """Scan classes decorated with @toolset and return a ToolTree."""
    tree: list[ToolSetInfo] = []

    for cls in toolset_classes:
        meta = getattr(cls, _TOOLSET_ATTR, None)
        if meta is None:
            raise ValueError(f"{cls} is not decorated with @toolset")

        ts = ToolSetInfo(
            cls=cls,
            label=meta["label"],
            tags=meta["tags"],
            icon=meta["icon"],
            description=meta["description"],
        )

        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            tool_meta = getattr(method, _TOOL_ATTR, None)
            if tool_meta is None:
                continue

            sig = inspect.signature(method)
            # get_type_hints evaluates stringified annotations (PEP 563 / Python 3.14)
            hints, annotated_hints = _resolve_hints(method)
            params: list[ParamInfo] = []

            placeholders = tool_meta["placeholders"]
            labels = tool_meta.get("labels", {})
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                annotation = hints.get(pname, inspect.Parameter.empty)
                meta = _find_field_meta(annotated_hints.get(pname))
                # The decorator wins over the annotation, so one tool can reword
                # a field it shares with others.
                label = labels.get(pname) or (meta.label if meta else None)
                placeholder = (
                    placeholders.get(pname)
                    or (meta.placeholder if meta else None)
                    or ""
                )
                params.append(ParamInfo(
                    name=pname,
                    annotation=annotation,
                    default=param.default,
                    has_default=(param.default is not inspect.Parameter.empty),
                    placeholder=placeholder,
                    label=label,
                ))

            return_ann = hints.get("return", None)

            completions = tool_meta.get("completions", {})
            cascade = tool_meta.get("cascade", {})
            defaults = tool_meta.get("defaults")
            validate_assist_config(
                tool_label=tool_meta["label"],
                cls=cls,
                params=params,
                completions=completions,
                cascade=cascade,
                defaults=defaults,
            )

            ts.tools.append(ToolInfo(
                tool_id=f"{cls.__name__}.{name}",
                method_name=name,
                method=method,
                label=tool_meta["label"],
                description=tool_meta["description"],
                icon=tool_meta["icon"],
                confirm=tool_meta["confirm"],
                timeout=tool_meta["timeout"],
                placeholders=tool_meta["placeholders"],
                params=params,
                return_annotation=return_ann,
                completions=completions,
                cascade=cascade,
                defaults=defaults,
                completion_debounce_ms=tool_meta.get(
                    "completion_debounce_ms", DEFAULT_DEBOUNCE_MS
                ),
                labels=labels,
            ))

        ts.tools.sort(key=lambda t: t.label.casefold())
        tree.append(ts)

    tree.sort(key=lambda s: s.label.casefold())
    return tree
