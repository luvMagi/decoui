"""Execution layer: the thread a tool runs on and the record it leaves behind.

Tools never import from here. It is the machinery between the Run button and a
tool method: :mod:`decoui.engine.worker` owns the thread, output capture,
cancellation and :func:`decoui.progress`; :mod:`decoui.engine.executor` owns the
history record and the run lifecycle.

Read :mod:`decoui.engine.worker` before writing a tool that starts a subprocess
or produces output from more than one thread.
"""

from .executor import ExecutionEngine
from .worker import ToolWorker, WorkerSignals

__all__ = ["ExecutionEngine", "ToolWorker", "WorkerSignals"]
