"""Which annotation builds which widget, and how to describe a field."""
from __future__ import annotations

import enum
import logging
import pathlib
from typing import Annotated

from decoui import F, tool, toolset


class LogLevel(enum.Enum):
    """Log levels offered as a dropdown.

    Any Enum subclass used as an annotation becomes a QComboBox, and the tool
    receives the member itself -- not its name or its value.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# An annotation shared between tools, carrying its own form text. F travels with
# the type, so a field described once reads the same wherever it is reused --
# and @tool(labels=/placeholders=) can still override it for a single tool.
#
# It must be importable at runtime. Under `from __future__ import annotations`
# every annotation is a string, and decoui resolves it with get_type_hints(), so
# an alias hidden behind `if TYPE_CHECKING:` would fail to resolve and take the
# type mapping down with it.
Archive = Annotated[
    pathlib.Path, F(label="Archive file", placeholder="Pick a .zip or .tar.gz")
]


@toolset(
    label="Fields",
    tags=["basics"],
    description="Every annotation decoui maps to a widget, in one form.",
)
class FieldTools:
    """What each annotation builds, and how to describe a field."""

    # The complete mapping, in one form so it can be seen at once:
    #
    #   str            QLineEdit
    #   int            QSpinBox
    #   float          QDoubleSpinBox
    #   bool           QCheckBox        (checked before int -- bool subclasses it)
    #   list           QTextEdit        one item per line, also split on commas
    #   dict           QTextEdit        parsed as JSON
    #   enum.Enum      QComboBox        the member is passed, not its name
    #   pathlib.Path   line edit + File... / Folder... buttons
    #
    # A parameter with no default is required and gets the asterisk; one with a
    # default is optional and the widget opens on that value.
    @tool(
        label="All Widgets",
        description="One field of every supported type.",
        # placeholders and labels are per-tool text. Prefer F on the annotation
        # when several tools share a field; use these to reword one of them.
        placeholders={
            "text": "a plain string",
            "lines": "one item per line",
            "options": '{"key": "value"}',
        },
        labels={"ratio": "Ratio (0-1)"},
    )
    def all_widgets(
        self,
        text: str,
        count: int = 3,
        ratio: float = 0.5,
        enabled: bool = True,
        lines: list = None,
        options: dict = None,
        target: pathlib.Path = pathlib.Path(),
        level: LogLevel = LogLevel.INFO,
    ) -> str:
        """Report back whatever was typed into each field.

        Run it once with the defaults to see what each control produces, then
        change one field at a time.

        Args:
            text: Required -- the only field here without a default, so it is
                the only one marked with an asterisk.
            count: A whole number.
            ratio: A number with a decimal part.
            enabled: A yes/no switch.
            lines: One item per line. Commas separate items too.
            options: JSON. Anything that is not valid JSON is reported before
                the tool runs.
            target: A file or folder. The buttons beside it open a picker.
            level: One of a fixed set of choices.

        Returns:
            A summary of the values received.
        """
        lines = lines or []
        options = options or {}
        logging.log(getattr(logging, level.value), "level came through as %r", level)
        print(f"text={text!r} count={count} ratio={ratio} enabled={enabled}")
        print(f"lines={lines}")
        print(f"options={options}")
        print(f"target={target}  (a {type(target).__name__})")
        return f"{len(lines)} lines, {len(options)} options, level {level.value}"

    # Archive is the shared annotation declared above. Its label and placeholder
    # come with it -- there is no placeholders= entry for `archive` here, yet
    # the field is still described.
    @tool(label="Shared Field", description="A field described once and reused.")
    def restore(self, archive: Archive, verify: bool = True) -> str:
        """Pretend to restore from an archive.

        Args:
            archive: The archive to read.
            verify: Check the contents before restoring.

        Returns:
            What would have been restored.
        """
        print(f"restoring from {archive}, verify={verify}")
        return f"would restore {archive.name or '(nothing chosen)'}"
