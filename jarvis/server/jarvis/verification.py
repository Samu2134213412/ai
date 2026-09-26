"""Verification Engine: nachprüfen, ob eine Aktion wirklich gewirkt hat
(Punkt 5) -- über einen **echten, unabhängigen** Folgeaufruf, nicht durch
erneutes Vertrauen auf ``ToolResult.ok`` des ursprünglichen Aufrufs.

Die bestehenden Datei-/Gedächtniswerkzeuge prüfen ihren eigenen Erfolg
bereits selbst (z. B. liest ``write_file`` die Dateigröße nach dem Schreiben
zurück, ``delete_file`` wirft, wenn die Datei danach noch existiert). Das
hier ist trotzdem kein Doppelbau: Eine Prüfung durch **denselben** Code, der
gerade geschrieben hat, kann denselben blinden Fleck haben. Die Verification
Engine geht über einen zweiten, unabhängigen Werkzeugaufruf (``read_file``
statt der Rückgabe von ``write_file``) -- genau das Muster aus der
Aufgabenstellung: "Datei erstellt: → existiert die Datei wirklich?"

Ein Verifizierer bekommt ein echtes ``run_tool`` hereingereicht (in der
Praxis ``Agent._run_tool``), damit sein Folgeaufruf durch denselben einen
Durchlaufpunkt läuft wie jeder andere Werkzeugaufruf -- mit Audit-Eintrag,
und wo zutreffend Permission-Check. Er liefert ``None``, wenn es für dieses
Werkzeug (noch) keinen Verifizierer gibt -- das ist kein Fehler, sondern
"hierfür heute keine zusätzliche Prüfung vorgesehen".
"""

from __future__ import annotations

from typing import Awaitable, Callable

from .tools.base import ToolResult

RunTool = Callable[[str, dict], Awaitable[ToolResult]]
Verifier = Callable[[dict, ToolResult, RunTool], Awaitable[ToolResult]]


def _wrap(tool: str, ok: bool, summary: str, evidence: dict | None = None) -> ToolResult:
    return ToolResult(tool=f"verify:{tool}", ok=ok, summary=summary, evidence=evidence or {})


async def _verify_write_file(arguments: dict, result: ToolResult, run_tool: RunTool) -> ToolResult:
    path = arguments.get("path", "")
    check = await run_tool("read_file", {"path": path})
    if not check.ok:
        return _wrap("write_file", False,
                     f"Datei ist nach dem Schreiben nicht lesbar: {path}",
                     {"pfad": path})
    expected = arguments.get("content")
    if expected is not None and not arguments.get("append") and check.payload != expected:
        return _wrap("write_file", False,
                     f"Inhalt von {path} stimmt nicht mit dem Geschriebenen überein",
                     {"pfad": path})
    return check


async def _verify_delete_file(arguments: dict, result: ToolResult, run_tool: RunTool) -> ToolResult:
    path = arguments.get("path", "")
    check = await run_tool("read_file", {"path": path})
    if check.ok:
        return _wrap("delete_file", False,
                     f"Datei ist nach dem Löschen weiterhin lesbar: {path}", {"pfad": path})
    return _wrap("delete_file", True, f"Bestätigt: {path} existiert nicht mehr", {"pfad": path})


async def _verify_move_file(arguments: dict, result: ToolResult, run_tool: RunTool) -> ToolResult:
    destination = arguments.get("destination", "")
    check = await run_tool("read_file", {"path": destination})
    if not check.ok:
        # Ziel könnte ein Verzeichnis oder eine Binärdatei sein, die read_file
        # ablehnt -- dann genügt list_dir auf dem Elternordner als Nachweis,
        # dass etwas an diesem Namen liegt.
        parent = destination.rsplit("/", 1)[0] if "/" in destination else "."
        listing = await run_tool("list_dir", {"path": parent})
        name = destination.rsplit("/", 1)[-1]
        if listing.ok and name in (listing.payload or ""):
            return _wrap("move_file", True, f"Bestätigt: {destination} existiert",
                        {"pfad": destination})
        return _wrap("move_file", False,
                     f"Ziel ist nach dem Verschieben nicht auffindbar: {destination}",
                     {"pfad": destination})
    return check


async def _verify_memory_add(arguments: dict, result: ToolResult, run_tool: RunTool) -> ToolResult:
    label = arguments.get("label", "")
    check = await run_tool("memory_search", {"query": label})
    if check.ok and label.strip() and label.strip() in (check.payload or ""):
        return check
    return _wrap("memory_add", False,
                 f"Erinnerung '{label}' ist über die Suche nicht auffindbar", {"titel": label})


VERIFIERS: dict[str, Verifier] = {
    "write_file": _verify_write_file,
    "delete_file": _verify_delete_file,
    "move_file": _verify_move_file,
    "memory_add": _verify_memory_add,
}


class VerificationEngine:
    """Der eine Ort, an dem entschieden wird, ob ein Werkzeug eine zusätzliche,
    unabhängige Nachprüfung bekommt."""

    def __init__(self, verifiers: dict[str, Verifier] | None = None):
        self.verifiers = verifiers if verifiers is not None else VERIFIERS

    def has_verifier(self, tool: str) -> bool:
        return tool in self.verifiers

    async def verify(self, tool: str, arguments: dict, result: ToolResult,
                     run_tool: RunTool) -> ToolResult | None:
        """Gibt ``None`` zurück, wenn für dieses Werkzeug keine Nachprüfung
        vorgesehen ist, oder wenn die ursprüngliche Aktion schon fehlgeschlagen
        ist (ein Fehlschlag ist bereits ehrlich -- ihn zu "verifizieren" hieße,
        ihm eine zweite Chance auf einen anderen Ausgang zu geben)."""
        if not result.ok:
            return None
        verifier = self.verifiers.get(tool)
        if verifier is None:
            return None
        return await verifier(arguments or {}, result, run_tool)
