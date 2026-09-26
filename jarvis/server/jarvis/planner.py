"""Planner: zerlegt einen komplexen Auftrag in benannte Schritte, bevor
irgendetwas ausgeführt wird.

"Jarvis soll niemals einfach blind Befehle ausführen" (Punkt 1) heißt hier
konkret: erst steht ein für den Nutzer sichtbarer Plan, dann erst läuft der
Executor ihn ab. Fragt das Modell nach einer nummerierten Liste konkreter
Schritte; antwortet es nicht brauchbar (kein JSON, leer, kaputt), fällt der
Planer ehrlich auf einen Ein-Schritt-Plan zurück -- der bestehende
Werkzeugaufruf-Loop übernimmt dann einfach den ganzen Auftrag als einen
Schritt, statt einen Plan vorzutäuschen, den das Modell nicht geliefert hat.
"""

from __future__ import annotations

import json
import re

from .ollama import OllamaClient

MAX_STEPS = 10

PLANNER_PROMPT = """\
Du zerlegst eine Aufgabe in konkrete, nacheinander ausführbare Schritte.
Antworte AUSSCHLIESSLICH mit einer JSON-Liste von kurzen Schritt-\
Beschreibungen auf Deutsch, ohne Erklärung drumherum, ohne Markdown.
Höchstens 10 Schritte, so wenige wie für die Aufgabe nötig.

Beispiel für die Aufgabe "Bring dieses GitHub-Projekt zum Laufen":
["Repository prüfen", "Voraussetzungen erkennen", "Abhängigkeiten installieren", \
"Konfiguration prüfen", "Projekt starten", "Fehler analysieren", "Fehler beheben", \
"Erneut testen", "Ergebnis melden"]
"""

_JSON_LIST = re.compile(r"\[.*\]", re.S)


def _extract_steps(text: str) -> list[str] | None:
    match = _JSON_LIST.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    steps = [str(s).strip() for s in data if str(s).strip()]
    return steps or None


async def plan(client: OllamaClient, goal: str, max_steps: int = MAX_STEPS) -> list[str]:
    """Gibt eine Schrittliste zurück. Liefert das Modell keinen brauchbaren
    Plan, ist das Ergebnis eine Liste mit genau einem Eintrag: dem Auftrag
    selbst -- niemals eine leere Liste und niemals ein erfundener Plan."""
    goal = (goal or "").strip()
    if not goal:
        return []
    try:
        turn = await client.chat([
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": goal},
        ])
    except Exception:  # noqa: BLE001 - ein unerreichbares Modell darf die
        # Planung nicht crashen lassen; der Aufrufer bekommt stattdessen den
        # ehrlichen Ein-Schritt-Rückfall und der eigentliche Fehler zeigt
        # sich beim ersten Ausführungsversuch.
        return [goal]
    steps = _extract_steps(turn.text)
    if not steps:
        return [goal]
    return steps[:max(1, max_steps)]
