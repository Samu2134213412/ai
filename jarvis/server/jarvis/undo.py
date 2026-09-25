"""Undo/Rollback: rückgängig machen, was ein Werkzeug verändert hat.

Zwei Phasen, weil manche Werkzeuge ihren tatsächlichen Zielpfad erst nach der
Ausführung kennen (``move_file`` hängt den Dateinamen an, wenn das Ziel ein
Verzeichnis ist; ``memory_add`` vergibt seine ``id`` erst beim Schreiben):

1. **capture** -- unmittelbar bevor ein Werkzeug läuft: Zustand einsammeln,
   solange er noch da ist (der Inhalt einer Datei, bevor sie überschrieben
   oder gelöscht wird; der bisherige Inhalt einer Erinnerung, bevor sie
   verschwindet).
2. **finalize** -- nachdem das Werkzeug erfolgreich gelaufen ist: den
   Snapshot mit dem tatsächlichen Ergebnis (``ToolResult.evidence``)
   vervollständigen und als Datensatz ablegen.

Ein Snapshot, der nicht gelingt, blockiert die eigentliche Aktion nie --
er bedeutet nur, dass diese eine Aktion sich hinterher nicht rückgängig
machen lässt. Das ist ehrlicher als ein Snapshot, der etwas vortäuscht.

Pfade werden genau wie die Werkzeuge selbst über ``Workspace.resolve``
aufgelöst (siehe ``UndoContext``) -- keine eigene, zweite Pfadlogik neben
``tools/files.py``.
"""

from __future__ import annotations

import base64
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class UndoError(Exception):
    """Rückgängigmachen ist nicht möglich oder selbst fehlgeschlagen."""


@dataclass
class UndoContext:
    """Was die Strategien brauchen, um genau wie die Werkzeuge selbst zu
    handeln. ``workspace`` und ``store`` sind optional, weil ein Aufruf ohne
    sie (z. B. in einem Test) einfach kein Undo anbietet, statt zu werfen."""

    workspace: Any = None  # jarvis.tools.files.Workspace
    store: Any = None      # jarvis.memory.MemoryStore


@dataclass(frozen=True)
class UndoRecord:
    id: str
    ts: float
    tool: str
    description: str
    snapshot: dict[str, Any]
    undone: bool = False


@dataclass(frozen=True)
class UndoStrategy:
    #: Vor der Ausführung. ``None`` heißt: nichts zu sichern (z. B. wenn die
    #: Zieldatei noch nicht existiert) oder Voraussetzungen fehlen.
    capture: Callable[[dict, UndoContext], dict | None]
    #: Nach erfolgreicher Ausführung. Bekommt den rohen Snapshot und das
    #: ``ToolResult``; gibt den endgültigen Snapshot zurück oder ``None``.
    finalize: Callable[[dict, Any], dict | None]
    #: Macht die Aktion rückgängig und gibt einen Satz für den Nutzer zurück.
    revert: Callable[[dict, UndoContext], str]


def _identity_finalize(pre: dict, _result: Any) -> dict | None:
    return pre


# ───────────────────────────────────────────────────────────── write_file
def _capture_write_file(arguments: dict, ctx: UndoContext) -> dict | None:
    if ctx.workspace is None:
        return None
    target = ctx.workspace.resolve(arguments.get("path", ""))
    if target.exists() and target.is_file():
        return {"path": str(target), "existed": True,
                "content_b64": base64.b64encode(target.read_bytes()).decode("ascii")}
    return {"path": str(target), "existed": False}


def _revert_write_file(snap: dict, _ctx: UndoContext) -> str:
    path = Path(snap["path"])
    if snap["existed"]:
        path.write_bytes(base64.b64decode(snap["content_b64"]))
        return f"Vorherigen Inhalt wiederhergestellt: {path}"
    if path.exists():
        path.unlink()
    return f"Neu angelegte Datei wieder entfernt: {path}"


# ──────────────────────────────────────────────────────────── delete_file
def _capture_delete_file(arguments: dict, ctx: UndoContext) -> dict | None:
    if ctx.workspace is None:
        return None
    target = ctx.workspace.resolve(arguments.get("path", ""))
    if not target.exists() or not target.is_file():
        return None  # das Werkzeug wird ohnehin scheitern -- kein Snapshot nötig
    return {"path": str(target),
            "content_b64": base64.b64encode(target.read_bytes()).decode("ascii")}


def _revert_delete_file(snap: dict, _ctx: UndoContext) -> str:
    path = Path(snap["path"])
    if path.exists():
        raise UndoError(
            f"Am Pfad liegt inzwischen eine neue Datei: {path}. "
            "Rückgängigmachen abgebrochen, um sie nicht zu überschreiben.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(snap["content_b64"]))
    return f"Gelöschte Datei wiederhergestellt: {path}"


# ────────────────────────────────────────────────────────────── move_file
def _capture_move_file(arguments: dict, ctx: UndoContext) -> dict | None:
    if ctx.workspace is None:
        return None
    source = ctx.workspace.resolve(arguments.get("source", ""))
    if not source.exists():
        return None
    return {"source": str(source)}


def _finalize_move_file(pre: dict, result: Any) -> dict | None:
    nach = (result.evidence or {}).get("nach")
    if not nach:
        return None
    return {"source": pre["source"], "destination": nach}


def _revert_move_file(snap: dict, _ctx: UndoContext) -> str:
    dest = Path(snap["destination"])
    source = Path(snap["source"])
    if not dest.exists():
        raise UndoError(f"Verschobene Datei ist nicht mehr da: {dest}")
    if source.exists():
        raise UndoError(
            f"Am ursprünglichen Pfad liegt inzwischen eine neue Datei: {source}. "
            "Rückgängigmachen abgebrochen, um sie nicht zu überschreiben.")
    source.parent.mkdir(parents=True, exist_ok=True)
    dest.rename(source)
    return f"Zurückverschoben nach {source}"


# ───────────────────────────────────────────────────────────── memory_add
def _capture_memory_add(_arguments: dict, ctx: UndoContext) -> dict | None:
    return {} if ctx.store is not None else None  # nichts vor der Erstellung zu sichern


def _finalize_memory_add(_pre: dict, result: Any) -> dict | None:
    node_id = (result.evidence or {}).get("id")
    return {"id": node_id} if node_id else None


def _revert_memory_add(snap: dict, ctx: UndoContext) -> str:
    if ctx.store is None:
        raise UndoError("Kein Gedächtnis verfügbar.")
    if not ctx.store.delete(snap["id"]):
        raise UndoError(f"Erinnerung ist nicht mehr da: {snap['id']}")
    return "Neu angelegte Erinnerung wieder entfernt"


# ────────────────────────────────────────────────────────── memory_forget
def _capture_memory_forget(arguments: dict, ctx: UndoContext) -> dict | None:
    if ctx.store is None:
        return None
    node = ctx.store.get(arguments.get("id", ""))
    if node is None:
        return None
    # Alle Felder sichern, nicht nur die vier ursprünglichen -- sonst würde
    # Rückgängigmachen die Wichtigkeit/Quelle/Sicherheit stillschweigend auf
    # die Vorgabe zurücksetzen, statt den Knoten wirklich wiederherzustellen.
    # "expires" gehört dazu: sonst würde eine vergessene Sitzungs-Erinnerung
    # beim Rückgängigmachen zu einer dauerhaften.
    return {"id": node.id, "label": node.label, "kind": node.kind, "text": node.text,
            "importance": node.importance, "source": node.source,
            "confidence": node.confidence, "expires": node.expires}


def _revert_memory_forget(snap: dict, ctx: UndoContext) -> str:
    if ctx.store is None:
        raise UndoError("Kein Gedächtnis verfügbar.")
    if ctx.store.get(snap["id"]) is not None:
        raise UndoError(f"Am Platz der gelöschten Erinnerung steht inzwischen etwas Neues: {snap['id']}")
    ctx.store.add(node_id=snap["id"], label=snap["label"], kind=snap["kind"], text=snap["text"],
                  importance=snap.get("importance", 0.5), source=snap.get("source", ""),
                  confidence=snap.get("confidence", 1.0), expires=snap.get("expires"))
    return f"Erinnerung wiederhergestellt: {snap['label']}"


STRATEGIES: dict[str, UndoStrategy] = {
    "write_file": UndoStrategy(_capture_write_file, _identity_finalize, _revert_write_file),
    "delete_file": UndoStrategy(_capture_delete_file, _identity_finalize, _revert_delete_file),
    "move_file": UndoStrategy(_capture_move_file, _finalize_move_file, _revert_move_file),
    "memory_add": UndoStrategy(_capture_memory_add, _finalize_memory_add, _revert_memory_add),
    "memory_forget": UndoStrategy(_capture_memory_forget, _identity_finalize, _revert_memory_forget),
}


_SCHEMA = """
CREATE TABLE IF NOT EXISTS undo_log (
    id          TEXT PRIMARY KEY,
    ts          REAL NOT NULL,
    tool        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    snapshot    TEXT NOT NULL,
    undone      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_undo_ts ON undo_log(ts);
"""


def _row_to_record(row: sqlite3.Row) -> UndoRecord:
    import json
    return UndoRecord(id=row["id"], ts=row["ts"], tool=row["tool"],
                      description=row["description"],
                      snapshot=json.loads(row["snapshot"]), undone=bool(row["undone"]))


class UndoStore:
    """Sammelt Snapshots ein und macht sie auf Zuruf rückgängig.

    Eine SQLite-Datei, wie ``MemoryStore`` und ``AuditLog`` -- überlebt einen
    Neustart, damit "die letzte Änderung" nicht am Serverneustart endet.
    """

    def __init__(self, path: str | Path = ":memory:", context: UndoContext | None = None):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self.context = context or UndoContext()

    def close(self) -> None:
        self._db.close()

    # -- vor/nach der Ausführung --------------------------------------------
    def begin(self, tool: str, arguments: dict) -> dict | None:
        """Vor der Ausführung. Wirft nie -- ein Fehlschlag heißt nur "kein Undo"."""
        strategy = STRATEGIES.get(tool)
        if strategy is None:
            return None
        try:
            return strategy.capture(dict(arguments or {}), self.context)
        except Exception:  # noqa: BLE001 - Snapshot-Fehler dürfen nie durchschlagen
            return None

    def finish(self, tool: str, description: str, pre_snapshot: dict | None,
              result: Any) -> UndoRecord | None:
        """Nach erfolgreicher Ausführung. ``None`` zurück, wenn nichts abzulegen war."""
        if pre_snapshot is None or not getattr(result, "ok", False):
            return None
        strategy = STRATEGIES.get(tool)
        if strategy is None:
            return None
        try:
            final = strategy.finalize(pre_snapshot, result)
        except Exception:  # noqa: BLE001 - dito
            return None
        if final is None:
            return None
        record = UndoRecord(id=uuid.uuid4().hex[:12], ts=time.time(), tool=tool,
                            description=description, snapshot=final)
        import json
        self._db.execute(
            "INSERT INTO undo_log (id, ts, tool, description, snapshot, undone) "
            "VALUES (?,?,?,?,?,0)",
            (record.id, record.ts, record.tool, record.description,
             json.dumps(record.snapshot, ensure_ascii=False)))
        self._db.commit()
        return record

    # -- abrufen / rückgängig machen ----------------------------------------
    def get(self, record_id: str) -> UndoRecord | None:
        row = self._db.execute("SELECT * FROM undo_log WHERE id=?", (record_id,)).fetchone()
        return _row_to_record(row) if row else None

    def list(self, limit: int = 20) -> list[UndoRecord]:
        limit = max(1, min(int(limit or 20), 200))
        rows = self._db.execute(
            "SELECT * FROM undo_log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_record(r) for r in rows]

    def last_undoable(self) -> UndoRecord | None:
        row = self._db.execute(
            "SELECT * FROM undo_log WHERE undone=0 ORDER BY ts DESC LIMIT 1").fetchone()
        return _row_to_record(row) if row else None

    def undo(self, record_id: str | None = None) -> str:
        """Macht einen Datensatz rückgängig -- den angegebenen, sonst den
        letzten noch nicht rückgängig gemachten. Wirft ``UndoError``, wenn es
        nichts zu tun gibt oder das Rückgängigmachen selbst scheitert."""
        record = self.get(record_id) if record_id else self.last_undoable()
        if record is None:
            raise UndoError("Es gibt nichts, das rückgängig gemacht werden könnte."
                           if not record_id else f"Unbekannter Datensatz: {record_id}")
        if record.undone:
            raise UndoError(f"Bereits rückgängig gemacht: {record.description}")
        strategy = STRATEGIES.get(record.tool)
        if strategy is None:
            raise UndoError(f"Für '{record.tool}' gibt es keine Undo-Strategie (mehr).")
        summary = strategy.revert(record.snapshot, self.context)
        self._db.execute("UPDATE undo_log SET undone=1 WHERE id=?", (record.id,))
        self._db.commit()
        return summary
