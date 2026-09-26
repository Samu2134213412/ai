"""Der Jarvis-Server: HTTP, WebSocket und die Oberfläche aus ``jarvis/web``.

Ein Zug wird an **alle** verbundenen Geräte gesendet. Was auf dem PC angefangen
wird, läuft auf dem Handy weiter — es ist dieselbe Sitzung, derselbe Verlauf,
dasselbe Gedächtnis. Genau das war gemeint mit „ein Manager für meinen PC und
mein Handy".
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
from pathlib import Path

from typing import Literal

from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import guard
from .agent import Agent
from .audit import AuditLog
from .autonomy import AutonomyLevel
from .config import Config
from .decision import DecisionEngine, DecisionLog
from .events import Event, EventBus, ProactiveEngine, Proposal
from .goals import GoalManager, GoalStatus
from .memory import DEFAULT_SEED, MemoryStore
from .ollama import OllamaClient
from .permissions import PermissionGate, PermissionLevel, PermissionPolicy
from .tasks import TaskManager
from .undo import UndoError
from .tools import (availability, build_registry, dependency_report,
                    system as system_tools, tool_status)
from .whisper import WhisperClient, WhisperError

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
TELEMETRY_SECONDS = 3.0


#: "code" geht an das Code-Modell (``coder.py``), ohne das Chat-Modell zu
#: befragen -- der Nutzer hat den Modus bewusst gewählt. "agent" zerlegt den
#: Auftrag zuerst in Schritte (Planner) und führt sie einzeln aus (Executor,
#: siehe ``Agent.handle_agent_task``). "macro" führt ein gespeichertes Makro
#: (``macros.py``) aus -- ``text`` ist dabei der Makroname, kein Auftrag ans
#: Modell.
CommandMode = Literal["chat", "code", "agent", "macro"]
_MODES: tuple[str, ...] = ("chat", "code", "agent", "macro")

#: Was sich an einem laufenden Ziel von außen steuern lässt (Punkt 7/22).
GoalAction = Literal["pause", "resume", "cancel"]


class CommandIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    mode: CommandMode = "chat"


class GraphIn(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    links: list[list] = Field(default_factory=list)


class WhisperKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=200)


class FocusModeIn(BaseModel):
    an: bool


class AutonomyIn(BaseModel):
    stufe: int = Field(..., ge=int(min(AutonomyLevel)), le=int(max(AutonomyLevel)))


#: Was sich am laufenden Erweiterungsmodus von außen steuern lässt --
#: "start" separat behandelt (siehe control_extension_mode), weil es als
#: einziges auch ohne laufende Schleife sinnvoll ist.
ExtensionAction = Literal["start", "pause", "resume", "stop"]


class PermissionResolveIn(BaseModel):
    request_id: str = Field(..., min_length=1)
    approved: bool = False


class UndoIn(BaseModel):
    record_id: str = Field(default="")


class EventIn(BaseModel):
    """Ein Ereignis von aussen -- ein Melder auf dem Rechner, die Oberflaeche,
    ein Skript. Was daraus folgt, entscheidet ``ProactiveEngine``, nicht der
    Absender."""

    kind: str = Field(..., min_length=1, max_length=120)
    source: str = Field(default="", max_length=120)
    severity: Literal["info", "warning", "error"] = "info"
    payload: dict = Field(default_factory=dict)


class ProposalIn(BaseModel):
    approved: bool = False


#: Was sich an einem einzelnen Werkzeug von außen umschalten lässt --
#: dieselbe Handlung wie die ``jarvis.tools.*``-Meta-Werkzeuge (Punkt 36),
#: hier als direkter HTTP-Weg für die Oberfläche (Punkt 47: Tool Explorer),
#: ohne den Umweg über das Modell.
ToolAction = Literal["favorite", "unfavorite", "disable", "enable"]


class ToolActionIn(BaseModel):
    reason: str = Field(default="", max_length=300)


class Hub:
    """Die offenen Verbindungen. Jede Meldung geht an alle."""

    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, socket: WebSocket) -> None:
        async with self._lock:
            self._sockets.add(socket)

    async def drop(self, socket: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(socket)

    @property
    def count(self) -> int:
        return len(self._sockets)

    async def send(self, kind: str, payload: dict) -> None:
        message = json.dumps({"type": kind, **payload}, ensure_ascii=False)
        async with self._lock:
            targets = list(self._sockets)
        for socket in targets:
            try:
                await socket.send_text(message)
            except Exception:  # noqa: BLE001 - eine tote Verbindung stoppt nichts
                await self.drop(socket)


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.load()
    store = MemoryStore(config.db_path)
    store.seed(DEFAULT_SEED)
    registry = build_registry(config, store)
    client = OllamaClient(url=config.ollama_url, model=config.model,
                          context_length=config.context_length,
                          temperature=config.temperature,
                          timeout=config.request_timeout)
    # Ein zweiter Draht zu demselben Ollama, nur mit dem Code-Modell,
    # niedrigerer Temperatur und längerem Timeout: ein 30B-Modell braucht
    # beim ersten Aufruf Zeit zum Laden. Steht kein Code-Modell in der
    # Konfiguration, nimmt der Code-Modus das Chat-Modell -- schlechter,
    # aber lauffähig statt abwesend.
    code_client = OllamaClient(url=config.ollama_url,
                               model=config.code.model or config.model,
                               context_length=config.context_length,
                               temperature=config.code.temperature,
                               timeout=config.code.timeout)
    # Ein drittes, optionales Modell für einfache Fragen ohne Werkzeugbedarf
    # (siehe complexity.py). Ohne Fallback: leer in der Konfiguration heißt
    # aus, nicht "nimm irgendein Modell" -- niemand bekommt einen zweiten
    # Download aufgezwungen (Punkt 55).
    fast_client = OllamaClient(url=config.ollama_url, model=config.fast_model,
                               context_length=config.context_length,
                               temperature=config.temperature,
                               timeout=config.request_timeout) if config.fast_model else None
    hub = Hub()
    audit = AuditLog(config.audit_db_path)
    permission_gate = PermissionGate(
        policy=PermissionPolicy(
            confirm_read=config.permissions.confirm_read,
            confirm_write=config.permissions.confirm_write,
            confirm_system=config.permissions.confirm_system,
            confirmation_timeout=config.permissions.confirmation_timeout),
        emit=hub.send)
    tasks = TaskManager(config.task_db_path)
    goals = GoalManager(config.goal_db_path)
    decisions = DecisionEngine(client, audit=audit, log=DecisionLog(config.decision_db_path))
    agent = Agent(config, store, registry, client, emit=hub.send,
                  permission_gate=permission_gate, audit=audit, undo=registry.undo_store,
                  tasks=tasks, goals=goals, decisions=decisions,
                  code_client=code_client, fast_client=fast_client,
                  macros=registry.macro_store, tool_history=registry.tool_history,
                  discovery=registry.discovery)
    busy = asyncio.Lock()
    bus = EventBus()
    proactive = ProactiveEngine()
    #: Vorschlaege, auf deren Zustimmung gewartet wird (Punkt 9).
    pending_proposals: dict[str, Proposal] = {}
    whisper = WhisperClient(api_key=config.whisper.api_key, model=config.whisper.model,
                            timeout=config.whisper.timeout)

    # ------------------------------------------- Ereignisse -> Reaktion
    async def on_event(event: Event) -> dict:
        """Der **eine** Ort, an dem aus einem Ereignis eine Reaktion wird.

        Handeln darf Jarvis nur, wenn ``ProactiveEngine`` das ausdruecklich
        erlaubt. In jedem anderen Fall geht ein Vorschlag an den Nutzer --
        und bis zu dessen Zustimmung passiert genau nichts.

        Zurueck kommt, was tatsaechlich entschieden wurde. Bewusst nicht
        "der Endpunkt entscheidet nochmal selbst": zweimal ``react`` aufrufen
        hiesse zwei Vorschlaege mit zwei verschiedenen ids, von denen nur
        einer bestaetigt werden kann."""
        await hub.send("event", event.as_dict())
        proposal = proactive.react(event, config.autonomy)
        if proposal is None:
            return {"reaktion": "keine", "vorschlag": None}
        if proposal.needs_approval:
            pending_proposals[proposal.id] = proposal
            await hub.send("proactive.suggested", proposal.as_dict())
            return {"reaktion": "vorschlag", "vorschlag": proposal.as_dict()}
        await hub.send("proactive.acting", proposal.as_dict())
        goal, reply = await agent.start_goal(proposal.goal)
        await hub.send("message", {"who": "jarvis", **reply.as_event()})
        return {"reaktion": "gestartet", "vorschlag": proposal.as_dict(),
                "ziel": goal.id if goal else None}

    #: Die Reaktion zum zuletzt gemeldeten Ereignis, damit ``POST /api/events``
    #: sie zurueckgeben kann, ohne die Entscheidung zu wiederholen.
    reactions: dict[str, dict] = {}

    async def dispatch(event: Event) -> None:
        reactions[event.id] = await on_event(event)
        for stale in list(reactions)[:-50]:
            reactions.pop(stale, None)

    bus.subscribe(dispatch)
    # Der Agent meldet eine Serie von Fehlschlägen desselben Werkzeugs als
    # Ereignis -- das eine proaktive Beispiel, das ohne fehlende Sensoren
    # auskommt (siehe docs/JARVIS.md 8.4).
    agent.bus = bus

    # -------------------------------------------------------- Telemetrie
    async def telemetry_loop() -> None:
        while True:
            await asyncio.sleep(TELEMETRY_SECONDS)
            if hub.count:
                values = await asyncio.to_thread(system_tools.telemetry)
                if values:
                    await hub.send("telemetry", values)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        ticker = asyncio.create_task(telemetry_loop())
        try:
            yield
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

    app = FastAPI(title="Jarvis", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.registry = registry
    app.state.agent = agent
    app.state.hub = hub
    app.state.whisper = whisper
    app.state.audit = audit
    app.state.permission_gate = permission_gate
    app.state.undo = registry.undo_store
    app.state.tasks = tasks
    app.state.goals = goals
    app.state.decisions = decisions
    app.state.bus = bus
    app.state.proactive = proactive

    # ------------------------------------------------------------ Zugang
    def check_token(supplied: str | None) -> None:
        """Ohne Token nur vom eigenen Rechner. Mit Token von überall."""
        if not config.token:
            if not config.is_loopback:
                raise HTTPException(status_code=503, detail=(
                    "Der Server ist aus dem Netz erreichbar, aber es ist kein "
                    "Token gesetzt. Das ist abgelehnt, nicht offen."))
            return
        # Zeitkonstant statt "!=": ein gewöhnlicher Vergleich bricht beim
        # ersten falschen Zeichen ab, und die Antwortzeit verrät dann über
        # das Netz, wie viele Anfangszeichen schon stimmen.
        if not hmac.compare_digest((supplied or "").encode("utf-8"),
                                   config.token.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Ungültiges Token")

    async def require_token(authorization: str | None = Header(default=None),
                            token: str | None = Query(default=None)) -> None:
        supplied = token
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        check_token(supplied)

    Guarded = [Depends(require_token)]

    # -------------------------------------------------------------- Status
    async def snapshot() -> dict:
        health = await client.health()
        # In einen Thread ausgelagert: dependency_report() ist nach dem ersten
        # Aufruf gecacht (siehe catalog.py), aber genau dieser erste Aufruf
        # prüft jede PROBE einzeln (shutil.which/importlib.import_module) --
        # synchron in der Event-Loop würde das jede andere gleichzeitige
        # Anfrage bis zum Abschluss blockieren.
        abhaengigkeiten = await asyncio.to_thread(dependency_report)
        return {
            "host": config.host,
            "model": config.model,
            "modelle": [
                {"id": config.model, "loaded": health.model_present,
                 "via": "Ollama · direkt"},
                # Das Code-Modell. "loaded" meldet, ob Ollama es wirklich
                # vorrätig hat -- nicht, ob es in der Konfiguration steht.
                {"id": config.code.model or config.model,
                 "loaded": (config.code.model or config.model) in health.models,
                 "via": "Ollama · direkt"},
                # Das schnelle Modell -- nur in der Liste, wenn eines
                # konfiguriert ist. Kein Eintrag heißt: Feature ist aus.
                *([{"id": config.fast_model,
                    "loaded": config.fast_model in health.models,
                    "via": "Ollama · direkt · für einfache Fragen"}]
                  if config.fast_model else []),
            ],
            "ollama": {"online": health.online, "version": health.version,
                       "modell_vorhanden": health.model_present,
                       "hinweis": health.detail},
            "werkzeuge": tool_status(registry, config),
            # Health-Check (Punkt 49/53): was auf DIESEM Rechner tatsächlich
            # installiert ist, mit Installationshinweis -- kein Rätselraten,
            # warum ein Werkzeug MISSING_DEPENDENCY meldet.
            "abhaengigkeiten": abhaengigkeiten,
            "arbeitsbereich": config.roots,
            "shell_aktiv": config.shell.enabled,
            "probleme": config.validate(),
            "geraete": hub.count,
            "whisper_configured": whisper.configured,
            "fokus_modus": agent.focus_mode,
            "autonomie": autonomy_state(),
            "erweiterungsmodus": agent.extension_status,
            "berechtigungen": {
                "read": permission_gate.policy.requires_confirmation(PermissionLevel.READ),
                "write": permission_gate.policy.requires_confirmation(PermissionLevel.WRITE),
                "system": permission_gate.policy.requires_confirmation(PermissionLevel.SYSTEM),
                "critical": True,  # nie abschaltbar, siehe permissions.py
                "offen": len(permission_gate.pending),
            },
        }

    def autonomy_state() -> dict:
        stufe = config.autonomy
        return {"stufe": int(stufe), "name": stufe.label,
                "stufen": [{"stufe": int(s), "name": s.label} for s in AutonomyLevel]}

    @app.get("/api/health")
    async def health() -> dict:
        return await snapshot()

    @app.get("/api/memory", dependencies=Guarded)
    async def get_memory() -> dict:
        return store.graph()

    @app.put("/api/memory", dependencies=Guarded)
    async def put_memory(body: GraphIn) -> dict:
        count = store.replace_graph(body.model_dump())
        await hub.send("memory", store.graph())
        return {"gespeichert": count}

    @app.get("/api/memory/search", dependencies=Guarded)
    async def search_memory(q: str, limit: int = 6) -> dict:
        return {"treffer": [m.as_dict() | {"score": m.score}
                            for m in store.search(q, min(max(limit, 1), 50))]}

    # ------------------------------------------------------ Audit / Undo
    @app.get("/api/audit", dependencies=Guarded)
    async def get_audit(tool: str | None = None, level: str | None = None,
                        ok: bool | None = None, limit: int = 100) -> dict:
        """Das Audit Log -- filterbar, wie in der Aufgabenstellung verlangt."""
        parsed_level = PermissionLevel.from_label(level) if level else None
        entries = await asyncio.to_thread(
            audit.query, tool=tool, level=parsed_level, ok=ok, limit=limit)
        return {"eintraege": [e.as_dict() for e in entries]}

    @app.get("/api/undo", dependencies=Guarded)
    async def list_undo(limit: int = 20) -> dict:
        records = await asyncio.to_thread(registry.undo_store.list, limit)
        return {"eintraege": [
            {"id": r.id, "zeit": r.ts, "werkzeug": r.tool,
             "beschreibung": r.description, "rueckgaengig_gemacht": r.undone}
            for r in records]}

    @app.post("/api/undo", dependencies=Guarded)
    async def do_undo(body: UndoIn) -> dict:
        try:
            summary = await asyncio.to_thread(registry.undo_store.undo, body.record_id or None)
        except UndoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ergebnis": summary}

    # ------------------------------------------------------------- Makros
    @app.get("/api/macros", dependencies=Guarded)
    async def list_macros() -> dict:
        """Gespeicherte Makros (Punkt 46) -- direkt, wie ``/api/tools``: die
        Kommando-Palette braucht sie, um ein Makro per Klick zu starten, ohne
        den Umweg über den Chat und ohne eine eigene, zweite Ablage."""
        macros = await asyncio.to_thread(registry.macro_store.list)
        return {"makros": [m.as_dict() for m in macros]}

    # ------------------------------------------------------ Werkzeuge (Punkt 47)
    # Derselbe Suchindex und dieselbe Historie wie ``jarvis.tools.*`` (Punkt 36),
    # hier direkt über HTTP statt über einen Modell-Zug -- die Command Palette
    # und der Tool Explorer im Frontend brauchen eine sofortige Antwort, kein
    # Werkzeugergebnis, das erst durch ``guard.verify()`` läuft.
    def tool_row(tool, favorites: set[str], disabled: dict[str, str],
                score: float | None = None) -> dict:
        zustand, grund = availability(tool)
        row = {
            "id": tool.name, "kategorie": tool.category, "unterkategorie": tool.subcategory,
            "beschreibung": tool.description, "stufe": tool.level.label, "risiko": tool.risk,
            "tags": list(tool.tags), "verfuegbarkeit": zustand.value,
            "verfuegbarkeit_grund": grund, "favorit": tool.name in favorites,
            "abgeschaltet": tool.name in disabled,
        }
        if score is not None:
            row["punkte"] = round(score, 3)
        return row

    @app.get("/api/tools", dependencies=Guarded)
    async def list_tools(q: str = "", category: str = "", tag: str = "",
                         limit: int = 60) -> dict:
        """Ohne ``q``: der volle, gefilterte Katalog (Tool Explorer). Mit
        ``q``: dieselbe Rangfolge wie im Chat (Action Search)."""
        favorites = set(registry.tool_history.favorites())
        disabled = registry.tool_history.disabled()
        begrenzt = min(max(limit, 1), 200)
        frage = q.strip()
        if frage:
            treffer = registry.discovery.search(
                frage, limit=begrenzt, category=category or None,
                tags=(tag,) if tag else None)
            rows = [tool_row(h.tool, favorites, disabled, h.score) for h in treffer]
        else:
            auswahl = registry.filter(category, tag)
            rows = [tool_row(t, favorites, disabled) for t in auswahl[:begrenzt]]
        return {"werkzeuge": rows, "gesamt_im_katalog": len(registry),
               "kategorien": registry.categories()}

    @app.post("/api/tools/{tool_name}/{action}", dependencies=Guarded)
    async def control_tool(tool_name: str, action: ToolAction,
                           body: ToolActionIn = ToolActionIn()) -> dict:
        if tool_name not in registry:
            raise HTTPException(status_code=404, detail=f"Unbekanntes Werkzeug: {tool_name}")
        real = registry.resolve(tool_name)
        history = registry.tool_history
        if action == "favorite":
            history.favorite(real)
        elif action == "unfavorite":
            if not history.unfavorite(real):
                raise HTTPException(status_code=409, detail=f"{real} war kein Favorit.")
        elif action == "disable":
            try:
                history.disable(real, body.reason)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif action == "enable":
            if not history.enable(real):
                raise HTTPException(status_code=409, detail=f"{real} war nicht abgeschaltet.")
        # Direkter Nutzer-Weg wie /api/undo, /api/goals/*/{pause,resume,cancel}
        # -- ohne Permission-Gate (der Nutzer bedient hier sein eigenes
        # Steuerelement, kein Modell handelt in seinem Namen), aber mit
        # Audit-Eintrag, damit "wer hat wann favorisiert/abgeschaltet" auch
        # außerhalb des Chat-Wegs nachvollziehbar bleibt.
        audit.record(tool=f"jarvis.tools.{action}", level=PermissionLevel.WRITE,
                    arguments={"name": real, "grund": body.reason} if action == "disable"
                    else {"name": real},
                    ok=True, summary=f"{real}: {action} (Kommando-Palette)",
                    request="command-palette")
        return {"angefordert": action, "werkzeug": real}

    @app.post("/api/permission/resolve", dependencies=Guarded)
    async def resolve_permission(body: PermissionResolveIn) -> dict:
        """Antwort auf ein ``permission.requested``-Ereignis -- von jedem
        Gerät, nicht nur dem, das die Aufgabe gestellt hat."""
        found = permission_gate.resolve(body.request_id, body.approved)
        return {"gefunden": found}

    # ------------------------------------------------------- Fokus-Modus
    @app.post("/api/focus-mode", dependencies=Guarded)
    async def set_focus_mode(body: FocusModeIn) -> dict:
        """Schaltet den Fokus-Modus um (siehe ``agent.py``): solange er läuft,
        laufen WRITE/SYSTEM-Werkzeuge im Code-Modus ohne Bestätigung.
        CRITICAL bleibt davon unberührt -- das ist in ``permissions.py`` fest
        verdrahtet, kein Konfigurationswert."""
        an = await agent.set_focus_mode(body.an)
        return {"fokus_modus": an}

    # --------------------------------------------------------- Autonomie
    @app.put("/api/autonomy", dependencies=Guarded)
    async def set_autonomy(body: AutonomyIn) -> dict:
        """Die Autonomiestufe (``autonomy.py``) -- das Steuerelement des
        Nutzers, wie ``/api/focus-mode``. Das Modell kommt hier nicht hin:
        Kein Werkzeug ändert die Stufe, und Jarvis' HTTP-Werkzeuge senden nur
        GET/HEAD. Gespeichert in der jarvis.json, damit ein Neustart nicht
        still auf eine andere Stufe zurückfällt; der Audit-Eintrag hält fest,
        wann sie von wo nach wo ging."""
        vorher = config.autonomy
        neu = AutonomyLevel.from_value(body.stufe)
        config.autonomy_level = int(neu)
        config.save()
        audit.record(tool="jarvis.autonomy.set", level=PermissionLevel.SYSTEM,
                     arguments={"vorher": int(vorher), "stufe": int(neu)}, ok=True,
                     summary=f"Autonomiestufe {int(vorher)} → {int(neu)} ({neu.label})",
                     request="oberflaeche")
        stand = autonomy_state()
        await hub.send("autonomy", stand)
        return stand

    @app.get("/api/tasks", dependencies=Guarded)
    async def list_tasks(limit: int = 20) -> dict:
        """Task History (Agent Mode) -- Grundlage der späteren Task-Queue-
        Oberfläche (Phase 7); heute schon abrufbar für Nachvollziehbarkeit."""
        found = await asyncio.to_thread(tasks.list, limit)
        return {"aufgaben": [t.as_dict() for t in found]}

    @app.get("/api/tasks/{task_id}", dependencies=Guarded)
    async def get_task(task_id: str) -> dict:
        task = await asyncio.to_thread(tasks.get, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unbekannte Aufgabe: {task_id}")
        return task.as_dict()

    # ------------------------------------------------------------- Ziele
    @app.get("/api/goals", dependencies=Guarded)
    async def list_goals(limit: int = 20, status: str | None = None) -> dict:
        """Die verfolgten Ziele -- die Ebene über den Aufgaben (``/api/tasks``):
        Priorität, Fortschritt, aktueller Schritt, Budget."""
        try:
            parsed = GoalStatus(status) if status else None
        except ValueError as exc:
            raise HTTPException(status_code=400,
                                detail=f"Unbekannter Status: {status}") from exc
        found = await asyncio.to_thread(goals.list, limit, parsed)
        laufend = {g.id for g in agent.active_goals}
        return {"ziele": [g.as_dict() | {"steuerbar": g.id in laufend} for g in found]}

    @app.get("/api/goals/{goal_id}", dependencies=Guarded)
    async def get_goal(goal_id: str) -> dict:
        goal = await asyncio.to_thread(goals.get, goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail=f"Unbekanntes Ziel: {goal_id}")
        laufend = {g.id for g in agent.active_goals}
        return goal.as_dict() | {
            "steuerbar": goal.id in laufend,
            "entscheidungen": await asyncio.to_thread(decisions.log.list, 20, goal_id),
        }

    @app.post("/api/goals/{goal_id}/{action}", dependencies=Guarded)
    async def control_goal(goal_id: str, action: GoalAction) -> dict:
        """Pause, Fortsetzen, Abbruch (Punkt 7/22).

        Die Antwort sagt ausdrücklich "angefordert", nicht "erledigt": ein
        laufendes Ziel hält an seinem nächsten Haltepunkt an, nicht mitten in
        einem Werkzeugaufruf. Was tatsächlich passiert ist, steht danach im
        Status des Ziels -- nicht in dieser Antwort."""
        if await asyncio.to_thread(goals.get, goal_id) is None:
            raise HTTPException(status_code=404, detail=f"Unbekanntes Ziel: {goal_id}")
        handler = {"pause": agent.pause_goal, "resume": agent.resume_goal,
                   "cancel": agent.cancel_goal}[action]
        touched = handler(goal_id)
        if not touched:
            raise HTTPException(
                status_code=409,
                detail=(f"Ziel {goal_id} läuft gerade nicht -- es lässt sich weder "
                        "pausieren noch abbrechen."))
        return {"angefordert": action, "ziel": goal_id}

    # ------------------------------------------------------ Erweiterungsmodus
    @app.get("/api/extension-mode", dependencies=Guarded)
    async def get_extension_mode() -> dict:
        """``status`` ist ``null``, solange nichts läuft."""
        return {"status": agent.extension_status}

    @app.post("/api/extension-mode/{action}", dependencies=Guarded)
    async def control_extension_mode(action: ExtensionAction) -> dict:
        """Start/Pause/Fortsetzen/Stopp der Erweiterungsmodus-Schleife
        (siehe ``agent.py``, ``Agent.start_extension_mode``). "start" läuft
        auch, wenn gerade nichts läuft -- das ist der Sinn dieses einen
        Zweigs; die anderen drei brauchen eine bereits laufende Schleife."""
        if action == "start":
            reply = await agent.start_extension_mode()
            await hub.send("message", {"who": "jarvis", **reply.as_event()})
            return {"angefordert": action, "status": agent.extension_status}
        handler = {"pause": agent.pause_extension_mode, "resume": agent.resume_extension_mode,
                   "stop": agent.stop_extension_mode}[action]
        touched = handler()
        if not touched:
            raise HTTPException(status_code=409,
                                detail="Der Erweiterungsmodus läuft gerade nicht.")
        return {"angefordert": action, "status": agent.extension_status}

    # -------------------------------------------------------- Ereignisse
    @app.post("/api/events", dependencies=Guarded)
    async def post_event(body: EventIn) -> dict:
        """Ein Ereignis melden (Punkt 8). Die Antwort sagt, was daraus folgt:
        nichts, ein Vorschlag, oder ein gestartetes Ziel."""
        event = await bus.publish(Event(kind=body.kind, source=body.source,
                                        severity=body.severity, payload=body.payload))
        return {"ereignis": event.as_dict(),
                **reactions.pop(event.id, {"reaktion": "keine", "vorschlag": None})}

    @app.get("/api/events", dependencies=Guarded)
    async def list_events(limit: int = 50) -> dict:
        recent = list(bus.recent)[-max(1, min(int(limit or 50), 200)):]
        return {"ereignisse": [e.as_dict() for e in reversed(recent)],
                "offene_vorschlaege": [p.as_dict() for p in pending_proposals.values()]}

    @app.post("/api/proactive/{proposal_id}", dependencies=Guarded)
    async def resolve_proposal(proposal_id: str, body: ProposalIn) -> dict:
        """Zustimmung oder Ablehnung zu einem Vorschlag. Ohne Zustimmung
        passiert nichts -- der Vorschlag wird verworfen, nicht aufgeschoben."""
        proposal = pending_proposals.pop(proposal_id, None)
        if proposal is None:
            raise HTTPException(status_code=404,
                                detail=f"Unbekannter Vorschlag: {proposal_id}")
        if not body.approved:
            await hub.send("proactive.declined", proposal.as_dict())
            return {"gestartet": False, "ziel": None}
        goal, reply = await agent.start_goal(proposal.goal)
        await hub.send("message", {"who": "jarvis", **reply.as_event()})
        return {"gestartet": goal is not None, "ziel": goal.id if goal else None}

    @app.get("/api/decisions", dependencies=Guarded)
    async def list_decisions(limit: int = 50, goal_id: str | None = None) -> dict:
        """Jede Abwägung ist nachlesbar (Punkt 3: "Die Entscheidung muss
        geloggt werden")."""
        return {"entscheidungen": await asyncio.to_thread(decisions.log.list, limit, goal_id)}

    @app.put("/api/whisper/key", dependencies=Guarded)
    async def set_whisper_key(body: WhisperKeyIn) -> dict:
        """Der Nutzer trägt seinen eigenen Whisper-Schlüssel ein. Leer löscht ihn."""
        config.whisper.api_key = body.api_key.strip()
        whisper.api_key = config.whisper.api_key
        config.save()
        return {"konfiguriert": whisper.configured}

    @app.post("/api/whisper/transcribe", dependencies=Guarded)
    async def transcribe(audio: UploadFile = File(...)) -> dict:
        """Spracheingabe -> Text. Nur ein echtes Whisper-Ergebnis wird zurückgegeben,
        nie eine Vermutung, falls der Aufruf scheitert."""
        daten = await audio.read()
        try:
            text = await asyncio.to_thread(
                whisper.transcribe, daten, audio.filename or "sprache.webm",
                audio.content_type or "audio/webm")
        except WhisperError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"text": text}

    @app.post("/api/command", dependencies=Guarded)
    async def command(body: CommandIn) -> dict:
        """Ein Zug über HTTP, für Skripte und zum Testen ohne WebSocket."""
        reply = await run_turn(body.text, body.mode)
        return reply.as_event()

    # ------------------------------------------------------------- Ein Zug
    async def run_turn(text: str, mode: str = "chat") -> guard.Reply:
        # Der Agent-Modus nimmt das Lock bewusst NICHT: ein Ziel läuft im
        # Hintergrund weiter, und genau darum geht es (Punkt 7 -- "Der Nutzer
        # kann Jarvis etwas fragen, während er weiterarbeitet"). Zurück kommt
        # sofort eine Zwischenmeldung; das Ergebnis stellt der Hintergrund-Lauf
        # später als eigene Nachricht zu.
        if mode == "agent":
            await hub.send("message", {"who": "me", "text": text, "mode": mode})
            _goal, reply = await agent.start_goal(text)
            await hub.send("message", {"who": "jarvis", **reply.as_event()})
            return reply

        if busy.locked():
            return guard.Reply(
                text="Ich bin noch mit der vorigen Aufgabe beschäftigt.",
                provenance=guard.TALK)
        async with busy:
            await hub.send("message", {"who": "me", "text": text, "mode": mode})
            try:
                if mode == "code":
                    reply = await agent.handle_code(text)
                elif mode == "macro":
                    reply = await agent.run_macro(text)
                else:
                    reply = await agent.handle(text)
            except Exception as exc:  # noqa: BLE001 - der Zug wird per
                # asyncio.create_task abgefeuert; ohne dieses Netz stirbt ein
                # unerwarteter Fehler lautlos im Hintergrund und der Nutzer
                # starrt auf "Denke", ohne je eine Antwort zu bekommen. Ein
                # interner Fehler ist auch ein ehrliches Ergebnis -- gemeldet
                # wird er, nicht verschwiegen.
                await hub.send("state", {"mode": "failed", "detail": ""})
                reply = guard.Reply(
                    text=f"Intern ist ein Fehler aufgetreten: {exc}",
                    provenance=guard.FAIL)
            await hub.send("message", {"who": "jarvis", **reply.as_event()})
            return reply

    # ----------------------------------------------------------- WebSocket
    @app.websocket("/ws")
    async def socket(ws: WebSocket, token: str | None = Query(default=None)) -> None:
        try:
            check_token(token)
        except HTTPException:
            await ws.close(code=4401)
            return
        await ws.accept()
        await hub.add(ws)
        try:
            await ws.send_text(json.dumps(
                {"type": "hello", **await snapshot(),
                 "gedaechtnis": store.graph(),
                 "telemetrie": system_tools.telemetry()}, ensure_ascii=False))
            while True:
                raw = await ws.receive_text()
                try:
                    payload = json.loads(raw)
                except ValueError:
                    continue
                if payload.get("type") == "command":
                    text = str(payload.get("text") or "").strip()[:20000]
                    mode = payload.get("mode") if payload.get("mode") in _MODES else "chat"
                    if text:
                        asyncio.create_task(run_turn(text, mode))
                elif payload.get("type") == "memory":
                    graph = payload.get("graph") or {}
                    if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
                        await asyncio.to_thread(store.replace_graph, graph)
                        await hub.send("memory", store.graph())
                elif payload.get("type") == "permission":
                    request_id = str(payload.get("request_id") or "")
                    if request_id:
                        permission_gate.resolve(request_id, bool(payload.get("approved")))
        except WebSocketDisconnect:
            pass
        finally:
            await hub.drop(ws)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> JSONResponse:
        """Der Browser fragt immer danach; ein 404 im Log wäre nur Rauschen."""
        return JSONResponse({}, status_code=204)

    # ------------------------------------------------------- Oberfläche
    index = WEB_DIR / "index.html"
    if index.is_file():
        @app.get("/")
        async def ui() -> FileResponse:
            return FileResponse(index)
    else:  # pragma: no cover - nur wenn jarvis/web fehlt
        @app.get("/")
        async def ui_missing() -> JSONResponse:
            return JSONResponse(
                {"fehler": f"Oberfläche nicht gefunden: {index}"}, status_code=500)

    # Installierbarkeit als App (Startbildschirm/Standalone): Manifest,
    # Service Worker und Icons liegen als eigene Dateien neben index.html
    # und werden nur ausgeliefert, wenn sie tatsächlich existieren.
    for name, media_type in (
        ("manifest.webmanifest", "application/manifest+json"),
        ("service-worker.js", "application/javascript"),
    ):
        path = WEB_DIR / name
        if path.is_file():
            route = f"/{name}"

            def _serve(path: Path = path, media_type: str = media_type) -> FileResponse:
                return FileResponse(path, media_type=media_type)

            app.add_api_route(route, _serve, methods=["GET"], include_in_schema=False)

    icons_dir = WEB_DIR / "icons"
    if icons_dir.is_dir():
        app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

    return app
