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

from ..permissions import PermissionLevel


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
    """Ein registrierter Operator samt Schema für das Modell.

    Die ersten fünf Felder sind die ursprünglichen und werden an vielen
    Stellen positionsbasiert gesetzt. Alles darunter ist Katalog-Metadatum
    mit Vorgabewert: ein Tool ohne diese Angaben bleibt ein vollständig
    gültiges Tool, und kein bestehender Aufruf musste angefasst werden.

    Gedacht ist das Ganze wie ein Blender-Operator: klein, benannt,
    kombinierbar. Deshalb gepunktete Namen (``system.cpu.usage``) für alles
    Neue -- Kategorie und Unterkategorie werden daraus abgeleitet, wenn sie
    nicht ausdrücklich gesetzt sind.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., ToolResult]
    #: Sicherheitsstufe für das Permission-System (``permissions.py``).
    #: Ersetzt das frühere ``mutating: bool``, das nirgends ausgewertet wurde.
    level: PermissionLevel = PermissionLevel.SAFE

    # ── Katalog (Aufgabenstellung Punkt 1) ────────────────────────────────
    #: Leer heißt: aus dem gepunkteten Namen ableiten (siehe ``__post_init__``).
    category: str = ""
    subcategory: str = ""
    #: Schlagworte für die Suche.
    tags: tuple[str, ...] = ()
    #: Weitere Namen, unter denen dieses Tool gefunden und aufgerufen werden
    #: darf -- Synonyme und die gepunktete bzw. die alte Schreibweise.
    aliases: tuple[str, ...] = ()
    #: Sätze, wie ein Mensch dieses Tool verlangen würde. Futter für die
    #: Suche, nicht für den Prompt.
    phrases: tuple[str, ...] = ()
    #: Beispielaufrufe als Argument-Dicts.
    examples: tuple[dict[str, Any], ...] = ()
    #: Kurzbeschreibung dessen, was zurückkommt.
    returns: str = ""
    #: Leer heißt: läuft überall. Sonst ``("windows",)``, ``("linux",)``, …
    #: -- Werte wie ``platform.system().lower()``.
    platforms: tuple[str, ...] = ()
    #: Schlüssel aus ``catalog.PROBES`` (z. B. "ffmpeg", "git", "psutil").
    requires: tuple[str, ...] = ()
    #: Sekunden, nach denen der Aufruf als hängend gilt.
    timeout: float = 30.0
    #: Wird von ``UndoStore`` erfasst, lässt sich also zurücknehmen.
    undoable: bool = False
    #: Versteht ein ``dry_run``-Argument und ändert dann nichts.
    dry_run: bool = False
    version: str = "1.0"

    def __post_init__(self) -> None:
        """Kategorie und Unterkategorie aus dem Namen ableiten, wenn sie nicht
        gesetzt sind: ``system.gpu.temperature`` → ``system`` / ``gpu``.
        ``object.__setattr__``, weil die Klasse eingefroren ist -- das ist die
        übliche Form für berechnete Vorgabewerte in ``frozen``-Dataclasses."""
        parts = self.name.split(".")
        if not self.category:
            object.__setattr__(self, "category", parts[0] if len(parts) > 1 else "core")
        if not self.subcategory and len(parts) >= 3:
            object.__setattr__(self, "subcategory", parts[1])

    # ── abgeleitet ────────────────────────────────────────────────────────
    @property
    def risk(self) -> str:
        """LOW/MEDIUM/HIGH -- dasselbe Risiko wie ``level``, nur in der
        Sprache der Aufgabenstellung. Keine zweite Skala."""
        return self.level.risk

    @property
    def mutating(self) -> bool:
        """Rückwärtskompatible Ableitung: alles über SAFE/READ verändert etwas."""
        return self.level >= PermissionLevel.WRITE

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

    def as_dict(self) -> dict[str, Any]:
        """Der Katalogeintrag für Oberfläche, API und Dokumentation."""
        return {
            "id": self.name,
            "beschreibung": self.description,
            "kategorie": self.category,
            "unterkategorie": self.subcategory,
            "tags": list(self.tags),
            "aliase": list(self.aliases),
            "phrasen": list(self.phrases),
            "beispiele": [dict(e) for e in self.examples],
            "parameter": self.parameters,
            "rueckgabe": self.returns,
            "stufe": self.level.label,
            "risiko": self.risk,
            "plattformen": list(self.platforms),
            "benoetigt": list(self.requires),
            "timeout": self.timeout,
            "rueckgaengig": self.undoable,
            "probelauf": self.dry_run,
            "version": self.version,
        }


class Registry:
    """Die Werkzeugliste. Was hier nicht steht, kann Jarvis nicht tun.

    Trägt zusätzlich einen Alias-Index: ein Tool ist unter seinem Namen und
    unter jedem seiner Aliase erreichbar. Damit konnten die sechzehn
    ursprünglichen Namen (``write_file``, ``get_cpu_info``, …) bleiben, wie
    sie sind -- sie stehen im Router, im Systemprompt und in vielen Tests --
    und trotzdem zusätzlich unter gepunkteten Operator-Namen erscheinen.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._aliases: dict[str, str] = {}

    def add(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Werkzeug doppelt registriert: {tool.name}")
        if tool.name in self._aliases:
            raise ValueError(
                f"Werkzeugname kollidiert mit einem Alias: {tool.name} "
                f"(gehört zu {self._aliases[tool.name]})")
        for alias in tool.aliases:
            if alias in self._tools:
                raise ValueError(f"Alias kollidiert mit einem Werkzeugnamen: {alias}")
            if alias in self._aliases and self._aliases[alias] != tool.name:
                raise ValueError(
                    f"Alias doppelt vergeben: {alias} "
                    f"({self._aliases[alias]} und {tool.name})")
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            self._aliases[alias] = tool.name
        return tool

    def extend(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.add(tool)

    def __contains__(self, name: object) -> bool:
        return name in self._tools or name in self._aliases

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools[n] for n in sorted(self._tools))

    def resolve(self, name: str) -> str:
        """Der echte Name hinter einem möglichen Alias."""
        if name in self._tools:
            return name
        return self._aliases.get(name, name)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[self.resolve(name)]
        except KeyError:
            raise ToolMissing(name) from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self, only: list[str] | None = None) -> list[dict[str, Any]]:
        """Die Werkzeugschemata für das Modell.

        ``only`` grenzt bewusst ein: ab einigen hundert Tools passt der
        vollständige Katalog nicht mehr in ein Kontextfenster, und ihn
        trotzdem mitzuschicken hieße, das Modell unbrauchbar zu machen.
        Die Vorauswahl trifft ``discovery.py``; ohne Angabe bleibt es beim
        alten Verhalten (alles), damit kleine Aufbauten unverändert laufen.
        """
        if only is None:
            chosen = sorted(self._tools)
        else:
            seen: dict[str, None] = {}
            for name in only:
                real = self.resolve(name)
                if real in self._tools:
                    seen[real] = None
            chosen = list(seen)
        return [self._tools[n].schema() for n in chosen]

    def categories(self) -> dict[str, int]:
        """Kategorie → Anzahl. Grundlage des Tool-Zählers in der Oberfläche
        (Punkt 42: nicht hartkodiert, sondern aus der Registry gerechnet)."""
        counts: dict[str, int] = {}
        for tool in self._tools.values():
            counts[tool.category] = counts.get(tool.category, 0) + 1
        return dict(sorted(counts.items()))

    def by_category(self, category: str, subcategory: str = "") -> list[Tool]:
        return [t for n, t in sorted(self._tools.items())
                if t.category == category and (not subcategory
                                               or t.subcategory == subcategory)]

    def filter(self, category: str = "", tag: str = "") -> list[Tool]:
        """Werkzeuge nach Kategorie und/oder Tag einschränken -- leer heißt
        kein Filter. Dieselbe "welche Werkzeuge passen"-Logik, die sowohl
        der Tool Explorer (``app.py::list_tools``) als auch das Meta-Werkzeug
        ``jarvis.tools.list`` brauchen."""
        return [t for t in self
                if (not category or t.category == category)
                and (not tag or tag in t.tags)]

    def tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tool in self._tools.values():
            for tag in tool.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

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
        # Punkt 30: Ein Probelauf, den das Werkzeug nicht kann, wird abgelehnt
        # und nicht stillschweigend zur echten Ausführung. Wer "zeig mir erst,
        # was passieren würde" sagt, will nicht, dass es stattdessen passiert.
        if (arguments or {}).get("dry_run") and not tool.dry_run:
            return ToolResult(
                tool=name, ok=False,
                summary=(f"{name} unterstützt keinen Probelauf. Ich habe deshalb "
                         "nichts ausgeführt."),
                evidence={"probelauf": False},
                duration_ms=int((time.perf_counter() - started) * 1000))
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
