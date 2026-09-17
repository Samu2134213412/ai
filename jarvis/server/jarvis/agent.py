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
import time
from typing import Any, Awaitable, Callable

from . import guard, planner, router
from .audit import AuditLog
from .autonomy import AutonomyLevel
from .config import Config
from .memory import MemoryStore
from .ollama import ChatTurn, OllamaClient, OllamaError
from .permissions import PermissionDenied, PermissionGate, PermissionLevel
from .tasks import StepStatus, Task, TaskManager, TaskStatus
from .tools import Registry, ToolMissing, ToolResult
from .undo import UndoStore

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


class Agent:
    def __init__(self, config: Config, store: MemoryStore, registry: Registry,
                 client: OllamaClient, emit: Emit | None = None,
                 history_turns: int = 12,
                 permission_gate: PermissionGate | None = None,
                 audit: AuditLog | None = None, undo: UndoStore | None = None,
                 tasks: TaskManager | None = None, max_step_retries: int = 2):
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

        pre_snapshot = self.undo.begin(name, arguments or {})
        await self.emit("tool.started", {"tool": name, "arguments": arguments})
        result = await asyncio.to_thread(self.registry.call, name, arguments)
        await self.emit("tool.finished", result.as_event())
        self.undo.finish(name, result.summary, pre_snapshot, result)
        self.audit.record(tool=name, level=tool.level, arguments=arguments or {},
                          ok=result.ok, summary=result.summary, request=request_text)
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

    # ------------------------------------------------------------ Agent Mode
    async def handle_agent_task(self, goal: str) -> guard.Reply:
        """Agent Mode (Punkt 1): ein komplexer Auftrag wird zuerst in
        benannte Schritte zerlegt (Planner), dann nacheinander ausgeführt
        (Executor). Scheitert ein Schritt, wird nicht sofort aufgegeben --
        ein neuer Versuch mit dem Fehler als Kontext, bis zum Retry-Limit
        (Error Recovery, Punkt 28). Der ganze Verlauf ist als Task
        persistent und wird nach jedem Schritt als Ereignis gesendet (Task
        History + State Manager)."""
        goal = (goal or "").strip()
        if not goal:
            return guard.Reply(text="", provenance=guard.TALK)

        autonomy = self.config.autonomy
        if autonomy < AutonomyLevel.GOAL_PURSUIT:
            return guard.Reply(
                text=(f"Autonomiestufe {int(autonomy)} ({autonomy.label}) erlaubt keine "
                      "eigenständige Zielverfolgung -- das braucht Stufe 3. Sage mir "
                      "stattdessen einzelne Schritte, oder hebe autonomy_level in "
                      "jarvis.json an."),
                provenance=guard.TALK)

        await self._state("thinking", "plane die Schritte")
        step_texts = await planner.plan(self.client, goal)
        task = self.tasks.create(goal, step_texts)
        await self.emit("task.created", task.as_dict())

        task.status = TaskStatus.RUNNING
        self.tasks.save(task)
        all_results: list[ToolResult] = []

        for step in task.steps:
            step.status = StepStatus.RUNNING
            step.started_at = time.time()
            self.tasks.save(task)
            await self._state("executing", f"Schritt: {step.description}")
            await self.emit("task.step.started", {"task_id": task.id, **step.as_dict()})

            instruction = step.description
            # Nur die Ergebnisse des jeweils LETZTEN Versuchs zählen für das
            # Gesamturteil -- ein Versuch, der scheiterte und dann durch einen
            # anderen Ansatz ersetzt wurde, darf ein am Ende erfolgreiches
            # Ergebnis nicht rückwirkend als Fehlschlag erscheinen lassen.
            # Sichtbar bleibt er trotzdem: im "task.step.retry"-Ereignis, in
            # step.retries und im Audit Log (jeder Versuch läuft durch
            # _run_tool und wird dort unabhängig protokolliert).
            step_results: list[ToolResult] = []
            for attempt in range(self.max_step_retries + 1):
                try:
                    text, step_results = await self._run_tool_loop(instruction, request_text=goal)
                except OllamaError as exc:
                    text, step_results = "", []
                    step.error = f"Modell nicht erreichbar: {exc}"
                else:
                    failed = [r for r in step_results if not r.ok]
                    if not failed:
                        step.status = StepStatus.DONE
                        step.result_summary = text.strip() or (
                            step_results[-1].summary if step_results else "erledigt")
                        break
                    step.error = "; ".join(r.summary for r in failed)

                step.retries = attempt + 1
                if attempt < self.max_step_retries:
                    await self.emit("task.step.retry", {
                        "task_id": task.id, "step_id": step.id,
                        "versuch": attempt + 1, "fehler": step.error})
                    instruction = (
                        f"Der vorige Versuch ist gescheitert: {step.error}. "
                        f"Versuche einen anderen Ansatz für: {step.description}")
                else:
                    step.status = StepStatus.FAILED

            all_results.extend(step_results)
            step.finished_at = time.time()
            self.tasks.save(task)
            await self.emit("task.step.finished", {"task_id": task.id, **step.as_dict()})

            if step.status == StepStatus.FAILED:
                task.status = TaskStatus.FAILED
                self.tasks.save(task)
                await self._state("failed")
                await self.emit("task.finished", task.as_dict())
                reply = guard.verify(
                    f"Schritt gescheitert: {step.description}. {step.error}", all_results)
                self._remember(goal, reply)
                return reply

        task.status = TaskStatus.COMPLETED
        self.tasks.save(task)
        await self._state("idle")
        await self.emit("task.finished", task.as_dict())
        final_text = " ".join(s.result_summary for s in task.steps if s.result_summary)
        reply = guard.verify(final_text or "Alle Schritte abgeschlossen.", all_results)
        self._remember(goal, reply)
        return reply

    # ------------------------------------------------------------- Interna
    async def _run_tool_loop(self, instruction: str,
                             request_text: str) -> tuple[str, list[ToolResult]]:
        """Eine eigenständige Werkzeugaufruf-Runde für einen einzelnen
        Ausführungsschritt (Agent Mode).

        Bewusst keine Wiederverwendung von ``handle()``s eigener Schleife:
        die ist eng an den laufenden Chat-Verlauf (``self.history``)
        gekoppelt und durch viele Tests abgesichert. Ein gemeinsamer
        Codepfad hätte dafür gesorgt haben können, dass eine Änderung für
        den Agent Mode unbemerkt das normale Chat-Verhalten mit verändert.
        Etwas Ähnlichkeit in der Struktur ist hier der günstigere Preis als
        dieses Risiko an bereits funktionierendem, getestetem Code.
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
                result = await self._run_tool(call.name, call.arguments, request_text=request_text)
                results.append(result)
                messages.append({"role": "tool", "name": call.name,
                                 "content": result.for_model()})
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
