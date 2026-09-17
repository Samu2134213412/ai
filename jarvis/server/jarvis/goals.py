"""Goal Manager: die äußere Hülle um ein selbstständig verfolgtes Ziel.

Bewusst **keine** zweite Ausführungsmaschine neben ``tasks.py``. Ein Goal
trägt, was ein Task nicht trägt -- Priorität, Deadline, Eltern-Ziel,
Erfolgs-/Fehlerbedingungen, Fortschritt in Prozent -- und verweist auf genau
eine ``Task`` (``tasks.py``) für seinen aktuellen Plan aus benannten
Schritten. Die eigentliche Ausführung, Retries und das Ereignis-Protokoll
bleiben, wo sie schon getestet sind: in ``agent.py``/``tasks.py``.

Die Zerlegung eines großen Ziels in Unterziele ist keine neue Funktion,
sondern ``planner.plan()`` (Phase 1) -- dasselbe „frage das Modell nach
einer JSON-Liste, falle bei Unbrauchbarem auf einen Ein-Schritt-Plan zurück"
gilt für ein Ziel genauso wie für einen Auftrag.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class GoalStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GoalBudget:
    """Grenzen, ohne die aus Selbstkorrektur eine Endlosschleife würde
    (Punkt 18). Die Zahlen aus dem Beispiel der Aufgabenstellung sind die
    Vorgabe."""

    max_steps: int = 50
    max_runtime_minutes: float = 30.0
    max_retries: int = 3
    max_tool_calls: int = 100

    def as_dict(self) -> dict[str, Any]:
        return {"max_steps": self.max_steps, "max_runtime_minutes": self.max_runtime_minutes,
                "max_retries": self.max_retries, "max_tool_calls": self.max_tool_calls}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "GoalBudget":
        raw = raw or {}
        defaults = cls()
        return cls(
            max_steps=int(raw.get("max_steps", defaults.max_steps)),
            max_runtime_minutes=float(raw.get("max_runtime_minutes",
                                              defaults.max_runtime_minutes)),
            max_retries=int(raw.get("max_retries", defaults.max_retries)),
            max_tool_calls=int(raw.get("max_tool_calls", defaults.max_tool_calls)))


@dataclass
class Goal:
    id: str
    description: str
    priority: int = 0
    status: GoalStatus = GoalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    deadline: float | None = None
    parent_goal: str | None = None
    #: IDs der `Task`s, die dieses Goal ausführen -- normalerweise genau eine;
    #: mehr als eine nur, wenn ein Goal nach einer Neuplanung (REFLECT) eine
    #: neue Task für einen neuen Plan bekommt.
    subtasks: list[str] = field(default_factory=list)
    progress: float = 0.0
    current_step: str = ""
    success_conditions: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    budget: GoalBudget = field(default_factory=GoalBudget)
    error: str = ""
    #: Working Memory (Punkt 14): was während der Ausführung wichtig war --
    #: letzte Aktionen/Fehler/Entscheidungen. Bewusst flüchtig-persistiert
    #: zusammen mit dem Goal, nicht im Langzeitgedächtnis (das ist
    #: `MemoryStore`, siehe agent.py für die Trennung).
    working_memory: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "beschreibung": self.description, "prioritaet": self.priority,
            "status": self.status.value, "erstellt": self.created_at,
            "aktualisiert": self.updated_at, "frist": self.deadline,
            "eltern_ziel": self.parent_goal, "unteraufgaben": self.subtasks,
            "fortschritt": self.progress, "aktueller_schritt": self.current_step,
            "erfolgsbedingungen": self.success_conditions,
            "fehlerbedingungen": self.failure_conditions,
            "budget": self.budget.as_dict(), "fehler": self.error,
            "arbeitsspeicher": self.working_memory,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Goal":
        return cls(
            id=raw["id"], description=raw["beschreibung"],
            priority=raw.get("prioritaet", 0), status=GoalStatus(raw["status"]),
            created_at=raw["erstellt"], updated_at=raw["aktualisiert"],
            deadline=raw.get("frist"), parent_goal=raw.get("eltern_ziel"),
            subtasks=list(raw.get("unteraufgaben", [])),
            progress=raw.get("fortschritt", 0.0), current_step=raw.get("aktueller_schritt", ""),
            success_conditions=list(raw.get("erfolgsbedingungen", [])),
            failure_conditions=list(raw.get("fehlerbedingungen", [])),
            budget=GoalBudget.from_dict(raw.get("budget")), error=raw.get("fehler", ""),
            working_memory=dict(raw.get("arbeitsspeicher", {})))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id         TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status     TEXT NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    parent_goal TEXT,
    document   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_updated ON goals(updated_at);
CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal);
"""


class GoalManager:
    """Legt Goals an, hält sie aktuell -- Persistenz nach demselben Muster
    wie ``TaskManager``: ein JSON-Dokument pro Zeile, eigene SQLite-Datei."""

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

    def create(self, description: str, *, priority: int = 0, deadline: float | None = None,
              parent_goal: str | None = None, success_conditions: list[str] | None = None,
              failure_conditions: list[str] | None = None,
              budget: GoalBudget | None = None) -> Goal:
        goal = Goal(id=uuid.uuid4().hex[:12], description=description, priority=priority,
                   deadline=deadline, parent_goal=parent_goal,
                   success_conditions=list(success_conditions or []),
                   failure_conditions=list(failure_conditions or []),
                   budget=budget or GoalBudget())
        self.save(goal)
        return goal

    def save(self, goal: Goal) -> None:
        goal.updated_at = time.time()
        self._db.execute(
            "INSERT INTO goals (id, description, status, priority, created_at, updated_at, "
            "parent_goal, document) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
            "updated_at=excluded.updated_at, document=excluded.document",
            (goal.id, goal.description, goal.status.value, goal.priority, goal.created_at,
             goal.updated_at, goal.parent_goal, json.dumps(goal.as_dict(), ensure_ascii=False)))
        self._db.commit()

    def get(self, goal_id: str) -> Goal | None:
        row = self._db.execute("SELECT document FROM goals WHERE id=?", (goal_id,)).fetchone()
        return Goal.from_dict(json.loads(row["document"])) if row else None

    def list(self, limit: int = 20, status: GoalStatus | None = None) -> list[Goal]:
        limit = max(1, min(int(limit or 20), 500))
        if status is not None:
            rows = self._db.execute(
                "SELECT document FROM goals WHERE status=? "
                "ORDER BY priority DESC, updated_at DESC LIMIT ?",
                (status.value, limit)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT document FROM goals ORDER BY priority DESC, updated_at DESC LIMIT ?",
                (limit,)).fetchall()
        return [Goal.from_dict(json.loads(r["document"])) for r in rows]

    def children(self, parent_goal_id: str) -> list[Goal]:
        rows = self._db.execute(
            "SELECT document FROM goals WHERE parent_goal=? ORDER BY created_at",
            (parent_goal_id,)).fetchall()
        return [Goal.from_dict(json.loads(r["document"])) for r in rows]
