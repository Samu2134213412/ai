"""Tool Pack: Suche.

Zwei Lücken, die es noch nicht gab: ``files.grep`` (``fs.py``) durchsucht den
**Inhalt** von Dateien, aber nicht ihre **Namen** -- ``search.files`` holt
das nach. Und es gibt bisher keine Möglichkeit, herauszufinden, welche
Programme auf dem Rechner überhaupt installiert sind, bevor man sie starten
will -- ``search.apps`` listet sie plattformabhängig auf (Desktop-Dateien
unter Linux, Verknüpfungen im Startmenü unter Windows, .app-Bündel unter
macOS). Das tatsächliche *Starten* eines Programms ist ein eigener,
zurückgestellter Punkt (``open_program``, siehe ``PLANNED`` in
``tools/__init__.py``) -- hier wird nur gefunden, nicht ausgeführt.
"""

from __future__ import annotations

import os
from pathlib import Path

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, current_platform
from ._base import integer, ok, params, table, text

MAX_ERGEBNISSE = 200
_AUSGESCHLOSSEN = {".git", "node_modules", "__pycache__", ".venv", "venv",
                  "dist", "build", ".mypy_cache", ".pytest_cache"}


def _aehnlichkeit(muster: str, name: str) -> int | None:
    """Enthält jeder Buchstabe des Musters, in Reihenfolge, im Namen? Je
    dichter beieinander, desto besser der Treffer -- dieselbe Logik, die
    "Datei öffnen"-Dialoge für Fuzzy-Suche verwenden."""
    m, n = muster.lower(), name.lower()
    pos = 0
    erster = -1
    letzter = -1
    for zeichen in m:
        pos = n.find(zeichen, pos)
        if pos == -1:
            return None
        if erster == -1:
            erster = pos
        letzter = pos
        pos += 1
    return letzter - erster


#: Modulebene statt in ``build()`` verschachtelt -- und mit injizierbaren
#: Suchordnern statt fest verdrahteter Systempfade, damit sich das
#: XDG-/Startmenü-/.app-Parsen gegen einen echten, selbst angelegten
#: Testordner prüfen lässt, ohne die echten Systemverzeichnisse zu brauchen.
def linux_apps(limit: int, ordner: list[Path] | None = None) -> list[list[str]]:
    ordner = ordner if ordner is not None else [
        Path("/usr/share/applications"), Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications"]
    rows = []
    gesehen = set()
    for basis in ordner:
        if not basis.is_dir():
            continue
        for datei in sorted(basis.glob("*.desktop")):
            if datei.name in gesehen:
                continue
            gesehen.add(datei.name)
            name, exec_zeile = "", ""
            try:
                for zeile in datei.read_text(encoding="utf-8", errors="replace").splitlines():
                    if zeile.startswith("Name=") and not name:
                        name = zeile[5:].strip()
                    elif zeile.startswith("Exec=") and not exec_zeile:
                        exec_zeile = zeile[5:].strip()
            except OSError:
                continue
            if name:
                rows.append([name, exec_zeile.split()[0] if exec_zeile else ""])
            if len(rows) >= limit:
                return rows
    return rows


def windows_apps(limit: int, ordner: list[Path] | None = None) -> list[list[str]]:
    ordner = ordner if ordner is not None else [
        Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("AppData", "")) / "Microsoft/Windows/Start Menu/Programs"]
    rows = []
    for basis in ordner:
        if not basis.is_dir():
            continue
        for datei in sorted(basis.rglob("*.lnk")):
            rows.append([datei.stem, str(datei)])
            if len(rows) >= limit:
                return rows
    return rows


def macos_apps(limit: int, ordner: list[Path] | None = None) -> list[list[str]]:
    ordner = ordner if ordner is not None else [Path("/Applications"),
                                                 Path.home() / "Applications"]
    rows = []
    for basis in ordner:
        if not basis.is_dir():
            continue
        for eintrag in sorted(basis.glob("*.app")):
            rows.append([eintrag.stem, str(eintrag)])
            if len(rows) >= limit:
                return rows
    return rows


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def search_files(query: str, path: str = "", limit: int = 40) -> ToolResult:
        muster = (query or "").strip()
        if not muster:
            raise ToolError("Kein Suchbegriff angegeben.")
        wurzel = ws.resolve(path) if path else (ws.roots[0] if ws.roots else None)
        if not wurzel or not wurzel.is_dir():
            raise ToolError(f"Ordner existiert nicht: {wurzel}")
        treffer: list[tuple[int, Path]] = []
        for aktuell, ordner, dateien in os.walk(wurzel):
            ordner[:] = [o for o in ordner if o not in _AUSGESCHLOSSEN]
            for name in dateien:
                distanz = _aehnlichkeit(muster, name)
                if distanz is not None:
                    treffer.append((distanz, Path(aktuell) / name))
            if len(treffer) > 5000:  # Notbremse gegen sehr große Bäume
                break
        treffer.sort(key=lambda t: (t[0], len(t[1].name)))
        n = max(1, min(int(limit or 40), MAX_ERGEBNISSE))
        gezeigt = treffer[:n]
        rows = [[str(p.relative_to(wurzel))] for _, p in gezeigt]
        return ok("search.files", f"{len(treffer)} Treffer für '{muster}'"
                  + (f" (erste {n} gezeigt)" if len(treffer) > n else ""),
                  payload=table(rows, headers=["Pfad"]) if rows else "(keine Treffer)",
                  anzahl=len(treffer))

    def search_apps(query: str = "", limit: int = 100) -> ToolResult:
        system = current_platform()
        n = max(1, min(int(limit or 100), MAX_ERGEBNISSE))
        if system == "linux":
            alle = linux_apps(2000)
        elif system == "windows":
            alle = windows_apps(2000)
        elif system == "darwin":
            alle = macos_apps(2000)
        else:
            raise ToolError(f"Unbekannte Plattform: {system}")
        muster = (query or "").strip()
        if muster:
            bewertet = []
            for zeile in alle:
                distanz = _aehnlichkeit(muster, zeile[0])
                if distanz is not None:
                    bewertet.append((distanz, zeile))
            bewertet.sort(key=lambda t: (t[0], len(t[1][0])))
            alle = [z for _, z in bewertet]
        gezeigt = alle[:n]
        return ok("search.apps", f"{len(alle)} Programm(e) gefunden"
                  + (f" (erste {n} gezeigt)" if len(alle) > n else ""),
                  payload=table(gezeigt, headers=["Name", "Pfad/Befehl"]) if gezeigt
                  else "(keine gefunden)", anzahl=len(alle))

    return [
        Tool("search.files", "Sucht Dateien anhand des Namens (nicht des Inhalts -- "
             "dafür gibt es files.grep). Unscharf: die Buchstaben des Suchbegriffs "
             "müssen nur in der richtigen Reihenfolge vorkommen.",
             params("query", query=text("Suchbegriff"),
                    path=text("Ordner, leer = erste freigegebene Wurzel"),
                    limit=integer("Max. Treffer, Vorgabe 40")),
             search_files, level=P.SAFE, tags=("suche", "dateien"),
             phrases=("wo ist die datei", "such die datei namens")),
        Tool("search.apps", "Listet installierte Programme, optional gefiltert nach Name. "
             "Startet nichts -- nur zum Finden.",
             params(query=text("Suchbegriff, leer = alle"),
                    limit=integer("Max. Treffer, Vorgabe 100")),
             search_apps, level=P.READ, tags=("suche", "programme"),
             phrases=("welche programme sind installiert", "ist x installiert")),
    ]
