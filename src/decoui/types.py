"""Field metadata a tool author writes into annotations.

:class:`F` attaches form text, and a field's identity, to a type through
``typing.Annotated``. It is the recommended way to describe a field that several
tools share.

The widget for a parameter is chosen in :mod:`decoui.widget_builder` from the
bare runtime type. Nothing in this module changes that choice.

Removed in 1.1.0:
    ``Text``, ``FilePath``, ``DirPath`` and ``Choice`` -- four ``str``
    subclasses that looked like they selected widgets and never did. Being
    ``str`` subclasses they fell through to a plain ``QLineEdit``, so annotating
    a parameter with one produced the same field as annotating it ``str``, with
    none of the promise.

    They are gone rather than implemented because decoui selects widgets from
    native types (see the design principles); a marker type whose only job is to
    pick a widget is the pattern that rules out. Write instead:

    ============  ==========================================================
    ``Text``      ``list`` for one item per line, or ``dict`` for JSON. A
                  multi-line **str** field has no annotation yet.
    ``FilePath``  ``pathlib.Path`` -- builds the field with File... and
                  Folder... buttons and hands the method a real ``Path``.
    ``DirPath``   ``pathlib.Path``; decoui has no directory-only field.
    ``Choice``    an ``enum.Enum`` subclass for a dropdown, or keep ``str``
                  and declare ``@tool(completions={...})`` for suggestions.
    ============  ==========================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated


@dataclass(frozen=True)
class F:
    """Field metadata, attached to a type through :data:`typing.Annotated`.

    Carrying the text next to the type keeps it with the field when the
    annotation is shared between tools, instead of repeating it in every
    ``@tool(placeholders=...)`` mapping.

    Args:
        label: Form label for the field. Defaults to the parameter name.
        placeholder: Hint text shown while the field is empty.
        id: This field's identity, shared across every tool that declares it.
            Two declarations carrying the same id are claiming to be the same
            field, which is what lets a tool's **return value** be sent into
            another tool's parameter -- see below.

    Example:
        DumpFile = Annotated[Path, F(label="Dump file", placeholder="Pick .dump")]

        @tool(label="Restore")
        def restore(self, archive: DumpFile): ...

    Note:
        ``@tool(labels=...)`` and ``@tool(placeholders=...)`` override this, so a
        single tool can reword a shared field without changing the annotation.

        Adding ``F`` is purely additive: the registry strips ``Annotated`` before
        storing the annotation, so widget choice, the required-field marker and
        type coercion all see the bare type and behave exactly as before.

        ``F`` is found however deeply it is nested, so
        ``Optional[Annotated[Path, F(...)]]`` works. Metadata that is not an
        ``F`` instance -- the ``{"min": 0}`` dicts below, for instance -- is
        ignored rather than rejected.

        Under ``from __future__ import annotations`` every annotation is a
        string at runtime and decoui resolves it with ``typing.get_type_hints``.
        An alias like ``DumpFile`` must therefore be importable at runtime;
        hiding it behind ``if TYPE_CHECKING:`` makes resolution fail and the
        ``F`` metadata is lost along with the type mapping.

        **About ``id``.** Declare the annotation once and share it:

            ArtifactId = Annotated[str, F(id="artifact", label="Artifact id")]

            def build(self) -> ArtifactId: ...                  # produces it
            def deploy(self, artifact: ArtifactId): ...         # consumes it

        Neither tool names the other. The registry matches them by id and the
        tool page offers to send the finished value straight into the field --
        see :func:`decoui.registry.field_index`.

        Three things to know about it:

        * On a **parameter**, an id has no effect other than making that field
          a destination. It does not change the widget, the label chain or the
          type coercion.
        * On a **return**, the id is only read at the top of the annotation
          (``Optional`` may wrap it). One return value carries at most one id;
          decoui does not route the members of a returned tuple or dataclass
          separately, and declaring an id inside one is an error rather than a
          half-working route.
        * Two fields sharing an id must resolve to the same runtime type, which
          is checked when the application starts.
    """

    label: str | None = None
    placeholder: str | None = None
    id: str | None = None


# ── Convenience aliases ───────────────────────────────────────────────────────
#
# The dict metadata here predates F and is *not* read by anything: widget_builder
# fixes QSpinBox to the full int range and QDoubleSpinBox to +/-1e15 with 4
# decimals regardless. These aliases are therefore equivalent to plain int/float
# today; the metadata records intent for a future constraint pass.

Age = Annotated[int, {"min": 0, "max": 150}]
Rate = Annotated[float, {"min": 0.0, "max": 1.0, "step": 0.01}]
