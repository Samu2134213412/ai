"""Der Draht zu Ollama.

Benutzt wird ``/api/chat`` mit ``tools`` — Ollamas nativer Werkzeugaufruf.
Jarvis spricht direkt mit Ollama, für das Chat-Modell wie für das Code-Modell
(siehe ``coder.py``); es steht kein weiterer Dienst dazwischen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class OllamaError(Exception):
    """Ollama war nicht erreichbar oder hat den Aufruf abgelehnt."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Health:
    online: bool
    version: str = ""
    models: list[str] = field(default_factory=list)
    model_present: bool = False
    detail: str = ""


class OllamaClient:
    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:7b",
                 context_length: int = 8192, temperature: float = 0.3,
                 timeout: int = 120):
        self.url = url.rstrip("/")
        self.model = model
        self.context_length = context_length
        self.temperature = temperature
        self.timeout = timeout

    async def health(self) -> Health:
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=5.0) as client:
                version = ""
                try:
                    res = await client.get("/api/version")
                    if res.status_code < 400:
                        version = res.json().get("version", "")
                except httpx.HTTPError:
                    pass
                tags = await client.get("/api/tags")
                if tags.status_code >= 400:
                    return Health(False, version, detail=f"HTTP {tags.status_code}")
                models = [m.get("name", "") for m in tags.json().get("models", [])]
        except httpx.HTTPError as exc:
            return Health(False, detail=f"nicht erreichbar: {exc}")
        present = any(m == self.model or m.split(":")[0] == self.model.split(":")[0]
                      for m in models)
        return Health(
            online=True, version=version, models=models, model_present=present,
            detail="" if present else
            f"Modell '{self.model}' ist nicht geladen. Holen mit: ollama pull {self.model}")

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> ChatTurn:
        """Ein Zug. Wirft ``OllamaError``, statt eine leere Antwort zu erfinden."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature,
                        "num_ctx": self.context_length},
        }
        if tools:
            body["tools"] = tools
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=self.timeout) as client:
                res = await client.post("/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama ist nicht erreichbar: {exc}") from exc
        if res.status_code >= 400:
            raise OllamaError(f"Ollama antwortete mit HTTP {res.status_code}: "
                              f"{res.text[:300]}")
        try:
            payload = res.json()
        except ValueError as exc:
            raise OllamaError("Ollama gab keine gültige JSON-Antwort.") from exc

        message = payload.get("message") or {}
        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = (raw or {}).get("function") or {}
            name = fn.get("name")
            if not name:
                continue
            args = fn.get("arguments")
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append(ToolCall(name=name, arguments=args if isinstance(args, dict) else {}))
        return ChatTurn(text=(message.get("content") or "").strip(), tool_calls=calls)
