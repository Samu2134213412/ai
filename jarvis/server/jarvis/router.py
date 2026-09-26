"""Der Direct Action Router: eindeutige Befehle gehen am Modell vorbei.

Aus der Vorgeschichte dieses Projekts: das kleine Modell rief ``write_file``
schlicht nicht auf und behauptete stattdessen, die Datei sei da. Die Lösung war
nicht ein besserer Prompt, sondern dieser Router — ein deterministischer Erkenner
für Befehle, bei denen es nichts zu interpretieren gibt.

Die Regel dafür ist streng: **im Zweifel nicht greifen.** Ein Router, der rät,
ist schlimmer als keiner, weil er Absichten verfälscht, ohne dass das Modell noch
eingreifen könnte. Was hier nicht sicher erkannt wird, geht an den Agenten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Dateiendungen, die als Dateiname zählen. Bewusst eine Liste statt „irgendwas
#: mit Punkt", damit „Version 3.2" oder „z. B." keinen Dateinamen ergeben.
_EXT = (r"txt|md|markdown|py|json|csv|tsv|log|html|htm|css|js|ts|bat|cmd|ps1|sh|"
        r"ini|cfg|conf|yaml|yml|toml|xml|sql|rs|go|java|c|cpp|h")

#: Ohne Leerzeichen. Ein Muster, das Leerzeichen zulässt, verschluckt das Verb
#: davor — aus "lies bericht.txt" wird sonst der Dateiname "lies bericht.txt".
_FILENAME = re.compile(rf"\b([\w\-.()äöüÄÖÜß]+\.(?:{_EXT}))\b", re.I)

_CREATE = re.compile(
    r"\b(?:erstell\w*|erzeug\w*|anleg\w*|leg\w*|schreib\w*|speicher\w*|"
    r"generier\w*|mach\w*)\b", re.I)
_READ = re.compile(r"\b(?:lies|les\w*|zeig\w*|öffne|oeffne|inhalt|was steht)\b", re.I)
_DELETE = re.compile(r"\b(?:lösch\w*|loesch\w*|entfern\w*)\b", re.I)
_LIST = re.compile(
    r"\b(?:liste?|zeig\w*|was ist|was liegt|inhalt)\b.{0,30}?"
    r"\b(?:ordner|verzeichnis|folder)\b", re.I)

#: „mit dem Inhalt …", „mit dem Text …", „Inhalt: …"
_CONTENT = re.compile(
    r"\bmit\s+(?:dem\s+|folgendem\s+)?(?:inhalt|text)\b\s*[:\-]?\s*(.+)$", re.I | re.S)
_CONTENT_COLON = re.compile(r"\b(?:inhalt|text)\s*:\s*(.+)$", re.I | re.S)
_QUOTED = re.compile(r"[\"„»']([^\"“«']{1,4000})[\"“«']", re.S)

_DESKTOP = re.compile(r"\b(?:auf (?:dem|den) )?desktop\b|\bschreibtisch\b", re.I)
_IN_PATH = re.compile(r"\bin\s+((?:[A-Za-z]:\\|/|~/)[^\s\"']{2,200})", re.I)

_RAM = re.compile(r"\b(?:ram|arbeitsspeicher|speicher(?:auslastung)?)\b", re.I)
_CPU = re.compile(r"\b(?:cpu|prozessor|rechenlast|auslastung)\b", re.I)
_DISK = re.compile(r"\b(?:festplatte|speicherplatz|laufwerk|disk)\b", re.I)
_SYSINFO = re.compile(
    r"\b(?:systeminfo\w*|system-?info\w*|welches (?:betriebs)?system|"
    r"was für ein (?:rechner|system))\b", re.I)
_PROCS = re.compile(r"\b(?:prozesse|programme)\b.{0,30}\b(?:läuft|laufen|offen)\b|"
                    r"\bwas läuft\b", re.I)

_REMEMBER = re.compile(
    r"^\s*(?:merk(?:e)?\s+dir|behalte?|notier(?:e)?\s+dir|vergiss nicht)\s*[:,]?\s*(.+)$",
    re.I | re.S)
_RECALL = re.compile(
    r"\b(?:was weißt du|was weisst du|woran erinnerst du dich|"
    r"erinnerst du dich)\b.{0,20}?\b(?:über|zu|an|von)\b\s*(.+)$", re.I | re.S)

#: "mach die letzte Änderung rückgängig", "rückgängig machen", "undo" --
#: eindeutig genug für ein einzelnes Wort, wie auch _DELETE/_LIST.
_UNDO = re.compile(r"\b(?:rückgängig|rueckgaengig|undo)\b", re.I)


@dataclass(frozen=True)
class Action:
    """Ein sicher erkannter Befehl samt fertigem Werkzeugaufruf."""

    tool: str
    arguments: dict
    #: Was Jarvis währenddessen im Zustandsband zeigt.
    detail: str


def _content_from(text: str) -> str:
    for pattern in (_CONTENT, _CONTENT_COLON):
        found = pattern.search(text)
        if found:
            body = found.group(1).strip().strip('"„“»«\'')
            if body:
                return body
    quoted = _QUOTED.search(text)
    if quoted:
        return quoted.group(1).strip()
    return ""


def _directory_from(text: str) -> str:
    explicit = _IN_PATH.search(text)
    if explicit:
        return explicit.group(1).rstrip(".,;")
    if _DESKTOP.search(text):
        for name in ("Desktop", "Schreibtisch"):
            candidate = Path.home() / name
            if candidate.is_dir():
                return str(candidate)
        return str(Path.home() / "Desktop")
    return ""


def _path_for(filename: str, text: str) -> str:
    directory = _directory_from(text)
    return str(Path(directory) / filename) if directory else filename


def route(message: str) -> Action | None:
    """Erkennt einen eindeutigen Befehl — oder gibt ``None`` zurück.

    ``None`` heißt: der Agent übernimmt. Das ist der Normalfall und kein
    Fehlschlag.
    """
    text = (message or "").strip()
    if not text:
        return None

    # -- Gedächtnis ---------------------------------------------------------
    remember = _REMEMBER.match(text)
    if remember:
        body = remember.group(1).strip().rstrip(".")
        if body:
            label = body.split(",")[0].split(".")[0][:60].strip() or body[:60]
            return Action("memory_add", {"label": label, "text": body, "kind": "fakt"},
                          f"lege Erinnerung an: {label}")
    recall = _RECALL.search(text)
    if recall:
        topic = recall.group(1).strip().rstrip("?.")
        if topic:
            return Action("memory_search", {"query": topic}, f"durchsuche Gedächtnis: {topic}")

    # -- Rückgängig -----------------------------------------------------------
    if _UNDO.search(text):
        return Action("undo_last_action", {}, "mache die letzte Änderung rückgängig")

    # -- Systemwerte --------------------------------------------------------
    if _SYSINFO.search(text):
        return Action("get_system_info", {}, "lese Systeminformationen")
    if _PROCS.search(text):
        return Action("list_processes", {}, "lese Prozessliste")
    if _RAM.search(text) and not _FILENAME.search(text):
        return Action("get_ram_info", {}, "lese Arbeitsspeicher")
    if _DISK.search(text) and not _FILENAME.search(text):
        return Action("get_disk_info", {}, "lese Laufwerksbelegung")
    if _CPU.search(text) and not _FILENAME.search(text):
        return Action("get_cpu_info", {}, "messe CPU-Auslastung")

    # -- Dateien ------------------------------------------------------------
    found = _FILENAME.search(text)
    if found:
        filename = found.group(1).strip()
        path = _path_for(filename, text)
        # Löschen zuerst: „lösche test.txt" darf nicht als Erstellen durchgehen.
        if _DELETE.search(text):
            return Action("delete_file", {"path": path}, f"lösche {filename}")
        if _CREATE.search(text):
            return Action("write_file", {"path": path, "content": _content_from(text)},
                          f"schreibe {path}")
        if _READ.search(text):
            return Action("read_file", {"path": path}, f"lese {filename}")

    if _LIST.search(text):
        directory = _directory_from(text)
        if directory:
            return Action("list_dir", {"path": directory}, f"liste {directory}")

    return None
