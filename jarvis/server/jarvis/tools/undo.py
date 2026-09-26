"""Das Undo-Werkzeug: "Jarvis, mach die letzte Änderung rückgängig."

Die eigentliche Snapshot-/Wiederherstellungslogik lebt in ``jarvis.undo``
(``UndoStore``) und läuft für jeden mutierenden Aufruf automatisch mit --
über ``Agent._run_tool``, nicht über dieses Werkzeug. Dieses Werkzeug ist nur
die Bedienoberfläche dafür: die letzte (oder eine bestimmte) Aufzeichnung
rückgängig machen, oder die Liste ansehen.
"""

from __future__ import annotations

from ..permissions import PermissionLevel
from ..undo import UndoError, UndoStore
from .base import Tool, ToolError, ToolResult


def build(store: UndoStore) -> list[Tool]:

    def undo_last_action(record_id: str = "") -> ToolResult:
        try:
            summary = store.undo(record_id or None)
        except UndoError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            tool="undo_last_action", ok=True, summary=summary,
            evidence={"id": record_id or "(letzte)"})

    def list_undoable(limit: int = 10) -> ToolResult:
        records = store.list(limit=limit)
        lines = [f"{r.id}  {'[bereits rückgängig gemacht] ' if r.undone else ''}"
                f"{r.tool}: {r.description}" for r in records]
        return ToolResult(
            tool="list_undoable", ok=True,
            summary=f"{len(records)} protokollierte Änderungen",
            evidence={"anzahl": len(records)},
            payload="\n".join(lines) if lines else "(keine)")

    _str = {"type": "string"}
    return [
        Tool("undo_last_action",
             "Macht die letzte rückgängig machbare Änderung rückgängig, oder "
             "eine bestimmte über ihre id (siehe list_undoable).",
             {"type": "object", "properties": {"record_id": _str}, "required": []},
             undo_last_action, level=PermissionLevel.WRITE),
        Tool("list_undoable",
             "Listet die letzten rückgängig machbaren Änderungen mit ihrer id.",
             {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []},
             list_undoable, level=PermissionLevel.SAFE),
    ]
