# Output and Logs

Everything a tool prints or logs appears in the output console below the form,
live, while it runs. Levels are colour-coded, and plain ``print`` output is
shown in its own colour so it stays distinguishable from logging.

If the application turns it on, a successful run's return value is printed at
the end of the output: a blank line, a ``========== Result ==========`` rule,
then the value. Nothing is printed when a run fails, is cancelled, or returns
nothing.

* ``Copy`` puts the whole console on the clipboard.
* ``View Log`` opens the run's output in a separate, resizable window.

The log window is the one to use when there is a lot of output. It adds:

* One toggle per level -- turn ``DEBUG`` off to see only what matters, or
  ``None`` then ``ERROR`` to see only failures.
* A search box that filters to matching lines.
* ``Copy All``.

Filtering there never disturbs the console on the page it came from; the window
holds its own copy of the lines.

A run's output is stored, so the same log can be reopened later from history
long after the tab has been closed.
