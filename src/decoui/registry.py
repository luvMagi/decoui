"""Annotation scanning and ToolTree construction.

Everything the decorators recorded is interpreted here, once, at startup.
:func:`build_tree` walks the decorated classes, resolves each tool's
annotations, validates the declarations against the real signature, and returns
the tree the UI is built from.

Two consequences for tools:

* **This is where a bad declaration is reported.** A ``placeholders`` key that
  names no parameter, a ``completions`` callback method that does not exist, a
  non-str label -- all raise here, when the application starts, naming the tool
  and listing the parameters it does have. Nothing is checked at import time, so
  calling a tool method directly is never blocked by a form-text mistake.

* **This is where ``Annotated`` is stripped.** ParamInfo stores the bare runtime
  type, so widget selection and value conversion never see metadata. ``F``
  metadata is read out separately, in a second pass.

Sorting happens at the end: toolsets and their tools are ordered by label,
case-insensitively. The order classes are passed in does not survive.
"""
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
    """Everything the UI needs to render and run one @tool method.

    Built once at startup and then read-only. Field names mirror the ``@tool``
    arguments, except for the four at the top, which are derived.

    Attributes:
        tool_id: Stable identity, ``'ClassName.method_name'``. Used as the
            history key, so renaming a class or method orphans its past runs.
        method_name: The attribute name on the toolset class.
        method: The unbound function. Called as ``method(instance, **params)``.
        return_annotation: Captured but currently unused -- the GUI does not
            render return values.
    """

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
    on_cancel: Any = None


@dataclass
class ParamInfo:
    """One parameter of a tool, as the form builder sees it.

    Attributes:
        name: The parameter name, and the key used everywhere else -- in
            ``placeholders``, ``completions``, replayed history, and the params
            dict the method is finally called with.
        annotation: The bare runtime type. ``Annotated`` is stripped and
            ``Optional`` is left intact here; the widget builder unwraps it.
        default: The declared default, or ``inspect.Parameter.empty``.
        has_default: False marks the field required, which is what draws the red
            asterisk in the form. It does not stop the tool from running.
        placeholder: Already resolved through the decorator/F/empty chain.
        label: Already resolved through the decorator/F/parameter-name chain.
            None means fall back to ``name`` at render time.
    """

    name: str
    annotation: Any       # Annotated metadata stripped; the bare runtime type
    default: Any          # inspect.Parameter.empty if no default
    has_default: bool
    placeholder: str = ""
    label: str | None = None   # None falls back to the parameter name


@dataclass
class ToolSetInfo:
    """One @toolset class and the tools found on it.

    Attributes:
        cls: The decorated class itself. decoui instantiates it once, with no
            arguments, and keeps that single instance for the whole session.
        tags: Sidebar filter labels. Filtering hides the group; it does not
            unload it.
        tools: Sorted by label, case-insensitively.
    """

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
    """Scan classes decorated with @toolset and return a ToolTree.

    Args:
        *toolset_classes: Classes carrying @toolset metadata.

    Returns:
        One ToolSetInfo per class, sorted by label, each holding its tools
        sorted by label.

    Raises:
        ValueError: If a class is not decorated with @toolset, or a declaration
            names a parameter the method does not have.
        TypeError: If a declaration has an unusable type -- a non-str label, a
            completions spec on a numeric field, and so on.
        AttributeError: If a declaration names a method the class does not have.

    Note:
        Nothing here touches Qt, and no instance is created: this runs on plain
        classes. It is therefore safe to call from a test to assert that an
        application's declarations are consistent.
    """
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
            on_cancel = tool_meta.get("on_cancel")
            validate_assist_config(
                tool_label=tool_meta["label"],
                cls=cls,
                params=params,
                placeholders=placeholders,
                labels=labels,
                completions=completions,
                cascade=cascade,
                defaults=defaults,
                on_cancel=on_cancel,
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
                on_cancel=on_cancel,
            ))

        ts.tools.sort(key=lambda t: t.label.casefold())
        tree.append(ts)

    tree.sort(key=lambda s: s.label.casefold())
    return tree
