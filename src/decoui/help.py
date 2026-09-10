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

A tool may also point at a Markdown file -- ``@tool(help="deploy.md")`` -- when
its help outgrows a docstring or wants translating. The file supplies the prose
and nothing else; see :func:`resolve_help_file` for where it is looked for and
:func:`build_tool_help` for what it does and does not replace.
"""
from __future__ import annotations

import enum
import inspect
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from .i18n import DEFAULT_LANGUAGE, active_language, t

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


def resolve_help_file(
    cls: type, name: str, language: str | None = None
) -> pathlib.Path | None:
    """Find the Markdown file a ``@tool(help=...)`` names.

    The search is rooted at the directory of the module ``cls`` is defined in,
    not at the working directory or at any configured path: help ships with the
    code it documents, and an application installed as a wheel has no other
    stable place to have put it.

    ``name`` is a relative path, and decoui's only contribution to it is to
    insert a language directory before the file. For ``help="doc/deploy.md"``,
    three locations are tried in this order::

        <module_dir>/doc/<language>/deploy.md
        <module_dir>/doc/<DEFAULT_LANGUAGE>/deploy.md
        <module_dir>/doc/deploy.md

    The first two are the same per-language fallback
    :func:`decoui.guide.guide_pages` uses, so translating a tool's help works
    the way translating decoui's own pages does. The third is for an application
    that has help but only one language, which should not have to make an ``en``
    directory to say so.

    The directory is the author's to name rather than fixed at ``help/``,
    because a fixed name is one an application may already have taken -- decoui
    itself could not use its own convention, having a :mod:`decoui.help` module
    sitting exactly where the directory would go.

    Args:
        cls: The toolset class, whose module locates the search.
        name: The relative path as written in the decorator. It is confined to
            the module's directory: a name that climbs out of it with ``..``,
            or that is absolute, is refused rather than followed.
        language: Language code, or None to follow the running language.

    Returns:
        The first path that exists, or None. Missing is not an error: the
        docstring is still there, and a help page that quietly falls back is a
        better failure than an application that will not start.
    """
    module = sys.modules.get(cls.__module__)
    origin = getattr(module, "__file__", None)
    if origin is None:
        return None

    root = pathlib.Path(origin).resolve().parent
    relative = pathlib.PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        return None

    parent, filename = relative.parent, relative.name
    wanted = language or active_language()
    candidates = (
        root / parent / wanted / filename,
        root / parent / DEFAULT_LANGUAGE / filename,
        root / parent / filename,
    )
    for candidate in candidates:
        # Resolved before the containment check: a symlink pointing out of the
        # tree is the same escape as "..", just spelled differently.
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.is_relative_to(root):
            return resolved
    return None


def _help_file_text(cls: type, name: str) -> str:
    """Read a tool's help file, or return nothing when it cannot be read.

    Args:
        cls: The toolset class the file is looked up beside.
        name: The file name from the decorator.

    Returns:
        The file's text, or ``""`` when there is no such file or it cannot be
        decoded. Both are reported the same way on purpose -- this runs while
        the help panel is being built, where the only useful behaviour is to
        fall back to the docstring.
    """
    path = resolve_help_file(cls, name)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def build_tool_help(tool_info: Any, cls: type | None = None) -> ToolHelp:
    """Collect one tool's help from its docstring and declaration.

    Args:
        tool_info: A ToolInfo from the registry.
        cls: The toolset class the tool is defined on, needed to locate a
            ``help=`` file. None skips the file lookup, which is what a caller
            with only a ToolInfo in hand can do.

    Returns:
        The assembled help. A tool with no docstring still produces a usable
        entry: the summary falls back to ``@tool(description=)`` and the
        parameter table is built from the signature alone.

    Note:
        A ``help=`` file replaces ``description`` -- the prose -- and nothing
        else. The summary stays the docstring's first line because it is also
        the tool's one-line entry in the contents table, and the parameter,
        Returns and Raises sections stay the docstring's because they describe
        the signature: a file sitting beside the module cannot be checked
        against the code, and help that silently disagrees with the form on
        screen is worse than help that is merely brief.
    """
    parsed = parse_docstring(getattr(tool_info.method, "__doc__", None))
    description = parsed.description
    if cls is not None and getattr(tool_info, "help", None):
        description = _help_file_text(cls, tool_info.help) or description
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
        description=description,
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
            tools=[
                build_tool_help(t, toolset_info.cls)
                for t in toolset_info.tools
            ],
        ))
    return result
