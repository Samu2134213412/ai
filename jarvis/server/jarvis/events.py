"""Event System (Punkt 8) und der proaktive Jarvis (Punkt 9).

Der Weg, den die Aufgabenstellung vorgibt:

    Ereignis -> Event Bus -> Regeln/Agent -> Entscheidung -> evtl. Aktion

Wichtig ist das "evtl.". Ein Ereignis ist eine **Beobachtung**, keine
Handlungsanweisung. Was daraus folgt, entscheidet hier deterministischer
Code anhand ausdruecklicher Regeln -- nicht das Modell. Und die Regel, die
darueber am meisten bestimmt, steht so in der Aufgabenstellung:

    "Jarvis darf nur bei bekannten, sicheren Ursachen selbst handeln.
     Bei riskanten oder unklaren Ursachen muss er fragen."

Deshalb ist ``Rule.known_cause`` per Vorgabe ``False``: eine Regel darf erst
dann ohne Rueckfrage handeln, wenn jemand sie ausdruecklich als bekannten,
sicheren Fall markiert hat. Alles andere landet als Vorschlag beim Nutzer.
Und selbst eine als sicher markierte Regel handelt nur ab Autonomiestufe 4
(``AutonomyLevel.PROACTIVE``) von sich aus -- darunter fragt Jarvis immer.

Der Bus selbst haelt keine Wahrheit fest. Er verteilt nur; was wirklich
passiert ist, steht wie immer im Audit Log und in den Werkzeugergebnissen.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .autonomy import AutonomyLevel

#: Schwere eines Ereignisses, aufsteigend. Eine Regel kann eine Mindestschwere
#: verlangen, damit eine Routinemeldung nicht dieselbe Reaktion ausloest wie
#: ein Absturz.
SEVERITIES = ("info", "warning", "error")


def _rank(severity: str) -> int:
    try:
        return SEVERITIES.index(severity)
    except ValueError:
        return 0


@dataclass(frozen=True)
class Event:
    """Etwas ist passiert. Mehr behauptet ein Event nicht."""

    kind: str
    source: str = ""
    severity: str = "info"
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "zeit": self.ts, "art": self.kind, "quelle": self.source,
                "schwere": self.severity, "daten": self.payload}


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Verteilt Ereignisse an alle Zuhoerer und merkt sich die letzten.

    Ein Zuhoerer, der wirft, stoppt die anderen nicht -- sonst haette ein
    kaputter Melder zur Folge, dass ein wichtiges Ereignis niemanden mehr
    erreicht.
    """

    def __init__(self, history: int = 100):
        self._handlers: list[Handler] = []
        self.recent: deque[Event] = deque(maxlen=history)

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: Event) -> Event:
        self.recent.append(event)
        for handler in list(self._handlers):
            try:
                await handler(event)
            except Exception:  # noqa: BLE001 - siehe Klassendoku
                continue
        return event


@dataclass(frozen=True)
class Rule:
    """Wann reagiert Jarvis worauf -- und ob er dabei fragen muss."""

    name: str
    kind: str
    #: Vorlage fuer das Ziel. ``{name}`` wird aus ``event.payload`` gefuellt.
    goal: str
    #: Nur wenn das ausdruecklich gesetzt ist, gilt die Ursache als bekannt
    #: und sicher -- die Voraussetzung fuer eigenstaendiges Handeln.
    known_cause: bool = False
    min_severity: str = "info"

    def matches(self, event: Event) -> bool:
        if _rank(event.severity) < _rank(self.min_severity):
            return False
        if self.kind.endswith("*"):
            return event.kind.startswith(self.kind[:-1])
        return event.kind == self.kind

    def goal_for(self, event: Event) -> str:
        try:
            return self.goal.format(**event.payload)
        except (KeyError, IndexError, ValueError):
            # Eine Vorlage mit einem Platzhalter, den das Ereignis nicht
            # mitbringt, wird unveraendert genommen statt zu scheitern --
            # lieber ein unscharfes Ziel als gar keine Reaktion.
            return self.goal


@dataclass(frozen=True)
class Proposal:
    """Was Jarvis aus einem Ereignis machen will. ``needs_approval`` ist die
    eigentliche Aussage: darf er, oder muss er fragen?"""

    event: Event
    rule: Rule
    goal: str
    needs_approval: bool
    reason: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "ziel": self.goal, "regel": self.rule.name,
                "braucht_zustimmung": self.needs_approval, "begruendung": self.reason,
                "ereignis": self.event.as_dict()}


#: Ein bewusst kleiner Vorrat. Alles hier ist ``known_cause=False`` -- also
#: fragt Jarvis. Wer will, dass er bei einem dieser Faelle selbst handelt,
#: setzt das ausdruecklich (und hebt die Autonomiestufe auf 4).
DEFAULT_RULES: tuple[Rule, ...] = (
    Rule(name="Programm abgestuerzt", kind="process.crashed", min_severity="warning",
         goal="Finde heraus, warum {name} abgestuerzt ist, und schlage eine Loesung vor."),
    Rule(name="Platte wird voll", kind="disk.low", min_severity="warning",
         goal="Finde heraus, was auf {mount} den meisten Platz belegt."),
    Rule(name="Werkzeug wiederholt gescheitert", kind="tool.failing", min_severity="warning",
         goal="Finde heraus, warum {tool} wiederholt fehlschlaegt."),
)


class ProactiveEngine:
    """Aus einem Ereignis wird ein Vorschlag -- oder nichts.

    Die Entscheidung ist deterministisch und in drei Saetzen erklaerbar:
    keine passende Regel -> nichts; Autonomiestufe unter 4 oder Ursache nicht
    ausdruecklich als sicher markiert -> fragen; sonst -> handeln.
    """

    def __init__(self, rules: tuple[Rule, ...] | list[Rule] | None = None):
        self.rules = list(DEFAULT_RULES if rules is None else rules)

    def rule_for(self, event: Event) -> Rule | None:
        for rule in self.rules:
            if rule.matches(event):
                return rule
        return None

    def react(self, event: Event, autonomy: AutonomyLevel) -> Proposal | None:
        rule = self.rule_for(event)
        if rule is None:
            return None
        if autonomy < AutonomyLevel.GOAL_PURSUIT:
            return Proposal(
                event=event, rule=rule, goal=rule.goal_for(event), needs_approval=True,
                reason=(f"Autonomiestufe {int(autonomy)} ({autonomy.label}) erlaubt keine "
                        "eigenstaendige Zielverfolgung."))
        if not rule.known_cause:
            return Proposal(
                event=event, rule=rule, goal=rule.goal_for(event), needs_approval=True,
                reason=("Die Ursache ist nicht als bekannt und sicher hinterlegt -- "
                        "bei unklaren Ursachen wird gefragt."))
        if autonomy < AutonomyLevel.PROACTIVE:
            return Proposal(
                event=event, rule=rule, goal=rule.goal_for(event), needs_approval=True,
                reason=(f"Eigenstaendiges Handeln auf ein Ereignis hin braucht "
                        f"Autonomiestufe 4; aktuell ist {int(autonomy)} gesetzt."))
        return Proposal(
            event=event, rule=rule, goal=rule.goal_for(event), needs_approval=False,
            reason=f"Bekannte, sichere Ursache laut Regel '{rule.name}'.")
