"""Das Permission-System: fünf Sicherheitsstufen statt eines Bits.

`tools/base.py` trug bisher nur ``mutating: bool`` -- ein Metadatum, das
nirgends ausgewertet wurde. Dieses Modul macht daraus eine echte
Entscheidung: SAFE und (per Voreinstellung) READ laufen automatisch, WRITE
und SYSTEM verlangen eine Bestätigung, CRITICAL verlangt sie **immer** und
das ist bewusst nicht konfigurierbar -- ein Schalter, der das aufheben
könnte, wäre genau die Umgehung, die die Aufgabenstellung verbietet
("Jarvis soll niemals Sicherheitsmechanismen umgehen, um eine Aktion
auszuführen").

Die Bestätigung selbst ist ein Round-Trip über die Oberfläche: ``check()``
sendet ein ``permission.requested``-Ereignis und wartet auf eine Antwort,
die von außen über :meth:`PermissionGate.resolve` hereinkommt (vom
WebSocket-Handler in ``app.py``, wenn ein Gerät antwortet). Ein
``asyncio.Future`` ist die Brücke dazwischen -- dasselbe Muster wie
CodePilots ``ApprovalBroker`` (``server/codepilot/bridge/approvals.py``) --
dort abgeschaut, hier eigenständig gebaut. Die beiden Projekte liegen zwar im
selben Repo, sind aber getrennte Pakete: Jarvis importiert aus CodePilot
nichts und hängt von ihm nicht ab.

``check()`` akzeptiert seit dem Fokus-Modus (``agent.py``) optional eine
andere ``policy`` für einen einzelnen Aufruf. Das ist ausdrücklich KEINE
Umgehung dieser Methode: ``check()`` läuft für jeden Aufruf unverändert
durch, prüft immer eine echte ``PermissionPolicy``, und CRITICAL verlangt
in jeder denkbaren Policy immer eine Bestätigung (siehe
``requires_confirmation`` -- dieses Feld gibt es dort absichtlich nicht).
Was sich ändert, ist nur, WELCHE vom Nutzer selbst gewählte Policy für
WRITE/SYSTEM gilt -- derselbe Hebel, den ``confirm_write`` in
``jarvis.json`` schon immer war, nur zur Laufzeit umschaltbar statt nur
beim Editieren der Datei.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable

Emit = Callable[[str, dict], Awaitable[None]]


class PermissionLevel(IntEnum):
    """Reihenfolge ist Absicht: höherer Wert heißt höheres Risiko.

    Zuordnung folgt exakt den Beispielen der Aufgabenstellung:

    * SAFE     -- Informationen anzeigen, Status prüfen, Dateien lesen
    * READ     -- Logs lesen, Systeminformationen abfragen
    * WRITE    -- Dateien verändern, Konfiguration ändern
    * SYSTEM   -- Programme installieren, Prozesse stoppen, Systemeinstellungen ändern
    * CRITICAL -- Dateien löschen, Konten verändern, sicherheitsrelevante Einstellungen ändern
    """

    SAFE = 0
    READ = 1
    WRITE = 2
    SYSTEM = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name

    @property
    def risk(self) -> str:
        """Dasselbe Risiko, in der Sprache der Autonomie-Aufgabenstellung
        (LOW/MEDIUM/HIGH) -- ein Label auf derselben Stufe, keine zweite,
        parallele Risiko-Engine."""
        if self <= PermissionLevel.READ:
            return "LOW"
        if self <= PermissionLevel.SYSTEM:
            return "MEDIUM"
        return "HIGH"

    @classmethod
    def from_label(cls, label: str) -> "PermissionLevel":
        try:
            return cls[label.strip().upper()]
        except KeyError:
            raise ValueError(f"Unbekannte Sicherheitsstufe: {label}") from None


class PermissionDenied(Exception):
    """Eine Aktion wurde nicht bestätigt -- abgelehnt oder Zeitüberschreitung."""


@dataclass
class PermissionPolicy:
    """Konfigurierbare Regeln -- innerhalb der nicht verhandelbaren Grenzen.

    SAFE ist immer automatisch erlaubt, CRITICAL verlangt immer eine
    Bestätigung. Beides steht absichtlich nicht als Feld hier, damit es
    nicht wegkonfigurierbar ist. Nur READ/WRITE/SYSTEM sind einstellbar.
    """

    confirm_read: bool = False
    confirm_write: bool = True
    confirm_system: bool = True
    #: Sekunden, die auf eine Bestätigung gewartet werden, bevor abgelehnt wird.
    #: Verhindert eine Aufgabe, die für immer auf eine Antwort wartet, die nie
    #: kommt ("keine Endlosschleifen" gilt auch für Bestätigungen).
    confirmation_timeout: float = 300.0

    def requires_confirmation(self, level: PermissionLevel) -> bool:
        if level is PermissionLevel.SAFE:
            return False
        if level is PermissionLevel.CRITICAL:
            return True
        if level is PermissionLevel.READ:
            return self.confirm_read
        if level is PermissionLevel.WRITE:
            return self.confirm_write
        if level is PermissionLevel.SYSTEM:
            return self.confirm_system
        raise AssertionError(level)  # pragma: no cover - IntEnum ist vollständig


@dataclass(frozen=True)
class PermissionRequest:
    """Eine offene Bestätigungsanfrage, wie sie an die Oberfläche geht."""

    id: str
    tool: str
    level: PermissionLevel
    arguments: dict[str, Any]
    detail: str = ""

    def as_event(self) -> dict[str, Any]:
        return {
            "request_id": self.id, "tool": self.tool, "level": self.level.label,
            "arguments": self.arguments, "detail": self.detail,
        }


class PermissionGate:
    """Der eine Ort, an dem entschieden wird: automatisch, oder erst fragen."""

    def __init__(self, policy: PermissionPolicy | None = None, emit: Emit | None = None):
        self.policy = policy or PermissionPolicy()
        self.emit = emit or self._silent
        self._pending: dict[str, asyncio.Future] = {}

    @staticmethod
    async def _silent(_kind: str, _payload: dict) -> None:
        return None

    @property
    def pending(self) -> list[str]:
        """Anfragen, die gerade auf eine Antwort warten -- für Tests und Status."""
        return list(self._pending)

    async def check(self, tool: str, level: PermissionLevel,
                    arguments: dict[str, Any] | None = None, detail: str = "",
                    force_confirm: bool = False,
                    policy: PermissionPolicy | None = None) -> None:
        """Kehrt zurück, wenn die Aktion laufen darf. Wirft ``PermissionDenied`` sonst.

        SAFE und nicht-konfigurierte Stufen laufen ohne Umweg durch. Alles
        andere wird als Ereignis an die Oberfläche gemeldet und wartet
        wirklich auf eine Antwort -- kein simuliertes "ja".

        ``force_confirm`` kommt von der Autonomiestufe (``autonomy.py``):
        Stufe 1 erzwingt auf diesem Weg eine Bestätigung für WRITE/SYSTEM,
        selbst wenn die Policy sie erlauben würde. Es kann also nur
        *strenger* werden als die Policy, nie lockerer -- eine niedrige
        Autonomiestufe darf keine Bestätigungspflicht aufheben.

        ``policy`` ersetzt für DIESEN einen Aufruf ``self.policy`` -- benutzt
        vom Fokus-Modus (``agent.py``), damit Code-Modus mit einer ausdrücklich
        vom Nutzer eingeschalteten, eigenen Policy laufen kann, ohne die
        Vorgabe-Policy für Chat/Agent-Modus anzufassen. Das ist kein Umgehen
        dieser Methode -- ``check()`` läuft für jeden Aufruf unverändert
        durch, prüft weiterhin eine echte ``PermissionPolicy``, und CRITICAL
        verlangt in JEDER Policy immer eine Bestätigung
        (``requires_confirmation``, nicht konfigurierbar).
        """
        aktive_policy = policy or self.policy
        if not (force_confirm or aktive_policy.requires_confirmation(level)):
            return
        request = PermissionRequest(id=uuid.uuid4().hex[:12], tool=tool, level=level,
                                    arguments=dict(arguments or {}), detail=detail)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request.id] = future
        await self.emit("permission.requested", request.as_event())
        try:
            approved = await asyncio.wait_for(future, timeout=aktive_policy.confirmation_timeout)
        except asyncio.TimeoutError:
            approved = False
            await self.emit("permission.timeout", {"request_id": request.id, "tool": tool})
        finally:
            self._pending.pop(request.id, None)

        if not approved:
            await self.emit("permission.denied", {"request_id": request.id, "tool": tool})
            raise PermissionDenied(
                f"Aktion '{tool}' ({level.label}) wurde nicht bestätigt.")
        await self.emit("permission.approved", {"request_id": request.id, "tool": tool})

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Beantwortet eine offene Anfrage. ``False``, wenn es sie nicht (mehr) gibt.

        Aufgerufen vom WebSocket-Handler, wenn ein Gerät auf eine
        ``permission.requested``-Nachricht antwortet -- von jedem
        verbundenen Gerät, nicht nur dem, das die Aufgabe gestellt hat,
        genau wie der Rest des Hub-Broadcasts geräteübergreifend ist.
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(bool(approved))
        return True
