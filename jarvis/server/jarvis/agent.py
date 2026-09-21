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
from typing import Any, Awaitable, Callable

from . import guard, planner, router, world_state
from .audit import AuditLog
from .autonomy import AutonomyLevel
from .config import Config
from .decision import DecisionEngine
from .goals import Goal, GoalBudget, GoalManager, GoalStatus
from .memory import MemoryStore
from .ollama import ChatTurn, OllamaClient, OllamaError
from .permissions import PermissionDenied, PermissionGate, PermissionLevel
from .tasks import StepStatus, Task, TaskManager, TaskStatus
from .tools import Registry, ToolMissing, ToolResult
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

Programmieraufgaben gibst du an codepilot_task weiter, wenn es verfügbar ist.
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


class Agent:
    def __init__(self, config: Config, store: MemoryStore, registry: Registry,
                 client: OllamaClient, emit: Emit | None = None,
                 history_turns: int = 12,
                 permission_gate: PermissionGate | None = None,
                 audit: AuditLog | None = None, undo: UndoStore | None = None,
                 tasks: TaskManager | None = None, max_step_retries: int = 2,
                 goals: GoalManager | None = None,
                 decisions: DecisionEngine | None = None,
                 verification: VerificationEngine | None = None):
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
        # Autonomy V1. Die drei Maschinen sind bewusst hereinreichbar: app.py
        # gibt dateibasierte Instanzen, Tests bauen eigene.
        self.goals = goals or GoalManager(":memory:")
        self.decisions = decisions or DecisionEngine(client, audit=self.audit)
        self.verification = verification if verification is not None else VerificationEngine()
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

    @staticmethod
    async def _silent(_kind: str, _payload: dict) -> None:
        return None

    async def _state(self, mode: str, detail: str = "") -> None:
        await self.emit("state", {"mode": mode, "detail": detail})

    async def _run_tool(self, name: str, arguments: dict,
                        request_text: str = "") -> ToolResult:
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
                              ok=False, summary=result.summary, request=request_text)
            return result
        force_confirm = (autonomy <= AutonomyLevel.READ_ONLY
                        and tool.level >= PermissionLevel.WRITE)

        try:
            await self.permission_gate.check(name, tool.level, arguments, detail=detail,
                                             force_confirm=force_confirm)
        except PermissionDenied as exc:
            result = ToolResult(tool=name, ok=False, summary=str(exc),
                                evidence={"stufe": tool.level.label, "verweigert": True})
            self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                              ok=False, summary=result.summary, request=request_text)
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
                          ok=result.ok, summary=result.summary, request=request_text)
        return result

    async def _execute(self, name: str, arguments: dict) -> ToolResult:
        pre_snapshot = self.undo.begin(name, arguments or {})
        await self.emit("tool.started", {"tool": name, "arguments": arguments})
        result = await asyncio.to_thread(self.registry.call, name, arguments)
        await self.emit("tool.finished", result.as_event())
        self.undo.finish(name, result.summary, pre_snapshot, result)
        return result

    # ---------------------------------------------------------- Code-Modus
    async def handle_code(self, message: str) -> guard.Reply:
        """Ein Zug im Code-Modus: geht immer direkt an ``codepilot_task``.

        Kein Router, kein Chat-Modell, keine Interpretation. Der Nutzer hat den
        Modus bewusst eingeschaltet — das ist die eindeutigste Aussage, die es
        gibt, eindeutiger als jedes erkannte Muster im Text. Also wird hier
        nicht geraten, sondern direkt das eine Werkzeug gerufen, das für Code
        zuständig ist.
        """
        task = (message or "").strip()
        if not task:
            return guard.Reply(text="", provenance=guard.TALK)
        if "codepilot_task" not in self.registry:
            await self._state("idle")
            reply = guard.Reply(
                text=f"{guard.REFUSAL} (benötigt: codepilot_task — CodePilot "
                     f"ist nicht eingerichtet, siehe jarvis.json unter 'codepilot')",
                provenance=guard.FAIL)
            self._remember(task, reply)
            return reply

        await self._state("executing", f"codepilot_task · {task[:70]}")
        result = await self._run_tool("codepilot_task", {"task": task}, request_text=task)
        await self._state("failed" if not result.ok else "idle")
        # Kein Modelltext im Spiel, also nichts zu beschönigen — die
        # Zusammenfassung des Werkzeugs ist die Antwort.
        reply = guard.verify("", [result])
        self._remember(task, reply)
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

        results: list[ToolResult] = []
        final = ""
        try:
            for round_no in range(self.config.max_tool_rounds):
                await self._state("thinking",
                                  "plane" if round_no == 0 else f"plane weiter ({round_no + 1})")
                turn: ChatTurn = await self.client.chat(messages, self.registry.schemas())

                if not turn.tool_calls:
                    final = turn.text
                    break

                messages.append({
                    "role": "assistant", "content": turn.text,
                    "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}}
                                   for c in turn.tool_calls]})
                for call in turn.tool_calls:
                    if call.name not in self.registry:
                        # Halluzinierter Werkzeugname. Das Modell erfährt es und
                        # bekommt die echte Liste zu sehen.
                        messages.append({
                            "role": "tool", "name": call.name,
                            "content": (f"FEHLGESCHLAGEN: Werkzeug '{call.name}' "
                                        f"existiert nicht. Verfügbar: "
                                        f"{', '.join(self.registry.names())}")})
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

    def _refuse_autonomy(self) -> guard.Reply:
        autonomy = self.config.autonomy
        return guard.Reply(
            text=(f"Autonomiestufe {int(autonomy)} ({autonomy.label}) erlaubt keine "
                  "eigenständige Zielverfolgung -- das braucht Stufe 3. Sage mir "
                  "stattdessen einzelne Schritte, oder hebe autonomy_level in "
                  "jarvis.json an."),
            provenance=guard.TALK)

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
            return self._refuse_autonomy()

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
            return None, self._refuse_autonomy()

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
                    watchdog=watchdog, control=control)
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
                kind="erfahrung")
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
                             control: _GoalControl | None = None
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
        context = await asyncio.to_thread(self.store.context_for, instruction)
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system",
                             "content": "Was du über deinen Nutzer weißt:\n" + context})
        messages.append({"role": "user", "content": instruction})

        results: list[ToolResult] = []
        final = ""
        for _round in range(self.config.max_tool_rounds):
            await self._checkpoint(control)
            turn: ChatTurn = await self.client.chat(messages, self.registry.schemas())
            if not turn.tool_calls:
                final = turn.text
                break
            messages.append({
                "role": "assistant", "content": turn.text,
                "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}}
                               for c in turn.tool_calls]})
            for call in turn.tool_calls:
                if call.name not in self.registry:
                    messages.append({
                        "role": "tool", "name": call.name,
                        "content": (f"FEHLGESCHLAGEN: Werkzeug '{call.name}' existiert "
                                    f"nicht. Verfügbar: {', '.join(self.registry.names())}")})
                    continue
                await self._checkpoint(control)
                # ── EXECUTE ───────────────────────────────────────────────
                result = await self._run_tool(call.name, call.arguments, request_text=request_text)
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
                    lambda name, args: self._run_tool(name, args, request_text=request_text))
                if check is not None and not check.ok:
                    results.append(check)
                    messages.append({
                        "role": "tool", "name": f"verify:{call.name}",
                        "content": f"NACHPRÜFUNG FEHLGESCHLAGEN: {check.summary}"})
        else:
            final = f"Schritt nach {self.config.max_tool_rounds} Runden abgebrochen."
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
            self.history = self.history[-cap:]
