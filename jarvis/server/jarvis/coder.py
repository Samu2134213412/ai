"""Der Code-Modus: Jarvis programmiert selbst.

Vorher lief das über CodePilot Remote -- Jarvis schickte eine Aufgabe per
HTTP an einen zweiten Server, der startete Claude Code, das wiederum sprach
mit Ollama. Drei Dienste zwischen der Frage und dem Modell, von denen jeder
einzeln laufen und eingerichtet sein musste. War einer davon nicht da, war
der ganze Code-Modus tot -- und genau das war der Normalzustand, weil
``codepilot.project_id`` in einer frischen Installation leer ist.

Jetzt macht Jarvis es selbst: ein Code-Modell direkt über Ollama, mit den
Werkzeugen, die Jarvis ohnehin hat. Das ist nicht nur weniger Kette, es ist
auch ehrlicher -- jede Dateiänderung läuft durch ``Agent._run_tool`` und
damit durch Permission-System, Undo-Snapshot und Audit Log. Beim Umweg über
CodePilot hat ein fremder Prozess die Dateien geschrieben; Jarvis hat nur
dessen Bericht weitergereicht und konnte ihn nicht überprüfen.

Der Aufbau folgt dem Rest des Projekts:

* Ein eigener Systemprompt, der auf Code zugeschnitten ist.
* Eine **eingegrenzte** Werkzeugauswahl statt des ganzen Katalogs -- ein
  Code-Modell soll Dateien lesen und schreiben, nicht Netzwerkadapter
  neustarten.
* Nach den Änderungen eine echte Nachprüfung (Syntax der geänderten
  Dateien), damit "fertig" nicht auf der Behauptung des Modells beruht.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CODE_SYSTEM_PROMPT = """\
Du bist der Code-Teil von Jarvis. Du arbeitest an echten Dateien auf dem
Rechner deines Nutzers und antwortest auf Deutsch, knapp und sachlich.

So gehst du vor:
1. Verschaffe dir zuerst einen Überblick. Lies die Dateien, um die es geht,
   bevor du sie änderst. Rate nie, was in einer Datei steht.
2. Ändere so wenig wie möglich. Kein Umbau, der nicht verlangt wurde.
3. Schreibe Änderungen mit write_file. Beim Überschreiben gibst du IMMER den
   vollständigen neuen Dateiinhalt an, nie nur den geänderten Ausschnitt --
   write_file ersetzt die Datei, es fügt nicht ein.
4. Prüfe danach nach: lies die geänderte Datei zurück oder lass die Tests
   laufen, wenn es welche gibt.

Die wichtigste Regel:
Du darfst eine Änderung NUR dann als erledigt melden, wenn du dafür ein
Werkzeug aufgerufen hast UND dieses Werkzeug ERFOLG zurückgegeben hat.
Beschreibe keinen Code, den du hättest schreiben können -- schreibe ihn.
Schlägt ein Werkzeug fehl, nenne den echten Fehler und beschönige nichts.

Fehlt dir ein Werkzeug für einen Schritt, sage genau das, statt dir einen
Umweg auszudenken.
"""

#: Was der Code-Modus benutzen darf. Bewusst eine Auswahl und nicht der ganze
#: Katalog: ein Code-Auftrag braucht Dateien, Suche und (wenn freigegeben)
#: die Shell -- er braucht keine Audiogeräte und keine Firewall. Weniger
#: Werkzeuge heißt außerdem weniger Kontext pro Anfrage und damit mehr Platz
#: für den eigentlichen Code.
CODE_TOOLS: tuple[str, ...] = (
    # Lesen und Orientieren
    "read_file", "list_dir", "search_files", "files.grep", "files.head",
    "files.tail", "files.lines", "files.line_count", "files.info",
    "files.exists", "dir.tree", "files.compare", "files.count.by_extension",
    # Ändern
    "write_file", "files.replace_text", "files.copy", "move_file",
    "files.rename", "files.backup", "dir.create", "files.json.read",
    "files.json.write",
    # Ausführen (nur da, wenn die Shell freigegeben ist)
    "run_command",
)

#: Dateiendungen, für die es eine echte, billige Syntaxprüfung gibt.
CHECKABLE = {".py", ".json"}

#: Werkzeuge, deren Erfolg bedeutet, dass sich eine Datei geändert hat.
WRITING_TOOLS = {"write_file", "files.replace_text", "files.json.write",
                 "files.copy", "move_file", "files.rename"}


@dataclass
class CodeChange:
    """Eine Datei, die tatsächlich angefasst wurde -- belegt durch ein
    erfolgreiches ``ToolResult``, nicht durch eine Aussage des Modells."""

    path: str
    tool: str
    detail: str = ""

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class CodeCheck:
    """Das Ergebnis der Nachprüfung einer geänderten Datei."""

    path: str
    ok: bool
    detail: str = ""

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class CodeOutcome:
    """Was am Ende eines Code-Auftrags wirklich passiert ist."""

    changes: list[CodeChange] = field(default_factory=list)
    checks: list[CodeCheck] = field(default_factory=list)
    model_text: str = ""

    @property
    def broken(self) -> list[CodeCheck]:
        return [c for c in self.checks if not c.ok]

    def summary(self) -> str:
        """Der Satz für den Nutzer -- aus den Belegen, nicht aus dem Modelltext.

        Der Modelltext kommt nur als Erläuterung dazu, und nur wenn wirklich
        etwas passiert ist. Behauptet das Modell eine Änderung, die kein
        Werkzeug belegt, bleibt hier "keine Datei geändert" stehen und der
        Wächter (``guard.py``) verwirft den Rest.
        """
        if not self.changes:
            return self.model_text or "Es wurde keine Datei geändert."
        namen = ", ".join(dict.fromkeys(c.name for c in self.changes))
        teile = [f"{len(self.changes)} Änderung(en): {namen}"]
        if self.broken:
            kaputt = ", ".join(f"{c.name} ({c.detail})" for c in self.broken)
            teile.append(f"Nachprüfung fehlgeschlagen bei {kaputt}")
        elif self.checks:
            teile.append(f"Syntax geprüft: {len(self.checks)} Datei(en) in Ordnung")
        if self.model_text:
            teile.append(self.model_text)
        return " — ".join(teile)


def changed_paths(results: list[Any]) -> list[CodeChange]:
    """Liest aus den Werkzeugergebnissen, welche Dateien angefasst wurden.

    Die Quelle ist ``ToolResult.evidence`` -- also das, was das Werkzeug nach
    getaner Arbeit von der Festplatte zurückgemeldet hat. Ein Modell kann
    hier nichts hineinschreiben.
    """
    changes: list[CodeChange] = []
    for result in results:
        if not getattr(result, "ok", False):
            continue
        tool = getattr(result, "tool", "")
        if tool not in WRITING_TOOLS:
            continue
        evidence = getattr(result, "evidence", {}) or {}
        pfad = evidence.get("pfad") or evidence.get("nach")
        if not pfad:
            continue
        changes.append(CodeChange(path=str(pfad), tool=tool,
                                  detail=str(evidence.get("bytes", ""))))
    return changes


def check_syntax(path: str, text: str) -> CodeCheck | None:
    """Eine echte, billige Nachprüfung für die Dateitypen, bei denen es sie
    gibt. ``None`` heißt: für diesen Typ ist keine vorgesehen -- das ist
    ehrlicher, als eine Prüfung zu behaupten, die nicht stattfindet."""
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return CodeCheck(path=path, ok=False,
                             detail=f"Zeile {exc.lineno}: {exc.msg}")
        return CodeCheck(path=path, ok=True, detail="Python-Syntax in Ordnung")
    if suffix == ".json":
        try:
            json.loads(text)
        except ValueError as exc:
            return CodeCheck(path=path, ok=False, detail=str(exc)[:120])
        return CodeCheck(path=path, ok=True, detail="JSON gültig")
    return None
