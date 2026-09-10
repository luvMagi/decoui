"""Field metadata and marker types a tool author writes into annotations.

Two unrelated things live here:

* :class:`F`, which attaches form text to a type through ``typing.Annotated``.
  This is fully implemented and is the recommended way to describe a field that
  several tools share.
* ``Text`` / ``FilePath`` / ``DirPath`` / ``Choice``, four ``str`` subclasses
  that were meant to select widgets. **They do not.** See the warning on each.

The widget for a parameter is chosen in :mod:`decoui.widget_builder` from the
bare runtime type. Nothing in this module changes that choice except by being
the type itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated


@dataclass(frozen=True)
class F:
    """Per-parameter form metadata, attached through :data:`typing.Annotated`.

    Carrying the text next to the type keeps it with the field when the
    annotation is shared between tools, instead of repeating it in every
    ``@tool(placeholders=...)`` mapping.

    Args:
        label: Form label for the field. Defaults to the parameter name.
        placeholder: Hint text shown while the field is empty.

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
    """

    label: str | None = None
    placeholder: str | None = None


# ── Marker types ──────────────────────────────────────────────────────────────
#
# These four are exported from the package and look like they select widgets.
# They do not: widget_builder._build_for_type() matches pathlib.Path, dict, bool,
# int, float, Enum and list, and sends everything else -- including every str
# subclass -- to a plain QLineEdit.
#
# They are kept because removing an exported name is a breaking change. Do not
# reach for them when writing tools; use the real annotation instead.


class Text(str):
    """A str subclass that was intended to select a multi-line text area.

    Warning:
        **Not implemented.** A parameter annotated ``Text`` gets an ordinary
        single-line ``QLineEdit``, exactly as if it were annotated ``str``.
        For a multi-line field, annotate the parameter ``list`` (one item per
        line) or ``dict`` (JSON), which are the mappings that really produce a
        ``QTextEdit``.
    """


class FilePath(str):
    """A str subclass that was intended to add a file-picker button.

    Warning:
        **Not implemented.** A parameter annotated ``FilePath`` gets a plain
        ``QLineEdit`` with no button. Annotate it ``pathlib.Path`` instead: that
        is the annotation that builds the field with **File...** and
        **Folder...** buttons, and the method then receives a real ``Path``.
    """


class DirPath(str):
    """A str subclass that was intended to add a directory-picker button.

    Warning:
        **Not implemented.** Same as :class:`FilePath` -- use ``pathlib.Path``.
        decoui has no directory-only field; the path widget offers both buttons.
    """


class Choice(str):
    """A str subclass that was intended to select a dropdown.

    Warning:
        **Not implemented.** A parameter annotated ``Choice`` gets a plain
        ``QLineEdit``. For a dropdown, annotate the parameter with an
        ``enum.Enum`` subclass: each member becomes an item and the method
        receives the member itself, not its name.

        For a free-text field with suggestions, keep ``str`` and declare
        ``@tool(completions={"name": [...]})`` instead.
    """


# ── Convenience aliases ───────────────────────────────────────────────────────
#
# The dict metadata here predates F and is *not* read by anything: widget_builder
# fixes QSpinBox to the full int range and QDoubleSpinBox to +/-1e15 with 4
# decimals regardless. These aliases are therefore equivalent to plain int/float
# today; the metadata records intent for a future constraint pass.

Age = Annotated[int, {"min": 0, "max": 150}]
Rate = Annotated[float, {"min": 0.0, "max": 1.0, "step": 0.01}]
