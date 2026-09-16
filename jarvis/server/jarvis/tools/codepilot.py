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

import time
from dataclasses import dataclass

import httpx

from .base import Tool, ToolError, ToolResult

#: Zustände, bei denen CodePilot fertig ist.
_DONE = {"completed", "failed", "cancelled", "error"}
_POLL_SECONDS = 1.5


@dataclass
class CodePilotLink:
    """Zugangsdaten zum CodePilot-Server."""

    url: str = "http://127.0.0.1:8765"
    token: str = ""
    project_id: str = ""
    timeout: int = 900

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token and self.project_id)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30.0)


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
                    "zeilen_minus": removed, "dauer_s": seconds}
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
