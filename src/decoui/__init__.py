"""decoui - Decorator-driven GUI framework for Python.

decoui turns ordinary methods into a PySide6 desktop application. You write a
plain class, decorate it, and the framework derives the form, runs the method on
a worker thread, streams its output to a console, and records the run.

Orientation for code that writes decoui tools
---------------------------------------------

The whole surface is four things::

    from decoui import gui_main, progress, tool, toolset

    @toolset(label="Database")          # a class becomes a sidebar group
    class DatabaseTools:

        @tool(label="Restore")          # a method becomes a page with a form
        def restore(self, archive: Path, dry_run: bool = False) -> None:
            progress(0, 3, "starting")  # optional: drive the progress bar
            print("working")            # stdout and logging both reach the GUI

    gui_main(title="Ops", toolsets=[DatabaseTools])

Rules that are easy to get wrong
--------------------------------

1. **A tool is still a normal method.** The decorators only attach metadata;
   they never wrap or replace the function. ``DatabaseTools().restore(path)``
   works exactly as if decoui were not installed, which is how tools are meant
   to be tested. Nothing in this package may be required for a direct call to
   succeed -- that is why :func:`progress` is a no-op outside the GUI.

2. **Decorator arguments are evaluated at import time**, when no instance
   exists. ``defaults={"env": self.config["env"]}`` cannot work. Pass the *name*
   of a method instead and decoui binds it to the instance later. The same
   applies to ``completions``, ``cascade`` and ``on_cancel``.

3. **The form comes from the type annotations**, not from any widget code. See
   :mod:`decoui.widget_builder` for the exact mapping, and note that any type it
   does not recognise silently becomes a single-line text field.

4. **Return values are not displayed.** They are recorded in the run history as
   JSON, but the GUI shows nothing. Use ``print()`` or ``logging`` for output the
   user must see.

   To carry something *forward* instead -- the environment last deployed to, the
   folder last exported into -- use :func:`decoui.store`, which persists it in
   the same database::

       store("deploy")["last_env"] = env

5. **Cancellation cannot interrupt a blocking call.** If a tool starts a
   subprocess, it must declare ``@tool(on_cancel=...)`` or pressing Stop will
   leave the child running. See :mod:`decoui.engine.worker` for why.

Where to read further
---------------------

============================  ==============================================
:mod:`decoui.decorators`      every ``@tool`` / ``@toolset`` argument
:mod:`decoui.types`           ``F`` field metadata and the marker types
:mod:`decoui.widget_builder`  annotation -> widget mapping, value conversion
:mod:`decoui.registry`        how annotations are resolved and validated
:mod:`decoui.runner`          ``gui_main`` and the startup order
:mod:`decoui.engine.worker`   threading, output capture, cancellation, progress
:mod:`decoui.process`         ``run_process()``: shelling out so Stop can stop it
:mod:`decoui.assist`          completions / cascade / defaults callback rules
:mod:`decoui.storage.store`   ``store()``: remembering something between runs
:mod:`decoui.storage.models`  what a run records
============================  ==============================================
"""

from .decorators import tool, toolset
from .engine.worker import progress
from .process import ProcessError, ProcessResult, run_process
from .runner import gui_main
from .storage.store import Store, store
from .types import Choice, DirPath, F, FilePath, Text

__all__ = [
    "toolset",
    "tool",
    "gui_main",
    "progress",
    "run_process",
    "ProcessResult",
    "ProcessError",
    "store",
    "Store",
    "F",
    "Text",
    "FilePath",
    "DirPath",
    "Choice",
]

__version__ = "1.0.0"
