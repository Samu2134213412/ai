"""Runs and supervises real Claude Code processes.

The whole point of CodePilot is that the agent layer stays Claude Code's: we
never send a prompt to Ollama ourselves. We launch the actual CLI in its
project directory with the local model wired in through the documented
``ANTHROPIC_BASE_URL`` contract, and translate its structured output stream into
typed events.

Transport choice: ``--print --output-format stream-json --input-format
stream-json --verbose``. That is Claude Code's supported non-interactive
streaming interface, it gives typed JSON rather than terminal text, and the
stream-json *input* side is what lets the phone send follow-up messages into a
turn that is already running. No PTY is needed, which also means no ANSI parsing
and no terminal-size games.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import sys
import time
import uuid
from pathlib import Path

from .. import events as E
from .. import git_tools
from ..db import Database
from ..events import EventHub
from .approvals import ApprovalBroker
from .normalize import MUTATING_TOOLS, normalize

#: Where `python -m codepilot...` can be imported from, for the MCP child.
PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class BridgeError(Exception):
    """A problem CodePilot can explain, as opposed to a crash."""


class ClaudeCodeSession:
    """One Claude Code subprocess and its event pump."""

    def __init__(self, *, session_id: str, project: dict, prompt: str, settings,
                 provider, db: Database, hub: EventHub, broker: ApprovalBroker,
                 permission_mode: str, model: str, resume_claude_id: str | None = None,
                 backend_url: str):
        self.session_id = session_id
        self.project = project
        self.prompt = prompt
        self.settings = settings
        self.provider = provider
        self.db = db
        self.hub = hub
        self.broker = broker
        self.permission_mode = permission_mode
        self.model = model
        self.resume_claude_id = resume_claude_id
        self.backend_url = backend_url

        self.proc: asyncio.subprocess.Process | None = None
        self._state: dict = {}
        self._pump: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail: list[str] = []
        self._stopping = False
        self._finished = asyncio.Event()
        self.base_commit: str | None = None

    # ------------------------------------------------------------- launching
    def _resolve_binary(self) -> str:
        binary = self.settings.claude_binary
        resolved = shutil.which(binary)
        if resolved:
            return resolved
        if os.path.isabs(binary) and os.path.exists(binary):
            return binary
        raise BridgeError(
            f"Claude Code binary '{binary}' was not found on PATH. "
            f"Install it with `npm install -g @anthropic-ai/claude-code`, or set "
            f"claude_binary in Settings to its full path."
        )

    def _mcp_config(self) -> str:
        """Config for the approval MCP server Claude Code will spawn."""
        return json.dumps({
            "mcpServers": {
                "codepilot": {
                    "command": sys.executable,
                    "args": ["-m", "codepilot.bridge.permission_mcp"],
                    "env": {
                        "PYTHONPATH": PACKAGE_ROOT,
                        "PYTHONUNBUFFERED": "1",
                        "CODEPILOT_BACKEND_URL": self.backend_url,
                        "CODEPILOT_INTERNAL_TOKEN": self.settings.internal_token,
                        "CODEPILOT_SESSION_ID": self.session_id,
                        "CODEPILOT_APPROVAL_TIMEOUT": str(self.settings.approval_timeout),
                    },
                }
            }
        })

    def _build_command(self) -> list[str]:
        cmd = [
            self._resolve_binary(),
            "--print",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--verbose",
            "--model", self.model,
            "--permission-mode", self.permission_mode,
            "--mcp-config", self._mcp_config(),
            # Claude Code decides what needs approval; this only says who answers.
            "--permission-prompt-tool", "mcp__codepilot__approve",
            "--permission-prompts", "host",
        ]
        if self.resume_claude_id:
            cmd += ["--resume", self.resume_claude_id]
        else:
            cmd += ["--session-id", self.session_id]
        return cmd

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Never let a cloud Anthropic credential leak into a "local model" run.
        for stale in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                      "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                      "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
            env.pop(stale, None)

        base_url_override = None
        if self.settings.compat_proxy_enabled:
            base_url_override = f"{self.backend_url.rstrip('/')}/llm"
        env.update(self.provider.claude_env(base_url_override))

        # A local model gets no benefit from update checks and background pings,
        # and they would fail anyway when Claude Code is pointed at localhost.
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        env["CODEPILOT_SESSION_ID"] = self.session_id
        return env

    async def start(self) -> None:
        project_path = Path(self.project["path"])
        if not project_path.is_dir():
            raise BridgeError(
                f"Project directory is missing: {project_path}. It may have been moved "
                f"or deleted — re-add the project with its new path.")

        self.base_commit = git_tools.head_commit(project_path)
        self.db.update_session(self.session_id, base_commit=self.base_commit)

        cmd = self._build_command()
        env = self._build_env()
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_path),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise BridgeError(f"Could not start Claude Code: {exc}") from exc

        await self.hub.publish(self.session_id, E.SESSION_STARTED, {
            "project_id": self.project["id"],
            "project_name": self.project["name"],
            "cwd": str(project_path),
            "prompt": self.prompt,
            "model": self.model,
            "context_length": self.settings.context_length,
            "permission_mode": self.permission_mode,
            "provider": self.provider.key,
            "model_gateway": "codepilot-compat-proxy" if self.settings.compat_proxy_enabled
                             else self.provider.upstream_url(),
            "resumed_from": self.resume_claude_id,
            "base_commit": self.base_commit,
            "pid": self.proc.pid,
        })

        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self._pump = asyncio.create_task(self._pump_stdout())
        await self.send_message(self.prompt, echo=False)

    # ---------------------------------------------------------------- stdin
    async def send_message(self, text: str, echo: bool = True) -> None:
        """Push a user message into the running turn (stream-json input)."""
        if self.proc is None or self.proc.stdin is None or self.proc.returncode is not None:
            raise BridgeError("this session is no longer running")
        frame = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        })
        try:
            self.proc.stdin.write((frame + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise BridgeError("Claude Code closed its input stream") from exc
        if echo:
            await self.hub.publish(self.session_id, E.USER_MESSAGE, {"text": text})

    # --------------------------------------------------------------- reading
    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        try:
            async for raw in self.proc.stderr:
                text = raw.decode("utf-8", "replace").rstrip()
                if not text:
                    continue
                self._stderr_tail.append(text)
                del self._stderr_tail[:-50]
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _pump_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        terminal_seen = False
        try:
            while True:
                try:
                    raw = await self.proc.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    # A single JSON line exceeded the stream buffer limit.
                    await self.hub.publish(self.session_id, E.ERROR, {
                        "message": "Claude Code emitted an oversized output line; it was skipped.",
                        "recoverable": True})
                    continue
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    await self.hub.publish(self.session_id, E.RAW,
                                           {"kind": "unparsed", "line": line[:4000]})
                    continue
                for etype, payload in normalize(obj, self._state):
                    if etype in (E.SESSION_COMPLETED, E.SESSION_FAILED):
                        terminal_seen = True
                    await self._emit(etype, payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            await self.hub.publish(self.session_id, E.ERROR,
                                   {"message": f"bridge read error: {exc!r}", "recoverable": False})
        finally:
            await self._on_exit(terminal_seen)

    async def _emit(self, etype: str, payload: dict) -> None:
        if etype == E.SESSION_STATUS and payload.get("claude_session_id"):
            self.db.update_session(self.session_id,
                                   claude_session_id=payload["claude_session_id"])
        await self.hub.publish(self.session_id, etype, payload)

        if etype == E.TOOL_FINISHED and payload.get("tool_name") in MUTATING_TOOLS:
            await self._emit_file_changes()
        elif etype in (E.SESSION_COMPLETED, E.SESSION_FAILED):
            await self._emit_file_changes()
            status = STATUS_COMPLETED if etype == E.SESSION_COMPLETED else STATUS_FAILED
            self.db.update_session(
                self.session_id, status=status, ended_at=time.time(),
                error=None if status == STATUS_COMPLETED else (payload.get("result") or "")[:2000],
            )

    async def _emit_file_changes(self) -> None:
        try:
            files = await asyncio.to_thread(
                git_tools.changed_files, self.project["path"], self.base_commit)
        except git_tools.GitUnavailable as exc:
            await self.hub.publish(self.session_id, E.ERROR, {
                "message": f"could not read git changes: {exc}", "recoverable": True})
            return
        except OSError as exc:
            await self.hub.publish(self.session_id, E.ERROR, {
                "message": f"project directory unreadable: {exc}", "recoverable": True})
            return
        signature = json.dumps(files, sort_keys=True)
        if signature == self._state.get("last_change_signature"):
            return
        self._state["last_change_signature"] = signature
        await self.hub.publish(self.session_id, E.FILE_CHANGED, {
            "files": files,
            "total_added": sum(f["added"] for f in files),
            "total_removed": sum(f["removed"] for f in files),
            "base_commit": self.base_commit,
        })

    # ---------------------------------------------------------------- ending
    async def _on_exit(self, terminal_seen: bool) -> None:
        code = None
        if self.proc is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                code = await asyncio.wait_for(self.proc.wait(), timeout=15)
        if self._stderr_task:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task

        await self.broker.cancel_session(self.session_id, "the Claude Code session ended")

        row = self.db.get_session(self.session_id) or {}
        if row.get("status") == STATUS_RUNNING:
            if self._stopping:
                self.db.update_session(self.session_id, status=STATUS_CANCELLED,
                                       ended_at=time.time())
                await self.hub.publish(self.session_id, E.SESSION_CANCELLED,
                                       {"reason": "stopped from the CodePilot app",
                                        "exit_code": code})
            else:
                detail = "\n".join(self._stderr_tail[-15:]).strip()
                message = (f"Claude Code exited with code {code} before finishing the task."
                           if not terminal_seen else
                           f"Claude Code exited with code {code}.")
                if detail:
                    message += f"\n\nLast output from Claude Code:\n{detail}"
                self.db.update_session(self.session_id, status=STATUS_FAILED,
                                       ended_at=time.time(), error=message[:2000])
                await self.hub.publish(self.session_id, E.SESSION_FAILED, {
                    "subtype": "process_exit", "is_error": True,
                    "exit_code": code, "result": message,
                })
        self._finished.set()

    async def stop(self, reason: str = "stopped from the CodePilot app") -> None:
        self._stopping = True
        await self.broker.cancel_session(self.session_id, reason)
        if self.proc is None or self.proc.returncode is not None:
            return
        # Ask nicely first so Claude Code can flush its transcript.
        with contextlib.suppress(ProcessLookupError, OSError):
            if os.name == "posix":
                self.proc.send_signal(signal.SIGINT)
            else:
                self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=8)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                self.proc.kill()

    async def wait(self) -> None:
        await self._finished.wait()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


class SessionManager:
    """Owns every live Claude Code session in this server process."""

    def __init__(self, db: Database, hub: EventHub, broker: ApprovalBroker,
                 settings_store, provider_factory, backend_url_factory):
        self.db = db
        self.hub = hub
        self.broker = broker
        self.settings_store = settings_store
        self.provider_factory = provider_factory
        self.backend_url_factory = backend_url_factory
        self.live: dict[str, ClaudeCodeSession] = {}

    def reconcile_on_boot(self) -> int:
        """A session cannot survive a server restart — mark orphans as failed."""
        orphans = self.db.running_sessions()
        for row in orphans:
            self.db.update_session(
                row["id"], status=STATUS_FAILED, ended_at=time.time(),
                error="The CodePilot server restarted while this session was running, "
                      "so the Claude Code process was lost. Use 'Continue session' to "
                      "resume from where it left off.")
        return len(orphans)

    async def create(self, *, project_id: str, prompt: str, model: str | None = None,
                     permission_mode: str | None = None,
                     context_length: int | None = None,
                     resume_session_id: str | None = None) -> dict:
        settings = self.settings_store.current
        project = self.db.get_project(project_id)
        if project is None:
            raise BridgeError("unknown project")
        if not prompt or not prompt.strip():
            raise BridgeError("prompt is empty")

        resume_claude_id = None
        parent = None
        if resume_session_id:
            previous = self.db.get_session(resume_session_id)
            if previous is None:
                raise BridgeError("cannot continue: that session does not exist")
            if previous["project_id"] != project_id:
                raise BridgeError("cannot continue a session from a different project")
            resume_claude_id = previous["claude_session_id"] or previous["id"]
            parent = resume_session_id

        if context_length and context_length != settings.context_length:
            settings = self.settings_store.update({"context_length": context_length})

        session_id = str(uuid.uuid4())
        chosen_model = model or settings.ollama_model
        mode = permission_mode or settings.default_permission_mode

        self.db.create_session(
            id=session_id, project_id=project_id, prompt=prompt.strip(),
            status=STATUS_RUNNING, model=chosen_model,
            context_length=settings.context_length, permission_mode=mode,
            parent_session=parent,
        )
        self.db.touch_project(project_id)

        session = ClaudeCodeSession(
            session_id=session_id, project=project, prompt=prompt.strip(),
            settings=settings, provider=self.provider_factory(settings), db=self.db,
            hub=self.hub, broker=self.broker, permission_mode=mode, model=chosen_model,
            resume_claude_id=resume_claude_id,
            backend_url=self.backend_url_factory(),
        )
        self.live[session_id] = session
        try:
            await session.start()
        except BridgeError as exc:
            self.live.pop(session_id, None)
            self.db.update_session(session_id, status=STATUS_FAILED,
                                   ended_at=time.time(), error=str(exc))
            await self.hub.publish(session_id, E.SESSION_FAILED, {
                "subtype": "launch_failed", "is_error": True, "result": str(exc)})
            raise
        asyncio.create_task(self._reap(session_id))
        return self.db.get_session(session_id)  # type: ignore[return-value]

    async def _reap(self, session_id: str) -> None:
        session = self.live.get(session_id)
        if session is None:
            return
        await session.wait()
        self.live.pop(session_id, None)

    async def stop(self, session_id: str) -> bool:
        session = self.live.get(session_id)
        if session is None:
            row = self.db.get_session(session_id)
            if row and row["status"] == STATUS_RUNNING:
                self.db.update_session(session_id, status=STATUS_CANCELLED,
                                       ended_at=time.time())
                await self.hub.publish(session_id, E.SESSION_CANCELLED,
                                       {"reason": "session was no longer attached"})
                return True
            return False
        await session.stop()
        return True

    async def send_message(self, session_id: str, text: str) -> None:
        session = self.live.get(session_id)
        if session is None:
            raise BridgeError(
                "this session is not running. Use 'Continue session' to start a new "
                "Claude Code turn that resumes its context.")
        await session.send_message(text)

    async def shutdown(self) -> None:
        for session in list(self.live.values()):
            await session.stop("the CodePilot server is shutting down")
