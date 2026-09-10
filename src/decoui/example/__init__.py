"""Example toolsets -- the reference for writing tools, in three groups.

Copy from this package rather than from prose. Every feature decoui supports
appears here at least once, in working form, and each module answers one
question:

=========================  ==================================================
:mod:`~decoui.example.fields`   which annotation builds which widget, and how
                                to describe a field
:mod:`~decoui.example.running`  what happens while a tool runs: output,
                                progress, confirmation, timeouts, and stopping
:mod:`~decoui.example.assist`   how a form fills itself in: completions,
                                cascading fill, lazy defaults, startup state
=========================  ==================================================

Run it::

    python -m decoui.example

The package is a directory rather than a module so that everything it owns sits
together: the toolsets, the Markdown help their tools point at, the sample data
they print, and the entry point that launches them. None of it is part of
decoui's own machinery, and keeping it out of the top-level namespace makes
that visible.

Note:
    **A tool's docstring is written for the person using the tool**, not for the
    person reading this code. It is the source the Help panel collects: the
    summary line, the paragraphs under it and the ``Args:`` entries all reach
    the screen. So they say what the field is for, never which Qt widget the
    annotation happens to produce.

    Notes aimed at whoever is copying this code -- which annotation builds which
    widget, why a check is written the way it is -- live in ``#`` comments
    instead. Comments are not collected, so the two audiences stay separated
    without either losing anything.

    **Logging needs a level set by the application.** decoui attaches its
    console handler to the root logger but does not change that logger's level,
    and an unconfigured root logger filters everything below WARNING. Tools here
    log at INFO and DEBUG, so their output only reaches the console when the
    entry point has called ``logging.basicConfig(level=...)`` -- see
    :mod:`decoui.example.__main__`.

    **Every tool is an ordinary method.** ``FieldTools().all_widgets("abc")``
    works with no GUI involved. That is the property to preserve when writing
    new tools.

    **Return values are not displayed.** They are recorded in the run's history
    entry and nothing else. Everything the user sees comes from ``print()`` or
    ``logging``.

    Four exported names are **not** demonstrated here on purpose: ``Text``,
    ``FilePath``, ``DirPath`` and ``Choice`` look like they select widgets and
    do not -- see :mod:`decoui.types`. Use ``list``, ``pathlib.Path`` and an
    ``Enum`` instead, as this package does.
"""

from pathlib import Path

from .assist import AssistTools
from .fields import Archive, FieldTools, LogLevel
from .running import RunTools

#: The three toolsets, in the order the modules above introduce them. The list
#: decides *what* loads, not the order it appears in -- the sidebar is always
#: sorted by label.
TOOLSETS = [FieldTools, RunTools, AssistTools]

#: Where this package keeps its own translations, one <language>.json per
#: language. Handed to gui_main(i18n_dir=...) -- see decoui.tool_i18n for what
#: goes in the file and why it cannot go in the decorator instead. Resolved from
#: __file__ rather than written relative to the working directory, so it is
#: still found when decoui is installed as a wheel.
I18N_DIR = Path(__file__).resolve().parent / "i18n"

__all__ = [
    "TOOLSETS",
    "I18N_DIR",
    "FieldTools",
    "RunTools",
    "AssistTools",
    "Archive",
    "LogLevel",
]
