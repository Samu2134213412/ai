"""Der Jarvis-Server: HTTP, WebSocket und die Oberfläche aus ``jarvis/web``.

Ein Zug wird an **alle** verbundenen Geräte gesendet. Was auf dem PC angefangen
wird, läuft auf dem Handy weiter — es ist dieselbe Sitzung, derselbe Verlauf,
dasselbe Gedächtnis. Genau das war gemeint mit „ein Manager für meinen PC und
mein Handy".
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

from typing import Literal

from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import guard
from .agent import Agent
from .audit import AuditLog
from .config import Config
from .memory import DEFAULT_SEED, MemoryStore
from .ollama import OllamaClient
from .permissions import PermissionGate, PermissionLevel, PermissionPolicy
from .tasks import TaskManager
from .undo import UndoError
from .tools import build_registry, system as system_tools, tool_status
from .whisper import WhisperClient, WhisperError

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
TELEMETRY_SECONDS = 3.0
CODEPILOT_STATUS_SECONDS = 4.0


#: "code" geht immer direkt an codepilot_task, ohne das Chat-Modell zu
#: befragen -- der Nutzer hat den Modus bewusst gewählt. "agent" zerlegt den
#: Auftrag zuerst in Schritte (Planner) und führt sie einzeln aus (Executor,
#: siehe ``Agent.handle_agent_task``).
CommandMode = Literal["chat", "code", "agent"]
_MODES: tuple[str, ...] = ("chat", "code", "agent")


class CommandIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    mode: CommandMode = "chat"


class GraphIn(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    links: list[list] = Field(default_factory=list)


class WhisperKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=200)


class PermissionResolveIn(BaseModel):
    request_id: str = Field(..., min_length=1)
    approved: bool = False


class UndoIn(BaseModel):
    record_id: str = Field(default="")


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
    agent = Agent(config, store, registry, client, emit=hub.send,
                  permission_gate=permission_gate, audit=audit, undo=registry.undo_store,
                  tasks=tasks)
    busy = asyncio.Lock()
    whisper = WhisperClient(api_key=config.whisper.api_key, model=config.whisper.model,
                            timeout=config.whisper.timeout)

    # -------------------------------------------------------- Telemetrie
    async def telemetry_loop() -> None:
        while True:
            await asyncio.sleep(TELEMETRY_SECONDS)
            if hub.count:
                values = await asyncio.to_thread(system_tools.telemetry)
                if values:
                    await hub.send("telemetry", values)

    # ------------------------------------------------- CodePilot-Statusmelder
    async def codepilot_status_loop() -> None:
        """Zeigt, ob CodePilot läuft und ob die Kette dahinter bereit ist --
        ohne dass jemand in ein Konsolenfenster schauen muss."""
        letzter: dict | None = None
        while True:
            await asyncio.sleep(CODEPILOT_STATUS_SECONDS)
            if not hub.count or not registry.codepilot_link.configured:
                continue
            status = await asyncio.to_thread(registry.codepilot_link.status_snapshot)
            if status != letzter:
                letzter = status
                await hub.send("codepilot_status", status)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        ticker = asyncio.create_task(telemetry_loop())
        codepilot_ticker = asyncio.create_task(codepilot_status_loop())
        try:
            yield
        finally:
            for task in (ticker, codepilot_ticker):
                task.cancel()
            for task in (ticker, codepilot_ticker):
                with contextlib.suppress(asyncio.CancelledError):
                    await task

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

    # ------------------------------------------------------------ Zugang
    def check_token(supplied: str | None) -> None:
        """Ohne Token nur vom eigenen Rechner. Mit Token von überall."""
        if not config.token:
            if not config.is_loopback:
                raise HTTPException(status_code=503, detail=(
                    "Der Server ist aus dem Netz erreichbar, aber es ist kein "
                    "Token gesetzt. Das ist abgelehnt, nicht offen."))
            return
        if supplied != config.token:
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
        return {
            "host": config.host,
            "model": config.model,
            "modelle": [
                {"id": config.model, "loaded": health.model_present,
                 "via": "Ollama · direkt"},
                {"id": config.codepilot.project_id and "qwen3-coder:30b" or "—",
                 "loaded": "codepilot_task" in registry,
                 "via": "CodePilot → Claude Code → Ollama"},
            ],
            "ollama": {"online": health.online, "version": health.version,
                       "modell_vorhanden": health.model_present,
                       "hinweis": health.detail},
            "werkzeuge": tool_status(registry, config),
            "arbeitsbereich": config.roots,
            "shell_aktiv": config.shell.enabled,
            "probleme": config.validate(),
            "geraete": hub.count,
            "codepilot_status": registry.codepilot_link.status_snapshot(),
            "whisper_configured": whisper.configured,
            "berechtigungen": {
                "read": permission_gate.policy.requires_confirmation(PermissionLevel.READ),
                "write": permission_gate.policy.requires_confirmation(PermissionLevel.WRITE),
                "system": permission_gate.policy.requires_confirmation(PermissionLevel.SYSTEM),
                "critical": True,  # nie abschaltbar, siehe permissions.py
                "offen": len(permission_gate.pending),
            },
        }

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

    @app.post("/api/permission/resolve", dependencies=Guarded)
    async def resolve_permission(body: PermissionResolveIn) -> dict:
        """Antwort auf ein ``permission.requested``-Ereignis -- von jedem
        Gerät, nicht nur dem, das die Aufgabe gestellt hat."""
        found = permission_gate.resolve(body.request_id, body.approved)
        return {"gefunden": found}

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
        if busy.locked():
            return guard.Reply(
                text="Ich bin noch mit der vorigen Aufgabe beschäftigt.",
                provenance=guard.TALK)
        async with busy:
            await hub.send("message", {"who": "me", "text": text, "mode": mode})
            try:
                if mode == "code":
                    reply = await agent.handle_code(text)
                elif mode == "agent":
                    reply = await agent.handle_agent_task(text)
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

    return app
