"""Marker types for decoui widget mapping."""
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
    """

    label: str | None = None
    placeholder: str | None = None


class Text(str):
    """Maps to QTextEdit (multi-line text area)."""


class FilePath(str):
    """Maps to QLineEdit with a file-picker button."""


class DirPath(str):
    """Maps to QLineEdit with a directory-picker button."""


class Choice(str):
    """Maps to QComboBox. Use with Annotated to specify choices."""


# Convenience Annotated aliases for constrained numeric types
Age = Annotated[int, {"min": 0, "max": 150}]
Rate = Annotated[float, {"min": 0.0, "max": 1.0, "step": 0.01}]
