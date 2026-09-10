"""Demo entry point.

Shows the explicit form of toolset registration: the classes to load are named,
so the imports are ordinary imports that a linter can see being used.

The alternative is to omit ``toolsets`` entirely, in which case gui_main()
scans the caller's namespace for anything decorated with @toolset. That works,
but every import then exists only to be scanned and has to be marked as such::

    from decoui.example import *  # noqa: F401, F403

    gui_main(title="decoui Examples", db_path="history.db")

Both forms are supported and neither is deprecated. Prefer this one when the set
of toolsets is known and fixed; prefer discovery when toolsets are assembled
dynamically, or when a plugin package registers its own.
"""
import logging

from decoui import gui_main
from decoui.example import AssistTools, DemoTools, NumberTools, TextTools

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gui_main(
        title="decoui Examples",
        db_path="history.db",
        # The list decides *what* loads, not the order it appears in: the
        # sidebar is always sorted by label.
        toolsets=[TextTools, NumberTools, DemoTools, AssistTools],
    )
