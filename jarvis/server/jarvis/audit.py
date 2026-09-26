"""Das Audit Log: jede wichtige Aktion dauerhaft und filterbar protokolliert.

Getrennt von den Live-Ereignissen, die der ``Hub`` in ``app.py`` an
verbundene Geräte sendet -- die sind flüchtig und verschwinden beim nächsten
Neustart. Dieses Protokoll bleibt, in einer eigenen SQLite-Datei neben
``gedaechtnis.sqlite3``, und lässt sich nach Werkzeug, Sicherheitsstufe,
Erfolg und Zeitraum durchsuchen (Punkt 24 der Aufgabenstellung: "Logs sollen
filterbar sein").
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .permissions import PermissionLevel

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id        TEXT PRIMARY KEY,
    ts        REAL NOT NULL,
    request   TEXT NOT NULL DEFAULT '',
    tool      TEXT NOT NULL,
    level     TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    ok        INTEGER NOT NULL,
    summary   TEXT NOT NULL DEFAULT '',
    task_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_log(tool);
CREATE INDEX IF NOT EXISTS idx_audit_level ON audit_log(level);
CREATE INDEX IF NOT EXISTS idx_audit_ok ON audit_log(ok);
"""


@dataclass(frozen=True)
class AuditEntry:
    id: str
    ts: float
    request: str
    tool: str
    level: PermissionLevel
    arguments: dict[str, Any]
    ok: bool
    summary: str
    task_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Die Form für die Oberfläche -- am Beispiel aus der Aufgabenstellung
        orientiert (Zeit, Anfrage, Aktion, Stufe, Ergebnis)."""
        return {
            "id": self.id,
            "zeit": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts)),
            "anfrage": self.request, "werkzeug": self.tool, "stufe": self.level.label,
            "argumente": self.arguments, "erfolg": self.ok, "ergebnis": self.summary,
            "task_id": self.task_id,
        }


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"], ts=row["ts"], request=row["request"], tool=row["tool"],
        level=PermissionLevel.from_label(row["level"]),
        arguments=json.loads(row["arguments"] or "{}"), ok=bool(row["ok"]),
        summary=row["summary"], task_id=row["task_id"])


class AuditLog:
    """Protokolliert jeden Werkzeugaufruf. Eine Datei, kein Dienst -- wie
    ``MemoryStore``. Ein Protokollierungsfehler darf eine echte Aktion nicht
    verhindern; wer ``record`` aufruft, tut das deshalb, nachdem das Werkzeug
    schon gelaufen ist, nie davor."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def record(self, *, tool: str, level: PermissionLevel, arguments: dict[str, Any],
              ok: bool, summary: str, request: str = "",
              task_id: str | None = None) -> AuditEntry:
        entry = AuditEntry(id=uuid.uuid4().hex[:12], ts=time.time(), request=request,
                           tool=tool, level=level, arguments=dict(arguments or {}),
                           ok=ok, summary=summary, task_id=task_id)
        self._db.execute(
            "INSERT INTO audit_log (id, ts, request, tool, level, arguments, ok, "
            "summary, task_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (entry.id, entry.ts, entry.request, entry.tool, entry.level.label,
             json.dumps(entry.arguments, ensure_ascii=False), int(entry.ok),
             entry.summary, entry.task_id))
        self._db.commit()
        return entry

    def query(self, *, tool: str | None = None, level: PermissionLevel | None = None,
              ok: bool | None = None, since: float | None = None,
              limit: int = 100) -> list[AuditEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if level is not None:
            clauses.append("level = ?")
            params.append(level.label)
        if ok is not None:
            clauses.append("ok = ?")
            params.append(int(ok))
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._db.execute(
            f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ?",
            (*params, limit)).fetchall()
        return [_row_to_entry(r) for r in rows]

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
