"""Die Brücke zum Coding-Agenten.

Alles, was Code ist, macht Jarvis nicht selbst. Er reicht es an CodePilot Remote
weiter — das Projekt, das in diesem Repo unter ``server/`` liegt und echtes
Claude Code gegen ``qwen3-coder`` fährt.

Der Gewinn liegt nicht in der Zahl der Modelle, sondern darin, **was
zurückkommt**: ein Diff und eine Testausgabe. Das ist ein Beleg. Damit gilt die
Grundregel auch eine Ebene höher — ``codepilot_task`` meldet Erfolg genau dann,
wenn CodePilot eine abgeschlossene Sitzung und geänderte Dateien meldet, und
niemals, weil das Chat-Modell es behauptet.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .base import Tool, ToolError, ToolResult

#: Zustände, bei denen CodePilot fertig ist.
_DONE = {"completed", "failed", "cancelled", "error"}
_POLL_SECONDS = 1.5


def default_start_dir() -> Path:
    """Wo CodePilot im Repo liegt: ``<repo>/server``, neben ``jarvis/``.

    Diese Datei steht in ``<repo>/jarvis/server/jarvis/tools/`` — vier Ebenen
    hoch ist die Wurzel des Repos.
    """
    return Path(__file__).resolve().parents[4] / "server"


@dataclass
class CodePilotLink:
    """Zugang zum CodePilot-Server — und, wenn nötig, sein Start.

    CodePilot lädt ein 18-GB-Modell. Es deshalb dauerhaft mitlaufen zu lassen,
    nur damit es *vielleicht* gebraucht wird, nimmt genau den VRAM weg, den das
    Chat-Modell braucht. Also startet Jarvis es erst, wenn wirklich eine
    Codeaufgabe kommt — und sagt hinterher im Beleg, ob er es gestartet hat.
    """

    url: str = "http://127.0.0.1:8765"
    token: str = ""
    project_id: str = ""
    timeout: int = 900
    #: Selbststart, wenn CodePilot bei einer Codeaufgabe nicht läuft.
    autostart: bool = True
    #: Leer heißt: aus dem Repo-Layout ableiten.
    start_dir: str = ""
    #: Wie lange auf „antwortet" gewartet wird, nachdem der Start angestoßen ist.
    start_timeout: int = 90
    #: Wohin die Startausgabe geht, damit ein Fehlstart nachlesbar ist.
    log_path: str = ""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token and self.project_id)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30.0)

    # ------------------------------------------------------------- Selbststart
    def is_healthy(self, seconds: float = 2.0) -> bool:
        try:
            res = httpx.get(f"{self.url.rstrip('/')}/api/health", timeout=seconds)
        except httpx.HTTPError:
            return False
        return res.status_code < 400

    def resolved_start_dir(self) -> Path:
        return Path(self.start_dir).expanduser() if self.start_dir else default_start_dir()

    def _spawn(self, workdir: Path):
        """Startet CodePilot losgelöst, damit es Jarvis' Neustart überlebt."""
        log = Path(self.log_path) if self.log_path else workdir / "codepilot-start.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = open(log, "ab", buffering=0)  # noqa: SIM115 - lebt im Kindprozess weiter
        handle.write(f"\n=== Start durch Jarvis: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                     .encode("utf-8"))
        kwargs: dict = {"cwd": str(workdir), "stdout": handle, "stderr": handle,
                        "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                       | getattr(subprocess, "DETACHED_PROCESS", 0))
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen([sys.executable, "-m", "codepilot"], **kwargs), log

    def ensure_running(self) -> str:
        """Gibt zurück, was für den Beleg gilt. Wirft, wenn es nicht klappt.

        Zwei Aufgaben dürfen nicht gleichzeitig starten, deshalb die Sperre —
        und nach dem Warten wird noch einmal geprüft, falls inzwischen eine
        andere Aufgabe den Start schon erledigt hat.
        """
        if self.is_healthy():
            return "lief bereits"

        with self._lock:
            if self.is_healthy():
                return "lief bereits"
            if not self.autostart:
                raise ToolError(
                    "CodePilot läuft nicht, und der Selbststart ist abgeschaltet "
                    "(codepilot.autostart in jarvis.json). Von Hand starten: "
                    f"cd {self.resolved_start_dir()} && start.bat")

            workdir = self.resolved_start_dir()
            if not (workdir / "codepilot").is_dir():
                raise ToolError(
                    f"CodePilot ist nicht zu finden: {workdir} enthält kein "
                    "'codepilot'-Paket. Pfad in jarvis.json unter "
                    "codepilot.start_dir eintragen.")

            started = time.monotonic()
            try:
                proc, log = self._spawn(workdir)
            except OSError as exc:
                raise ToolError(f"CodePilot ließ sich nicht starten: {exc}") from exc

            while time.monotonic() - started < self.start_timeout:
                if self.is_healthy(1.5):
                    return f"von Jarvis gestartet ({time.monotonic() - started:.0f} s)"
                if proc.poll() is not None:
                    raise ToolError(
                        f"CodePilot hat sich beim Start sofort beendet "
                        f"(Code {proc.returncode}). Letzte Ausgabe:\n{_tail(log)}")
                time.sleep(1.0)

            raise ToolError(
                f"CodePilot antwortet {self.start_timeout} s nach dem Start noch "
                f"nicht unter {self.url}. Letzte Ausgabe:\n{_tail(log)}")


def _tail(log: Path, lines: int = 12) -> str:
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(Protokoll nicht lesbar)"
    return "\n".join(text.splitlines()[-lines:]) or "(leer)"


def build(link: CodePilotLink) -> list[Tool]:

    def codepilot_task(task: str, project_id: str = "") -> ToolResult:
        if not link.configured:
            raise ToolError(
                "CodePilot ist nicht eingerichtet. Es fehlen URL, Gerätetoken "
                "oder Projekt-ID in der Konfiguration unter 'codepilot'.")
        if not (task or "").strip():
            raise ToolError("Es wurde keine Aufgabe angegeben.")

        project = project_id or link.project_id
        started = time.monotonic()
        # Wenn nötig, CodePilot erst hochfahren. Wirft mit klarer Begründung,
        # wenn das nicht gelingt -- kein stiller Fehlschlag.
        start_hinweis = link.ensure_running()
        try:
            with link._client() as client:
                created = client.post("/api/sessions", json={
                    "project_id": project, "prompt": task.strip()})
                if created.status_code == 401:
                    raise ToolError("CodePilot hat das Gerätetoken abgelehnt (401).")
                if created.status_code >= 400:
                    raise ToolError(
                        f"CodePilot lehnte den Auftrag ab ({created.status_code}): "
                        f"{created.text[:300]}")
                session = (created.json().get("session") or {})
                sid = session.get("id")
                if not sid:
                    raise ToolError("CodePilot gab keine Sitzungs-ID zurück.")

                status, last_seq, tools_used, messages = "running", 0, 0, []
                while status not in _DONE:
                    if time.monotonic() - started > link.timeout:
                        client.post(f"/api/sessions/{sid}/stop")
                        raise ToolError(
                            f"Abgebrochen: CodePilot war nach {link.timeout} s "
                            f"nicht fertig (Sitzung {sid}).")
                    time.sleep(_POLL_SECONDS)
                    events = client.get(f"/api/sessions/{sid}/events",
                                        params={"after": last_seq})
                    if events.status_code < 400:
                        body = events.json()
                        last_seq = body.get("last_seq", last_seq)
                        for ev in body.get("events", []):
                            kind = ev.get("type") or ev.get("event_type")
                            if kind == "tool.finished":
                                tools_used += 1
                            elif kind == "assistant.message":
                                text = (ev.get("payload") or {}).get("text")
                                if text:
                                    messages.append(text)
                    state = client.get(f"/api/sessions/{sid}")
                    if state.status_code >= 400:
                        raise ToolError(
                            f"CodePilot-Sitzung {sid} nicht mehr abrufbar "
                            f"({state.status_code}).")
                    status = (state.json().get("session") or {}).get("status", "running")

                changes = client.get(f"/api/sessions/{sid}/changes")
                files, added, removed = [], 0, 0
                if changes.status_code < 400:
                    body = changes.json()
                    files = body.get("files", [])
                    added = body.get("total_added", 0)
                    removed = body.get("total_removed", 0)
        except httpx.HTTPError as exc:
            raise ToolError(f"CodePilot ist nicht erreichbar: {exc}") from exc

        seconds = round(time.monotonic() - started, 1)
        evidence = {"sitzung": sid, "status": status, "werkzeugaufrufe": tools_used,
                    "dateien": len(files), "zeilen_plus": added,
                    "zeilen_minus": removed, "dauer_s": seconds,
                    "codepilot": start_hinweis}
        if status != "completed":
            return ToolResult(
                tool="codepilot_task", ok=False,
                summary=f"CodePilot hat den Auftrag nicht abgeschlossen (Status: {status}).",
                evidence=evidence,
                payload="\n".join(messages[-3:]) or "(keine Rückmeldung)")

        names = ", ".join(f.get("path", "?") for f in files[:6]) or "keine"
        return ToolResult(
            tool="codepilot_task", ok=True,
            summary=(f"CodePilot fertig: {len(files)} Datei(en) geändert, "
                     f"+{added}/−{removed} Zeilen"),
            evidence=evidence,
            payload=f"Geänderte Dateien: {names}\n\n" + "\n".join(messages[-3:]))

    return [
        Tool("codepilot_task",
             "Gibt eine Programmieraufgabe an CodePilot Remote weiter, das echtes "
             "Claude Code mit qwen3-coder fährt. Für alles, was Code schreibt, "
             "ändert, testet oder in einem Repository arbeitet. Liefert Diff und "
             "Testausgabe zurück. Dauert Minuten — nur für echte Codeaufgaben.",
             {"type": "object",
              "properties": {
                  "task": {"type": "string",
                           "description": "Die Aufgabe, so genau wie möglich"},
                  "project_id": {"type": "string",
                                 "description": "Projekt-ID, sonst das Standardprojekt"}},
              "required": ["task"]},
             codepilot_task, mutating=True),
    ]
