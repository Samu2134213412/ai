"""Kleine Helfer, die jedes Tool-Pack benutzt.

Bei mehreren hundert Werkzeugen entscheidet die Menge an Wiederholung
darüber, ob der Werkzeugkasten lesbar bleibt. Diese Helfer nehmen genau die
Wiederholung weg -- das JSON-Schema-Gerüst und das Zusammenbauen eines
``ToolResult`` -- und **nicht** die Sachlogik. Jedes Tool behält seine eigene
Implementierung; nur das Drumherum ist geteilt.
"""

from __future__ import annotations

from typing import Any

from ..base import ToolResult

STR: dict[str, Any] = {"type": "string"}
INT: dict[str, Any] = {"type": "integer"}
NUM: dict[str, Any] = {"type": "number"}
BOOL: dict[str, Any] = {"type": "boolean"}
LIST: dict[str, Any] = {"type": "array", "items": {"type": "string"}}


def text(description: str) -> dict[str, Any]:
    return {**STR, "description": description}


def integer(description: str) -> dict[str, Any]:
    return {**INT, "description": description}


def flag(description: str) -> dict[str, Any]:
    return {**BOOL, "description": description}


def params(*required: str, **properties: dict[str, Any]) -> dict[str, Any]:
    """Ein JSON-Schema-Objekt. Pflichtfelder zuerst als Namen, dann die
    Eigenschaften als Schlüsselwortargumente."""
    return {"type": "object", "properties": properties, "required": list(required)}


NO_PARAMS: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

#: Der Probelauf-Parameter ist überall gleich (Punkt 30).
DRY = flag("Nur zeigen, was passieren würde, ohne es zu tun")


def ok(tool: str, summary: str, payload: Any = None, **evidence: Any) -> ToolResult:
    return ToolResult(tool=tool, ok=True, summary=summary,
                      evidence={k: v for k, v in evidence.items() if v is not None},
                      payload=payload)


def planned(tool: str, summary: str, payload: Any = None, **evidence: Any) -> ToolResult:
    """Das Ergebnis eines Probelaufs. Ausdrücklich ``ok=True`` -- der Probelauf
    selbst ist gelungen --, aber mit ``probelauf=True`` im Beleg, damit weder
    Oberfläche noch Modell ihn für eine ausgeführte Änderung halten können."""
    return ToolResult(tool=tool, ok=True, summary=f"Probelauf: {summary}",
                      evidence={"probelauf": True,
                                **{k: v for k, v in evidence.items() if v is not None}},
                      payload=payload)


def table(rows: list[list[Any]], headers: list[str] | None = None,
          limit: int = 200) -> str:
    """Eine schlichte Textspalten-Darstellung für ``payload``.

    Das Modell liest ``payload``; eine ausgerichtete Tabelle ist dafür
    deutlich besser zu verwerten als JSON-Gewimmel, und der Mensch im
    Verlauf liest sie auch.
    """
    shown = rows[:limit]
    if headers:
        shown = [headers, *shown]
    if not shown:
        return "(nichts)"
    widths = [max(len(str(r[i])) for r in shown if i < len(r))
              for i in range(max(len(r) for r in shown))]
    lines = []
    for index, row in enumerate(shown):
        lines.append("  ".join(str(cell).ljust(widths[i])
                               for i, cell in enumerate(row)).rstrip())
        if headers and index == 0:
            lines.append("  ".join("-" * w for w in widths))
    if len(rows) > limit:
        lines.append(f"… und {len(rows) - limit} weitere")
    return "\n".join(lines)


def human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - von der Schleife abgedeckt
