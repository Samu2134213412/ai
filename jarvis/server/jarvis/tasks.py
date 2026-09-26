"""Task Manager: ein komplexer Auftrag als Folge benannter, nachvollziehbarer
Schritte -- die Grundlage für den Agent Mode (Punkt 1 der Aufgabenstellung:
"Jeder Schritt soll intern nachvollziehbar sein").

Getrennt vom kurzen, flüchtigen ``Agent.history`` (den letzten paar
Chat-Runden): ein ``Task`` ist ein eigenständiger, persistenter Auftrag mit
einem Lebenszyklus, der einen Server-Neustart übersteht -- die Ablage, auf
der die spätere Task-Queue (Phase 7) aufbaut. Ein Task ist absichtlich ein
einzelnes JSON-Dokument pro Zeile statt zweier normalisierter Tabellen: die
Schrittzahl ist klein (Aufgabenstellung nennt bis zu neun), und "die ganze
Task neu schreiben" ist einfacher und robuster als Teil-Updates über zwei
Tabellen hinweg zu synchronisieren.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    result_summary: str = ""
    error: str = ""
    retries: int = 0
    started_at: float | None = None
    finished_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "beschreibung": self.description, "status": self.status.value,
            "ergebnis": self.result_summary, "fehler": self.error, "versuche": self.retries,
            "gestartet": self.started_at, "beendet": self.finished_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskStep":
        return cls(id=raw["id"], description=raw["beschreibung"],
                  status=StepStatus(raw.get("status", "pending")),
                  result_summary=raw.get("ergebnis", ""), error=raw.get("fehler", ""),
                  retries=raw.get("versuche", 0), started_at=raw.get("gestartet"),
                  finished_at=raw.get("beendet"))


@dataclass
class Task:
    id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: TaskStatus = TaskStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "ziel": self.goal, "status": self.status.value,
            "erstellt": self.created_at, "aktualisiert": self.updated_at,
            "schritte": [s.as_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        return cls(id=raw["id"], goal=raw["ziel"], status=TaskStatus(raw["status"]),
                  created_at=raw["erstellt"], updated_at=raw["aktualisiert"],
                  steps=[TaskStep.from_dict(s) for s in raw.get("schritte", [])])

    def current_step(self) -> TaskStep | None:
        for step in self.steps:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                return step
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    goal       TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    document   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);
"""


class TaskManager:
    """Legt Tasks an, hält sie aktuell, und ist die Task History."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # Punkt 17: dieselbe Begründung wie in ``goals.py`` -- seit Ziele
        # parallel im Hintergrund laufen, teilen sich Event-Loop und
        # Worker-Threads diese Verbindung.
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create(self, goal: str, step_descriptions: list[str]) -> Task:
        steps = [TaskStep(id=uuid.uuid4().hex[:8], description=d.strip())
                for d in step_descriptions if d and d.strip()]
        if not steps:
            steps = [TaskStep(id=uuid.uuid4().hex[:8], description=goal)]
        task = Task(id=uuid.uuid4().hex[:12], goal=goal, steps=steps)
        self.save(task)
        return task

    def save(self, task: Task) -> None:
        task.updated_at = time.time()
        document = json.dumps(task.as_dict(), ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (id, goal, status, created_at, updated_at, document) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
                "updated_at=excluded.updated_at, document=excluded.document",
                (task.id, task.goal, task.status.value, task.created_at, task.updated_at,
                 document))
            self._db.commit()

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._db.execute(
                "SELECT document FROM tasks WHERE id=?", (task_id,)).fetchone()
        return Task.from_dict(json.loads(row["document"])) if row else None

    def list(self, limit: int = 20, status: TaskStatus | None = None) -> list[Task]:
        limit = max(1, min(int(limit or 20), 500))
        with self._lock:
            if status is not None:
                rows = self._db.execute(
                    "SELECT document FROM tasks WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                    (status.value, limit)).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT document FROM tasks ORDER BY updated_at DESC LIMIT ?",
                    (limit,)).fetchall()
        return [Task.from_dict(json.loads(r["document"])) for r in rows]
