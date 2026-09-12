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

Order is decided at the end, by the ``order`` argument. The default,
``"declaration"``, is the order the source reads in: toolsets in the order they
were passed to :func:`~decoui.runner.gui_main` (or discovered), tools in the
order their ``def`` statements appear in the class body. ``"label"`` sorts both
alphabetically, case-insensitively, and is what decoui did unconditionally up to
v1.0.0.

Declaration order is the default because a class body is something the author
controls and can reorder; an alphabetical sidebar is not, and it scatters tools
that belong together as soon as one is renamed.
"""
from __future__ import annotations

import inspect
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, TypeAlias

from .assist import DEFAULT_DEBOUNCE_MS, validate_assist_config
from .decorators import _TOOLSET_ATTR, _TOOL_ATTR
from .tool_i18n import param_text, translated
from .types import F

#: Parameter name -> resolved annotation, as returned by get_type_hints().
HintMap: TypeAlias = dict[str, Any]

#: Sidebar order: the order the source declares things in. The default.
ORDER_DECLARATION = "declaration"
#: Sidebar order: by label, case-insensitively.
ORDER_LABEL = "label"
#: Everything ``order=`` accepts.
ORDERS = (ORDER_DECLARATION, ORDER_LABEL)


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
        return_annotation: The bare runtime type the method declares it
            returns, with ``Annotated`` stripped. Nothing renders it; it is
            kept because it costs nothing and describes the tool.
        return_field_id: The ``F(id=...)`` carried at the top of the return
            annotation, or None. This is what makes a finished run's value
            sendable into another tool's field.
        print_result: This tool's answer to "print the return value when the
            run succeeds": True, False, or None for "whatever the application
            said". Nothing here resolves the None -- the page does, because the
            application default is not known to the registry.
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
    # Defaulted, and therefore down here rather than beside `description` where
    # it belongs by meaning: ToolInfo is constructed positionally in places
    # outside this module, and a new required field would break every one of
    # them. Optional metadata earns no right to do that.
    help: str | None = None
    on_cancel: Any = None
    return_field_id: str | None = None
    print_result: bool | None = None


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
        field_id: The ``F(id=...)`` this parameter's annotation carries, or
            None. It makes the field a destination for a return value declaring
            the same id, and does nothing else -- not the widget, not the
            label, not the coercion.
    """

    name: str
    annotation: Any       # Annotated metadata stripped; the bare runtime type
    default: Any          # inspect.Parameter.empty if no default
    has_default: bool
    placeholder: str = ""
    label: str | None = None   # None falls back to the parameter name
    field_id: str | None = None


@dataclass
class ToolSetInfo:
    """One @toolset class and the tools found on it.

    Attributes:
        cls: The decorated class itself. decoui instantiates it once, with no
            arguments, and keeps that single instance for the whole session.
        tags: Sidebar filter labels. Filtering hides the group; it does not
            unload it.
        tools: In the order ``build_tree(order=...)`` decided -- as declared by
            default, by label when asked for.
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


def _unwrap_optional(annotation: Any) -> Any:
    """Reduce ``Optional[X]`` / ``X | None`` to ``X``.

    A local copy of the same reduction :mod:`decoui.widget_builder` does, kept
    here rather than imported: that module pulls in Qt, and this one is
    deliberately importable without it.

    Args:
        annotation: Any annotation.

    Returns:
        The single non-None member of a two-member union, or the annotation
        unchanged. A union with two real types is left alone.
    """
    origin = typing.get_origin(annotation)
    if origin is types.UnionType or str(origin) == "typing.Union":
        non_none = [
            arg for arg in typing.get_args(annotation) if arg is not type(None)
        ]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _top_level_field_meta(annotation: Any) -> F | None:
    """Return the F sitting at the top of an annotation, without recursing.

    The counterpart to :func:`_find_field_meta`, and deliberately *not* a call
    to it. That one searches the whole annotation tree, which is right for a
    parameter -- ``Optional[Annotated[Path, F(...)]]`` has to be found -- and
    wrong for a return value, where it would report an ``F`` buried inside a
    container as if it described the container. Routing a whole tuple into a
    field typed for one of its members is the sort of failure that produces a
    plausible wrong value instead of an error, so the two searches are kept
    apart and :func:`build_tree` compares them.

    Args:
        annotation: A return annotation retrieved with include_extras=True.

    Returns:
        The metadata attached directly to the annotation, or to the single
        non-None member of an ``Optional``. None when there is none there.
    """
    for candidate in (annotation, _unwrap_optional(annotation)):
        for meta in getattr(candidate, "__metadata__", ()):
            if isinstance(meta, F):
                return meta
    return None


def _return_field_id(annotation: Any, tool_key: str) -> str | None:
    """Read the field id a return annotation declares.

    Args:
        annotation: The return annotation, metadata included. May be None when
            the method has no return annotation at all.
        tool_key: ``'ClassName.method_name'``, for the error message.

    Returns:
        The declared id, or None when the return carries no ``F(id=...)``.

    Raises:
        ValueError: If an id is declared somewhere inside the annotation rather
            than at the top of it -- inside a tuple, list or dict. decoui routes
            a return value whole, so an id in there describes nothing it can
            act on, and half-honouring it would hand the container to a field
            declared for one of its members.
    """
    top = _top_level_field_meta(annotation)
    if top is not None and top.id:
        return top.id

    nested = _find_field_meta(annotation)
    if nested is not None and nested.id:
        raise ValueError(
            f"{tool_key} declares F(id={nested.id!r}) inside its return "
            f"annotation rather than on the return itself. decoui sends a "
            f"return value whole and does not route the members of a tuple or "
            f"dataclass separately, so this id could not be honoured. Return "
            f"the one value that is meant to travel, annotated directly: "
            f"-> Annotated[X, F(id={nested.id!r})]"
        )
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


def validate_order(order: str) -> str:
    """Check an ``order`` argument and hand it back.

    Split out so :func:`decoui.runner.gui_main` can reject a misspelling before
    it builds a QApplication, rather than raising out of the middle of startup.

    Args:
        order: The value passed as ``order=``.

    Returns:
        The same string.

    Raises:
        ValueError: If it is not one of :data:`ORDERS`.
    """
    if order not in ORDERS:
        raise ValueError(
            f"order={order!r} is not one of {list(ORDERS)}"
        )
    return order


def _tool_methods(cls: type) -> list[tuple[str, Any]]:
    """Return a class's @tool methods in the order they were written.

    ``inspect.getmembers`` would be one line, but it sorts by attribute name,
    and a method's name is not what the sidebar is read for. A class body's
    namespace keeps insertion order, so walking the MRO from the base class
    down and taking each ``vars()`` in turn recovers source order, with
    inherited tools ahead of the ones the subclass added.

    Args:
        cls: A class carrying @toolset metadata.

    Returns:
        ``(name, function)`` pairs, ordered as declared. A tool a subclass
        overrides keeps the position its base gave it and contributes the
        subclass's function; a name the subclass re-declares *without* ``@tool``
        drops out, because the lookup is resolved on ``cls``.
    """
    names: list[str] = []
    seen: set[str] = set()
    for klass in reversed(cls.__mro__):
        for name in vars(klass):
            if name not in seen:
                seen.add(name)
                names.append(name)

    methods: list[tuple[str, Any]] = []
    for name in names:
        attr = getattr(cls, name, None)
        if inspect.isfunction(attr) and hasattr(attr, _TOOL_ATTR):
            methods.append((name, attr))
    return methods


def build_tree(*toolset_classes, order: str = ORDER_DECLARATION) -> list[ToolSetInfo]:
    """Scan classes decorated with @toolset and return a ToolTree.

    Args:
        *toolset_classes: Classes carrying @toolset metadata.
        order: ``"declaration"`` (the default) keeps the order the source reads
            in -- these classes in the order they were passed, each class's
            tools in the order their ``def`` statements appear. ``"label"``
            sorts both by label instead, case-insensitively.

    Returns:
        One ToolSetInfo per class, each holding its tools, both ordered as
        ``order`` asks.

    Raises:
        ValueError: If ``order`` is not a recognised value, a class is not
            decorated with @toolset, or a declaration names a parameter the
            method does not have.
        TypeError: If a declaration has an unusable type -- a non-str label, a
            completions spec on a numeric field, and so on.
        AttributeError: If a declaration names a method the class does not have.

    Note:
        Nothing here touches Qt, and no instance is created: this runs on plain
        classes. It is therefore safe to call from a test to assert that an
        application's declarations are consistent.
    """
    validate_order(order)
    tree: list[ToolSetInfo] = []

    for cls in toolset_classes:
        meta = getattr(cls, _TOOLSET_ATTR, None)
        if meta is None:
            raise ValueError(f"{cls} is not decorated with @toolset")

        # An application's own text is translated here rather than in the
        # decorator, because a decorator's arguments are evaluated at import,
        # before gui_main() has settled the language. Everything downstream is
        # built from what this function returns, so one substitution reaches
        # the sidebar, the tabs, the forms, the Help panel and the history.
        # An application that named no i18n_dir gets the strings it wrote.
        set_key = cls.__name__
        ts = ToolSetInfo(
            cls=cls,
            label=translated(set_key, "label", meta["label"]),
            tags=meta["tags"],
            icon=meta["icon"],
            description=translated(set_key, "description", meta["description"]),
        )

        for name, method in _tool_methods(cls):
            tool_meta = getattr(method, _TOOL_ATTR)

            sig = inspect.signature(method)
            # get_type_hints evaluates stringified annotations (PEP 563 / Python 3.14)
            hints, annotated_hints = _resolve_hints(method)
            params: list[ParamInfo] = []

            tool_key = f"{cls.__name__}.{name}"
            placeholders = param_text(
                tool_key, "placeholder", tool_meta["placeholders"]
            )
            labels = param_text(tool_key, "label", tool_meta.get("labels", {}))
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
                    field_id=(meta.id or None) if meta else None,
                ))

            return_ann = hints.get("return", None)
            return_field_id = _return_field_id(
                annotated_hints.get("return"), tool_key
            )

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
                tool_id=tool_key,
                method_name=name,
                method=method,
                label=translated(tool_key, "label", tool_meta["label"]),
                description=translated(
                    tool_key, "description", tool_meta["description"]
                ),
                help=tool_meta.get("help"),
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
                return_field_id=return_field_id,
                # Read, not checked: all three of True / False / None are
                # legal, so there is no such thing as a wrong value here.
                print_result=tool_meta.get("print_result"),
            ))

        if order == ORDER_LABEL:
            ts.tools.sort(key=lambda t: t.label.casefold())
        tree.append(ts)

    if order == ORDER_LABEL:
        tree.sort(key=lambda s: s.label.casefold())

    _check_field_types(tree)
    return tree


#: One destination for a value: the tool that owns it and the parameter's name.
FieldTarget: TypeAlias = tuple[str, str]


def field_index(tree: list[ToolSetInfo]) -> dict[str, list[FieldTarget]]:
    """Map each declared field id to the parameters that accept it.

    This is the whole of the routing table. A tool that returns a value
    declaring id ``x`` can send it to every parameter listed under ``x``, and
    neither side ever names the other -- which is why adding a consumer needs
    no change to the producer.

    Args:
        tree: The toolset tree returned by :func:`build_tree`.

    Returns:
        ``{field_id: [(tool_id, param_name), ...]}``, covering parameters only.
        Ids that no parameter claims are absent rather than present and empty;
        :func:`unconsumed_field_ids` is what reports those.

    Note:
        Targets follow the tree's own order, so the menu a tool page builds
        from this reads in the same order as the sidebar.
    """
    index: dict[str, list[FieldTarget]] = {}
    for toolset_info in tree:
        for tool_info in toolset_info.tools:
            for param in tool_info.params:
                if param.field_id:
                    index.setdefault(param.field_id, []).append(
                        (tool_info.tool_id, param.name)
                    )
    return index


def unconsumed_field_ids(tree: list[ToolSetInfo]) -> list[str]:
    """Return the field ids some tool produces but no parameter accepts.

    Almost always a typo: ``F(id="artifcat")`` on a return leaves the tool page
    with no Send button and nothing to explain why. It can also be legitimate
    while a producer is written before its consumer, which is why this reports
    rather than raises -- :func:`decoui.runner.gui_main` turns each entry into
    a startup problem, and the application still opens.

    Args:
        tree: The toolset tree returned by :func:`build_tree`.

    Returns:
        The unmatched ids, deduplicated, in the order the tree declares them.

    Note:
        Nothing here touches Qt, so an application's test suite can assert that
        its own routing is wired up without starting a GUI.
    """
    consumed = field_index(tree)
    missing: list[str] = []
    for toolset_info in tree:
        for tool_info in toolset_info.tools:
            field_id = tool_info.return_field_id
            if field_id and field_id not in consumed and field_id not in missing:
                missing.append(field_id)
    return missing


def _check_field_types(tree: list[ToolSetInfo]) -> None:
    """Verify that everything sharing a field id resolves to the same type.

    An id is a claim that two declarations are the same field. If they disagree
    about the type, the claim is false and sending a value between them would
    put an int in a field built for a str -- so this is refused at startup,
    where a declaration mistake is meant to surface.

    ``Optional`` is unwrapped before comparing, so a parameter that tolerates
    None and one that does not still count as the same field.

    Args:
        tree: The toolset tree, already assembled.

    Raises:
        ValueError: If one id appears with two different runtime types. The
            message names both sites.
    """
    seen: dict[str, tuple[Any, str]] = {}

    def visit(field_id: str, annotation: Any, where: str) -> None:
        """Record one declaration of an id, or raise if it contradicts another.

        Args:
            field_id: The declared id.
            annotation: The declaration's bare annotation.
            where: Human-readable location, for the error message.

        Raises:
            ValueError: If the id was already seen with a different type.
        """
        bare = _unwrap_optional(annotation)
        if field_id not in seen:
            seen[field_id] = (bare, where)
            return
        first_type, first_where = seen[field_id]
        if first_type != bare:
            raise ValueError(
                f"F(id={field_id!r}) is declared with two different types: "
                f"{first_where} has {first_type!r}, {where} has {bare!r}. "
                f"One id means one field, so both ends have to agree -- give "
                f"the two fields separate ids, or make the types match."
            )

    for toolset_info in tree:
        for tool_info in toolset_info.tools:
            for param in tool_info.params:
                if param.field_id:
                    visit(
                        param.field_id,
                        param.annotation,
                        f"{tool_info.tool_id}({param.name})",
                    )
            if tool_info.return_field_id:
                visit(
                    tool_info.return_field_id,
                    tool_info.return_annotation,
                    f"{tool_info.tool_id} return",
                )
