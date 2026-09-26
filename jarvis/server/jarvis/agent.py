"""Der Zug: von der Nachricht bis zur belegten Antwort.

Die Reihenfolge ist Absicht:

1. **Router.** Ist der Befehl eindeutig, läuft das Werkzeug sofort. Das Modell
   wird gar nicht erst gefragt und kann folglich auch nichts erfinden.
2. **Gedächtnis.** Passende Erinnerungen werden abgerufen und in den Kontext
   gelegt, bevor das Modell denkt.
3. **Agent.** Das Modell plant und ruft Werkzeuge auf. Jeder Aufruf erzeugt ein
   ``ToolResult``.
4. **Wächter.** Die Antwort entsteht aus den ``ToolResult``s. Behauptet das
   Modell etwas ohne Beleg, wird sein Text verworfen.

Der Systemprompt sagt dem Modell dieselbe Regel. Das ist der Gürtel. Der Wächter
ist der Hosenträger — und der hält auch, wenn das Modell den Gürtel ignoriert,
was der Vorgänger dieses Projekts zuverlässig getan hat.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import coder, complexity, guard, planner, router, world_state
from .audit import AuditLog
from .autonomy import AutonomyLevel
from .config import Config
from .decision import DecisionEngine
from .goals import Goal, GoalBudget, GoalManager, GoalStatus
from .macros import MacroEngine, MacroError, MacroStore
from .memory import MemoryStore
from .ollama import ChatTurn, OllamaClient, OllamaError
from .permissions import PermissionDenied, PermissionGate, PermissionLevel, PermissionPolicy
from .tasks import StepStatus, Task, TaskManager, TaskStatus
from .tools import Registry, ToolDiscovery, ToolHistory, ToolMissing, ToolResult
from .undo import UndoStore
from .verification import VerificationEngine
from .watchdog import Watchdog

Emit = Callable[[str, dict], Awaitable[None]]

SYSTEM_PROMPT = """\
Du bist Jarvis, ein persönlicher Assistent auf dem Rechner deines Nutzers.
Du antwortest auf Deutsch, knapp und direkt, ohne Floskeln.

Die wichtigste Regel:
Du darfst eine reale Aktion NUR dann als erledigt melden, wenn du dafür ein
Werkzeug aufgerufen hast UND dieses Werkzeug ERFOLG zurückgegeben hat.

- Willst du etwas an der Welt verändern — eine Datei schreiben, etwas löschen,
  ein Programm starten, dir etwas merken — dann rufe das passende Werkzeug auf.
  Beschreibe die Aktion nicht, führe sie aus.
- Gibt es für eine Aufgabe kein Werkzeug, dann sage genau das:
  "Das kann ich aktuell noch nicht ausführen, weil mir dafür kein Tool zur
  Verfügung steht." Denke dir keinen Umweg aus.
- Schlägt ein Werkzeug fehl, nenne den echten Fehler. Beschönige nichts.
- Behaupte niemals einen Erfolg, den du nicht als Werkzeugergebnis gesehen hast.

Programmieraufgaben kannst du selbst erledigen -- lies die Datei, ändere sie
mit write_file, und prüfe danach nach.
Reine Fragen beantwortest du ohne Werkzeug.
"""

# ── Eingriffe des Nutzers (Punkt 22) ───────────────────────────────────────
# Absichtlich hier und nicht in ``router.py``: der Router ordnet Text einem
# *Werkzeug* zu, hier geht es um die Steuerung eines schon laufenden Ziels.
# Die Muster greifen nur, wenn tatsächlich ein Ziel läuft (siehe ``interrupt``)
# -- sonst wäre ein harmloses "weiter" im Gespräch plötzlich ein Steuerbefehl.
_STOP = re.compile(
    r"^\s*(stopp?|halt|abbrechen|abbruch|brich\s+ab|h(ö|oe)r\s+auf|"
    r"mach\s+(et)?was\s+anderes)\b", re.I)
_PAUSE = re.compile(r"^\s*(pause|pausier(e|en)?|warte(\s+mal)?|moment)\b", re.I)
_RESUME = re.compile(r"^\s*(weiter|mach\s+weiter|weitermachen|fortsetzen|fortfahren)\b", re.I)
_ALTERNATIVE = re.compile(
    r"(versuch\w*\s+(es\s+|mal\s+)?(mit\s+)?(methode|weg|ansatz|variante|option)"
    r"|ander(en|e|er)\s+(ansatz|methode|weg|variante))", re.I)


#: Wie oft dasselbe Werkzeug hintereinander scheitern darf, bevor das als
#: Ereignis gemeldet wird (siehe ``Agent._note_reliability``).
_FAILURE_STREAK = 3

#: Die Policy des Fokus-Modus (siehe ``handle_code``): WRITE/SYSTEM laufen
#: ohne Bestätigung, solange er eingeschaltet ist. CRITICAL bleibt davon
#: unberührt -- ``requires_confirmation`` verlangt sie in jeder Policy immer,
#: das Feld gibt es hier absichtlich nicht (siehe ``permissions.py``). Das
#: ist keine Umgehung des Permission-Systems, sondern eine zweite, vom
#: Nutzer selbst per Schalter aktivierte Policy -- derselbe Hebel, den
#: ``confirm_write`` in ``jarvis.json`` schon immer war, nur zur Laufzeit
#: umschaltbar und ausdrücklich auf den Code-Modus begrenzt.
_FOCUS_POLICY = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)

#: Erweiterungsmodus (siehe ``start_extension_mode``): Pause zwischen zwei
#: Runden -- ohne sie würde die Schleife den lokalen Ollama-Server (und
#: damit die GPU) ohne Unterbrechung dauerbelasten, auch wenn der Nutzer
#: gerade selbst mit Jarvis spricht.
_EXTENSION_PAUSE_SECONDS = 60.0
#: Wie viele Runden in Folge ohne echten Fortschritt (keine Aufgabe erkannt,
#: oder ein Werkzeug ist gescheitert), bevor die Schleife sich selbst
#: anhält, statt unbeaufsichtigt gegen dieselbe Wand zu laufen.
_EXTENSION_FAILURE_LIMIT = 5

#: Session-Ebene zwischen Kurz- und Langzeitgedächtnis (ROADMAP Phase 2,
#: "noch ohne festgelegten Mechanismus"): Zug-Paare, die aus dem kurzlebigen
#: ``self.history``-Fenster fallen, landen als ``kind="sitzung"`` im
#: Gedächtnis statt spurlos zu verschwinden -- aber mit eigener Ablaufzeit,
#: damit sie den Wissensnetz nicht auf Dauer mit flüchtigem Chat-Kleinkram
#: vollstopfen. Zwei Tage: länger als eine einzelne Sitzung am Rechner,
#: kurz genug, dass es sich wirklich wie "vergessen" statt wie "gemerkt"
#: anfühlt, wenn niemand in der Zwischenzeit darauf zurückkommt.
_SESSION_TTL_HOURS = 48.0

_EXTENSION_PLANNING_PROMPT = """\
Du hilfst dabei, ein Softwareprojekt eigenständig weiterzuentwickeln, ohne \
dass jemand zusieht. Unten steht, was über das Projekt bekannt ist -- vor \
allem, was zuletzt daran gearbeitet wurde.

Nenne GENAU EINE konkrete, klein geschnittene Programmieraufgabe, die als \
Nächstes sinnvoll ist -- ein bis zwei Sätze, keine Erklärung drumherum, kein \
Code. Erfinde nichts: wenn sich aus dem, was du über das Projekt weißt, \
keine sinnvolle nächste Aufgabe ergibt, antworte ausschließlich mit den \
Worten "KEINE AUFGABE".
"""


def _tool_names(schemas: list[dict]) -> str:
    """Die aktuell angebotene Werkzeugauswahl als Text -- für die Meldung an
    das Modell, wenn es einen halluzinierten Namen aufruft."""
    return ", ".join(s["function"]["name"] for s in schemas)


class _GoalCancelled(Exception):
    """Der Nutzer hat abgebrochen. Kein Fehler -- eine Anweisung."""


@dataclass
class _GoalControl:
    """Der Griff, an dem ein laufendes Ziel von außen gehalten wird (Punkt 7
    und 22): Pause, Fortsetzen, Abbruch -- und ein Hinweis des Nutzers, der
    beim nächsten Schritt einfließt ("Nein, versuch Methode B").

    Bewusst kooperativ statt ``task.cancel()``: ein Abbruch mitten in einem
    laufenden Werkzeugaufruf würde die Welt in einem halben Zustand
    hinterlassen, den niemand protokolliert hat. Stattdessen gibt es feste
    Haltepunkte (``_checkpoint``) zwischen den Aktionen.
    """

    goal: Goal
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    run_event: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str = ""
    hint: str = ""

    def __post_init__(self) -> None:
        self.run_event.set()  # läuft, bis jemand pausiert


@dataclass
class _ExtensionControl:
    """Der Griff des Erweiterungsmodus -- dasselbe Pause/Fortsetzen/Abbruch-
    Muster wie ``_GoalControl``, aber für eine offene Folge kleiner
    Code-Aufträge statt für ein einzelnes Ziel: es gibt hier keinen
    ``Goal``, an dem sich Fortschritt/Budget aufhängen ließe, jeder Auftrag
    läuft für sich über ``handle_code``, das schon seine eigene
    Rundenbegrenzung mitbringt.
    """

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    run_event: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str = ""
    started_at: float = field(default_factory=time.time)
    rounds: int = 0
    failures: int = 0
    last_task: str = ""

    def __post_init__(self) -> None:
        self.run_event.set()

    def as_dict(self) -> dict[str, Any]:
        return {"laeuft": not self.cancel_event.is_set(),
                "pausiert": not self.run_event.is_set(),
                "runden": self.rounds, "fehlschlaege_in_folge": self.failures,
                "letzter_auftrag": self.last_task, "gestartet": self.started_at}


class Agent:
    def __init__(self, config: Config, store: MemoryStore, registry: Registry,
                 client: OllamaClient, emit: Emit | None = None,
                 history_turns: int = 12,
                 permission_gate: PermissionGate | None = None,
                 audit: AuditLog | None = None, undo: UndoStore | None = None,
                 tasks: TaskManager | None = None, max_step_retries: int = 2,
                 goals: GoalManager | None = None,
                 decisions: DecisionEngine | None = None,
                 verification: VerificationEngine | None = None,
                 code_client: OllamaClient | None = None,
                 fast_client: OllamaClient | None = None,
                 macros: MacroStore | None = None,
                 tool_history: ToolHistory | None = None,
                 discovery: ToolDiscovery | None = None):
        self.config = config
        self.store = store
        self.registry = registry
        self.client = client
        self.emit = emit or self._silent
        self.history: list[dict[str, Any]] = []
        self.history_turns = history_turns
        self.tasks = tasks or TaskManager(":memory:")
        #: Wie oft ein gescheiterter Schritt mit einem alternativen Ansatz neu
        #: versucht wird, bevor der ganze Auftrag als gescheitert gilt --
        #: "Setze ein Retry Limit. Keine Endlosschleifen." (Punkt 28).
        self.max_step_retries = max_step_retries
        # Ohne Angabe: sichere Voreinstellung bzw. reine In-Memory-Ablage, für
        # Aufrufer (Tests, Skripte), die sich um Berechtigung/Protokoll nicht
        # selbst kümmern -- app.py baut in Betrieb echte, dateibasierte
        # Instanzen und reicht sie hier hinein. Undo ist ein Sonderfall: eine
        # frisch angelegte ``UndoStore()`` ohne Workspace/Gedächtnis-Kontext
        # würde nie einen Snapshot aufnehmen (siehe ``UndoContext``), also
        # wird zuerst die schon richtig verkabelte Instanz von der Registry
        # übernommen (``build_registry`` legt sie dort immer ab) und nur ohne
        # eine solche Registry auf eine funktionslose Ablage zurückgefallen.
        self.permission_gate = permission_gate or PermissionGate(emit=self.emit)
        self.audit = audit or AuditLog(":memory:")
        self.undo = undo or getattr(registry, "undo_store", None) or UndoStore(":memory:")
        #: Werkzeug-Historie/Favoriten/Abschalten (``history.py``, Punkt 36).
        #: Wie bei ``undo`` zuerst die von der Registry mitgebrachte Instanz
        #: übernehmen -- so teilen sich Werkzeugaufruf und die
        #: ``jarvis.tools.*``-Meta-Werkzeuge dieselbe Ablage statt zweier
        #: SQLite-Verbindungen auf dieselbe Datei.
        self.tool_history = (tool_history or getattr(registry, "tool_history", None)
                             or ToolHistory(":memory:"))
        #: Die Werkzeugauswahl vor jeder Modellanfrage (``discovery.py``,
        #: Punkt 34/35) -- ohne sie ginge der volle Katalog (mehrere hundert
        #: Schemata) in jede Chat-Anfrage, was das Kontextfenster sprengt.
        self.discovery = (discovery or getattr(registry, "discovery", None)
                          or ToolDiscovery(registry, history=self.tool_history))
        # Autonomy V1. Die drei Maschinen sind bewusst hereinreichbar: app.py
        # gibt dateibasierte Instanzen, Tests bauen eigene.
        self.goals = goals or GoalManager(":memory:")
        self.decisions = decisions or DecisionEngine(client, audit=self.audit)
        self.verification = verification if verification is not None else VerificationEngine()
        #: Das Modell für den Code-Modus (``coder.py``). Ohne eigenes
        #: Code-Modell nimmt der Code-Modus schlicht das Chat-Modell -- das
        #: ist schlechter, aber es läuft, statt eine Absage zu sein.
        self.code_client = code_client or client
        #: Das kleine, schnelle Modell für einfache Fragen (``complexity.py``).
        #: Anders als beim Code-Modell KEIN Fallback auf ``client`` -- ohne
        #: eigenes schnelles Modell ist das Feature schlicht aus, nicht "das
        #: Hauptmodell tut so, als wäre es schnell".
        self.fast_client = fast_client
        #: Gespeicherte Makros (``macros.py``) -- eine feste Schrittfolge, die
        #: unter einem Namen läuft, ohne dass das Modell jedes Mal neu planen
        #: muss. Ohne eigene Ablage: reine In-Memory-Ablage, wie bei den
        #: übrigen Maschinen oben.
        self.macros = macros or MacroStore(":memory:")
        #: Laufende Ziele, über die von außen gesteuert werden kann.
        self._controls: dict[str, _GoalControl] = {}
        #: Die Hintergrund-Tasks -- gehalten, damit der Garbage Collector sie
        #: nicht einsammelt, solange sie laufen (asyncio hält nur schwache
        #: Referenzen auf Tasks).
        self._runners: set[asyncio.Task] = set()
        #: Punkt 17, "Verhindere Race Conditions bei Dateien und gemeinsamen
        #: Ressourcen": Seit Ziele im Hintergrund laufen, können zwei von
        #: ihnen gleichzeitig an derselben Datei arbeiten wollen. Verändernde
        #: Werkzeuge (WRITE und höher) laufen deshalb streng nacheinander --
        #: der Preis ist etwas weniger Parallelität, der Gewinn ist, dass ein
        #: Undo-Snapshot immer zu genau dem Zustand gehört, der gleich
        #: verändert wird. Lesen bleibt parallel.
        self._mutation_lock = asyncio.Lock()
        #: Der Event Bus, falls einer verkabelt ist (app.py). Ohne ihn
        #: verhält sich der Agent genau wie vorher -- er meldet dann nichts,
        #: statt zu scheitern.
        self.bus: Any = None
        #: Fehlschläge in Folge, je Werkzeug (siehe ``_note_reliability``).
        self._failure_streak: dict[str, int] = {}
        #: Fokus-Modus (siehe ``handle_code``/``set_focus_mode``): explizit
        #: vom Nutzer eingeschaltet, gilt nur für den Code-Modus, lebt nur im
        #: Arbeitsspeicher -- ein Serverneustart schaltet ihn wieder aus,
        #: genau wie eine Sitzung es nahelegt.
        self.focus_mode: bool = False
        #: Die laufende Erweiterungsmodus-Schleife, falls eine läuft (siehe
        #: ``start_extension_mode``). Nur eine gleichzeitig -- zwei Schleifen,
        #: die sich gegenseitig die Werkzeuge streitig machen, wären
        #: schwerer nachzuvollziehen als nützlich.
        self._extension: _ExtensionControl | None = None

    @staticmethod
    async def _silent(_kind: str, _payload: dict) -> None:
        return None

    async def _state(self, mode: str, detail: str = "") -> None:
        await self.emit("state", {"mode": mode, "detail": detail})

    async def set_focus_mode(self, on: bool) -> bool:
        """Schaltet den Fokus-Modus um (siehe ``_FOCUS_POLICY``) und meldet
        das als Ereignis, damit jedes verbundene Gerät den Zustand sieht --
        eine Policy, die niemand sieht, wäre keine bewusste Entscheidung des
        Nutzers mehr, sondern ein stiller Zustand."""
        self.focus_mode = bool(on)
        await self.emit("focus_mode", {"an": self.focus_mode})
        return self.focus_mode

    async def _run_tool(self, name: str, arguments: dict, request_text: str = "",
                        goal_id: str | None = None,
                        policy: PermissionPolicy | None = None) -> ToolResult:
        """Der eine Durchlauf für jeden Werkzeugaufruf -- Router-Direkttreffer,
        Chat-Loop und Code-Modus rufen alle diese eine Methode auf. Genau
        deshalb sitzen Permission-Check, Undo-Snapshot und Audit-Eintrag hier
        und nirgends sonst: kein Aufrufer kann sie versehentlich umgehen.

        Reihenfolge: Berechtigung prüfen (kann blockieren, bis eine Antwort
        kommt oder die Zeit abläuft) -> Snapshot für Undo -> ausführen ->
        protokollieren. Eine verweigerte Berechtigung wird zu einem ganz
        normalen fehlgeschlagenen ``ToolResult`` -- der Wächter behandelt sie
        dann genauso ehrlich wie jeden anderen Fehlschlag, ohne dass hier ein
        Sonderfall nötig wäre.
        """
        tool = self.registry.get(name)
        detail = f"{name}({', '.join(f'{k}={v}' for k, v in (arguments or {}).items())})"
        real_name = self.registry.resolve(name)

        # Abgeschaltet (Punkt 26, jarvis.tools.disable): eine Vorliebe des
        # Nutzers, keine Berechtigungsstufe -- deshalb vor der Autonomiestufe
        # geprüft, nicht als Sonderfall des Permission-Systems.
        abgeschaltet = self.tool_history.disabled()
        if real_name in abgeschaltet:
            result = ToolResult(
                tool=name, ok=False,
                summary=(f"{real_name} ist abgeschaltet"
                         + (f" ({abgeschaltet[real_name]})" if abgeschaltet[real_name] else "")
                         + " -- jarvis.tools.enable schaltet es wieder an."),
                evidence={"stufe": tool.level.label, "abgeschaltet": True})
            self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                              ok=False, summary=result.summary, request=request_text,
                              task_id=goal_id)
            return result

        # Autonomiestufe (autonomy.py) ist der Rahmen um das Permission-System
        # herum, nicht dessen Ersatz: Stufe 0 lässt gar nichts laufen, Stufe 1
        # erzwingt eine Bestätigung für WRITE+, selbst wenn die Policy sie
        # erlauben würde. Beides kann die Policy nur verschärfen, nie lockern.
        autonomy = self.config.autonomy
        if autonomy <= AutonomyLevel.NONE:
            result = ToolResult(
                tool=name, ok=False,
                summary=(f"Autonomiestufe {int(autonomy)} ({autonomy.label}): "
                         "Jarvis führt keine Aktionen aus, nur Gespräch."),
                evidence={"stufe": tool.level.label, "autonomiestufe": int(autonomy)})
            self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                              ok=False, summary=result.summary, request=request_text,
                              task_id=goal_id)
            return result
        force_confirm = (autonomy <= AutonomyLevel.READ_ONLY
                        and tool.level >= PermissionLevel.WRITE)

        try:
            await self.permission_gate.check(name, tool.level, arguments, detail=detail,
                                             force_confirm=force_confirm, policy=policy)
        except PermissionDenied as exc:
            result = ToolResult(tool=name, ok=False, summary=str(exc),
                                evidence={"stufe": tool.level.label, "verweigert": True})
            self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                              ok=False, summary=result.summary, request=request_text,
                              task_id=goal_id)
            return result

        # Snapshot, Ausführung und Undo-Eintrag gehören zusammen -- bei
        # verändernden Werkzeugen darf sich dazwischen nichts anderes
        # dazwischendrängen (siehe ``_mutation_lock``).
        if tool.level >= PermissionLevel.WRITE:
            async with self._mutation_lock:
                result = await self._execute(name, arguments)
        else:
            result = await self._execute(name, arguments)
        self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                          ok=result.ok, summary=result.summary, request=request_text,
                          task_id=goal_id)
        # Die werkzeugzentrierte Historie (Punkt 36) -- anders als das Audit
        # Log nur für tatsächlich gelaufene Aufrufe: eine verweigerte
        # Berechtigung hat keine echte Dauer und sagt nichts über die
        # Zuverlässigkeit des Werkzeugs selbst aus.
        self.tool_history.record(
            tool=real_name, arguments=arguments, ok=result.ok, summary=result.summary,
            duration_ms=result.duration_ms, level=tool.level.label,
            request=request_text, request_id=goal_id or "")
        self.discovery.note_use(real_name)
        await self._note_reliability(name, result)
        return result

    async def _note_reliability(self, name: str, result: ToolResult) -> None:
        """Das eine proaktive Beispiel, das heute schon echt ist (Punkt 8/9):
        Wenn dasselbe Werkzeug dreimal hintereinander scheitert, ist das eine
        beobachtbare Tatsache -- keine Vermutung, kein Sensor, den es nicht
        gibt. Daraus wird ein Ereignis; was daraus folgt, entscheidet die
        ``ProactiveEngine``, nicht diese Stelle hier.

        Genau einmal pro Fehlschlag-Serie, damit aus einer Meldung kein
        Dauerfeuer wird."""
        if result.ok:
            self._failure_streak.pop(name, None)
            return
        streak = self._failure_streak.get(name, 0) + 1
        self._failure_streak[name] = streak
        if streak != _FAILURE_STREAK or self.bus is None:
            return
        from .events import Event  # lokal: sonst importieren sich die Module im Kreis
        await self.bus.publish(Event(
            kind="tool.failing", source="agent", severity="warning",
            payload={"tool": name, "anzahl": streak, "letzter_fehler": result.summary}))

    async def _execute(self, name: str, arguments: dict) -> ToolResult:
        pre_snapshot = self.undo.begin(name, arguments or {})
        await self.emit("tool.started", {"tool": name, "arguments": arguments})
        result = await asyncio.to_thread(self.registry.call, name, arguments)
        await self.emit("tool.finished", result.as_event())
        self.undo.finish(name, result.summary, pre_snapshot, result)
        return result

    # ---------------------------------------------------------- Code-Modus
    async def handle_code(self, message: str, *, focus: bool | None = None) -> guard.Reply:
        """Ein Zug im Code-Modus: das Code-Modell arbeitet direkt an den
        Dateien, mit Jarvis' eigenen Werkzeugen.

        Kein Router, kein Chat-Modell -- der Nutzer hat den Modus bewusst
        eingeschaltet, das ist die eindeutigste Aussage, die es gibt. Aber
        auch kein Zwischenserver mehr: früher ging das über CodePilot
        Remote, und wenn der nicht eingerichtet war (der Normalfall), konnte
        der Code-Modus gar nichts. Siehe ``coder.py`` für die Begründung.

        Der Ablauf hier ist der Punkt, an dem sich Code-Modus und Chat
        unterscheiden: nach den Änderungen wird **nachgeprüft**, und die
        Antwort entsteht aus den geänderten Dateien plus dem Prüfergebnis --
        nicht aus dem Satz des Modells, es sei fertig.

        ``focus``: läuft dieser eine Aufruf mit der Fokus-Modus-Policy
        (``_FOCUS_POLICY``, WRITE/SYSTEM ohne Bestätigung, CRITICAL bleibt
        unberührt)? Ohne Angabe gilt der interaktive Schalter
        (``self.focus_mode``, siehe ``set_focus_mode``). Der Erweiterungsmodus
        (``start_extension_mode``) setzt ihn immer ausdrücklich auf ``True``
        -- er läuft unbeaufsichtigt, da kann niemand eine Bestätigung geben.
        """
        aktiver_fokus = self.focus_mode if focus is None else focus
        policy = _FOCUS_POLICY if aktiver_fokus else None
        task = (message or "").strip()
        if not task:
            return guard.Reply(text="", provenance=guard.TALK)

        # Die Autonomiestufe gilt hier genauso wie überall sonst: Stufe 0
        # redet nur, Stufe 1 lässt nichts schreiben, ohne zu fragen. Die
        # Durchsetzung sitzt in _run_tool, hier steht nur die ehrliche
        # Absage, bevor das große Modell überhaupt geladen wird.
        if self.config.autonomy <= AutonomyLevel.NONE:
            await self._state("idle")
            reply = guard.Reply(
                text=(f"Autonomiestufe 0 ({AutonomyLevel.NONE.label}): Ich führe "
                      "keine Aktionen aus, also auch keine Codeänderungen."),
                provenance=guard.TALK)
            self._remember(task, reply)
            return reply

        verfuegbar = [n for n in coder.CODE_TOOLS if n in self.registry]
        if not verfuegbar:
            await self._state("idle")
            reply = guard.Reply(
                text=f"{guard.REFUSAL} (im Code-Modus ist kein Dateiwerkzeug "
                     "registriert -- prüfe 'roots' in jarvis.json)",
                provenance=guard.FAIL)
            self._remember(task, reply)
            return reply

        await self._state("thinking", f"Code-Modell · {task[:60]}")
        try:
            text, results = await self._run_tool_loop(
                self._code_instruction(task), request_text=task,
                client=self.code_client, tool_names=verfuegbar,
                system_prompt=coder.CODE_SYSTEM_PROMPT,
                max_rounds=self.config.code.max_rounds, policy=policy)
        except OllamaError as exc:
            await self._state("failed", str(exc))
            reply = guard.Reply(
                text=f"Das Code-Modell ist nicht erreichbar: {exc}",
                provenance=guard.FAIL)
            self._remember(task, reply)
            return reply

        outcome = coder.CodeOutcome(changes=coder.changed_paths(results),
                                    model_text=text.strip())
        if self.config.code.auto_check and outcome.changes:
            await self._state("executing", "prüfe die Änderungen nach")
            results.extend(await self._check_changes(outcome, request_text=task))

        await self._state("failed" if outcome.broken else "idle")
        reply = guard.verify(outcome.summary(), results)
        if reply.blocked:
            await self.emit("guard.blocked", {
                "verworfen": reply.blocked_text, "ersetzt_durch": reply.text})
        self._remember_code_work(task, outcome)
        self._remember(task, reply)
        return reply

    async def run_macro(self, name: str) -> guard.Reply:
        """Führt ein gespeichertes Makro (``macros.py``) aus.

        Bewusst blockierend wie ``handle_code``, nicht Hintergrund wie
        ``start_goal``: ein Makro ist eine feste, im Voraus bekannte
        Schrittfolge mit harten Obergrenzen -- kein offenes, potenziell
        langes Ziel, das eine eigene Steuerung (Pause/Fortsetzen/Abbruch)
        bräuchte.

        Jeder Werkzeugschritt läuft über ``self._run_tool`` -- also mit
        Permission-Gate, Undo-Snapshot und Audit-Eintrag wie jeder andere
        Aufruf auch (siehe ``macros.py``-Docstring). Die Autonomiestufe wird
        hier vorab geprüft, damit bei Stufe 0 nicht erst eine Engine gebaut
        und dann jeder einzelne Schritt einzeln abgewiesen wird.
        """
        macro_name = (name or "").strip()
        definition = self.macros.get_by_name(macro_name)
        if definition is None:
            reply = guard.Reply(
                text=f"Kein Makro mit dem Namen '{macro_name}' gefunden.",
                provenance=guard.FAIL)
            self._remember(f"Makro: {macro_name}", reply)
            return reply

        if self.config.autonomy <= AutonomyLevel.NONE:
            await self._state("idle")
            reply = guard.Reply(
                text=(f"Autonomiestufe 0 ({AutonomyLevel.NONE.label}): Ich führe "
                      "keine Aktionen aus, also auch kein Makro."),
                provenance=guard.TALK)
            self._remember(f"Makro: {macro_name}", reply)
            return reply

        async def werkzeug_aufruf(tool_name: str, arguments: dict) -> ToolResult:
            return await self._run_tool(tool_name, arguments,
                                        request_text=f"Makro '{macro_name}'")

        await self._state("executing", f"Makro · {macro_name}")
        engine = MacroEngine(werkzeug_aufruf)
        try:
            lauf = await engine.run(definition.steps)
        except MacroError as exc:
            await self._state("failed", str(exc))
            reply = guard.Reply(
                text=f"Makro '{macro_name}' abgebrochen: {exc}", provenance=guard.FAIL)
            self._remember(f"Makro: {macro_name}", reply)
            return reply

        await self._state("failed" if not lauf.ok else "idle")
        reply = guard.verify(lauf.summary(macro_name), list(lauf.all_results))
        self._remember(f"Makro: {macro_name}", reply)
        return reply

    def _code_instruction(self, task: str) -> str:
        """Der Auftrag samt dem, was das Modell über den Arbeitsbereich wissen
        muss. Ohne diese Angabe rät ein Code-Modell Pfade -- und ein geratener
        Pfad wird vom Workspace abgewiesen, was eine Runde kostet."""
        roots = getattr(self.registry, "workspace", None)
        bereich = roots.describe() if roots is not None else "(unbekannt)"
        return (f"Arbeitsbereich (nur hier darfst du Dateien anfassen): {bereich}\n\n"
                f"Auftrag: {task}")

    async def _check_changes(self, outcome: "coder.CodeOutcome",
                             request_text: str) -> list[ToolResult]:
        """Liest jede geänderte Datei über ein echtes ``read_file`` zurück und
        prüft, was prüfbar ist.

        Derselbe Gedanke wie die Verification Engine in Autonomy V1: die
        Rückmeldung des schreibenden Werkzeugs allein ist zu wenig. Erst ein
        zweiter, unabhängiger Lesevorgang zeigt, was wirklich in der Datei
        steht.
        """
        geprueft: set[str] = set()
        results: list[ToolResult] = []
        for change in outcome.changes:
            if change.path in geprueft:
                continue
            geprueft.add(change.path)
            if Path(change.path).suffix.lower() not in coder.CHECKABLE:
                continue
            gelesen = await self._run_tool("read_file", {"path": change.path},
                                           request_text=request_text)
            results.append(gelesen)
            if not gelesen.ok:
                outcome.checks.append(coder.CodeCheck(
                    path=change.path, ok=False,
                    detail="nach dem Schreiben nicht lesbar"))
                continue
            check = coder.check_syntax(change.path, gelesen.payload or "")
            if check is None:
                continue
            outcome.checks.append(check)
            if not check.ok:
                # Ein kaputtes Ergebnis ist ein Fehlschlag, kein Erfolg mit
                # Fußnote -- also kommt es als fehlgeschlagenes ToolResult in
                # die Beweiskette und färbt die Antwort entsprechend.
                results.append(ToolResult(
                    tool="check:syntax", ok=False,
                    summary=f"{check.name}: {check.detail}",
                    evidence={"pfad": check.path}))
        return results

    async def _try_fast(self, messages: list[dict[str, Any]], text: str) -> guard.Reply | None:
        """Schneller Pfad für einfache Fragen ohne Werkzeugbedarf.

        Bewusst ohne Werkzeugschema: ein kleines Modell ruft Werkzeuge
        unzuverlässig auf (siehe README, Abschnitt "Warum nicht ein Modell für
        beides"), bekommt hier also gar keine Gelegenheit dazu. Behauptet es
        trotzdem eine Aktion, fängt ``guard.verify()`` das ab wie jede andere
        Antwort auch -- kein Sonderfall, dieselbe Regel.

        Gibt ``None`` zurück, wenn das schnelle Modell nicht erreichbar war
        oder nichts Verwertbares geliefert hat -- der Aufrufer fällt dann auf
        die normale Runde mit dem Hauptmodell zurück, statt aufzugeben.
        """
        await self._state("thinking", "schnelle Antwort")
        try:
            turn = await self.fast_client.chat(messages)
        except OllamaError:
            return None
        if not turn.text.strip():
            return None
        reply = guard.verify(turn.text, [])
        await self._state("idle")
        self._remember(text, reply)
        return reply

    # ------------------------------------------------------------------ Zug
    async def handle(self, message: str) -> guard.Reply:
        text = (message or "").strip()
        if not text:
            return guard.Reply(text="", provenance=guard.TALK)

        # 0. Greift der Nutzer in ein laufendes Ziel ein? Das hat Vorrang vor
        #    allem anderen -- "Stopp" darf nicht erst nach dem nächsten
        #    Werkzeugaufruf wirken (Punkt 22).
        interruption = await self.interrupt(text)
        if interruption is not None:
            self._remember(text, interruption)
            return interruption

        # 1. Eindeutiger Befehl? Dann direkt, ohne Modell.
        action = router.route(text)
        if action and action.tool in self.registry:
            await self._state("executing", f"{action.tool} · {action.detail}")
            result = await self._run_tool(action.tool, action.arguments, request_text=text)
            await self._state("idle")
            reply = guard.verify(self._phrase(result), [result])
            self._remember(text, reply)
            return reply

        # Der Router hat etwas erkannt, wofür das Werkzeug fehlt. Das ist eine
        # ehrliche Absage — und besser, als das Modell darüber fantasieren zu
        # lassen.
        if action and action.tool not in self.registry:
            await self._state("idle")
            return guard.Reply(
                text=f"{guard.REFUSAL} (benötigt: {action.tool})",
                provenance=guard.FAIL)

        # 2. Gedächtnis abrufen, bevor das Modell denkt.
        await self._state("thinking", "rufe Erinnerungen ab")
        context = await asyncio.to_thread(self.store.context_for, text)

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system",
                             "content": "Was du über deinen Nutzer weißt:\n" + context})
        messages.extend(self.history[-self.history_turns * 2:])
        messages.append({"role": "user", "content": text})

        # 2b. Einfache Frage, schnelles Modell konfiguriert? Dann dort zuerst
        # versuchen -- ohne Werkzeugschema, siehe complexity.py und _try_fast.
        if self.fast_client is not None and complexity.is_simple(text):
            fast_reply = await self._try_fast(messages, text)
            if fast_reply is not None:
                return fast_reply

        # Werkzeugauswahl über Discovery statt des vollen Katalogs (Punkt 35):
        # bei mehreren hundert Tools passen die vollständigen Schemata nicht
        # mehr ins Kontextfenster. Einmal berechnet, nicht pro Runde neu --
        # die Auswahl richtet sich nach der Nutzeranfrage, nicht danach,
        # welches Werkzeug die letzte Runde gerade aufgerufen hat. Findet das
        # Modell darunter nichts Passendes, steht ihm jarvis.tools.search
        # (immer in der Auswahl, siehe discovery.CORE_TOOLS) offen, um gezielt
        # nachzusuchen.
        schemas = self.discovery.schemas_for(text)

        results: list[ToolResult] = []
        final = ""
        try:
            for round_no in range(self.config.max_tool_rounds):
                await self._state("thinking",
                                  "plane" if round_no == 0 else f"plane weiter ({round_no + 1})")
                turn: ChatTurn = await self.client.chat(messages, schemas)

                if not turn.tool_calls:
                    final = turn.text
                    break

                messages.append({
                    "role": "assistant", "content": turn.text,
                    "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}}
                                   for c in turn.tool_calls]})
                for call in turn.tool_calls:
                    if call.name not in self.registry:
                        # Halluzinierter Werkzeugname. Das Modell erfährt es --
                        # mit der aktuell angebotenen Auswahl, nicht dem ganzen
                        # Katalog (der passt bei mehreren hundert Tools nicht
                        # mehr sinnvoll in eine Werkzeugantwort). jarvis.tools.
                        # search steht immer in der Auswahl, falls das Gesuchte
                        # nicht dabei war.
                        angeboten = _tool_names(schemas)
                        messages.append({
                            "role": "tool", "name": call.name,
                            "content": (f"FEHLGESCHLAGEN: Werkzeug '{call.name}' existiert "
                                        f"nicht oder steht gerade nicht zur Auswahl. Angeboten: "
                                        f"{angeboten}. Mit jarvis.tools.search lässt sich der "
                                        "ganze Werkzeugkasten durchsuchen.")})
                        continue
                    await self._state("executing", f"{call.name}")
                    result = await self._run_tool(call.name, call.arguments, request_text=text)
                    results.append(result)
                    messages.append({"role": "tool", "name": call.name,
                                     "content": result.for_model()})
            else:
                final = ("Ich habe die Aufgabe nach "
                         f"{self.config.max_tool_rounds} Schritten abgebrochen, "
                         "weil sie nicht zum Abschluss kam.")
        except OllamaError as exc:
            await self._state("failed", str(exc))
            return guard.Reply(text=f"Das Modell ist nicht erreichbar: {exc}",
                               provenance=guard.FAIL, results=results)
        except ToolMissing as exc:
            await self._state("failed")
            return guard.Reply(text=f"{guard.REFUSAL} (fehlt: {exc})",
                               provenance=guard.FAIL, results=results)

        # Ein Zug ohne Werkzeugaufruf und ohne Text ist kein Fehler des
        # Wächters, aber auch keine Antwort -- das Modell hat schlicht nichts
        # gesagt (z. B. bei "denkenden" Modellen, wenn der Kontext für die
        # eigentliche Antwort nicht mehr reichte). Das bekommt der Nutzer
        # ehrlich mitgeteilt, statt eine leere Sprechblase zu sehen.
        if not final.strip() and not results:
            final = ("Ich habe dazu keine Antwort vom Modell erhalten. Das kann "
                     "an einem zu knappen Kontext liegen (context_length in "
                     "jarvis.json) oder daran, dass das Modell nichts "
                     "Verwertbares zurückgegeben hat.")

        # 4. Der Wächter entscheidet, was rausgeht.
        reply = guard.verify(final, results)
        await self._state("failed" if reply.provenance == guard.FAIL else "idle")
        if reply.blocked:
            await self.emit("guard.blocked", {
                "verworfen": reply.blocked_text, "ersetzt_durch": reply.text})
        self._remember(text, reply)
        return reply

    # ═════════════════════════════════════════════ Zielverfolgung (Autonomy)
    #
    # Die Schleife aus Punkt 1 der Aufgabenstellung, mit den Phasen an genau
    # den Stellen, an denen sie etwas Reales tun:
    #
    #   GOAL          -- ``start_goal``/``handle_agent_task`` legen das Ziel an
    #   ANALYZE       -- ``_analyze``: echter Weltzustand, keine Vermutung
    #   PLAN          -- ``planner.plan`` (bestehend, Phase 1)
    #   SELECT ACTION -- das Modell wählt Werkzeuge; nach einem Fehlschlag
    #                    wählt stattdessen die ``DecisionEngine`` den nächsten
    #                    Ansatz deterministisch
    #   EXECUTE       -- ``_run_tool`` (bestehend: Berechtigung, Undo, Audit)
    #   VERIFY        -- ``VerificationEngine``: ein zweiter, unabhängiger
    #                    Werkzeugaufruf
    #   REFLECT       -- Retry mit dem echten Fehler als Kontext, Lehre ins
    #                    Gedächtnis, Watchdog-Urteil
    #   CONTINUE/FINISH
    #
    # Was hier *nicht* passiert: Das Modell darf an keiner Stelle den Zustand
    # eines Schrittes setzen. Ob ein Schritt gelungen ist, entscheidet
    # ausschließlich die Liste der ``ToolResult``s -- und, wo es einen
    # Verifizierer gibt, dessen unabhängige Nachprüfung.

    def _refuse_autonomy(self, goal: str = "", *, extension: bool = False) -> guard.Reply:
        """Die Stufe reicht nicht -- und nur der Nutzer darf sie anheben.

        Die Antwort trägt deshalb ein Angebot, aus dem die Oberfläche einen
        Knopf macht ("Stufe 3 erlauben und Ziel starten"): Der Nutzer
        bestätigt, die Oberfläche setzt die Stufe über ``PUT /api/autonomy``
        und schickt den Auftrag erneut. Jarvis selbst hebt die Stufe nie an --
        kein Werkzeug führt dorthin."""
        autonomy = self.config.autonomy
        return guard.Reply(
            text=(f"Autonomiestufe {int(autonomy)} ({autonomy.label}) erlaubt keine "
                  "eigenständige Zielverfolgung -- das braucht Stufe 3. Du kannst sie "
                  "hier direkt erlauben (bleibt gespeichert, zurückstellen im Regler "
                  "„Autonomie“), mir stattdessen einzelne Schritte sagen oder "
                  "autonomy_level in jarvis.json anheben."),
            provenance=guard.TALK,
            offer={"art": "autonomie", "stufe": int(AutonomyLevel.GOAL_PURSUIT),
                   "ziel": goal, "erweiterung": extension})

    async def handle_agent_task(self, goal: str, *, budget: GoalBudget | None = None
                                ) -> guard.Reply:
        """Zielverfolgung, auf den Abschluss gewartet.

        Der synchrone Einstieg: legt das Ziel an und arbeitet es hier und
        jetzt ab. Für den laufenden Betrieb ist ``start_goal`` der Weg (dort
        blockiert nichts), aber diese Variante bleibt -- sie ist der
        testbare, deterministische Kern, und Skripte, die auf das Ergebnis
        warten wollen, brauchen sie."""
        description = (goal or "").strip()
        if not description:
            return guard.Reply(text="", provenance=guard.TALK)
        if self.config.autonomy < AutonomyLevel.GOAL_PURSUIT:
            return self._refuse_autonomy(description)

        target, control = self._open_goal(description, budget=budget)
        reply = await self._pursue_goal(target, control)
        self._remember(description, reply)
        return reply

    async def start_goal(self, goal: str, *, budget: GoalBudget | None = None
                         ) -> tuple[Goal | None, guard.Reply]:
        """Zielverfolgung im Hintergrund (Punkt 7): Jarvis fängt an und
        antwortet sofort -- der Nutzer kann weiterreden, während gearbeitet
        wird.

        Die Zwischenmeldung behauptet nichts über ein Ergebnis, sie meldet
        nur, dass die Arbeit *begonnen* hat. Das ist keine Ausnahme von der
        Kernregel: Was am Ende herauskommt, meldet der Abschluss -- belegt
        durch die Werkzeugergebnisse, wie überall sonst."""
        description = (goal or "").strip()
        if not description:
            return None, guard.Reply(text="", provenance=guard.TALK)
        if self.config.autonomy < AutonomyLevel.GOAL_PURSUIT:
            return None, self._refuse_autonomy(description)

        target, control = self._open_goal(description, budget=budget)
        runner = asyncio.create_task(self._run_goal_in_background(target, control))
        self._runners.add(runner)
        runner.add_done_callback(self._runners.discard)
        return target, guard.Reply(
            text=(f"Ich arbeite daran: {description}. Du kannst mir in der "
                  "Zwischenzeit etwas anderes sagen -- \"Stopp\" oder \"Pause\" "
                  "gelten jederzeit."),
            provenance=guard.TALK)

    def _open_goal(self, description: str, *, budget: GoalBudget | None = None
                   ) -> tuple[Goal, _GoalControl]:
        target = self.goals.create(description, budget=budget)
        control = _GoalControl(goal=target)
        self._controls[target.id] = control
        return target, control

    async def _run_goal_in_background(self, target: Goal, control: _GoalControl) -> None:
        try:
            reply = await self._pursue_goal(target, control)
        except Exception as exc:  # noqa: BLE001 - ein Hintergrund-Task, der
            # lautlos stirbt, wäre das Gegenteil von nachvollziehbar.
            await self._state("failed", str(exc))
            reply = guard.Reply(text=f"Intern ist ein Fehler aufgetreten: {exc}",
                                provenance=guard.FAIL)
        # Der Nutzer wartet nicht auf diese Antwort -- also wird sie ihm
        # zugestellt statt zurückgegeben.
        await self.emit("message", {"who": "jarvis", **reply.as_event()})

    # ---------------------------------------------------------- Die Schleife
    async def _pursue_goal(self, target: Goal, control: _GoalControl) -> guard.Reply:
        watchdog = Watchdog(budget=target.budget)
        all_results: list[ToolResult] = []
        task: Task | None = None
        try:
            # ── ANALYZE ────────────────────────────────────────────────────
            target.status = GoalStatus.PLANNING
            self.goals.save(target)
            await self.emit("goal.created", target.as_dict())
            state = await self._analyze()
            target.working_memory["weltzustand"] = state

            # ── PLAN ───────────────────────────────────────────────────────
            await self._state("thinking", "plane die Schritte")
            step_texts = await planner.plan(self.client, target.description)
            task = self.tasks.create(target.description, step_texts)
            task.status = TaskStatus.RUNNING
            self.tasks.save(task)
            await self.emit("task.created", task.as_dict())

            target.subtasks.append(task.id)
            target.status = GoalStatus.RUNNING
            self.goals.save(target)
            await self.emit("goal.updated", target.as_dict())

            for index, step in enumerate(task.steps):
                await self._checkpoint(control)

                # ── Watchdog vor jedem Schritt (Punkt 18/19) ───────────────
                watchdog.note_step()
                verdict = watchdog.verdict()
                if not verdict.ok:
                    return await self._abort_goal(target, task, control, all_results,
                                                  verdict.reason, GoalStatus.BLOCKED)

                target.current_step = step.description
                target.progress = index / max(len(task.steps), 1)
                self.goals.save(target)

                await self._run_step(target, task, step, control, watchdog, all_results)

                if step.status is StepStatus.FAILED:
                    return await self._abort_goal(
                        target, task, control, all_results,
                        f"Schritt gescheitert: {step.description}. {step.error}",
                        GoalStatus.FAILED)

            # ── FINISH ─────────────────────────────────────────────────────
            task.status = TaskStatus.COMPLETED
            self.tasks.save(task)
            target.status = GoalStatus.COMPLETED
            target.progress = 1.0
            target.current_step = ""
            self.goals.save(target)
            await self._state("idle")
            await self.emit("task.finished", task.as_dict())
            await self.emit("goal.finished", target.as_dict())
            final_text = " ".join(s.result_summary for s in task.steps if s.result_summary)
            return guard.verify(final_text or "Alle Schritte abgeschlossen.", all_results)

        except _GoalCancelled as stop:
            return await self._abort_goal(target, task, control, all_results,
                                          str(stop), GoalStatus.CANCELLED)
        finally:
            self._controls.pop(target.id, None)

    async def _run_step(self, target: Goal, task: Task, step, control: _GoalControl,
                        watchdog: Watchdog, all_results: list[ToolResult]) -> None:
        """Ein Schritt: ausführen, prüfen, bei Fehlschlag einen anderen Weg
        wählen -- bis zum Retry-Limit (Punkt 6)."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        self.tasks.save(task)
        await self._state("executing", f"Schritt: {step.description}")
        await self.emit("task.step.started", {"task_id": task.id, **step.as_dict()})

        instruction = step.description
        if control.hint:
            # "Nein, versuch Methode B." -- der Hinweis des Nutzers geht in den
            # nächsten Schritt ein und wird dann verbraucht.
            instruction = f"{instruction}\n\nHinweis des Nutzers: {control.hint}"
            control.hint = ""

        # Nur die Ergebnisse des jeweils LETZTEN Versuchs zählen für das
        # Gesamturteil -- ein Versuch, der scheiterte und dann durch einen
        # anderen Ansatz ersetzt wurde, darf ein am Ende erfolgreiches
        # Ergebnis nicht rückwirkend als Fehlschlag erscheinen lassen.
        # Sichtbar bleibt er trotzdem: im "task.step.retry"-Ereignis, in
        # step.retries und im Audit Log (jeder Versuch läuft durch _run_tool
        # und wird dort unabhängig protokolliert).
        step_results: list[ToolResult] = []
        first_error = ""
        for attempt in range(self.max_step_retries + 1):
            await self._checkpoint(control)
            try:
                text, step_results = await self._run_tool_loop(
                    instruction, request_text=target.description,
                    watchdog=watchdog, control=control, goal_id=target.id)
            except OllamaError as exc:
                text, step_results = "", []
                step.error = f"Modell nicht erreichbar: {exc}"
            else:
                failed = [r for r in step_results if not r.ok]
                if not failed:
                    step.status = StepStatus.DONE
                    step.result_summary = text.strip() or (
                        step_results[-1].summary if step_results else "erledigt")
                    if attempt:
                        # ── Experience Learning (Punkt 15) ────────────────
                        self._learn(step.description, first_error, step.result_summary)
                    break
                step.error = "; ".join(r.summary for r in failed)
            first_error = first_error or step.error

            step.retries = attempt + 1
            if attempt < self.max_step_retries:
                await self.emit("task.step.retry", {
                    "task_id": task.id, "step_id": step.id,
                    "versuch": attempt + 1, "fehler": step.error})
                instruction = await self._next_approach(target, step, step.error)
            else:
                step.status = StepStatus.FAILED

        all_results.extend(step_results)
        step.finished_at = time.time()
        self.tasks.save(task)
        # ── Working Memory (Punkt 14): was gerade wirklich passiert ist ────
        verlauf = target.working_memory.setdefault("verlauf", [])
        verlauf.append({"schritt": step.description, "status": step.status.value,
                        "ergebnis": step.result_summary, "fehler": step.error,
                        "versuche": step.retries})
        del verlauf[:-10]  # nur das Nahe bleibt im Arbeitsspeicher
        self.goals.save(target)
        await self.emit("task.step.finished", {"task_id": task.id, **step.as_dict()})

    async def _next_approach(self, target: Goal, step, error: str) -> str:
        """SELECT ACTION nach einem Fehlschlag: nicht denselben Versuch
        wiederholen, sondern abwägen (Punkt 3) -- und die Wahl protokollieren."""
        decision = await self.decisions.choose(
            f"Der Versuch '{step.description}' ist gescheitert: {error}. "
            "Welche Vorgehensweisen kommen jetzt in Frage?",
            registry_names=set(self.registry.names()), goal_id=target.id)
        target.working_memory.setdefault("entscheidungen", []).append(decision.as_dict())
        del target.working_memory["entscheidungen"][:-10]
        self.goals.save(target)
        await self.emit("decision.made", decision.as_dict())
        chosen = decision.chosen
        werkzeug = f" (Werkzeug: {chosen.tool})" if chosen.tool else ""
        return (f"Der vorige Versuch ist gescheitert: {error}. "
                f"Gewählter neuer Ansatz: {chosen.description}{werkzeug}. "
                f"Ziel des Schrittes bleibt: {step.description}")

    def _learn(self, step_description: str, error: str, result: str) -> None:
        """Was nach einem Fehlschlag doch funktioniert hat, wird gemerkt
        (Punkt 15).

        Ausdrücklich als *Hinweis* für die Planung, nicht als Ersatz für eine
        Aktion: Eine Erinnerung landet über ``store.context_for`` nur im
        Kontext, bevor geplant wird. Sie kann keinen Werkzeugaufruf ersetzen
        und keinen Zustand behaupten -- der aktuelle Zustand wird trotzdem
        jedes Mal neu geprüft (ANALYZE + VERIFY)."""
        if not error:
            return
        try:
            self.store.add(
                label=f"Erfahrung: {step_description[:70]}",
                text=(f"Erster Versuch scheiterte an: {error}. "
                      f"Erfolgreich war danach: {result}"),
                kind="erfahrung", source="autonomy")
        except Exception:  # noqa: BLE001 - eine Lehre, die sich nicht ablegen
            # lässt, darf den laufenden Auftrag nicht scheitern lassen.
            pass

    async def _analyze(self) -> dict[str, Any]:
        """World State (Punkt 13): was messbar ist, wird gemessen -- nicht
        erfragt. Ein nicht erreichbares Modell macht daraus keinen Fehler,
        sondern ein ehrliches "nicht erreichbar"."""
        try:
            health = await self.client.health()
        except Exception:  # noqa: BLE001
            health = None
        state = await asyncio.to_thread(world_state.snapshot, health, self.goals)
        await self.emit("world.state", state)
        return state

    async def _abort_goal(self, target: Goal, task: Task | None, control: _GoalControl,
                          results: list[ToolResult], reason: str,
                          status: GoalStatus) -> guard.Reply:
        """Ein Ziel endet vorzeitig -- abgebrochen, blockiert oder gescheitert.
        In allen drei Fällen dasselbe: ehrlich benennen, protokollieren, und
        nichts behaupten, was nicht belegt ist."""
        if task is not None:
            task.status = (TaskStatus.CANCELLED if status is GoalStatus.CANCELLED
                           else TaskStatus.FAILED)
            self.tasks.save(task)
            await self.emit("task.finished", task.as_dict())
        target.status = status
        target.error = reason
        target.current_step = ""
        self.goals.save(target)
        await self._state("idle" if status is GoalStatus.CANCELLED else "failed")
        await self.emit("goal.finished", target.as_dict())
        if status is GoalStatus.CANCELLED:
            return guard.verify(f"Abgebrochen: {target.description}. {reason}", results)
        if status is GoalStatus.BLOCKED:
            return guard.verify(
                f"Ich habe angehalten, bevor das Ziel erreicht war: {reason}. "
                "Sag mir, wie es weitergehen soll.", results)
        return guard.verify(reason, results)

    # -------------------------------------------------- Steuerung von außen
    async def _checkpoint(self, control: _GoalControl | None) -> None:
        """Ein Haltepunkt zwischen zwei Aktionen. Nie mittendrin -- siehe
        ``_GoalControl``."""
        if control is None:
            return
        if control.cancel_event.is_set():
            raise _GoalCancelled(control.reason or "Vom Nutzer abgebrochen.")
        if control.run_event.is_set():
            return
        target = control.goal
        target.status = GoalStatus.WAITING
        self.goals.save(target)
        await self._state("idle", "pausiert")
        await self.emit("goal.updated", target.as_dict())
        await control.run_event.wait()
        if control.cancel_event.is_set():
            raise _GoalCancelled(control.reason or "Vom Nutzer abgebrochen.")
        target.status = GoalStatus.RUNNING
        self.goals.save(target)
        await self.emit("goal.updated", target.as_dict())

    @property
    def active_goals(self) -> list[Goal]:
        return [c.goal for c in self._controls.values()]

    def pause_goal(self, goal_id: str | None = None) -> list[str]:
        """Angefordert, nicht behauptet: die Pause greift am nächsten
        Haltepunkt. Zurück kommt, welche Ziele angesprochen wurden."""
        touched = []
        for control in self._select(goal_id):
            control.run_event.clear()
            touched.append(control.goal.id)
        return touched

    def resume_goal(self, goal_id: str | None = None) -> list[str]:
        touched = []
        for control in self._select(goal_id):
            control.run_event.set()
            touched.append(control.goal.id)
        return touched

    def cancel_goal(self, goal_id: str | None = None, reason: str = "") -> list[str]:
        touched = []
        for control in self._select(goal_id):
            control.reason = reason or "Vom Nutzer abgebrochen."
            control.cancel_event.set()
            control.run_event.set()  # aus einer Pause heraus abbrechen können
            touched.append(control.goal.id)
        return touched

    def hint_goal(self, hint: str, goal_id: str | None = None) -> list[str]:
        touched = []
        for control in self._select(goal_id):
            control.hint = hint
            touched.append(control.goal.id)
        return touched

    def _select(self, goal_id: str | None) -> list[_GoalControl]:
        if goal_id:
            control = self._controls.get(goal_id)
            return [control] if control else []
        return list(self._controls.values())

    # ------------------------------------------------------ Erweiterungsmodus
    @property
    def extension_status(self) -> dict[str, Any] | None:
        """``None`` heißt: läuft gerade nicht -- für ``GET /api/extension-mode``."""
        return self._extension.as_dict() if self._extension is not None else None

    async def start_extension_mode(self) -> guard.Reply:
        """Erweiterungsmodus (siehe Modul-Docstring-Konstanten oben): fragt
        in einer Schleife das Chat-Modell, welche Aufgabe als Nächstes
        sinnvoll ist, und lässt sie über ``handle_code`` erledigen -- mit der
        Fokus-Modus-Policy, weil niemand zusieht, der eine Bestätigung geben
        könnte. Läuft, bis der Nutzer stoppt oder zu viele Runden in Folge
        nichts Echtes zustande bringen (``_EXTENSION_FAILURE_LIMIT``).

        Dieselbe Autonomiestufe wie eigenständige Zielverfolgung (Stufe 3) --
        eine Schleife, die unbeaufsichtigt und ohne Bestätigung Dateien
        ändert, ist mindestens so viel Eigeninitiative wie ein einzelnes Ziel.
        """
        if self.config.autonomy < AutonomyLevel.GOAL_PURSUIT:
            return self._refuse_autonomy(extension=True)
        if self._extension is not None:
            return guard.Reply(text="Der Erweiterungsmodus läuft schon.",
                               provenance=guard.TALK)

        control = _ExtensionControl()
        self._extension = control
        runner = asyncio.create_task(self._run_extension_mode(control))
        self._runners.add(runner)
        runner.add_done_callback(self._runners.discard)
        return guard.Reply(
            text=("Erweiterungsmodus gestartet: ich suche mir jetzt selbst "
                  "Programmieraufgaben und arbeite sie ab, ohne bei jeder "
                  "einzelnen Änderung nachzufragen. \"Stopp\" oder \"Pause\" "
                  "gelten jederzeit."),
            provenance=guard.TALK)

    def pause_extension_mode(self) -> bool:
        if self._extension is None:
            return False
        self._extension.run_event.clear()
        return True

    def resume_extension_mode(self) -> bool:
        if self._extension is None:
            return False
        self._extension.run_event.set()
        return True

    def stop_extension_mode(self, reason: str = "") -> bool:
        if self._extension is None:
            return False
        self._extension.reason = reason or "Vom Nutzer gestoppt."
        self._extension.cancel_event.set()
        self._extension.run_event.set()  # aus einer Pause heraus stoppen können
        return True

    async def _run_extension_mode(self, control: _ExtensionControl) -> None:
        try:
            while not control.cancel_event.is_set():
                await control.run_event.wait()
                if control.cancel_event.is_set():
                    break

                control.rounds += 1
                task = await self._plan_extension_task()
                if not task:
                    control.failures += 1
                    await self.emit("extension.idle", {
                        "runde": control.rounds,
                        "hinweis": "Keine sinnvolle nächste Aufgabe erkannt."})
                else:
                    control.last_task = task
                    await self.emit("extension.task", {"runde": control.rounds, "auftrag": task})
                    try:
                        reply = await self.handle_code(task, focus=True)
                    except Exception as exc:  # noqa: BLE001 - eine Hintergrundschleife,
                        # die lautlos stirbt, wäre das Gegenteil von nachvollziehbar
                        # (dasselbe Muster wie ``_run_goal_in_background``).
                        reply = guard.Reply(text=f"Intern ist ein Fehler aufgetreten: {exc}",
                                            provenance=guard.FAIL)
                    await self.emit("message", {"who": "jarvis", **reply.as_event()})
                    control.failures = 0 if reply.provenance == guard.TOOL else control.failures + 1

                if control.failures >= _EXTENSION_FAILURE_LIMIT:
                    control.reason = (f"{_EXTENSION_FAILURE_LIMIT}x in Folge ohne echten "
                                      "Fortschritt -- angehalten, statt unbeaufsichtigt "
                                      "gegen dieselbe Wand weiterzulaufen.")
                    break

                await self._extension_sleep(control)
        finally:
            grund = control.reason or "beendet"
            self._extension = None
            await self.emit("extension.stopped", {"grund": grund, **control.as_dict()})

    async def _extension_sleep(self, control: _ExtensionControl) -> None:
        """Pause zwischen zwei Runden -- unterbrechbar, damit ein Stopp nicht
        erst nach voller Wartezeit greift."""
        try:
            await asyncio.wait_for(control.cancel_event.wait(),
                                   timeout=_EXTENSION_PAUSE_SECONDS)
        except asyncio.TimeoutError:
            pass

    async def _plan_extension_task(self) -> str:
        """Fragt das Chat-Modell (nicht das Code-Modell -- das ist hier eine
        reine Planungsfrage ohne Werkzeugaufruf) nach der nächsten sinnvollen
        Aufgabe, ausgehend von dem, was im Gedächtnis über das Projekt steht
        (vor allem die ``projekt``-Einträge, die ``handle_code`` nach jeder
        echten Änderung selbst anlegt -- siehe ``_remember_code_work``)."""
        kontext = await asyncio.to_thread(
            self.store.context_for, "Projekt Aufgabe ROADMAP TODO offen coden", 10)
        messages = [
            {"role": "system", "content": _EXTENSION_PLANNING_PROMPT},
            {"role": "user", "content": ("Was über das Projekt bekannt ist:\n" + kontext)
                                        if kontext else
                                        "Über das Projekt ist noch nichts im Gedächtnis."},
        ]
        try:
            turn = await self.client.chat(messages)
        except OllamaError:
            return ""
        vorschlag = (turn.text or "").strip()
        if not vorschlag or vorschlag.upper().startswith("KEINE AUFGABE"):
            return ""
        return vorschlag

    async def interrupt(self, text: str) -> guard.Reply | None:
        """Punkt 22: "Stopp." / "Pause." / "Mach weiter." / "Nein, versuch
        Methode B." -- jederzeit, auch mitten in einem laufenden Ziel.

        Gibt ``None`` zurück, wenn der Text kein Eingriff ist oder gar kein
        Ziel läuft. Dann geht der Zug ganz normal weiter."""
        if not self._controls:
            return None
        text = (text or "").strip()
        if _STOP.search(text):
            ids = self.cancel_goal(reason=f"Nutzer: \"{text}\"")
            wortlaut = "laufendes Ziel" if len(ids) == 1 else "laufende Ziele"
            return guard.Reply(text=f"Angehalten. {len(ids)} {wortlaut} abgebrochen.",
                               provenance=guard.TALK)
        if _PAUSE.search(text):
            ids = self.pause_goal()
            return guard.Reply(
                text=f"Pausiert ({len(ids)}). Sag \"weiter\", wenn es weitergehen soll.",
                provenance=guard.TALK)
        if _RESUME.search(text):
            ids = self.resume_goal()
            return guard.Reply(text=f"Weiter ({len(ids)}).", provenance=guard.TALK)
        if _ALTERNATIVE.search(text):
            ids = self.hint_goal(text)
            return guard.Reply(
                text=f"Verstanden, ich nehme das für den nächsten Schritt auf ({len(ids)}).",
                provenance=guard.TALK)
        return None

    # ------------------------------------------------------------- Interna
    async def _run_tool_loop(self, instruction: str, request_text: str,
                             watchdog: Watchdog | None = None,
                             control: _GoalControl | None = None,
                             goal_id: str | None = None,
                             client: OllamaClient | None = None,
                             tool_names: list[str] | None = None,
                             system_prompt: str | None = None,
                             max_rounds: int | None = None,
                             policy: PermissionPolicy | None = None
                             ) -> tuple[str, list[ToolResult]]:
        """Eine eigenständige Werkzeugaufruf-Runde für einen einzelnen
        Ausführungsschritt (Agent Mode).

        Bewusst keine Wiederverwendung von ``handle()``s eigener Schleife:
        die ist eng an den laufenden Chat-Verlauf (``self.history``)
        gekoppelt und durch viele Tests abgesichert. Ein gemeinsamer
        Codepfad hätte dafür gesorgt haben können, dass eine Änderung für
        den Agent Mode unbemerkt das normale Chat-Verhalten mit verändert.
        Etwas Ähnlichkeit in der Struktur ist hier der günstigere Preis als
        dieses Risiko an bereits funktionierendem, getestetem Code.

        Hier -- und nicht in ``_run_tool`` -- sitzen Watchdog und
        Verifizierung, weil beide die **Argumente** des Aufrufs brauchen:
        ``ToolResult`` trägt sie nicht.
        """
        model = client or self.client
        rounds = int(max_rounds or self.config.max_tool_rounds)
        # Explizite Liste (Code-Modus: coder.CODE_TOOLS) bleibt exakt das --
        # ohne eine, wie im Agent Mode, entscheidet Discovery anhand des
        # Schritt-Auftrags, denselben Grund wie in ``handle()`` (Punkt 35).
        schemas = (self.registry.schemas(only=tool_names) if tool_names is not None
                  else self.discovery.schemas_for(instruction))
        context = await asyncio.to_thread(self.store.context_for, instruction)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system",
                             "content": "Was du über deinen Nutzer weißt:\n" + context})
        messages.append({"role": "user", "content": instruction})

        results: list[ToolResult] = []
        final = ""
        for _round in range(rounds):
            await self._checkpoint(control)
            turn: ChatTurn = await model.chat(messages, schemas)
            if not turn.tool_calls:
                final = turn.text
                break
            messages.append({
                "role": "assistant", "content": turn.text,
                "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}}
                               for c in turn.tool_calls]})
            for call in turn.tool_calls:
                if call.name not in self.registry:
                    angeboten = _tool_names(schemas)
                    messages.append({
                        "role": "tool", "name": call.name,
                        "content": (f"FEHLGESCHLAGEN: Werkzeug '{call.name}' existiert "
                                    f"nicht oder steht gerade nicht zur Auswahl. Angeboten: "
                                    f"{angeboten}. Mit jarvis.tools.search lässt sich der "
                                    "ganze Werkzeugkasten durchsuchen.")})
                    continue
                await self._checkpoint(control)
                # ── EXECUTE ───────────────────────────────────────────────
                result = await self._run_tool(call.name, call.arguments,
                                              request_text=request_text, goal_id=goal_id,
                                              policy=policy)
                results.append(result)
                messages.append({"role": "tool", "name": call.name,
                                 "content": result.for_model()})
                if watchdog is not None:
                    watchdog.note_tool_call(call.name, call.arguments, result.ok, result.summary)

                # ── VERIFY ────────────────────────────────────────────────
                # Ein zweiter, unabhängiger Werkzeugaufruf. Schlägt er fehl,
                # zählt der Schritt als gescheitert -- auch wenn das
                # ursprüngliche Werkzeug "erfolgreich" gemeldet hat. Genau das
                # ist "Jarvis darf niemals allein aufgrund seiner eigenen
                # Antwort davon ausgehen, dass etwas funktioniert hat".
                check = await self.verification.verify(
                    call.name, call.arguments, result,
                    lambda name, args: self._run_tool(name, args,
                                                      request_text=request_text,
                                                      goal_id=goal_id, policy=policy))
                if check is not None and not check.ok:
                    results.append(check)
                    messages.append({
                        "role": "tool", "name": f"verify:{call.name}",
                        "content": f"NACHPRÜFUNG FEHLGESCHLAGEN: {check.summary}"})
        else:
            final = f"Schritt nach {rounds} Runden abgebrochen."
        return final, results

    @staticmethod
    def _phrase(result: ToolResult) -> str:
        """Der Satz für einen Direktbefehl — aus dem Ergebnis, nicht aus Prosa."""
        if not result.ok:
            return f"Die Aktion ist fehlgeschlagen: {result.summary}"
        # Die Einzelheiten stehen als Beleg unter der Antwort; hier wären sie
        # nur Dopplung.
        return result.summary

    def _remember(self, user_text: str, reply: guard.Reply) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply.text})
        cap = self.history_turns * 2
        if len(self.history) > cap:
            verdraengt, self.history = self.history[:-cap], self.history[-cap:]
            self._archive_to_session(verdraengt)

    def _archive_to_session(self, verdraengte_zuege: list[dict[str, Any]]) -> None:
        """Session-Ebene zwischen Kurz- und Langzeitgedächtnis (``_SESSION_TTL_HOURS``).

        Was aus dem kurzlebigen ``self.history``-Fenster fällt, ist damit
        nicht automatisch wertlos -- es landet hier mit eigener Ablaufzeit im
        Gedächtnis, statt spurlos zu verschwinden. Anders als eine Langzeit-
        Erinnerung (``kind="fakt"``/``"projekt"``/…) verschwindet es von
        selbst wieder, sobald ``_SESSION_TTL_HOURS`` um ist (``MemoryStore``
        blendet abgelaufene Knoten in jedem Abruf aus und räumt sie beim
        nächsten Start endgültig weg) -- niemand muss diese Sitzungsnotiz je
        von Hand löschen.
        """
        text = "\n".join(f"{zug['role']}: {zug['content']}" for zug in verdraengte_zuege
                         if (zug.get("content") or "").strip())
        if not text.strip():
            return
        try:
            self.store.add(
                label=f"Sitzung {time.strftime('%Y-%m-%d %H:%M')}", text=text[:2000],
                kind="sitzung", source="sitzung",
                expires=time.time() + _SESSION_TTL_HOURS * 3600)
        except Exception:  # noqa: BLE001 - dieselbe Vorsicht wie in _learn()
            pass

    def _remember_code_work(self, task: str, outcome: coder.CodeOutcome) -> None:
        """Speichert echte Code-Fortschritte im Langzeitgedächtnis (Wissensnetz).

        ``self.history`` (siehe ``_remember``) lebt nur im Arbeitsspeicher
        dieses Prozesses -- ein Serverneustart oder ein neues Gespräch
        beginnt ganz ohne sie. ``_run_tool_loop`` ruft vor jedem Auftrag
        bereits ``store.context_for()`` ab (dieselbe Stelle wie im Chat),
        aber ohne einen Eintrag, den es dort finden kann, bleibt der Abruf
        leer -- genau das war die Lücke: Jarvis konnte frühere Code-Arbeit
        nicht "lesen", weil nie etwas darüber abgelegt wurde. Hier wird das
        nachgeholt, als ``kind="projekt"`` (genau dafür in ``memory.KINDS``
        vorgesehen) und mit echten Dateipfaden aus ``outcome.changes`` --
        die kommen aus ToolResult-Belegen, nie aus einer Behauptung des
        Modells. Ein Auftrag ohne Dateiänderung ist keine Projekt-Erinnerung
        wert und wird nicht gespeichert. Über das Wissensnetz (``net``-
        Ansicht) sieht und bearbeitet der Nutzer denselben Eintrag von Hand.
        """
        if not outcome.changes:
            return
        pfade = list(dict.fromkeys(c.path for c in outcome.changes))
        text = f"Auftrag: {task}\nGeänderte Datei(en): " + ", ".join(pfade)
        if outcome.broken:
            kaputt = ", ".join(f"{c.name} ({c.detail})" for c in outcome.broken)
            text += f"\nAchtung, Nachprüfung fehlgeschlagen bei: {kaputt}"
        try:
            self.store.add(label=task[:70], text=text, kind="projekt", source="code-modus")
        except Exception:  # noqa: BLE001 - eine nicht speicherbare Erinnerung
            # darf den eigentlichen Code-Auftrag nicht scheitern lassen --
            # dieselbe Vorsicht wie in _learn().
            pass
