"""SQLite persistence for decoui execution history and application settings."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import ExecutionRecord, ExecutionParam, ExecutionLog

_DB_PATH: Path = Path.home() / ".decoui" / "history.db"


def set_db_path(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = path


def _get_db_path() -> Path:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


@contextmanager
def _conn():
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


def insert_record(rec: ExecutionRecord) -> int:
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
    with _conn() as con:
        con.execute(
            "UPDATE execution_record SET status=?, finished_at=?, result_json=?, error_msg=? WHERE id=?",
            (status, finished_at.isoformat(), result_json, error_msg, rec_id),
        )


def insert_logs(logs: list[ExecutionLog]) -> None:
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
    with _conn() as con:
        rows = con.execute(
            "SELECT record_id, param_name, param_value, param_type FROM execution_params WHERE record_id=?",
            (record_id,),
        ).fetchall()
    return [ExecutionParam(r[0], r[1], r[2], r[3]) for r in rows]


def query_logs(record_id: int) -> list[ExecutionLog]:
    with _conn() as con:
        rows = con.execute(
            "SELECT record_id, seq, level, message, logged_at FROM execution_log WHERE record_id=? ORDER BY seq",
            (record_id,),
        ).fetchall()
    return [ExecutionLog(r[0], r[1], r[2], r[3], datetime.fromisoformat(r[4])) for r in rows]


def delete_records(record_ids: list[int]) -> None:
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
