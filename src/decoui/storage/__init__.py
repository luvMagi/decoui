"""SQLite persistence for run history and application settings.

Every run of every tool is recorded: what was run, with which parameters, what
it printed, how it ended, and what it returned. That record is what the History
page reads and what Replay restores a form from.

Tools do not write here. If a tool needs its own persistent data, it should own
that storage itself -- this database belongs to the framework.
"""

from .models import ExecutionRecord, ExecutionParam, ExecutionLog
from .db import init_db, insert_record, update_record, insert_logs, query_records, query_params, query_logs, delete_records

__all__ = [
    "ExecutionRecord", "ExecutionParam", "ExecutionLog",
    "init_db", "insert_record", "update_record", "insert_logs",
    "query_records", "query_params", "query_logs", "delete_records",
]
