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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import guard
from .agent import Agent
from .config import Config
from .memory import DEFAULT_SEED, MemoryStore
from .ollama import OllamaClient
from .tools import build_registry, system as system_tools, tool_status

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
TELEMETRY_SECONDS = 3.0


class CommandIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    #: "code" geht immer direkt an codepilot_task, ohne das Chat-Modell zu
    #: befragen -- der Nutzer hat den Modus bewusst gewählt.
    mode: Literal["chat", "code"] = "chat"


class GraphIn(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    links: list[list] = Field(default_factory=list)


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
    agent = Agent(config, store, registry, client, emit=hub.send)
    busy = asyncio.Lock()

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
                reply = (await agent.handle_code(text) if mode == "code"
                         else await agent.handle(text))
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
                    mode = payload.get("mode") if payload.get("mode") in ("chat", "code") else "chat"
                    if text:
                        asyncio.create_task(run_turn(text, mode))
                elif payload.get("type") == "memory":
                    graph = payload.get("graph") or {}
                    if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
                        await asyncio.to_thread(store.replace_graph, graph)
                        await hub.send("memory", store.graph())
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
