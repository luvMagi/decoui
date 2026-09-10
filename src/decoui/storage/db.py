"""SQLite persistence for decoui execution history and application settings.

One database file holds every run of every tool plus a small key/value settings
table. It defaults to ``~/.decoui/history.db`` and is overridden per application
with ``gui_main(db_path=...)``.

Notes that matter when reasoning about the data:

* **Every connection is short-lived.** Each call opens, commits or rolls back,
  and closes. There is no shared connection and no pooling, so these functions
  are safe to call from any thread -- which is why the engine can flush log
  batches while the GUI queries history.
* **WAL mode is on**, so the real footprint is the ``.db`` plus its ``-wal`` and
  ``-shm`` sidecars. :func:`get_db_size` counts all three.
* **Foreign keys are enforced per connection**, so deleting a record cascades to
  its params and logs.
* Timestamps are stored as ISO-8601 strings, which sort correctly as text -- the
  history query orders on them directly.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import ExecutionRecord, ExecutionParam, ExecutionLog

_DB_PATH: Path = Path.home() / ".decoui" / "history.db"


def set_db_path(path: Path) -> None:
    """Point every later connection at a different database file.

    Process-global, and must be called before anything opens the database --
    :func:`decoui.runner.gui_main` does it first thing when given ``db_path``.
    Tests use it to redirect history into a temporary directory.

    Args:
        path: Target database file. Its parent directory is created on demand.
    """
    global _DB_PATH
    _DB_PATH = path


def _get_db_path() -> Path:
    """Return the database path, creating its parent directory if needed.

    Returns:
        The configured database file path.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


@contextmanager
def _conn():
    """Open a connection that commits on success and rolls back on failure.

    Yields:
        A sqlite3.Connection with WAL journaling and foreign keys enabled.

    Note:
        The connection is closed on the way out, so nothing may hold on to it or
        to a cursor past the ``with`` block.
    """
    db = _get_db_path()
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_record (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id      TEXT    NOT NULL,
    tool_label   TEXT    NOT NULL,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT,
    status       TEXT    NOT NULL,
    result_json  TEXT,
    error_msg    TEXT
);

CREATE TABLE IF NOT EXISTS execution_params (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id) ON DELETE CASCADE,
    param_name   TEXT    NOT NULL,
    param_value  TEXT,
    param_type   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES execution_record(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    level        TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    logged_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS app_setting (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_record ON execution_log(record_id, seq);
"""


def init_db() -> None:
    """Create the schema if it is missing.

    Idempotent -- every statement is ``CREATE ... IF NOT EXISTS`` -- and called
    on every application start and by every ExecutionEngine.

    Note:
        There is no migration mechanism. Adding a column to a table here will
        not alter an existing database file.
    """
    with _conn() as con:
        con.executescript(_SCHEMA)


def get_setting(key: str, default: str | None = None) -> str | None:
    """Return a persisted application setting.

    Args:
        key: Stable setting identifier.
        default: Value returned when the setting does not exist.

    Returns:
        The stored string value, or the provided default.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT value FROM app_setting WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row[0]) if row is not None else default


def set_setting(key: str, value: str) -> None:
    """Insert or update a persisted application setting.

    Args:
        key: Stable setting identifier.
        value: String representation of the setting value.
    """
    with _conn() as con:
        con.execute(
            """
            INSERT INTO app_setting (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, datetime.now().isoformat()),
        )


def delete_setting(key: str) -> None:
    """Remove a persisted setting, if it is there.

    Args:
        key: The setting to drop. Deleting a key that was never written is not
            an error: the caller wanted it gone, and it is.
    """
    with _conn() as con:
        con.execute("DELETE FROM app_setting WHERE key = ?", (key,))


def settings_with_prefix(prefix: str) -> list[tuple[str, str]]:
    """Return every setting whose key starts with a prefix.

    Args:
        prefix: The literal prefix to match. ``%`` and ``_`` in it are escaped,
            so a prefix is never read as a LIKE pattern.

    Returns:
        ``(key, value)`` pairs, sorted by key. The keys are full keys, prefix
        included -- trimming them is the caller's business, since only the
        caller knows what it prefixed with.

    Note:
        ``key`` is the table's primary key, so this is an index range scan
        rather than a table scan. That is what lets a namespace live in the key
        instead of needing a column of its own.
    """
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with _conn() as con:
        rows = con.execute(
            "SELECT key, value FROM app_setting "
            "WHERE key LIKE ? ESCAPE '\\' ORDER BY key",
            (pattern,),
        ).fetchall()
    return [(str(k), str(v)) for k, v in rows]


def insert_record(rec: ExecutionRecord) -> int:
    """Insert a run and its parameter snapshot, returning the new id.

    Called before the tool starts, with ``status='running'``.

    Args:
        rec: The record to store. Its ``id`` is ignored; ``params`` are written
            with the id assigned here.

    Returns:
        The new record id.
    """
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO execution_record (tool_id, tool_label, started_at, status) VALUES (?,?,?,?)",
            (rec.tool_id, rec.tool_label, rec.started_at.isoformat(), rec.status),
        )
        rec_id = cur.lastrowid
        if rec.params:
            con.executemany(
                "INSERT INTO execution_params (record_id, param_name, param_value, param_type) VALUES (?,?,?,?)",
                [(rec_id, p.param_name, p.param_value, p.param_type) for p in rec.params],
            )
        return rec_id


def update_record(
    rec_id: int,
    status: str,
    finished_at: datetime,
    result_json: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Finalise a run once it has ended.

    Args:
        rec_id: The record to update.
        status: ``'success'``, ``'error'`` or ``'cancelled'``.
        finished_at: End timestamp.
        result_json: Serialised return value, or None.
        error_msg: Accepted but never supplied by the engine today; failures
            are recorded as ERROR log lines instead.
    """
    with _conn() as con:
        con.execute(
            "UPDATE execution_record SET status=?, finished_at=?, result_json=?, error_msg=? WHERE id=?",
            (status, finished_at.isoformat(), result_json, error_msg, rec_id),
        )


def insert_logs(logs: list[ExecutionLog]) -> None:
    """Append a batch of console lines in one statement.

    Args:
        logs: Lines to store. Each carries its own ``record_id`` and ``seq``.
    """
    if not logs:
        return
    with _conn() as con:
        con.executemany(
            "INSERT INTO execution_log (record_id, seq, level, message, logged_at) VALUES (?,?,?,?,?)",
            [(l.record_id, l.seq, l.level, l.message, l.logged_at.isoformat()) for l in logs],
        )


def query_records(
    tool_id: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = 500,
) -> list[ExecutionRecord]:
    """Query runs, newest first.

    Args:
        tool_id: Restrict to one tool, as ``'ClassName.method_name'``.
        status: Restrict to one status.
        since: Only runs started at or after this moment.
        limit: Maximum rows returned. The default caps the History page.

    Returns:
        Matching records without their params or logs -- fetch those with
        :func:`query_params` and :func:`query_logs` when a row is opened.
    """
    clauses = []
    args: list = []
    if tool_id:
        clauses.append("tool_id = ?"); args.append(tool_id)
    if status:
        clauses.append("status = ?"); args.append(status)
    if since:
        clauses.append("started_at >= ?"); args.append(since.isoformat())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT id, tool_id, tool_label, started_at, finished_at, status, result_json, error_msg FROM execution_record {where} ORDER BY started_at DESC LIMIT ?"
    args.append(limit)

    records: list[ExecutionRecord] = []
    with _conn() as con:
        for row in con.execute(sql, args):
            rec = ExecutionRecord(
                id=row[0],
                tool_id=row[1],
                tool_label=row[2],
                started_at=datetime.fromisoformat(row[3]),
                finished_at=datetime.fromisoformat(row[4]) if row[4] else None,
                status=row[5],
                result_json=row[6],
                error_msg=row[7],
            )
            records.append(rec)
    return records


def query_params(record_id: int) -> list[ExecutionParam]:
    """Return the argument snapshot of one run, for display or replay.

    Args:
        record_id: The run to read.

    Returns:
        Its parameters, in insertion order (the method's signature order).
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT record_id, param_name, param_value, param_type FROM execution_params WHERE record_id=?",
            (record_id,),
        ).fetchall()
    return [ExecutionParam(r[0], r[1], r[2], r[3]) for r in rows]


def query_logs(record_id: int) -> list[ExecutionLog]:
    """Return the full console output of one run.

    Args:
        record_id: The run to read.

    Returns:
        Its lines ordered by ``seq``.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT record_id, seq, level, message, logged_at FROM execution_log WHERE record_id=? ORDER BY seq",
            (record_id,),
        ).fetchall()
    return [ExecutionLog(r[0], r[1], r[2], r[3], datetime.fromisoformat(r[4])) for r in rows]


def delete_records(record_ids: list[int]) -> None:
    """Delete runs, cascading to their params and logs.

    Args:
        record_ids: Ids to remove. An empty list is a no-op.

    Note:
        Space is not reclaimed on disk; only :func:`clear_all_records` vacuums.
    """
    if not record_ids:
        return
    placeholders = ",".join("?" * len(record_ids))
    with _conn() as con:
        con.execute(f"DELETE FROM execution_record WHERE id IN ({placeholders})", record_ids)


def get_db_size() -> int:
    """Return the on-disk size of the history database in bytes.

    The write-ahead log and shared-memory sidecar files are included, so the
    number reflects the total disk footprint rather than the main file alone.

    Returns:
        Total size in bytes, or 0 when the database has not been created yet.
    """
    db = _DB_PATH
    total = 0
    for path in (db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def clear_all_records() -> None:
    """Delete every execution record and reclaim the freed disk space.

    Params and logs are removed through the foreign-key cascade. Application
    settings are preserved. The database is checkpointed and vacuumed so the
    size reported by :func:`get_db_size` actually shrinks.
    """
    with _conn() as con:
        con.execute("DELETE FROM execution_record")

    con = sqlite3.connect(str(_get_db_path()), isolation_level=None)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
    finally:
        con.close()
