"""Was ein Werkzeug zurückgibt — und warum die Form so streng ist.

Der Vorgänger dieses Projekts hat Aktionen als erledigt gemeldet, die nie
stattgefunden haben. Die Gegenmaßnahme ist nicht eine Bitte im Prompt, sondern
diese Datenstruktur: **eine Erfolgsmeldung an den Nutzer wird aus einem
``ToolResult`` erzeugt, niemals aus dem Fließtext des Modells.**

Ein ``ToolResult`` entsteht ausschließlich dort, wo ein Werkzeug tatsächlich
gelaufen ist. Es lässt sich nicht erzählen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


class ToolError(Exception):
    """Ein Werkzeug ist fehlgeschlagen. Die Nachricht wird dem Nutzer gezeigt."""


class ToolMissing(Exception):
    """Für diese Aufgabe existiert kein Werkzeug."""


@dataclass(frozen=True)
class ToolResult:
    """Der Beleg. Ohne ihn darf nichts als erfolgreich gemeldet werden.

    ``summary`` ist der Satz für den Nutzer. ``evidence`` sind die harten
    Einzelheiten — Pfad, Bytes, Exit-Code, Dauer —, die im Verlauf unter der
    Antwort stehen und sie überprüfbar machen.
    """

    tool: str
    ok: bool
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    #: Rohdaten für das Modell. Der Nutzer sieht ``summary``/``evidence``.
    payload: Any = None

    def as_event(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "summary": self.summary,
            "evidence": self.evidence,
            "duration_ms": self.duration_ms,
        }

    def for_model(self) -> str:
        """Was das Modell nach dem Aufruf zu sehen bekommt."""
        head = "ERFOLG" if self.ok else "FEHLGESCHLAGEN"
        parts = [f"{head}: {self.summary}"]
        for key, value in self.evidence.items():
            parts.append(f"{key}={value}")
        if self.payload is not None:
            parts.append(f"\n{self.payload}")
        return "\n".join(parts)


@dataclass(frozen=True)
class Tool:
    """Ein registriertes Werkzeug samt Schema für das Modell."""

    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., ToolResult]
    #: Werkzeuge, die Zustand verändern, brauchen eine Freigabe.
    mutating: bool = False

    def schema(self) -> dict[str, Any]:
        """Ollamas Werkzeugformat (OpenAI-kompatibel)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Registry:
    """Die Werkzeugliste. Was hier nicht steht, kann Jarvis nicht tun."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Werkzeug doppelt registriert: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolMissing(name) from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[n].schema() for n in sorted(self._tools)]

    def status(self) -> list[dict[str, str]]:
        """Für die Oberfläche: was ist da, was fehlt."""
        return [{"name": n, "status": "ok"} for n in sorted(self._tools)]

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Führt ein Werkzeug aus und gibt immer ein ``ToolResult`` zurück.

        Auch ein Fehlschlag ist ein Beleg — ein ehrlicher. Nur ein fehlendes
        Werkzeug ist keiner und fliegt als ``ToolMissing`` heraus.
        """
        tool = self.get(name)
        started = time.perf_counter()
        try:
            result = tool.run(**arguments)
        except ToolMissing:
            raise
        except ToolError as exc:
            return ToolResult(
                tool=name, ok=False, summary=str(exc),
                evidence={"fehler": type(exc).__name__},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except TypeError as exc:
            return ToolResult(
                tool=name, ok=False,
                summary=f"Aufruf von {name} hatte falsche Argumente: {exc}",
                evidence={"fehler": "TypeError"},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - ein Absturz ist ein Ergebnis
            return ToolResult(
                tool=name, ok=False,
                summary=f"{name} ist abgestürzt: {exc}",
                evidence={"fehler": type(exc).__name__},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        if not isinstance(result, ToolResult):
            raise TypeError(f"{name} gab {type(result).__name__} statt ToolResult zurück")
        if result.duration_ms:
            return result
        return ToolResult(
            tool=result.tool, ok=result.ok, summary=result.summary,
            evidence=result.evidence, payload=result.payload,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
