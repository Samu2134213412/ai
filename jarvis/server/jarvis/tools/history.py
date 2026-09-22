"""Werkzeug-Historie und Favoriten (Aufgabenstellung Punkt 36/37).

Bewusst **kein zweites Audit Log**. ``audit.py`` bleibt das
sicherheitsrelevante Protokoll: jeder Aufruf mit Stufe, Argumenten, Erfolg
und Ziel-ID, unveränderlich. Hier geht es um etwas anderes -- die
werkzeugzentrierte Sicht, die eine Oberfläche braucht: wie oft, wie lange,
wie zuverlässig, und was hat der Nutzer als Favorit markiert.

Secrets werden nicht im Klartext abgelegt (Punkt 36/51): Argumente, deren
Name nach Geheimnis aussieht, werden beim Schreiben ersetzt.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Argumentnamen, deren Inhalt nie protokolliert wird.
SECRET_HINTS = ("token", "password", "passwort", "secret", "api_key", "apikey",
                "key", "credential", "auth", "cookie", "session")
REDACTED = "«entfernt»"

#: Längere Argumentwerte werden gekürzt -- die Historie ist eine Übersicht,
#: kein Datenspeicher.
MAX_VALUE = 200

#: Diese beiden dürfen sich nicht selbst abschalten -- sonst gäbe es keinen
#: Weg mehr zurück außer einer manuellen Änderung an der Datenbank. Die
#: Prüfung sitzt hier, im Mechanismus selbst (``disable()``), und nicht bei
#: jedem einzelnen Aufrufer -- zwei Aufrufer (das ``jarvis.tools.disable``-
#: Werkzeug und der HTTP-Weg der Kommando-Palette) hatten sie zuvor beide
#: für sich re-implementiert, und ein dritter Aufrufer hätte sie vergessen
#: können.
PROTECTED = frozenset({"jarvis.tools.enable", "jarvis.tools.disable"})


def redact(arguments: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (arguments or {}).items():
        lowered = str(key).lower()
        if any(hint in lowered for hint in SECRET_HINTS):
            out[key] = REDACTED
            continue
        text = value if isinstance(value, (int, float, bool, type(None))) else str(value)
        if isinstance(text, str) and len(text) > MAX_VALUE:
            text = text[:MAX_VALUE] + "…"
        out[key] = text
    return out


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_history (
    id         TEXT PRIMARY KEY,
    ts         REAL NOT NULL,
    tool       TEXT NOT NULL,
    arguments  TEXT NOT NULL DEFAULT '{}',
    ok         INTEGER NOT NULL,
    summary    TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    level      TEXT NOT NULL DEFAULT '',
    request    TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_th_ts ON tool_history(ts);
CREATE INDEX IF NOT EXISTS idx_th_tool ON tool_history(tool);

CREATE TABLE IF NOT EXISTS tool_favorites (
    tool TEXT PRIMARY KEY,
    ts   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_disabled (
    tool   TEXT PRIMARY KEY,
    ts     REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    ts: float
    tool: str
    arguments: dict[str, Any]
    ok: bool
    summary: str
    duration_ms: int
    level: str = ""
    request: str = ""
    request_id: str = ""
    error_type: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "zeit": self.ts, "werkzeug": self.tool,
                "argumente": self.arguments, "erfolg": self.ok,
                "ergebnis": self.summary, "dauer_ms": self.duration_ms,
                "stufe": self.level, "anfrage": self.request,
                "request_id": self.request_id, "fehlerart": self.error_type}


class ToolHistory:
    """Aufrufe, Kennzahlen, Favoriten -- eine Datei, gleiches Muster wie die
    übrigen Ablagen des Projekts."""

    def __init__(self, path: str | Path = ":memory:", keep: int = 5000):
        self.path = str(path)
        #: Wie viele Einträge aufgehoben werden. Eine Historie, die ewig
        #: wächst, wäre ein Speicherleck mit Extraschritten.
        self.keep = keep
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------ schreiben
    def record(self, *, tool: str, arguments: dict[str, Any] | None, ok: bool,
               summary: str, duration_ms: int = 0, level: str = "",
               request: str = "", request_id: str = "",
               error_type: str = "") -> HistoryEntry:
        entry = HistoryEntry(
            id=uuid.uuid4().hex[:12], ts=time.time(), tool=tool,
            arguments=redact(arguments), ok=bool(ok), summary=summary or "",
            duration_ms=int(duration_ms or 0), level=level, request=request,
            request_id=request_id, error_type=error_type)
        with self._lock:
            self._db.execute(
                "INSERT INTO tool_history (id, ts, tool, arguments, ok, summary, "
                "duration_ms, level, request, request_id, error_type) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (entry.id, entry.ts, entry.tool,
                 json.dumps(entry.arguments, ensure_ascii=False), int(entry.ok),
                 entry.summary, entry.duration_ms, entry.level, entry.request,
                 entry.request_id, entry.error_type))
            self._db.execute(
                "DELETE FROM tool_history WHERE id NOT IN "
                "(SELECT id FROM tool_history ORDER BY ts DESC LIMIT ?)", (self.keep,))
            self._db.commit()
        return entry

    # --------------------------------------------------------------- lesen
    def list(self, limit: int = 50, tool: str | None = None,
             ok: bool | None = None) -> list[HistoryEntry]:
        limit = max(1, min(int(limit or 50), 1000))
        clauses, params = [], []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if ok is not None:
            clauses.append("ok = ?")
            params.append(int(ok))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM tool_history {where} ORDER BY ts DESC LIMIT ?",
                params).fetchall()
        return [HistoryEntry(
            id=r["id"], ts=r["ts"], tool=r["tool"],
            arguments=json.loads(r["arguments"] or "{}"), ok=bool(r["ok"]),
            summary=r["summary"], duration_ms=r["duration_ms"], level=r["level"],
            request=r["request"], request_id=r["request_id"],
            error_type=r["error_type"]) for r in rows]

    def stats(self, limit: int = 50) -> list[dict[str, Any]]:
        """Je Werkzeug: Aufrufe, Erfolgsquote, mittlere Dauer. Die Grundlage
        für „welche Tools benutzt du eigentlich" und für den Health-Check."""
        with self._lock:
            rows = self._db.execute(
                "SELECT tool, COUNT(*) AS aufrufe, SUM(ok) AS erfolge, "
                "AVG(duration_ms) AS dauer, MAX(ts) AS zuletzt "
                "FROM tool_history GROUP BY tool "
                "ORDER BY aufrufe DESC LIMIT ?", (max(1, int(limit or 50)),)).fetchall()
        return [{"werkzeug": r["tool"], "aufrufe": r["aufrufe"],
                 "erfolge": r["erfolge"] or 0,
                 "erfolgsquote": round((r["erfolge"] or 0) / r["aufrufe"], 3),
                 "dauer_ms": round(r["dauer"] or 0),
                 "zuletzt": r["zuletzt"]} for r in rows]

    def recent_tools(self, limit: int = 20) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT tool, MAX(ts) AS zuletzt FROM tool_history "
                "GROUP BY tool ORDER BY zuletzt DESC LIMIT ?",
                (max(1, int(limit or 20)),)).fetchall()
        return [r["tool"] for r in rows]

    # ----------------------------------------------------------- Favoriten
    def favorites(self) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT tool FROM tool_favorites ORDER BY ts DESC").fetchall()
        return [r["tool"] for r in rows]

    def favorite(self, tool: str) -> bool:
        with self._lock:
            self._db.execute(
                "INSERT INTO tool_favorites (tool, ts) VALUES (?,?) "
                "ON CONFLICT(tool) DO NOTHING", (tool, time.time()))
            self._db.commit()
        return True

    def unfavorite(self, tool: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM tool_favorites WHERE tool=?", (tool,))
            self._db.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------- Ab-/Anschalten
    def disabled(self) -> dict[str, str]:
        """Vom Nutzer abgeschaltete Werkzeuge (Punkt 26: ``jarvis.tools.disable``).

        Das ist ausdrücklich **keine** Sicherheitsfunktion -- eine Stufe
        weniger als das Permission-System, nicht eine mehr. Es geht darum,
        Werkzeuge aus dem Weg zu räumen, die man nicht benutzen will.
        """
        with self._lock:
            rows = self._db.execute("SELECT tool, reason FROM tool_disabled").fetchall()
        return {r["tool"]: r["reason"] for r in rows}

    def disable(self, tool: str, reason: str = "") -> bool:
        if tool in PROTECTED:
            raise ValueError(f"{tool} lässt sich nicht abschalten -- sonst gäbe es "
                             "keinen Weg mehr zurück.")
        with self._lock:
            self._db.execute(
                "INSERT INTO tool_disabled (tool, ts, reason) VALUES (?,?,?) "
                "ON CONFLICT(tool) DO UPDATE SET reason=excluded.reason",
                (tool, time.time(), reason))
            self._db.commit()
        return True

    def enable(self, tool: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM tool_disabled WHERE tool=?", (tool,))
            self._db.commit()
        return cur.rowcount > 0
