"""Qt widgets that render the tool tree, the forms and the run history.

Nothing a tool author writes reaches into this package: a tool declares types
and metadata, and these widgets are derived from them. It is worth reading only
to answer "what will the user actually see", above all
:mod:`decoui.ui.tool_page`, which builds the form and owns the Run/Stop cycle.
"""

from .main_window import MainWindow

__all__ = ["MainWindow"]
