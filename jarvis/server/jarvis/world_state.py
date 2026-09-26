"""World State (Punkt 13): ein Schnappschuss dessen, was Jarvis über die
reale Umgebung gerade wirklich weiß.

Bewusst nur Felder, die heute tatsächlich messbar sind. Das Beispiel der
Aufgabenstellung nennt auch ``active_app``/``current_project`` -- das setzt
Screen/Context Awareness voraus (Phase 4, nicht gebaut) und wird hier nicht
vorgetäuscht. Was drinsteht, kommt aus echten, schon vorhandenen Quellen:
``tools/system.py``s Telemetrie und Ollamas eigenem Health-Check.
"""

from __future__ import annotations

from typing import Any

from .goals import GoalManager, GoalStatus
from .ollama import Health
from .tools import system as system_tools


def snapshot(health: Health | None, goals: GoalManager) -> dict[str, Any]:
    telemetry = system_tools.telemetry()
    aktive = goals.list(limit=100, status=GoalStatus.RUNNING)
    return {
        "system": telemetry or {"hinweis": "psutil nicht installiert"},
        "ollama_erreichbar": bool(health and health.online),
        "aktive_ziele": len(aktive),
    }


def as_text(state: dict[str, Any]) -> str:
    """Kurzform für den Planungskontext -- kein Ersatz für einen echten
    Werkzeugaufruf, nur Orientierung, bevor geplant wird (ANALYZE)."""
    system = state.get("system") or {}
    parts = []
    if "cpu" in system:
        parts.append(f"CPU {system['cpu']:.0f}%")
    if "ram" in system:
        parts.append(f"RAM {system['ram']['used']}/{system['ram']['total']} GB")
    parts.append("Ollama erreichbar" if state.get("ollama_erreichbar") else "Ollama nicht erreichbar")
    parts.append(f"{state.get('aktive_ziele', 0)} aktive Ziele")
    return ", ".join(parts)
