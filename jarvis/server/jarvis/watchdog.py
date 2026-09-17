"""Watchdog: erkennt, wenn ein Goal feststeckt, statt es endlos weiterlaufen
zu lassen (Punkt 19). Arbeitet zusammen mit ``goals.py``s ``GoalBudget``
(Punkt 18) -- beides zusammen ist die technische Umsetzung von "keine
Endlosschleifen", die die Selbstkorrektur (Punkt 6) erst sicher macht.

Ein Watchdog gehört zu **einem** laufenden Goal und wird bei jedem
Werkzeugaufruf bzw. jedem Schritt gefüttert. Er verändert nichts selbst --
er liefert nur ein ehrliches Urteil, das der Aufrufer (``agent.py``) in eine
Entscheidung umsetzt: weitermachen, oder mit einer klaren Begründung
aufhören."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .goals import GoalBudget

#: Wie oft dieselbe Aktion bzw. derselbe Fehler hintereinander auftreten darf,
#: bevor der Watchdog von einer Schleife statt einem normalen Versuch spricht.
REPEAT_THRESHOLD = 3
#: Wie viele der letzten Aufrufe für die Wiederholungserkennung betrachtet werden.
_WINDOW = 8


@dataclass(frozen=True)
class WatchdogVerdict:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - Bequemlichkeit
        return self.ok


_CONTINUE = WatchdogVerdict(ok=True)


def _signature(tool: str, arguments: dict[str, Any]) -> str:
    return f"{tool}({sorted((arguments or {}).items())})"


@dataclass
class _Call:
    tool: str
    signature: str
    ok: bool
    summary: str


@dataclass
class Watchdog:
    budget: GoalBudget = field(default_factory=GoalBudget)
    started_at: float = field(default_factory=time.time)
    step_count: int = 0
    tool_call_count: int = 0
    _recent: deque = field(default_factory=lambda: deque(maxlen=_WINDOW))

    def note_step(self) -> None:
        self.step_count += 1

    def note_tool_call(self, tool: str, arguments: dict[str, Any], ok: bool,
                       summary: str) -> None:
        self.tool_call_count += 1
        self._recent.append(_Call(tool=tool, signature=_signature(tool, arguments),
                                  ok=ok, summary=summary))

    def _repeated_action(self) -> str:
        if len(self._recent) < REPEAT_THRESHOLD:
            return ""
        tail = list(self._recent)[-REPEAT_THRESHOLD:]
        if len({c.signature for c in tail}) == 1 and not tail[-1].ok:
            return f"Dieselbe fehlgeschlagene Aktion wurde {REPEAT_THRESHOLD}x wiederholt: {tail[-1].tool}"
        return ""

    def _repeated_error(self) -> str:
        if len(self._recent) < REPEAT_THRESHOLD:
            return ""
        tail = list(self._recent)[-REPEAT_THRESHOLD:]
        failed = [c for c in tail if not c.ok]
        if len(failed) == REPEAT_THRESHOLD and len({c.summary for c in failed}) == 1:
            return f"Derselbe Fehler ist {REPEAT_THRESHOLD}x aufgetreten: {failed[0].summary}"
        return ""

    def verdict(self) -> WatchdogVerdict:
        """Darf das Goal weitermachen? Prüft Budgets zuerst (billig, klar),
        dann Wiederholungsmuster."""
        if self.step_count > self.budget.max_steps:
            return WatchdogVerdict(
                ok=False,
                reason=f"Schritt-Limit erreicht ({self.budget.max_steps} Schritte)")
        if self.tool_call_count > self.budget.max_tool_calls:
            return WatchdogVerdict(
                ok=False,
                reason=f"Werkzeugaufruf-Limit erreicht ({self.budget.max_tool_calls})")
        elapsed_minutes = (time.time() - self.started_at) / 60.0
        if elapsed_minutes > self.budget.max_runtime_minutes:
            return WatchdogVerdict(
                ok=False,
                reason=f"Zeitlimit erreicht ({self.budget.max_runtime_minutes} Minuten)")
        loop = self._repeated_action()
        if loop:
            return WatchdogVerdict(ok=False, reason=loop)
        stagnation = self._repeated_error()
        if stagnation:
            return WatchdogVerdict(ok=False, reason=stagnation)
        return _CONTINUE
