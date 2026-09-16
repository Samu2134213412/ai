"""SQLite persistence.

Everything the phone may need after a reconnect lives here: projects, sessions,
the full ordered event log, approval requests and paired devices. Events carry a
monotonic per-session ``seq`` so a returning client can replay from a cursor.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .config import config_home

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL,
    last_used   REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    claude_session_id TEXT,
    prompt          TEXT NOT NULL,
    status          TEXT NOT NULL,
    model           TEXT,
    context_length  INTEGER,
    permission_mode TEXT,
    started_at      REAL NOT NULL,
    ended_at        REAL,
    error           TEXT,
    base_commit     TEXT,
    parent_session  TEXT
);

CREATE TABLE IF NOT EXISTS events (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    ts          REAL NOT NULL,
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS approvals (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    tool_input  TEXT NOT NULL,
    status      TEXT NOT NULL,
    reason      TEXT,
    created_at  REAL NOT NULL,
    decided_at  REAL
);

CREATE TABLE IF NOT EXISTS devices (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL,
    last_seen   REAL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approvals(session_id, status);
"""


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or config_home() / "codepilot.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- plumbing
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------- projects
    def add_project(self, project_id: str, name: str, path: str) -> dict:
        now = time.time()
        self.execute(
            "INSERT INTO projects (id, name, path, created_at) VALUES (?,?,?,?)",
            (project_id, name, path, now),
        )
        return self.get_project(project_id)  # type: ignore[return-value]

    def get_project(self, project_id: str) -> dict | None:
        return self.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))

    def get_project_by_path(self, path: str) -> dict | None:
        return self.query_one("SELECT * FROM projects WHERE path = ?", (path,))

    def list_projects(self) -> list[dict]:
        return self.query(
            "SELECT * FROM projects ORDER BY COALESCE(last_used, created_at) DESC"
        )

    def touch_project(self, project_id: str) -> None:
        self.execute(
            "UPDATE projects SET last_used = ? WHERE id = ?", (time.time(), project_id)
        )

    def delete_project(self, project_id: str) -> None:
        self.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    # ------------------------------------------------------------- sessions
    def create_session(self, **row: Any) -> dict:
        row.setdefault("started_at", time.time())
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.execute(f"INSERT INTO sessions ({cols}) VALUES ({marks})", row.values())
        return self.get_session(row["id"])  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict | None:
        return self.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))

    def update_session(self, session_id: str, **changes: Any) -> None:
        if not changes:
            return
        sets = ", ".join(f"{k} = ?" for k in changes)
        self.execute(
            f"UPDATE sessions SET {sets} WHERE id = ?",
            (*changes.values(), session_id),
        )

    def list_sessions(self, project_id: str | None = None, limit: int = 50) -> list[dict]:
        if project_id:
            return self.query(
                "SELECT * FROM sessions WHERE project_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (project_id, limit),
            )
        return self.query("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,))

    def running_sessions(self) -> list[dict]:
        return self.query("SELECT * FROM sessions WHERE status = 'running'")

    # --------------------------------------------------------------- events
    def append_event(self, session_id: str, etype: str, payload: dict) -> dict:
        """Append an event, assigning the next per-session sequence number."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM events WHERE session_id = ?",
                (session_id,),
            )
            seq = cur.fetchone()["n"]
            ts = time.time()
            self._conn.execute(
                "INSERT INTO events (session_id, seq, ts, type, payload) VALUES (?,?,?,?,?)",
                (session_id, seq, ts, etype, json.dumps(payload)),
            )
            self._conn.commit()
        return {"session_id": session_id, "seq": seq, "ts": ts, "type": etype, "payload": payload}

    def get_events(self, session_id: str, after_seq: int = 0, limit: int = 2000) -> list[dict]:
        rows = self.query(
            "SELECT * FROM events WHERE session_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (session_id, after_seq, limit),
        )
        for r in rows:
            r["payload"] = json.loads(r["payload"])
        return rows

    # ------------------------------------------------------------ approvals
    def create_approval(self, approval_id: str, session_id: str, tool_name: str,
                        tool_input: dict) -> dict:
        self.execute(
            "INSERT INTO approvals (id, session_id, tool_name, tool_input, status, created_at)"
            " VALUES (?,?,?,?,'pending',?)",
            (approval_id, session_id, tool_name, json.dumps(tool_input), time.time()),
        )
        return self.get_approval(approval_id)  # type: ignore[return-value]

    def get_approval(self, approval_id: str) -> dict | None:
        row = self.query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if row:
            row["tool_input"] = json.loads(row["tool_input"])
        return row

    def decide_approval(self, approval_id: str, status: str, reason: str | None) -> None:
        self.execute(
            "UPDATE approvals SET status = ?, reason = ?, decided_at = ?"
            " WHERE id = ? AND status = 'pending'",
            (status, reason, time.time(), approval_id),
        )

    def pending_approvals(self, session_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM approvals WHERE status = 'pending'"
        params: tuple = ()
        if session_id:
            sql += " AND session_id = ?"
            params = (session_id,)
        rows = self.query(sql + " ORDER BY created_at", params)
        for r in rows:
            r["tool_input"] = json.loads(r["tool_input"])
        return rows

    # -------------------------------------------------------------- devices
    def add_device(self, device_id: str, name: str, token_hash: str) -> dict:
        self.execute(
            "INSERT INTO devices (id, name, token_hash, created_at) VALUES (?,?,?,?)",
            (device_id, name, token_hash, time.time()),
        )
        return self.query_one("SELECT * FROM devices WHERE id = ?", (device_id,))  # type: ignore

    def device_by_token_hash(self, token_hash: str) -> dict | None:
        return self.query_one(
            "SELECT * FROM devices WHERE token_hash = ? AND revoked = 0", (token_hash,)
        )

    def list_devices(self) -> list[dict]:
        return self.query("SELECT id, name, created_at, last_seen, revoked FROM devices "
                          "ORDER BY created_at DESC")

    def touch_device(self, device_id: str) -> None:
        self.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (time.time(), device_id))

    def revoke_device(self, device_id: str) -> None:
        self.execute("UPDATE devices SET revoked = 1 WHERE id = ?", (device_id,))
