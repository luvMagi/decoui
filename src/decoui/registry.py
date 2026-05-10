"""Annotation scanning and ToolTree construction."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from .decorators import _TOOLSET_ATTR, _TOOL_ATTR


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


@dataclass
class ParamInfo:
    name: str
    annotation: Any
    default: Any          # inspect.Parameter.empty if no default
    has_default: bool
    placeholder: str = ""


@dataclass
class ToolSetInfo:
    cls: type
    label: str
    tags: list[str]
    icon: str | None
    description: str
    tools: list[ToolInfo] = field(default_factory=list)


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
            try:
                import typing
                hints = typing.get_type_hints(method)
            except Exception:
                hints = getattr(method, "__annotations__", {})
            params: list[ParamInfo] = []

            placeholders = tool_meta["placeholders"]
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                annotation = hints.get(pname, inspect.Parameter.empty)
                params.append(ParamInfo(
                    name=pname,
                    annotation=annotation,
                    default=param.default,
                    has_default=(param.default is not inspect.Parameter.empty),
                    placeholder=placeholders.get(pname, ""),
                ))

            return_ann = hints.get("return", None)

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
            ))

        tree.append(ts)

    return tree
