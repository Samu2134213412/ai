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
from typing import Any, Awaitable, Callable

from . import guard, router
from .config import Config
from .memory import MemoryStore
from .ollama import ChatTurn, OllamaClient, OllamaError
from .tools import Registry, ToolMissing, ToolResult

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
                 history_turns: int = 12):
        self.config = config
        self.store = store
        self.registry = registry
        self.client = client
        self.emit = emit or self._silent
        self.history: list[dict[str, Any]] = []
        self.history_turns = history_turns

    @staticmethod
    async def _silent(_kind: str, _payload: dict) -> None:
        return None

    async def _state(self, mode: str, detail: str = "") -> None:
        await self.emit("state", {"mode": mode, "detail": detail})

    async def _run_tool(self, name: str, arguments: dict) -> ToolResult:
        """Führt ein Werkzeug aus und meldet Start und Ende an die Oberfläche."""
        await self.emit("tool.started", {"tool": name, "arguments": arguments})
        result = await asyncio.to_thread(self.registry.call, name, arguments)
        await self.emit("tool.finished", result.as_event())
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
        result = await self._run_tool("codepilot_task", {"task": task})
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
            result = await self._run_tool(action.tool, action.arguments)
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
                    result = await self._run_tool(call.name, call.arguments)
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

        # 4. Der Wächter entscheidet, was rausgeht.
        reply = guard.verify(final, results)
        await self._state("failed" if reply.provenance == guard.FAIL else "idle")
        if reply.blocked:
            await self.emit("guard.blocked", {
                "verworfen": reply.blocked_text, "ersetzt_durch": reply.text})
        self._remember(text, reply)
        return reply

    # ------------------------------------------------------------- Interna
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
