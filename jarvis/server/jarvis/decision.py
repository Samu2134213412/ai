"""Decision Engine: mehrere mögliche Vorgehensweisen abwägen, bevor eine
gewählt wird (Punkt 3) -- vor allem für Selbstkorrektur (Punkt 6), wenn ein
Schritt gescheitert ist und nicht einfach derselbe Versuch wiederholt werden
soll.

Bewertet wird nach genau den Kriterien aus der Aufgabenstellung:
Erfolgswahrscheinlichkeit, Kosten, Risiko, Zeit -- und "bisherige Erfahrung",
was hier ein **echtes** Signal ist, kein erfundenes: die Erfolgsquote des
infrage kommenden Werkzeugs aus dem bestehenden ``AuditLog``. Kandidaten
schlägt das Modell vor (nach demselben robusten Muster wie ``planner.py``:
JSON erwartet, bei Unbrauchbarem ein ehrlicher Ein-Kandidat-Rückfall, nie
eine erfundene Auswahl), die Gewichtung und die Wahl selbst sind
deterministischer Code, keine zweite Modellanfrage."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .ollama import OllamaClient

DECISION_PROMPT = """\
Du schlägst mögliche Vorgehensweisen für ein Problem vor, damit eine davon \
ausgewählt werden kann. Antworte AUSSCHLIESSLICH mit einer JSON-Liste von \
2 bis 5 Objekten, ohne Erklärung drumherum, ohne Markdown. Jedes Objekt hat:
"beschreibung" (kurz, deutsch), "werkzeug" (Name eines Werkzeugs, das dafür \
passen würde, oder null), "erfolgswahrscheinlichkeit" (0 bis 1), \
"kosten" (0 bis 1, höher heißt aufwändiger), "risiko" ("LOW", "MEDIUM" oder \
"HIGH"), "zeit" (0 bis 1, höher heißt langsamer).

Beispiel für das Problem "Programm startet nicht":
[{"beschreibung": "Logs analysieren", "werkzeug": "read_file", \
"erfolgswahrscheinlichkeit": 0.6, "kosten": 0.2, "risiko": "LOW", "zeit": 0.2}, \
{"beschreibung": "Prozess prüfen", "werkzeug": "list_processes", \
"erfolgswahrscheinlichkeit": 0.5, "kosten": 0.1, "risiko": "LOW", "zeit": 0.1}, \
{"beschreibung": "Programm neu starten", "werkzeug": "run_command", \
"erfolgswahrscheinlichkeit": 0.4, "kosten": 0.3, "risiko": "MEDIUM", "zeit": 0.3}]
"""

_JSON_LIST = re.compile(r"\[.*\]", re.S)
_RISK_PENALTY = {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.0}

#: Gewichtung der Kriterien aus der Aufgabenstellung. Bewusst als benannte
#: Konstanten statt magischer Zahlen mitten in der Formel -- und damit auch
#: in Tests unabhängig überprüfbar.
WEIGHT_SUCCESS = 0.40
WEIGHT_COST = 0.15
WEIGHT_RISK = 0.15
WEIGHT_TIME = 0.10
WEIGHT_HISTORY = 0.20


@dataclass(frozen=True)
class Candidate:
    description: str
    tool: str | None = None
    success: float = 0.5
    cost: float = 0.5
    risk: str = "MEDIUM"
    time_cost: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return {"beschreibung": self.description, "werkzeug": self.tool,
                "erfolgswahrscheinlichkeit": self.success, "kosten": self.cost,
                "risiko": self.risk, "zeit": self.time_cost}


@dataclass(frozen=True)
class Decision:
    id: str
    ts: float
    problem: str
    chosen: Candidate
    candidates: list[Candidate]
    score: float
    goal_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "zeit": self.ts, "problem": self.problem,
            "gewaehlt": self.chosen.as_dict(), "score": round(self.score, 3),
            "kandidaten": [c.as_dict() for c in self.candidates], "goal_id": self.goal_id,
        }


def _clamp01(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _parse_candidates(text: str) -> list[Candidate]:
    match = _JSON_LIST.search(text or "")
    if not match:
        return []
    try:
        data = json.loads(match.group())
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    out: list[Candidate] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        description = str(item.get("beschreibung") or "").strip()
        if not description:
            continue
        tool = item.get("werkzeug")
        tool = str(tool).strip() if tool else None
        risk = str(item.get("risiko") or "MEDIUM").strip().upper()
        if risk not in _RISK_PENALTY:
            risk = "MEDIUM"
        out.append(Candidate(
            description=description, tool=tool or None,
            success=_clamp01(item.get("erfolgswahrscheinlichkeit")),
            cost=_clamp01(item.get("kosten")), risk=risk,
            time_cost=_clamp01(item.get("zeit"))))
    return out


_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id       TEXT PRIMARY KEY,
    ts       REAL NOT NULL,
    problem  TEXT NOT NULL,
    goal_id  TEXT,
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_goal ON decisions(goal_id);
"""


class DecisionLog:
    """Jede Entscheidung dauerhaft nachvollziehbar -- eigene Datei, gleiches
    Muster wie ``AuditLog``/``TaskManager``."""

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

    def record(self, decision: Decision) -> None:
        self._db.execute(
            "INSERT INTO decisions (id, ts, problem, goal_id, document) VALUES (?,?,?,?,?)",
            (decision.id, decision.ts, decision.problem, decision.goal_id,
             json.dumps(decision.as_dict(), ensure_ascii=False)))
        self._db.commit()

    def list(self, limit: int = 50, goal_id: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        if goal_id:
            rows = self._db.execute(
                "SELECT document FROM decisions WHERE goal_id=? ORDER BY ts DESC LIMIT ?",
                (goal_id, limit)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT document FROM decisions ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r["document"]) for r in rows]


class DecisionEngine:
    """Fragt das Modell nach Kandidaten, wählt deterministisch anhand der
    Kriterien der Aufgabenstellung -- die Auswahl selbst ist kein zweiter
    LLM-Aufruf und damit nachvollziehbar und reproduzierbar."""

    def __init__(self, client: OllamaClient, audit: AuditLog | None = None,
                log: DecisionLog | None = None):
        self.client = client
        self.audit = audit
        self.log = log or DecisionLog(":memory:")

    def _history_bonus(self, tool: str | None) -> float:
        """Erfolgsquote des Werkzeugs aus dem echten Audit Log -- "bisherige
        Erfahrung" ist hier eine reale Kennzahl, keine Erfindung. Ohne
        Historie oder ohne Werkzeug: neutral (0.5), weder Bonus noch Malus."""
        if not tool or self.audit is None:
            return 0.5
        entries = self.audit.query(tool=tool, limit=50)
        if not entries:
            return 0.5
        return sum(1 for e in entries if e.ok) / len(entries)

    def _score(self, candidate: Candidate) -> float:
        history = self._history_bonus(candidate.tool)
        risk_penalty = _RISK_PENALTY.get(candidate.risk, 0.5)
        return (WEIGHT_SUCCESS * candidate.success
               + WEIGHT_COST * (1 - candidate.cost)
               + WEIGHT_RISK * (1 - risk_penalty)
               + WEIGHT_TIME * (1 - candidate.time_cost)
               + WEIGHT_HISTORY * history)

    async def choose(self, problem: str, *, registry_names: set[str] | None = None,
                     goal_id: str | None = None) -> Decision:
        problem = (problem or "").strip()
        candidates: list[Candidate] = []
        if problem:
            try:
                turn = await self.client.chat([
                    {"role": "system", "content": DECISION_PROMPT},
                    {"role": "user", "content": problem},
                ])
                candidates = _parse_candidates(turn.text)
            except Exception:  # noqa: BLE001 - ein unerreichbares Modell darf
                # die Entscheidung nicht crashen lassen; der ehrliche
                # Ein-Kandidat-Rückfall unten übernimmt.
                candidates = []

        if registry_names is not None:
            candidates = [c for c in candidates if c.tool is None or c.tool in registry_names]
        if not candidates:
            # Kein brauchbarer Vorschlag -- ein einzelner, neutraler
            # Kandidat statt einer erfundenen Auswahl (dasselbe Prinzip wie
            # planner.plan()s Ein-Schritt-Rückfall).
            candidates = [Candidate(description=problem or "unverändert weitermachen")]

        scored = sorted(candidates, key=self._score, reverse=True)
        chosen = scored[0]
        decision = Decision(id=uuid.uuid4().hex[:12], ts=time.time(), problem=problem,
                           chosen=chosen, candidates=candidates, score=self._score(chosen),
                           goal_id=goal_id)
        self.log.record(decision)
        return decision
