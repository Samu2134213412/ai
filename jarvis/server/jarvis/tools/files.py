"""Dateiwerkzeuge — und die Grenze, innerhalb derer sie wirken dürfen.

Jarvis darf Dateien anlegen und ändern, aber nicht überall. Ein ``Workspace``
hält eine Liste erlaubter Wurzeln; jeder Pfad wird aufgelöst und gegen diese
Liste geprüft, bevor irgendetwas geschrieben wird. Aufgelöst heißt: ``..`` und
Symlinks, die aus dem erlaubten Bereich herausführen, werden abgewiesen — nicht
nur wörtliches ``..`` im String.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..permissions import PermissionLevel
from .base import Tool, ToolError, ToolResult

#: Größere Dateien werden nicht ins Modell geladen.
MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 5_000_000


class Workspace:
    """Die erlaubten Wurzeln. Alles außerhalb ist für Jarvis nicht vorhanden."""

    def __init__(self, roots: list[str | Path] | None = None):
        self.roots: list[Path] = []
        for raw in roots or []:
            try:
                resolved = Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()
            except OSError:
                continue
            if resolved.is_dir():
                self.roots.append(resolved)

    def describe(self) -> str:
        return ", ".join(str(r) for r in self.roots) or "(keine)"

    def resolve(self, raw: str) -> Path:
        """Löst einen Pfad auf oder verweigert ihn mit klarer Begründung."""
        if not raw or not str(raw).strip():
            raise ToolError("Es wurde kein Pfad angegeben.")
        if not self.roots:
            raise ToolError(
                "Es ist kein Arbeitsbereich freigegeben. Trage in der "
                "Konfiguration unter 'roots' ein, wo Jarvis arbeiten darf.")
        candidate = Path(os.path.expandvars(os.path.expanduser(str(raw).strip())))
        if not candidate.is_absolute():
            candidate = self.roots[0] / candidate
        # Nicht strict: die Datei darf noch nicht existieren, ihr Elternpfad
        # aber schon, und genau der wird geprüft.
        resolved = Path(os.path.normpath(candidate))
        try:
            probe = resolved if resolved.exists() else resolved.parent
            real = probe.resolve()
        except OSError as exc:
            raise ToolError(f"Pfad nicht auflösbar: {raw} ({exc})") from exc
        for root in self.roots:
            if real == root or root in real.parents:
                return resolved if resolved.is_absolute() else real
        raise ToolError(
            f"Der Pfad liegt außerhalb des freigegebenen Bereichs: {raw}. "
            f"Erlaubt ist: {self.describe()}")


def build(workspace: Workspace) -> list[Tool]:
    """Erzeugt die Dateiwerkzeuge für einen konkreten Arbeitsbereich."""

    def write_file(path: str, content: str = "", append: bool = False) -> ToolResult:
        target = workspace.resolve(path)
        data = (content or "").encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            raise ToolError(f"Inhalt zu groß: {len(data)} Bytes, erlaubt sind {MAX_WRITE_BYTES}.")
        if target.exists() and target.is_dir():
            raise ToolError(f"{target} ist ein Verzeichnis, keine Datei.")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "ab" if append else "wb") as fh:
                fh.write(data)
        except OSError as exc:
            raise ToolError(f"Schreiben fehlgeschlagen: {exc}") from exc
        # Der Beleg wird von der Festplatte gelesen, nicht aus der Absicht.
        size = target.stat().st_size
        return ToolResult(
            tool="write_file", ok=True,
            summary=f"Datei geschrieben: {target.name}",
            evidence={"pfad": str(target), "bytes": size,
                      "modus": "angehängt" if append else "neu geschrieben"},
            payload=f"{target} ({size} Bytes)")

    def read_file(path: str) -> ToolResult:
        target = workspace.resolve(path)
        if not target.exists():
            raise ToolError(f"Datei existiert nicht: {target}")
        if target.is_dir():
            raise ToolError(f"{target} ist ein Verzeichnis. Nutze list_dir.")
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise ToolError(f"Datei zu groß zum Lesen: {size} Bytes "
                            f"(Grenze {MAX_READ_BYTES}).")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolError(f"Lesen fehlgeschlagen: {exc}") from exc
        return ToolResult(
            tool="read_file", ok=True,
            summary=f"Datei gelesen: {target.name}",
            evidence={"pfad": str(target), "bytes": size,
                      "zeilen": text.count("\n") + 1},
            payload=text)

    def list_dir(path: str = ".") -> ToolResult:
        target = workspace.resolve(path)
        if not target.is_dir():
            raise ToolError(f"Kein Verzeichnis: {target}")
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"{'[D]' if e.is_dir() else '   '} {e.name}" for e in entries[:400]]
        return ToolResult(
            tool="list_dir", ok=True,
            summary=f"{len(entries)} Einträge in {target.name or target}",
            evidence={"pfad": str(target), "eintraege": len(entries)},
            payload="\n".join(lines))

    def search_files(pattern: str, path: str = ".", limit: int = 50) -> ToolResult:
        target = workspace.resolve(path)
        if not target.is_dir():
            raise ToolError(f"Kein Verzeichnis: {target}")
        if not pattern or not pattern.strip():
            raise ToolError("Es wurde kein Suchmuster angegeben.")
        limit = max(1, min(int(limit or 50), 500))
        hits = []
        for found in target.rglob(pattern.strip()):
            hits.append(str(found))
            if len(hits) >= limit:
                break
        return ToolResult(
            tool="search_files", ok=True,
            summary=f"{len(hits)} Treffer für '{pattern}'",
            evidence={"muster": pattern, "wurzel": str(target), "treffer": len(hits)},
            payload="\n".join(hits) if hits else "(nichts gefunden)")

    def delete_file(path: str) -> ToolResult:
        target = workspace.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        if target.is_dir():
            raise ToolError(
                f"{target} ist ein Verzeichnis. Jarvis löscht keine Verzeichnisse.")
        size = target.stat().st_size
        try:
            target.unlink()
        except OSError as exc:
            raise ToolError(f"Löschen fehlgeschlagen: {exc}") from exc
        if target.exists():
            raise ToolError(f"Datei ist nach dem Löschen noch vorhanden: {target}")
        return ToolResult(
            tool="delete_file", ok=True,
            summary=f"Datei gelöscht: {target.name}",
            evidence={"pfad": str(target), "bytes": size})

    def move_file(source: str, destination: str) -> ToolResult:
        src = workspace.resolve(source)
        dst = workspace.resolve(destination)
        if not src.exists():
            raise ToolError(f"Quelle existiert nicht: {src}")
        if dst.exists() and dst.is_dir():
            dst = dst / src.name
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            raise ToolError(f"Verschieben fehlgeschlagen: {exc}") from exc
        if not dst.exists():
            raise ToolError(f"Ziel ist nach dem Verschieben nicht vorhanden: {dst}")
        return ToolResult(
            tool="move_file", ok=True,
            summary=f"Verschoben nach {dst.name}",
            evidence={"von": str(src), "nach": str(dst)})

    _str = {"type": "string"}
    return [
        Tool("write_file",
             "Schreibt Text in eine Datei und gibt Pfad und Bytezahl zurück. "
             "Legt fehlende Ordner an. Für jede Art von Datei-Erstellung.",
             {"type": "object",
              "properties": {"path": {**_str, "description": "Pfad der Datei"},
                             "content": {**_str, "description": "Der Inhalt"},
                             "append": {"type": "boolean",
                                        "description": "Anhängen statt überschreiben"}},
              "required": ["path"]},
             write_file, level=PermissionLevel.WRITE, category="files",
             aliases=("files.write",), tags=("datei", "schreiben"), undoable=True,
             returns="Pfad und Bytezahl der geschriebenen Datei",
             phrases=("schreib das in eine datei", "leg eine datei an",
                      "speichere den text")),
        Tool("read_file", "Liest eine Textdatei und gibt ihren Inhalt zurück.",
             {"type": "object", "properties": {"path": _str}, "required": ["path"]},
             read_file, level=PermissionLevel.SAFE, category="files",
             aliases=("files.read",), tags=("datei", "lesen"),
             returns="Der Textinhalt der Datei",
             phrases=("lies die datei", "zeig mir den inhalt", "was steht in")),
        Tool("list_dir", "Listet den Inhalt eines Verzeichnisses auf.",
             {"type": "object", "properties": {"path": _str}, "required": []},
             list_dir, level=PermissionLevel.SAFE, category="files",
             aliases=("files.list", "dir.list"), tags=("ordner", "lesen"),
             phrases=("was liegt in dem ordner", "zeig mir den ordner", "ls")),
        Tool("search_files",
             "Sucht Dateien nach Namensmuster, z. B. '*.py', rekursiv ab einem Ordner.",
             {"type": "object",
              "properties": {"pattern": _str, "path": _str,
                             "limit": {"type": "integer"}},
              "required": ["pattern"]},
             search_files, level=PermissionLevel.SAFE, category="files",
             aliases=("files.search",), tags=("suche", "datei"),
             phrases=("finde die datei", "such nach dateien", "wo liegt die datei")),
        Tool("delete_file", "Löscht eine einzelne Datei. Keine Verzeichnisse.",
             {"type": "object", "properties": {"path": _str}, "required": ["path"]},
             delete_file, level=PermissionLevel.CRITICAL, category="files",
             aliases=("files.delete",), tags=("datei", "loeschen"), undoable=True,
             phrases=("lösch die datei", "entferne die datei", "weg damit")),
        Tool("move_file", "Verschiebt oder benennt eine Datei um.",
             {"type": "object",
              "properties": {"source": _str, "destination": _str},
              "required": ["source", "destination"]},
             move_file, level=PermissionLevel.WRITE, category="files",
             aliases=("files.move",), tags=("datei", "verschieben"), undoable=True,
             phrases=("verschieb die datei", "schieb das nach")),
    ]
