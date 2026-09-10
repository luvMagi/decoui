"""Collect per-tool help from the docstrings the tools already carry.

decoui reads the same docstring a developer writes for any other reason: the
summary line, the prose under it, and the ``Args:`` / ``Returns:`` / ``Raises:``
sections of Google style. Nothing has to be declared twice, and a tool that has
never heard of the Help panel still appears in it.

Only Google style is parsed. That is not a limitation in this codebase -- the
studio standard mandates it -- and it keeps decoui on its single runtime
dependency instead of pulling in a general docstring library.

The parser is deliberately forgiving: an unparseable docstring degrades to
"summary only" rather than raising. Help is presentation, and no tool should
become unusable because its prose is shaped oddly.
"""
from __future__ import annotations

import enum
import inspect
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

from .i18n import t

#: Section headers recognised at the top level of a Google-style docstring.
#: ``Args`` and ``Parameters`` are both accepted because the second is common
#: enough in the wild that rejecting it would silently drop a whole section.
_SECTION_NAMES = frozenset({
    "Args", "Arguments", "Parameters",
    "Returns", "Return",
    "Raises", "Raise", "Except", "Exceptions",
    "Yields", "Yield",
    "Attributes",
    "Note", "Notes",
    "Example", "Examples",
    "Warning", "Warnings",
    "See Also",
    "Todo",
})

#: A line that opens a section: ``Args:`` at zero indent, nothing after it.
_SECTION_RE = re.compile(r"^(?P<name>[A-Z][A-Za-z ]*):\s*$")

#: One entry inside an ``Args:`` block: ``name: text`` or ``name (type): text``.
_ARG_RE = re.compile(r"^(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<text>.*)$")


@dataclass(frozen=True)
class ParsedDocstring:
    """One docstring, split into the parts the Help panel renders.

    Attributes:
        summary: The first line. Empty when there is no docstring at all.
        description: Everything between the summary and the first section
            header, with blank lines preserved between paragraphs.
        args: Parameter name to its description, from ``Args:``.
        returns: The body of ``Returns:``.
        raises: The body of ``Raises:``.
    """

    summary: str = ""
    description: str = ""
    args: dict[str, str] = field(default_factory=dict)
    returns: str = ""
    raises: str = ""


def parse_docstring(doc: str | None) -> ParsedDocstring:
    """Split a Google-style docstring into summary, prose and sections.

    Args:
        doc: The raw ``__doc__``, or None. Indentation is normalised here, so
            callers may pass the attribute directly.

    Returns:
        The parsed parts. A None or blank docstring yields an empty result
        rather than an error.
    """
    if not doc or not doc.strip():
        return ParsedDocstring()

    lines = inspect.cleandoc(doc).splitlines()

    summary = lines[0].strip() if lines else ""
    body = lines[1:]

    prose: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in body:
        match = _SECTION_RE.match(line)
        if match and match.group("name") in _SECTION_NAMES:
            current = match.group("name")
            sections.setdefault(current, [])
            continue
        if current is None:
            prose.append(line)
        else:
            sections[current].append(line)

    args: dict[str, str] = {}
    for key in ("Args", "Arguments", "Parameters"):
        if key in sections:
            args = _parse_args(sections[key])
            break

    return ParsedDocstring(
        summary=summary,
        description="\n".join(prose).strip(),
        args=args,
        returns=_join_section(sections, ("Returns", "Return")),
        raises=_join_section(sections, ("Raises", "Raise", "Except", "Exceptions")),
    )


def _join_section(sections: dict[str, list[str]], names: tuple[str, ...]) -> str:
    """Return the first present section's text, dedented and stripped.

    Args:
        sections: Section name to its raw lines.
        names: Accepted spellings, in priority order.

    Returns:
        The section body, or an empty string when none of the names is present.
    """
    for name in names:
        if name in sections:
            return inspect.cleandoc("\n".join(sections[name])).strip()
    return ""


def _parse_args(lines: list[str]) -> dict[str, str]:
    """Parse an ``Args:`` block into one entry per parameter.

    An entry runs until the next line indented no further than the one that
    opened it, so a description may wrap over as many lines as it needs.

    Args:
        lines: The raw lines of the section, still indented.

    Returns:
        Parameter name to its description. Lines that do not open an entry and
        do not continue one are ignored rather than treated as an error.
    """
    args: dict[str, str] = {}
    current: str | None = None
    entry_indent = 0
    buffer: list[str] = []

    def flush() -> None:
        if current is not None:
            args[current] = " ".join(part.strip() for part in buffer if part.strip())

    for line in lines:
        if not line.strip():
            if current is not None:
                buffer.append("")
            continue
        indent = len(line) - len(line.lstrip())
        match = _ARG_RE.match(line.strip())
        # A new entry only starts at the block's own indent level; anything
        # deeper is a continuation, which is what lets a description wrap.
        if match and (current is None or indent <= entry_indent):
            flush()
            current = match.group("name").lstrip("*")
            entry_indent = indent
            buffer = [match.group("text")]
        elif current is not None:
            buffer.append(line)

    flush()
    return args


def type_name(annotation: Any) -> str:
    """Return a short, readable name for a parameter's annotation.

    Args:
        annotation: The bare runtime type stored on ParamInfo.

    Returns:
        A name fit to print in a table -- ``Path``, ``SortOrder``, ``list`` --
        or an empty string when the parameter is unannotated.
    """
    if annotation is inspect.Parameter.empty or annotation is None:
        return ""
    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return annotation.__name__
        if issubclass(annotation, pathlib.PurePath):
            return "Path"
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def default_text(param: Any) -> str:
    """Render a parameter's default for display.

    Args:
        param: A ParamInfo.

    Returns:
        The default as text, ``—`` when the parameter is required, and the
        member name for an Enum so the table matches the dropdown.
    """
    if not param.has_default:
        return "—"
    value = param.default
    if isinstance(value, enum.Enum):
        return value.name
    if value is None or value == "":
        return t("help.default_empty")
    return repr(value)


@dataclass(frozen=True)
class ParamHelp:
    """One row of a tool's parameter table.

    Attributes:
        name: The parameter name -- the key, not necessarily what the form shows.
        label: What the form actually labels this field.
        type_name: Short type name for display.
        default: Rendered default, or ``—`` when required.
        required: True when the form draws the red asterisk.
        text: Description from the docstring's ``Args:``, if it has one.
    """

    name: str
    label: str
    type_name: str
    default: str
    required: bool
    text: str


@dataclass(frozen=True)
class ToolHelp:
    """Everything the Help panel shows for one tool.

    Attributes:
        tool_id: Stable id, ``ClassName.method_name``.
        label: The tool's display name.
        summary: Docstring summary line, falling back to ``@tool(description=)``.
        description: Docstring prose under the summary. The detailed help that
            has no other home -- ``description=`` only ever carried the summary.
        params: One entry per parameter, in signature order.
        returns: Docstring ``Returns:`` text.
        raises: Docstring ``Raises:`` text.
    """

    tool_id: str
    label: str
    summary: str
    description: str
    params: list[ParamHelp]
    returns: str
    raises: str


@dataclass(frozen=True)
class ToolSetHelp:
    """One sidebar group in the Help panel.

    Attributes:
        set_id: Stable identity, the decorated class's name. Shares its shape
            with :attr:`ToolHelp.tool_id`, which is ``'ClassName.method'`` --
            so a group and its tools are addressed by the same scheme, and a
            cross-reference in a docstring can name either.
        label: Group name.
        summary: Class docstring summary line.
        description: Class docstring prose.
        tools: The group's tools, in the order build_tree sorted them.
    """

    set_id: str
    label: str
    summary: str
    description: str
    tools: list[ToolHelp]


def build_tool_help(tool_info: Any) -> ToolHelp:
    """Collect one tool's help from its docstring and declaration.

    Args:
        tool_info: A ToolInfo from the registry.

    Returns:
        The assembled help. A tool with no docstring still produces a usable
        entry: the summary falls back to ``@tool(description=)`` and the
        parameter table is built from the signature alone.
    """
    parsed = parse_docstring(getattr(tool_info.method, "__doc__", None))
    params = [
        ParamHelp(
            name=param.name,
            label=param.label or param.name,
            type_name=type_name(param.annotation),
            default=default_text(param),
            required=not param.has_default,
            text=parsed.args.get(param.name, ""),
        )
        for param in tool_info.params
    ]
    return ToolHelp(
        tool_id=tool_info.tool_id,
        label=tool_info.label,
        summary=parsed.summary or tool_info.description,
        description=parsed.description,
        params=params,
        returns=parsed.returns,
        raises=parsed.raises,
    )


def build_help(tree: list) -> list[ToolSetHelp]:
    """Collect help for every loaded toolset.

    Args:
        tree: The toolset tree from :func:`decoui.registry.build_tree`.

    Returns:
        One entry per toolset, in the order the tree already sorted them, so
        the Help panel and the sidebar agree.
    """
    result: list[ToolSetHelp] = []
    for toolset_info in tree:
        parsed = parse_docstring(getattr(toolset_info.cls, "__doc__", None))
        result.append(ToolSetHelp(
            set_id=toolset_info.cls.__name__,
            label=toolset_info.label,
            summary=parsed.summary,
            description=parsed.description,
            tools=[build_tool_help(t) for t in toolset_info.tools],
        ))
    return result
