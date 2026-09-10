"""Run the examples: ``python -m decoui.example``.

Shows the explicit form of toolset registration -- the classes to load are
named, so the imports are ordinary imports a linter can see being used.

The alternative is to omit ``toolsets`` entirely, in which case ``gui_main()``
scans the caller's namespace for anything decorated with ``@toolset``. That
works, but every import then exists only to be scanned and has to be marked as
such::

    from decoui.example import *  # noqa: F401, F403

    gui_main(title="decoui Examples", db_path="history.db")

Both forms are supported and neither is deprecated. Prefer this one when the set
of toolsets is known and fixed; prefer discovery when toolsets are assembled
dynamically, or when a plugin package registers its own.
"""
import logging

from decoui import gui_main

from . import I18N_DIR, TOOLSETS


def main() -> None:
    """Launch the example application."""
    # DEBUG, not INFO: decoui attaches its console handler to the root logger
    # but never changes that logger's level, and an unconfigured root logger
    # filters at WARNING. Whatever level is set here is the floor for what a
    # tool's logging.* calls can reach the output console -- at INFO the
    # examples' own logging.debug lines would be dropped before decoui ever
    # sees them.
    logging.basicConfig(level=logging.DEBUG)
    gui_main(
        title="decoui Examples",
        db_path="history.db",
        toolsets=TOOLSETS,
        # The examples' own labels and field text, translated.
        # Switch the interface to Japanese in Settings to see it.
        i18n_dir=I18N_DIR,
    )


if __name__ == "__main__":
    main()
