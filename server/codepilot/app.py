"""FastAPI application: REST API, WebSocket, model gateway and web dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from pathlib import Path

from fastapi import (Depends, FastAPI, Header, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, compat_proxy, detect, git_tools
from .api_models import (ApprovalDecision, InternalApprovalRequest, MessageIn,
                         PairRequest, ProjectCreate, SessionCreate, SettingsUpdate)
from .bridge.approvals import ApprovalBroker
from .bridge.claude_session import BridgeError, SessionManager
from .config import CONTEXT_CHOICES, SettingsStore
from .db import Database
from .events import EventHub
from .providers import PROVIDERS, get_provider
from .security import (AuthError, DeviceAuth, PairingManager, PathNotAllowed,
                       extract_bearer, normalize_project_path)

WEB_DIR = Path(__file__).parent / "web"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def create_app(settings_store: SettingsStore | None = None,
               db: Database | None = None) -> FastAPI:
    store = settings_store or SettingsStore()
    database = db or Database()
    hub = EventHub(database)
    broker = ApprovalBroker(database, hub, timeout=store.current.approval_timeout)
    device_auth = DeviceAuth(database)
    pairing = PairingManager()

    def backend_url() -> str:
        # Claude Code and the MCP child always reach us over loopback, whatever
        # the bind mode is.
        return f"http://127.0.0.1:{store.current.port}"

    sessions = SessionManager(database, hub, broker, store, get_provider, backend_url)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        orphaned = sessions.reconcile_on_boot()
        if orphaned:
            print(f"[codepilot] marked {orphaned} interrupted session(s) as failed")
        yield
        await sessions.shutdown()

    app = FastAPI(title="CodePilot Remote", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.db = database
    app.state.hub = hub
    app.state.broker = broker
    app.state.pairing = pairing
    app.state.device_auth = device_auth
    app.state.sessions = sessions

    # ---------------------------------------------------------- dependencies
    def require_device(authorization: str | None = Header(default=None)) -> dict:
        try:
            return device_auth.authenticate(extract_bearer(authorization))
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc),
                                headers={"WWW-Authenticate": "Bearer"}) from None

    def require_local(request: Request) -> None:
        """Desktop-only endpoints (pairing, settings, project allowlist).

        A phone must never be able to widen the allowlist or mint credentials,
        so these are restricted to the machine the server runs on.
        """
        client = request.client.host if request.client else None
        if client not in LOOPBACK:
            raise HTTPException(
                status_code=403,
                detail="This action is only available from the desktop dashboard "
                       "on the PC itself.")

    def require_internal(request: Request,
                         x_codepilot_internal: str | None = Header(default=None)) -> None:
        client = request.client.host if request.client else None
        if client not in LOOPBACK:
            raise HTTPException(status_code=403, detail="internal endpoint")
        import hmac
        if not x_codepilot_internal or not hmac.compare_digest(
                x_codepilot_internal, store.current.internal_token):
            raise HTTPException(status_code=401, detail="bad internal token")


    # ------------------------------------------------------- model gateway
    # Mounted as /llm so ANTHROPIC_BASE_URL=http://127.0.0.1:<port>/llm resolves
    # to /llm/v1/messages, which is what Claude Code requests.
    app.include_router(compat_proxy.build_router(lambda: store.current), prefix="/llm")

    # ------------------------------------------------------------- probing
    @app.get("/api/health")
    async def health() -> dict:
        """Unauthenticated liveness probe.

        The mobile app hits this on each candidate address (LAN, Tailscale) to
        pick one that works. It deliberately exposes nothing but identity.
        """
        return {"service": "codepilot-remote", "version": __version__,
                "auth_required": True}

    # ------------------------------------------------------------- pairing
    @app.post("/api/pairing/token", dependencies=[Depends(require_local)])
    async def create_pairing_token() -> dict:
        token = pairing.issue()
        settings = store.current
        tailscale = await detect.detect_tailscale()
        addresses = detect.server_addresses(settings, tailscale)
        payload = {
            "v": 1,
            "token": token.token,
            "addresses": [a["url"] for a in addresses if a["kind"] != "local"] or
                         [a["url"] for a in addresses],
        }
        return {
            "token": token.token,
            "expires_at": token.created_at + 300,
            "addresses": addresses,
            "qr_payload": json.dumps(payload, separators=(",", ":")),
            "warning": None if settings.bind_mode == "private" else
                       "The server is bound to 127.0.0.1, so your phone cannot reach it. "
                       "Switch Network access to 'LAN + Tailscale' in Settings and restart.",
        }

    @app.delete("/api/pairing/token", dependencies=[Depends(require_local)])
    async def revoke_pairing_tokens() -> dict:
        pairing.revoke_all()
        return {"ok": True}

    @app.get("/api/pairing/qr.svg", dependencies=[Depends(require_local)])
    async def pairing_qr(payload: str):
        try:
            import qrcode
            import qrcode.image.svg
        except ImportError:
            raise HTTPException(status_code=501,
                                detail="qrcode is not installed; pip install qrcode") from None
        img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage,
                          box_size=10, border=2)
        import io
        buf = io.BytesIO()
        img.save(buf)
        return PlainTextResponse(buf.getvalue().decode("utf-8"), media_type="image/svg+xml")

    @app.post("/api/pair")
    async def pair(body: PairRequest) -> dict:
        try:
            pairing.redeem(body.token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from None
        device, raw = device_auth.register(body.device_name)
        return {
            "device_id": device["id"],
            "device_name": device["name"],
            "device_token": raw,  # shown exactly once
            "server": {"version": __version__, "name": "CodePilot Remote"},
        }

    @app.get("/api/devices", dependencies=[Depends(require_local)])
    async def list_devices() -> dict:
        return {"devices": database.list_devices()}

    @app.delete("/api/devices/{device_id}", dependencies=[Depends(require_local)])
    async def revoke_device(device_id: str) -> dict:
        database.revoke_device(device_id)
        return {"ok": True}

    # -------------------------------------------------------------- status
    @app.get("/api/status")
    async def status(_: dict = Depends(require_device)) -> dict:
        return await detect.gather_environment(store.current)

    @app.get("/api/status/local", dependencies=[Depends(require_local)])
    async def status_local() -> dict:
        return await detect.gather_environment(store.current)

    # ------------------------------------------------------------- settings
    @app.get("/api/settings", dependencies=[Depends(require_local)])
    async def get_settings() -> dict:
        return {"settings": store.current.public_fields(),
                "context_choices": CONTEXT_CHOICES,
                "providers": sorted(PROVIDERS)}

    @app.put("/api/settings", dependencies=[Depends(require_local)])
    async def put_settings(body: SettingsUpdate) -> dict:
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            updated = store.update(changes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        broker.timeout = updated.approval_timeout
        restart_needed = any(k in changes for k in ("bind_mode", "port"))
        return {"settings": updated.public_fields(), "restart_required": restart_needed}

    @app.get("/api/models")
    async def models(_: dict = Depends(require_device)) -> dict:
        provider = get_provider(store.current)
        health = await provider.health()
        return {
            "provider": provider.key,
            "configured": store.current.ollama_model,
            "installed": health.installed_models,
            "online": health.online,
            "model_available": health.model_available,
            "detail": health.detail,
            "remedy": health.remedy,
            "install_command": provider.install_hint(store.current.ollama_model),
            "context_choices": CONTEXT_CHOICES,
            "context_length": store.current.context_length,
        }

    @app.get("/api/models/local", dependencies=[Depends(require_local)])
    async def models_local() -> dict:
        return await models(_={"id": "local"})  # type: ignore[arg-type]

    # ------------------------------------------------------------- projects
    def _project_view(row: dict) -> dict:
        path = row["path"]
        view = dict(row)
        view["exists"] = Path(path).is_dir()
        if not view["exists"]:
            view.update({"git": None,
                         "error": "the project directory no longer exists"})
            return view
        try:
            view["git"] = git_tools.status(path)
            view["error"] = None
        except git_tools.GitUnavailable as exc:
            view["git"] = None
            view["error"] = str(exc)
        return view

    @app.get("/api/projects")
    async def list_projects(_: dict = Depends(require_device)) -> dict:
        return {"projects": [_project_view(p) for p in database.list_projects()]}

    @app.get("/api/projects/local", dependencies=[Depends(require_local)])
    async def list_projects_local() -> dict:
        return {"projects": [_project_view(p) for p in database.list_projects()]}

    @app.post("/api/projects", dependencies=[Depends(require_local)])
    async def add_project(body: ProjectCreate) -> dict:
        try:
            resolved = normalize_project_path(body.path)
        except PathNotAllowed as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if database.get_project_by_path(str(resolved)):
            raise HTTPException(status_code=409, detail="that path is already a project")
        project = database.add_project(str(uuid.uuid4()), body.name.strip(), str(resolved))
        return {"project": _project_view(project)}

    @app.delete("/api/projects/{project_id}", dependencies=[Depends(require_local)])
    async def delete_project(project_id: str) -> dict:
        if database.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="unknown project")
        database.delete_project(project_id)
        return {"ok": True}

    def _require_project(project_id: str) -> dict:
        project = database.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="unknown project")
        return project

    @app.get("/api/projects/{project_id}/git")
    async def project_git(project_id: str, _: dict = Depends(require_device)) -> dict:
        project = _require_project(project_id)
        try:
            return {"git": git_tools.status(project["path"])}
        except git_tools.GitUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.get("/api/projects/{project_id}/changes")
    async def project_changes(project_id: str, base: str | None = None,
                              _: dict = Depends(require_device)) -> dict:
        project = _require_project(project_id)
        try:
            files = git_tools.changed_files(project["path"], base)
        except git_tools.GitUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return {"files": files,
                "total_added": sum(f["added"] for f in files),
                "total_removed": sum(f["removed"] for f in files)}

    @app.get("/api/projects/{project_id}/diff")
    async def project_diff(project_id: str, path: str, base: str | None = None,
                           _: dict = Depends(require_device)) -> dict:
        project = _require_project(project_id)
        # Containment check: `path` comes from a phone, so it is validated
        # against the project root before it reaches git.
        from .security import ensure_within
        try:
            ensure_within(project["path"], path)
        except PathNotAllowed as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        try:
            diff = git_tools.file_diff(project["path"], path, base)
        except git_tools.GitUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return {"path": path, "diff": diff, "base": base}

    # -------------------------------------------------------------- sessions
    @app.get("/api/sessions")
    async def list_sessions(project_id: str | None = None, limit: int = 50,
                            _: dict = Depends(require_device)) -> dict:
        rows = database.list_sessions(project_id, min(limit, 200))
        for row in rows:
            row["live"] = row["id"] in sessions.live
        return {"sessions": rows}

    @app.get("/api/sessions/local", dependencies=[Depends(require_local)])
    async def list_sessions_local(limit: int = 50) -> dict:
        rows = database.list_sessions(None, min(limit, 200))
        for row in rows:
            row["live"] = row["id"] in sessions.live
        return {"sessions": rows}

    def _require_session(session_id: str) -> dict:
        row = database.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown session")
        return row

    @app.post("/api/sessions", status_code=201)
    async def create_session(body: SessionCreate, _: dict = Depends(require_device)) -> dict:
        try:
            row = await sessions.create(
                project_id=body.project_id, prompt=body.prompt, model=body.model,
                permission_mode=body.permission_mode,
                context_length=body.context_length,
                resume_session_id=body.resume_session_id)
        except BridgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"session": row}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, _: dict = Depends(require_device)) -> dict:
        row = _require_session(session_id)
        row["live"] = session_id in sessions.live
        row["pending_approvals"] = database.pending_approvals(session_id)
        return {"session": row, "project": database.get_project(row["project_id"])}

    @app.get("/api/sessions/{session_id}/events")
    async def session_events(session_id: str, after: int = 0, limit: int = 1000,
                             _: dict = Depends(require_device)) -> dict:
        _require_session(session_id)
        events = database.get_events(session_id, after, min(limit, 5000))
        return {"events": events,
                "last_seq": events[-1]["seq"] if events else after}

    @app.post("/api/sessions/{session_id}/stop")
    async def stop_session(session_id: str, _: dict = Depends(require_device)) -> dict:
        _require_session(session_id)
        stopped = await sessions.stop(session_id)
        return {"stopped": stopped}

    @app.post("/api/sessions/{session_id}/message")
    async def session_message(session_id: str, body: MessageIn,
                              _: dict = Depends(require_device)) -> dict:
        _require_session(session_id)
        try:
            await sessions.send_message(session_id, body.text)
        except BridgeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/continue", status_code=201)
    async def continue_session(session_id: str, body: MessageIn,
                               _: dict = Depends(require_device)) -> dict:
        """Start a new Claude Code turn that resumes this session's context."""
        previous = _require_session(session_id)
        try:
            row = await sessions.create(
                project_id=previous["project_id"], prompt=body.text,
                model=previous["model"], permission_mode=previous["permission_mode"],
                resume_session_id=session_id)
        except BridgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"session": row}

    @app.get("/api/sessions/{session_id}/changes")
    async def session_changes(session_id: str, _: dict = Depends(require_device)) -> dict:
        row = _require_session(session_id)
        project = database.get_project(row["project_id"])
        if project is None:
            raise HTTPException(status_code=404, detail="the project was deleted")
        try:
            files = git_tools.changed_files(project["path"], row["base_commit"])
        except git_tools.GitUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return {"files": files, "base": row["base_commit"],
                "project_id": project["id"],
                "total_added": sum(f["added"] for f in files),
                "total_removed": sum(f["removed"] for f in files)}

    # ------------------------------------------------------------- approvals
    @app.get("/api/approvals")
    async def list_approvals(session_id: str | None = None,
                             _: dict = Depends(require_device)) -> dict:
        return {"approvals": database.pending_approvals(session_id)}

    @app.post("/api/approvals/{approval_id}/decide")
    async def decide_approval(approval_id: str, body: ApprovalDecision,
                              _: dict = Depends(require_device)) -> dict:
        record = database.get_approval(approval_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown approval request")
        if record["status"] != "pending":
            raise HTTPException(status_code=409,
                                detail=f"already {record['status']}")
        delivered = await broker.resolve(approval_id, body.approve, body.reason)
        return {"ok": True, "delivered": delivered,
                "note": None if delivered else
                        "Recorded, but Claude Code was no longer waiting for it."}

    @app.post("/internal/approvals/request", dependencies=[Depends(require_internal)])
    async def internal_approval(body: InternalApprovalRequest) -> dict:
        """Called only by the approval MCP server that Claude Code spawns."""
        return await broker.request(body.session_id, body.tool_name, body.tool_input,
                                    body.suggestions)

    # ------------------------------------------------------------- websocket
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token") or extract_bearer(
            websocket.headers.get("authorization"))
        try:
            device = device_auth.authenticate(token)
        except AuthError:
            # Accept-then-close so the client can read a reason instead of a
            # bare handshake failure.
            await websocket.accept()
            await websocket.send_json({"type": "error", "code": "unauthorized",
                                       "message": "pair this device again"})
            await websocket.close(code=4401)
            return

        await websocket.accept()
        target = websocket.query_params.get("session") or "*"
        try:
            after = int(websocket.query_params.get("after") or 0)
        except ValueError:
            after = 0
        verbose = websocket.query_params.get("verbose") == "1"

        await websocket.send_json({
            "type": "connected", "device": device["name"], "scope": target,
            "server_time": time.time(), "version": __version__,
        })

        def frame(event: dict) -> dict:
            # The envelope key must not collide with the event's own "type".
            return {"type": "event", "event_type": event["type"], "seq": event["seq"],
                    "ts": event["ts"], "session_id": event["session_id"],
                    "payload": event["payload"]}

        async with hub.subscribe(target) as queue:
            # Replay what was missed while the phone was away, before any live
            # event, so ordering is preserved.
            if target != "*":
                for event in hub.replay(target, after):
                    if not verbose and event["type"] in ("claude.raw",):
                        continue
                    await websocket.send_json(frame(event))
                    after = event["seq"]
                await websocket.send_json({"type": "replay_complete", "last_seq": after})

            async def pump() -> None:
                while True:
                    event = await queue.get()
                    if event["seq"] <= after and event["session_id"] == target:
                        continue
                    if not verbose and event["type"] in ("claude.raw",):
                        continue
                    await websocket.send_json(frame(event))

            pump_task = asyncio.create_task(pump())
            try:
                while True:
                    raw = await websocket.receive_text()
                    await _handle_ws_command(websocket, raw)
            except WebSocketDisconnect:
                pass
            finally:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump_task

    async def _handle_ws_command(websocket: WebSocket, raw: str) -> None:
        """Small command channel so the phone does not need a second round-trip."""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "invalid JSON"})
            return
        action = message.get("action")
        if action == "ping":
            await websocket.send_json({"type": "pong", "server_time": time.time()})
        elif action == "approve":
            await broker.resolve(message.get("approval_id", ""),
                                 approve=bool(message.get("approve")),
                                 reason=message.get("reason"))
        elif action == "stop":
            await sessions.stop(message.get("session_id", ""))
        elif action == "message":
            try:
                await sessions.send_message(message.get("session_id", ""),
                                            message.get("text", ""))
            except BridgeError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
        else:
            await websocket.send_json({"type": "error",
                                       "message": f"unknown action: {action}"})

    # ------------------------------------------------------------- dashboard
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/")
        async def dashboard() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    @app.exception_handler(PathNotAllowed)
    async def path_handler(_request: Request, exc: PathNotAllowed) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    return app
