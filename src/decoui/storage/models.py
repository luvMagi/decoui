"""Dataclass definitions for execution records.

These three describe exactly what one run of one tool leaves behind. They are
the answer to "what can I find out afterwards" -- which is how the reported data
incidents were traced back to a specific run and its arguments.

The shapes here mirror the SQLite tables in :mod:`decoui.storage.db` one to one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExecutionParam:
    """One argument value, snapshotted at the moment a tool was run.

    Attributes:
        record_id: Owning ExecutionRecord id.
        param_name: The parameter name from the method signature.
        param_value: ``json.dumps(value, default=str)`` of the argument. Lossy
            by design -- a Path becomes its string form -- so this is a record
            of what was passed, not a value to deserialise back.
        param_type: ``type(value).__name__`` at call time, or ``'NoneType'``.
    """

    record_id: int
    param_name: str
    param_value: str | None   # JSON-serialized
    param_type: str


@dataclass
class ExecutionLog:
    """One console line produced by a run.

    Written in batches (50 lines or one second), so the tail of a running tool
    may not be in the database yet; it is always flushed before the record is
    finalised.

    Attributes:
        record_id: Owning ExecutionRecord id.
        seq: Position within the run, starting at 0. Ordering key -- timestamps
            are not unique enough at this rate.
        level: ``'stdout'`` for print output, otherwise a logging level name.
        message: The line text, already formatted by the logging handler.
        logged_at: When the line reached the GUI thread, not when it was written.
    """

    record_id: int
    seq: int
    level: str               # 'stdout' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
    message: str
    logged_at: datetime


@dataclass
class ExecutionRecord:
    """One run of one tool, from the moment Run was pressed.

    Inserted with ``status='running'`` *before* the tool starts, so a run that
    never reported back is still visible afterwards -- a record left as
    ``running`` means the application died mid-run.

    Attributes:
        tool_id: ``'ClassName.method_name'``. Renaming either orphans the past
            runs of that tool.
        tool_label: The display name at the time of the run, kept so history
            stays readable after a label change.
        started_at: When the run was scheduled.
        status: ``'running'`` -> ``'success'`` | ``'error'`` | ``'cancelled'``.
        id: Database id; 0 until inserted.
        finished_at: None while running.
        result_json: The return value, serialised with ``default=str`` and
            falling back to ``str(result)``. None for error and cancelled runs,
            whose return value is dropped.
        error_msg: Reserved. Failures are recorded as ERROR log lines instead,
            and nothing writes this field today.
        params: The argument snapshot. Replay reads it to refill the form.
    """

    tool_id: str
    tool_label: str
    started_at: datetime
    status: str              # 'running' | 'success' | 'error' | 'cancelled'
    id: int = 0
    finished_at: datetime | None = None
    result_json: str | None = None
    error_msg: str | None = None
    params: list[ExecutionParam] = field(default_factory=list)
