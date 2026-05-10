"""Dataclass definitions for execution records."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExecutionParam:
    record_id: int
    param_name: str
    param_value: str | None   # JSON-serialized
    param_type: str


@dataclass
class ExecutionLog:
    record_id: int
    seq: int
    level: str               # 'stdout' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
    message: str
    logged_at: datetime


@dataclass
class ExecutionRecord:
    tool_id: str
    tool_label: str
    started_at: datetime
    status: str              # 'running' | 'success' | 'error' | 'cancelled'
    id: int = 0
    finished_at: datetime | None = None
    result_json: str | None = None
    error_msg: str | None = None
    params: list[ExecutionParam] = field(default_factory=list)
