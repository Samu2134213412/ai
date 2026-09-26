"""Tool Pack: Dateien, Ordner und Archive.

Der Blender-Gedanke der Aufgabenstellung, angewendet auf Dateien: nicht ein
``file_manager_do_everything``, sondern viele kleine benannte Operatoren, die
sich kombinieren lassen. ``files.hash`` und ``files.duplicate.find`` sind
zwei Werkzeuge, nicht eines mit einem Schalter.

**Jeder** Pfad geht durch ``Workspace.resolve`` (``tools/files.py``). Damit
gilt die bestehende Grenze -- Jarvis arbeitet nur in freigegebenen Wurzeln --
auch für diese sechzig Werkzeuge, ohne dass eines davon sie selbst
durchsetzen müsste. Eine Datei außerhalb existiert für Jarvis nicht.
"""

from __future__ import annotations

import csv
import filecmp
import difflib
import gzip
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import stat
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Iterator

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import (DRY, INT, STR, flag, human_bytes, integer,
                    ok, params, planned, table, text)

#: Obergrenze für Operationen, die viele Dateien anfassen. Ein Werkzeug, das
#: eine Million Dateien durchläuft, blockiert den Server -- dann lieber ein
#: ehrliches "abgeschnitten bei N".
MAX_WALK = 20_000
MAX_TEXT = 400_000

#: Magische Bytes am Dateianfang. Reicht für die häufigen Fälle und kostet
#: keine zusätzliche Abhängigkeit (``python-magic`` ist nicht installiert).
MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
    (b"RIFF", "riff (wav/webp/avi)"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip (auch docx/xlsx/jar)"),
    (b"\x1f\x8b", "application/gzip"),
    (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    (b"Rar!\x1a\x07", "application/vnd.rar"),
    (b"\x00\x00\x00\x18ftyp", "video/mp4"),
    (b"\x00\x00\x00\x20ftyp", "video/mp4"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mpeg"),
    (b"\x7fELF", "application/x-elf"),
    (b"MZ", "application/x-msdownload"),
    (b"SQLite format 3\x00", "application/vnd.sqlite3"),
)

_HASHES = ("md5", "sha1", "sha256", "sha512")


# ══════════════════════════════════════════════════════════════ Werkzeuge

def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    # ───────────────────────────────────────────────────────── Hilfsmittel
    def need_file(raw: str) -> Path:
        target = ws.resolve(raw)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        if target.is_dir():
            raise ToolError(f"{target} ist ein Verzeichnis, keine Datei.")
        return target

    def need_dir(raw: str) -> Path:
        target = ws.resolve(raw)
        if not target.is_dir():
            raise ToolError(f"Kein Verzeichnis: {target}")
        return target

    def walk(root: Path, pattern: str = "*", files_only: bool = True) -> Iterator[Path]:
        count = 0
        for found in root.rglob(pattern or "*"):
            if files_only and not found.is_file():
                continue
            yield found
            count += 1
            if count >= MAX_WALK:
                return

    def digest(target: Path, algorithm: str) -> str:
        algorithm = (algorithm or "sha256").lower()
        if algorithm not in _HASHES:
            raise ToolError(f"Unbekanntes Verfahren: {algorithm}. "
                            f"Möglich: {', '.join(_HASHES)}")
        hasher = hashlib.new(algorithm)
        with open(target, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def read_text(target: Path) -> str:
        size = target.stat().st_size
        if size > MAX_TEXT:
            raise ToolError(f"Datei zu groß für diese Operation: {human_bytes(size)} "
                            f"(Grenze {human_bytes(MAX_TEXT)}).")
        return target.read_text(encoding="utf-8", errors="replace")

    # ═══════════════════════════════════════════════════ Datei: Grundlagen
    def files_copy(source: str, destination: str, overwrite: bool = False) -> ToolResult:
        src, dst = need_file(source), ws.resolve(destination)
        if dst.is_dir():
            dst = dst / src.name
        if dst.exists() and not overwrite:
            raise ToolError(f"Ziel existiert schon: {dst}. Mit overwrite=true überschreiben.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if not dst.exists():
            raise ToolError(f"Kopie fehlt nach dem Kopieren: {dst}")
        return ok("files.copy", f"Kopiert nach {dst.name}", von=str(src), nach=str(dst),
                  bytes=dst.stat().st_size)

    def files_rename(path: str, new_name: str) -> ToolResult:
        src = ws.resolve(path)
        if not src.exists():
            raise ToolError(f"Existiert nicht: {src}")
        if not new_name or "/" in new_name or "\\" in new_name:
            raise ToolError("new_name ist ein reiner Dateiname ohne Pfadtrenner. "
                            "Zum Verschieben nimm files.move.")
        dst = src.with_name(new_name)
        if dst.exists():
            raise ToolError(f"Es gibt schon etwas mit diesem Namen: {dst}")
        src.rename(dst)
        return ok("files.rename", f"Umbenannt in {dst.name}", von=str(src), nach=str(dst))

    def files_exists(path: str) -> ToolResult:
        target = ws.resolve(path)
        art = ("Verzeichnis" if target.is_dir() else
               "Datei" if target.is_file() else "nichts")
        return ok("files.exists",
                  f"{target.name}: {art}" if target.exists() else f"Existiert nicht: {target}",
                  pfad=str(target), existiert=target.exists(), art=art)

    def files_info(path: str) -> ToolResult:
        target = ws.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        info = target.stat()
        guessed = mimetypes.guess_type(target.name)[0] or "unbekannt"
        rows = {
            "pfad": str(target), "name": target.name, "endung": target.suffix,
            "art": "Verzeichnis" if target.is_dir() else "Datei",
            "bytes": info.st_size, "groesse": human_bytes(info.st_size),
            "mime": guessed,
            "geaendert": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info.st_mtime)),
            "erstellt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info.st_ctime)),
            "rechte": stat.filemode(info.st_mode),
        }
        return ok("files.info", f"{target.name} · {rows['groesse']} · {guessed}",
                  payload="\n".join(f"{k}: {v}" for k, v in rows.items()), **rows)

    def files_size(path: str) -> ToolResult:
        target = need_file(path)
        size = target.stat().st_size
        return ok("files.size", f"{target.name}: {human_bytes(size)}",
                  pfad=str(target), bytes=size)

    def files_hash(path: str, algorithm: str = "sha256") -> ToolResult:
        target = need_file(path)
        value = digest(target, algorithm)
        return ok("files.hash", f"{algorithm}: {value}", payload=value,
                  pfad=str(target), verfahren=algorithm.lower())

    def files_hash_compare(path_a: str, path_b: str, algorithm: str = "sha256") -> ToolResult:
        a, b = need_file(path_a), need_file(path_b)
        ha, hb = digest(a, algorithm), digest(b, algorithm)
        gleich = ha == hb
        return ok("files.hash.compare",
                  "Inhaltlich identisch" if gleich else "Unterschiedlicher Inhalt",
                  identisch=gleich, a=ha, b=hb, verfahren=algorithm.lower())

    def files_touch(path: str) -> ToolResult:
        target = ws.resolve(path)
        neu = not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        return ok("files.touch",
                  f"{'Angelegt' if neu else 'Zeitstempel aktualisiert'}: {target.name}",
                  pfad=str(target), neu=neu)

    def files_append_line(path: str, line: str) -> ToolResult:
        target = ws.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
        return ok("files.append_line", f"Zeile angehängt an {target.name}",
                  pfad=str(target), bytes=target.stat().st_size)

    # ═══════════════════════════════════════════════════════ Datei: Inhalt
    def files_head(path: str, lines: int = 20) -> ToolResult:
        target, count = need_file(path), max(1, min(int(lines or 20), 2000))
        out = []
        with open(target, encoding="utf-8", errors="replace") as fh:
            for index, line in enumerate(fh):
                if index >= count:
                    break
                out.append(line.rstrip("\n"))
        return ok("files.head", f"Erste {len(out)} Zeilen aus {target.name}",
                  payload="\n".join(out), pfad=str(target), zeilen=len(out))

    def files_tail(path: str, lines: int = 20) -> ToolResult:
        target, count = need_file(path), max(1, min(int(lines or 20), 2000))
        # Ringpuffer statt die ganze Datei zu laden -- funktioniert auch bei
        # einem Logfile von mehreren hundert Megabyte.
        buffer: list[str] = []
        with open(target, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                buffer.append(line.rstrip("\n"))
                if len(buffer) > count:
                    buffer.pop(0)
        return ok("files.tail", f"Letzte {len(buffer)} Zeilen aus {target.name}",
                  payload="\n".join(buffer), pfad=str(target), zeilen=len(buffer))

    def files_lines(path: str, start: int = 1, end: int = 0) -> ToolResult:
        target = need_file(path)
        start = max(1, int(start or 1))
        end = int(end or 0) or start + 99
        if end < start:
            raise ToolError(f"end ({end}) liegt vor start ({start}).")
        out = []
        with open(target, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, start=1):
                if number > end:
                    break
                if number >= start:
                    out.append(f"{number:>6}  {line.rstrip()}")
        return ok("files.lines", f"Zeilen {start}–{end} aus {target.name}",
                  payload="\n".join(out) or "(leer)", pfad=str(target), zeilen=len(out))

    def files_line_count(path: str) -> ToolResult:
        target = need_file(path)
        count = 0
        with open(target, "rb") as fh:
            for _ in fh:
                count += 1
        return ok("files.line_count", f"{target.name}: {count} Zeilen",
                  pfad=str(target), zeilen=count)

    def files_grep(pattern: str, path: str = ".", glob: str = "*",
                   ignore_case: bool = True, limit: int = 100) -> ToolResult:
        root = ws.resolve(path)
        if not pattern:
            raise ToolError("Es wurde kein Muster angegeben.")
        try:
            regex = re.compile(pattern, re.I if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
        limit = max(1, min(int(limit or 100), 1000))
        hits: list[list[Any]] = []
        durchsucht = 0
        targets = [root] if root.is_file() else walk(root, glob)
        for found in targets:
            durchsucht += 1
            try:
                if found.stat().st_size > MAX_TEXT:
                    continue
                with open(found, encoding="utf-8", errors="replace") as fh:
                    for number, line in enumerate(fh, start=1):
                        if regex.search(line):
                            hits.append([found.name, number, line.strip()[:160]])
                            if len(hits) >= limit:
                                break
            except OSError:
                continue
            if len(hits) >= limit:
                break
        return ok("files.grep", f"{len(hits)} Fundstellen für '{pattern}'",
                  payload=table(hits, ["datei", "zeile", "text"]) if hits else "(nichts gefunden)",
                  muster=pattern, treffer=len(hits), dateien=durchsucht)

    def files_replace_text(path: str, search: str, replace: str = "",
                           regex: bool = False, dry_run: bool = False) -> ToolResult:
        target = need_file(path)
        if not search:
            raise ToolError("Es wurde kein Suchtext angegeben.")
        original = read_text(target)
        if regex:
            try:
                pattern = re.compile(search)
            except re.error as exc:
                raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
            neu, count = pattern.subn(replace, original)
        else:
            count = original.count(search)
            neu = original.replace(search, replace)
        if dry_run:
            return planned("files.replace_text",
                           f"{count} Stellen in {target.name} würden ersetzt",
                           pfad=str(target), treffer=count)
        if count:
            target.write_text(neu, encoding="utf-8")
        return ok("files.replace_text", f"{count} Stellen in {target.name} ersetzt",
                  pfad=str(target), treffer=count, bytes=target.stat().st_size)

    def files_compare(path_a: str, path_b: str, context: int = 3) -> ToolResult:
        a, b = need_file(path_a), need_file(path_b)
        if filecmp.cmp(a, b, shallow=False):
            return ok("files.compare", "Die Dateien sind identisch",
                      identisch=True, a=str(a), b=str(b))
        diff = list(difflib.unified_diff(
            read_text(a).splitlines(), read_text(b).splitlines(),
            fromfile=a.name, tofile=b.name, lineterm="", n=max(0, int(context or 3))))
        return ok("files.compare", f"{len(diff)} Zeilen Unterschied",
                  payload="\n".join(diff[:400]), identisch=False, a=str(a), b=str(b))

    def files_type_detect(path: str) -> ToolResult:
        target = need_file(path)
        with open(target, "rb") as fh:
            head = fh.read(32)
        magic = next((label for sig, label in MAGIC if head.startswith(sig)), "")
        guessed = mimetypes.guess_type(target.name)[0] or ""
        binaer = b"\x00" in head
        art = magic or guessed or ("binär" if binaer else "Text")
        return ok("files.type.detect", f"{target.name}: {art}",
                  pfad=str(target), magic=magic or None, nach_endung=guessed or None,
                  binaer=binaer)

    def files_encoding_detect(path: str) -> ToolResult:
        """Ohne ``chardet``: die Kodierungen der Reihe nach probieren. Das ist
        keine Statistik, sondern ein Test -- und damit ehrlicher als eine
        Wahrscheinlichkeit, die niemand nachprüfen kann."""
        target = need_file(path)
        raw = target.read_bytes()[:200_000]
        boms = ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"),
                (b"\xfe\xff", "utf-16-be"))
        for sig, name in boms:
            if raw.startswith(sig):
                return ok("files.encoding.detect", f"{target.name}: {name} (BOM erkannt)",
                          pfad=str(target), kodierung=name, sicher=True)
        for name in ("utf-8", "cp1252", "latin-1"):
            try:
                raw.decode(name)
            except UnicodeDecodeError:
                continue
            return ok("files.encoding.detect", f"{target.name}: dekodiert als {name}",
                      pfad=str(target), kodierung=name,
                      sicher=name == "utf-8")
        raise ToolError(f"{target.name} ließ sich mit keiner geprüften Kodierung lesen "
                        "-- vermutlich eine Binärdatei.")

    def files_timestamps_read(path: str) -> ToolResult:
        target = ws.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        info = target.stat()
        werte = {k: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))
                 for k, v in (("geaendert", info.st_mtime), ("zugriff", info.st_atime),
                              ("status", info.st_ctime))}
        return ok("files.timestamps.read", f"{target.name} geändert {werte['geaendert']}",
                  pfad=str(target), **werte)

    def files_timestamps_set(path: str, modified: str = "") -> ToolResult:
        target = ws.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        if not modified:
            stamp = time.time()
        else:
            try:
                stamp = time.mktime(time.strptime(modified, "%Y-%m-%d %H:%M:%S"))
            except ValueError as exc:
                raise ToolError("modified erwartet 'JJJJ-MM-TT HH:MM:SS', "
                                f"bekommen: {modified}") from exc
        os.utime(target, (stamp, stamp))
        return ok("files.timestamps.set", f"Zeitstempel von {target.name} gesetzt",
                  pfad=str(target),
                  geaendert=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stamp)))

    def files_permissions_read(path: str) -> ToolResult:
        target = ws.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        info = target.stat()
        return ok("files.permissions.read",
                  f"{target.name}: {stat.filemode(info.st_mode)}",
                  pfad=str(target), rechte=stat.filemode(info.st_mode),
                  oktal=oct(stat.S_IMODE(info.st_mode)),
                  lesbar=os.access(target, os.R_OK),
                  schreibbar=os.access(target, os.W_OK),
                  ausfuehrbar=os.access(target, os.X_OK))

    def files_permissions_change(path: str, mode: str) -> ToolResult:
        target = ws.resolve(path)
        if not target.exists():
            raise ToolError(f"Existiert nicht: {target}")
        try:
            value = int(str(mode).strip(), 8)
        except ValueError as exc:
            raise ToolError(f"mode erwartet eine Oktalzahl wie '644', bekommen: {mode}") from exc
        vorher = oct(stat.S_IMODE(target.stat().st_mode))
        target.chmod(value)
        nachher = oct(stat.S_IMODE(target.stat().st_mode))
        if nachher != oct(value):
            raise ToolError(f"Rechte wurden nicht übernommen: {nachher} statt {oct(value)}")
        return ok("files.permissions.change", f"{target.name}: {vorher} → {nachher}",
                  pfad=str(target), vorher=vorher, nachher=nachher)

    def files_backup(path: str, suffix: str = ".bak") -> ToolResult:
        src = need_file(path)
        dst = src.with_name(src.name + (suffix or ".bak"))
        index = 1
        while dst.exists():
            dst = src.with_name(f"{src.name}{suffix or '.bak'}.{index}")
            index += 1
        shutil.copy2(src, dst)
        return ok("files.backup", f"Sicherung angelegt: {dst.name}",
                  von=str(src), nach=str(dst), bytes=dst.stat().st_size)

    def files_temp_create(suffix: str = ".tmp", content: str = "") -> ToolResult:
        if not ws.roots:
            raise ToolError("Es ist kein Arbeitsbereich freigegeben.")
        # Bewusst im Arbeitsbereich, nicht in /tmp: was Jarvis anlegt, soll
        # dort liegen, wo der Nutzer es auch findet und wo Undo greift.
        handle, raw = tempfile.mkstemp(suffix=suffix or ".tmp", dir=str(ws.roots[0]))
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(content or "")
        target = Path(raw)
        return ok("files.temp.create", f"Temporäre Datei: {target.name}",
                  pfad=str(target), bytes=target.stat().st_size)

    def files_json_read(path: str, pointer: str = "") -> ToolResult:
        target = need_file(path)
        try:
            data = json.loads(read_text(target))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        if pointer:
            for part in pointer.strip("/.").replace("/", ".").split("."):
                if not part:
                    continue
                try:
                    data = data[int(part)] if isinstance(data, list) else data[part]
                except (KeyError, IndexError, ValueError, TypeError) as exc:
                    raise ToolError(f"Pfad '{pointer}' führt ins Leere bei '{part}'") from exc
        rendered = json.dumps(data, ensure_ascii=False, indent=2)[:MAX_TEXT]
        return ok("files.json.read", f"JSON gelesen: {target.name}", payload=rendered,
                  pfad=str(target), typ=type(data).__name__)

    def files_json_write(path: str, data: str, indent: int = 2) -> ToolResult:
        target = ws.resolve(path)
        try:
            parsed = json.loads(data)
        except ValueError as exc:
            raise ToolError(f"data ist kein gültiges JSON: {exc}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(parsed, ensure_ascii=False,
                                     indent=max(0, min(int(indent or 2), 8))),
                          encoding="utf-8")
        return ok("files.json.write", f"JSON geschrieben: {target.name}",
                  pfad=str(target), bytes=target.stat().st_size)

    def files_csv_preview(path: str, rows: int = 10, delimiter: str = "") -> ToolResult:
        target = need_file(path)
        raw = read_text(target)
        sep = delimiter or _sniff_delimiter(raw)
        reader = csv.reader(io.StringIO(raw), delimiter=sep)
        gelesen = [row for _, row in zip(range(max(1, min(int(rows or 10), 200))), reader)]
        return ok("files.csv.preview", f"{len(gelesen)} Zeilen aus {target.name}",
                  payload=table(gelesen), pfad=str(target), trenner=sep,
                  spalten=len(gelesen[0]) if gelesen else 0)

    def files_csv_columns(path: str, delimiter: str = "") -> ToolResult:
        target = need_file(path)
        raw = read_text(target)
        sep = delimiter or _sniff_delimiter(raw)
        header = next(csv.reader(io.StringIO(raw), delimiter=sep), [])
        return ok("files.csv.columns", f"{len(header)} Spalten in {target.name}",
                  payload="\n".join(f"{i}: {name}" for i, name in enumerate(header)),
                  pfad=str(target), trenner=sep, spalten=len(header))

    # ═════════════════════════════════════════════════════════ Datei: Suche
    def files_large_find(path: str = ".", min_mb: float = 100.0,
                         limit: int = 30) -> ToolResult:
        root = need_dir(path)
        grenze = max(0.0, float(min_mb or 100)) * 1024 * 1024
        rows = []
        for found in walk(root):
            try:
                size = found.stat().st_size
            except OSError:
                continue
            if size >= grenze:
                rows.append((size, found))
        rows.sort(reverse=True, key=lambda r: r[0])
        top = rows[:max(1, min(int(limit or 30), 500))]
        return ok("files.large.find",
                  f"{len(rows)} Dateien ab {min_mb} MB in {root.name or root}",
                  payload=table([[human_bytes(s), str(p)] for s, p in top],
                                ["groesse", "pfad"]),
                  wurzel=str(root), treffer=len(rows),
                  gesamt_bytes=sum(s for s, _ in rows))

    def files_old_find(path: str = ".", days: int = 365, limit: int = 30) -> ToolResult:
        root = need_dir(path)
        grenze = time.time() - max(1, int(days or 365)) * 86400
        rows = []
        for found in walk(root):
            try:
                mtime = found.stat().st_mtime
            except OSError:
                continue
            if mtime < grenze:
                rows.append((mtime, found))
        rows.sort(key=lambda r: r[0])
        top = rows[:max(1, min(int(limit or 30), 500))]
        return ok("files.old.find", f"{len(rows)} Dateien älter als {days} Tage",
                  payload=table([[time.strftime("%Y-%m-%d", time.localtime(m)), str(p)]
                                 for m, p in top], ["geaendert", "pfad"]),
                  wurzel=str(root), treffer=len(rows), tage=int(days or 365))

    def files_recent_find(path: str = ".", hours: int = 24, limit: int = 30) -> ToolResult:
        root = need_dir(path)
        grenze = time.time() - max(1, int(hours or 24)) * 3600
        rows = [(f.stat().st_mtime, f) for f in walk(root)
                if _safe_mtime(f) and f.stat().st_mtime >= grenze]
        rows.sort(reverse=True, key=lambda r: r[0])
        top = rows[:max(1, min(int(limit or 30), 500))]
        return ok("files.recent.find", f"{len(rows)} Dateien aus den letzten {hours} Stunden",
                  payload=table([[time.strftime("%Y-%m-%d %H:%M", time.localtime(m)), str(p)]
                                 for m, p in top], ["geaendert", "pfad"]),
                  wurzel=str(root), treffer=len(rows))

    def files_empty_find(path: str = ".", limit: int = 50) -> ToolResult:
        root = need_dir(path)
        leer = [f for f in walk(root) if _safe_size(f) == 0]
        return ok("files.empty.find", f"{len(leer)} leere Dateien",
                  payload="\n".join(str(p) for p in leer[:int(limit or 50)]) or "(keine)",
                  wurzel=str(root), treffer=len(leer))

    def files_duplicate_find(path: str = ".", limit: int = 20) -> ToolResult:
        """Erst nach Größe gruppieren, dann nur innerhalb gleicher Größen
        hashen -- sonst würde jede Datei im Baum gelesen, auch die, die
        garantiert kein Duplikat haben kann."""
        root = need_dir(path)
        nach_groesse: dict[int, list[Path]] = {}
        for found in walk(root):
            size = _safe_size(found)
            if size:
                nach_groesse.setdefault(size, []).append(found)
        gruppen: list[tuple[int, list[Path]]] = []
        verschwendet = 0
        for size, kandidaten in nach_groesse.items():
            if len(kandidaten) < 2:
                continue
            nach_hash: dict[str, list[Path]] = {}
            for found in kandidaten:
                try:
                    nach_hash.setdefault(digest(found, "sha256"), []).append(found)
                except OSError:
                    continue
            for gleiche in nach_hash.values():
                if len(gleiche) > 1:
                    gruppen.append((size, gleiche))
                    verschwendet += size * (len(gleiche) - 1)
        gruppen.sort(reverse=True, key=lambda g: g[0] * (len(g[1]) - 1))
        lines = []
        for size, gleiche in gruppen[:max(1, int(limit or 20))]:
            lines.append(f"{human_bytes(size)} × {len(gleiche)}:")
            lines.extend(f"    {p}" for p in gleiche)
        return ok("files.duplicate.find",
                  f"{len(gruppen)} Duplikatgruppen, {human_bytes(verschwendet)} belegt",
                  payload="\n".join(lines) or "(keine Duplikate)",
                  wurzel=str(root), gruppen=len(gruppen), verschwendet_bytes=verschwendet)

    def files_count_by_extension(path: str = ".", limit: int = 30) -> ToolResult:
        root = need_dir(path)
        zaehler: dict[str, list[int]] = {}
        for found in walk(root):
            key = found.suffix.lower() or "(ohne Endung)"
            eintrag = zaehler.setdefault(key, [0, 0])
            eintrag[0] += 1
            eintrag[1] += _safe_size(found)
        rows = sorted(zaehler.items(), key=lambda kv: -kv[1][0])
        return ok("files.count.by_extension", f"{len(rows)} verschiedene Dateitypen",
                  payload=table([[k, v[0], human_bytes(v[1])]
                                 for k, v in rows[:int(limit or 30)]],
                                ["endung", "anzahl", "groesse"]),
                  wurzel=str(root), typen=len(rows))

    # ══════════════════════════════════════════════════════ Pfade, Symlinks
    def files_path_info(path: str) -> ToolResult:
        target = ws.resolve(path)
        teile = {"absolut": str(target), "ordner": str(target.parent),
                 "name": target.name, "stamm": target.stem, "endung": target.suffix,
                 "teile": " / ".join(target.parts[-5:])}
        return ok("files.path.info", str(target),
                  payload="\n".join(f"{k}: {v}" for k, v in teile.items()), **teile)

    def files_path_relative(path: str, base: str = ".") -> ToolResult:
        target, root = ws.resolve(path), ws.resolve(base)
        try:
            relativ = os.path.relpath(target, root)
        except ValueError as exc:
            raise ToolError(f"Kein gemeinsamer Bezug: {exc}") from exc
        return ok("files.path.relative", relativ, payload=relativ,
                  von=str(root), nach=str(target))

    def files_symlink_create(path: str, target: str) -> ToolResult:
        link, ziel = ws.resolve(path), ws.resolve(target)
        if link.exists() or link.is_symlink():
            raise ToolError(f"Es gibt dort schon etwas: {link}")
        try:
            link.symlink_to(ziel)
        except OSError as exc:
            raise ToolError(f"Symlink nicht möglich: {exc}") from exc
        if not link.is_symlink():
            raise ToolError(f"Symlink ist nach dem Anlegen nicht da: {link}")
        return ok("files.symlink.create", f"Symlink {link.name} → {ziel.name}",
                  link=str(link), ziel=str(ziel))

    def files_symlink_read(path: str) -> ToolResult:
        link = ws.resolve(path)
        if not link.is_symlink():
            return ok("files.symlink.read", f"{link.name} ist kein Symlink",
                      pfad=str(link), symlink=False)
        ziel = os.readlink(link)
        return ok("files.symlink.read", f"{link.name} → {ziel}", payload=ziel,
                  pfad=str(link), symlink=True, ziel=ziel,
                  ziel_existiert=Path(link).resolve().exists())

    # ══════════════════════════════════════════════════════════════ Ordner
    def dir_create(path: str) -> ToolResult:
        target = ws.resolve(path)
        schon_da = target.is_dir()
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise ToolError(f"Ordner ist nach dem Anlegen nicht da: {target}")
        return ok("dir.create",
                  f"{'Gab es schon' if schon_da else 'Angelegt'}: {target.name}",
                  pfad=str(target), neu=not schon_da)

    def dir_delete(path: str, recursive: bool = False, dry_run: bool = False) -> ToolResult:
        target = need_dir(path)
        inhalt = list(target.iterdir())
        if inhalt and not recursive:
            raise ToolError(f"{target.name} ist nicht leer ({len(inhalt)} Einträge). "
                            "Mit recursive=true wirklich alles löschen.")
        anzahl = sum(1 for _ in walk(target, files_only=False)) if inhalt else 0
        if dry_run:
            return planned("dir.delete",
                           f"{target} würde gelöscht ({anzahl} Einträge darin)",
                           pfad=str(target), eintraege=anzahl)
        shutil.rmtree(target) if recursive else target.rmdir()
        if target.exists():
            raise ToolError(f"Ordner ist nach dem Löschen noch da: {target}")
        return ok("dir.delete", f"Ordner gelöscht: {target.name}",
                  pfad=str(target), eintraege=anzahl)

    def dir_copy(source: str, destination: str, dry_run: bool = False) -> ToolResult:
        src, dst = need_dir(source), ws.resolve(destination)
        dateien = list(walk(src))
        bytes_gesamt = sum(_safe_size(f) for f in dateien)
        if dry_run:
            return planned("dir.copy",
                           f"{len(dateien)} Dateien ({human_bytes(bytes_gesamt)}) "
                           f"würden nach {dst} kopiert",
                           von=str(src), nach=str(dst), dateien=len(dateien))
        if dst.exists():
            raise ToolError(f"Ziel existiert schon: {dst}")
        shutil.copytree(src, dst)
        return ok("dir.copy", f"{len(dateien)} Dateien kopiert nach {dst.name}",
                  von=str(src), nach=str(dst), dateien=len(dateien),
                  bytes=bytes_gesamt)

    def dir_move(source: str, destination: str) -> ToolResult:
        src, dst = need_dir(source), ws.resolve(destination)
        if dst.exists():
            raise ToolError(f"Ziel existiert schon: {dst}")
        shutil.move(str(src), str(dst))
        if not dst.is_dir():
            raise ToolError(f"Ziel ist nach dem Verschieben kein Ordner: {dst}")
        return ok("dir.move", f"Ordner verschoben nach {dst.name}",
                  von=str(src), nach=str(dst))

    def dir_tree(path: str = ".", depth: int = 2, limit: int = 300) -> ToolResult:
        root = need_dir(path)
        tiefe = max(1, min(int(depth or 2), 8))
        lines, gezaehlt = [], 0

        def descend(current: Path, level: int, prefix: str) -> None:
            nonlocal gezaehlt
            if level > tiefe or gezaehlt >= limit:
                return
            try:
                eintraege = sorted(current.iterdir(),
                                   key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                return
            for entry in eintraege:
                if gezaehlt >= limit:
                    lines.append(f"{prefix}… (abgeschnitten bei {limit})")
                    return
                gezaehlt += 1
                lines.append(f"{prefix}{'📁 ' if entry.is_dir() else '   '}{entry.name}")
                if entry.is_dir():
                    descend(entry, level + 1, prefix + "  ")

        descend(root, 1, "")
        return ok("dir.tree", f"{gezaehlt} Einträge unter {root.name or root}",
                  payload="\n".join(lines) or "(leer)", wurzel=str(root),
                  eintraege=gezaehlt, tiefe=tiefe)

    def dir_size(path: str = ".") -> ToolResult:
        root = need_dir(path)
        dateien = list(walk(root))
        gesamt = sum(_safe_size(f) for f in dateien)
        return ok("dir.size", f"{root.name or root}: {human_bytes(gesamt)} "
                              f"in {len(dateien)} Dateien",
                  pfad=str(root), bytes=gesamt, dateien=len(dateien))

    def dir_usage_breakdown(path: str = ".", limit: int = 20) -> ToolResult:
        """Welcher Unterordner frisst den Platz -- die Frage, die man
        tatsächlich stellt, wenn die Platte voll ist."""
        root = need_dir(path)
        rows = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            rows.append((sum(_safe_size(f) for f in walk(child)), child.name))
        dateien_direkt = sum(_safe_size(f) for f in root.iterdir() if f.is_file())
        if dateien_direkt:
            rows.append((dateien_direkt, "(Dateien direkt hier)"))
        rows.sort(reverse=True)
        gesamt = sum(s for s, _ in rows) or 1
        return ok("dir.usage.breakdown", f"{root.name or root}: {human_bytes(gesamt)}",
                  payload=table([[human_bytes(s), f"{s / gesamt * 100:4.1f}%", name]
                                 for s, name in rows[:int(limit or 20)]],
                                ["groesse", "anteil", "ordner"]),
                  pfad=str(root), bytes=gesamt, ordner=len(rows))

    def dir_empty_find(path: str = ".", limit: int = 50) -> ToolResult:
        root = need_dir(path)
        leer = [d for d in root.rglob("*") if d.is_dir() and not any(d.iterdir())]
        return ok("dir.empty.find", f"{len(leer)} leere Ordner",
                  payload="\n".join(str(p) for p in leer[:int(limit or 50)]) or "(keine)",
                  wurzel=str(root), treffer=len(leer))

    def dir_compare(path_a: str, path_b: str) -> ToolResult:
        a, b = need_dir(path_a), need_dir(path_b)
        namen_a = {p.relative_to(a).as_posix() for p in walk(a)}
        namen_b = {p.relative_to(b).as_posix() for p in walk(b)}
        nur_a, nur_b = sorted(namen_a - namen_b), sorted(namen_b - namen_a)
        gemeinsam = namen_a & namen_b
        verschieden = [n for n in sorted(gemeinsam)
                       if not filecmp.cmp(a / n, b / n, shallow=False)]
        lines = ([f"nur in A: {n}" for n in nur_a[:100]]
                 + [f"nur in B: {n}" for n in nur_b[:100]]
                 + [f"verschieden: {n}" for n in verschieden[:100]])
        return ok("dir.compare",
                  f"{len(nur_a)} nur links, {len(nur_b)} nur rechts, "
                  f"{len(verschieden)} inhaltlich verschieden",
                  payload="\n".join(lines) or "(identisch)",
                  nur_a=len(nur_a), nur_b=len(nur_b), verschieden=len(verschieden),
                  gemeinsam=len(gemeinsam))

    def dir_sync(source: str, destination: str, delete: bool = False,
                 dry_run: bool = True) -> ToolResult:
        """Einweg-Abgleich. ``dry_run`` steht hier **auf true als Vorgabe**:
        ein Abgleich, der beim ersten Versuch ungefragt Dateien überschreibt,
        ist der Klassiker unter den teuren Fehlern."""
        src, dst = need_dir(source), ws.resolve(destination)
        dst.mkdir(parents=True, exist_ok=True)
        neu, geaendert, ueberzaehlig = [], [], []
        for found in walk(src):
            relativ = found.relative_to(src)
            ziel = dst / relativ
            if not ziel.exists():
                neu.append(relativ)
            elif not filecmp.cmp(found, ziel, shallow=False):
                geaendert.append(relativ)
        if delete:
            quelle_namen = {p.relative_to(src) for p in walk(src)}
            ueberzaehlig = [p.relative_to(dst) for p in walk(dst)
                            if p.relative_to(dst) not in quelle_namen]
        zusammenfassung = (f"{len(neu)} neu, {len(geaendert)} geändert"
                           + (f", {len(ueberzaehlig)} überzählig" if delete else ""))
        payload = "\n".join([*(f"neu: {p}" for p in neu[:80]),
                             *(f"geändert: {p}" for p in geaendert[:80]),
                             *(f"würde gelöscht: {p}" for p in ueberzaehlig[:80])])
        if dry_run:
            return planned("dir.sync", zusammenfassung, payload=payload or "(nichts zu tun)",
                           von=str(src), nach=str(dst), neu=len(neu),
                           geaendert=len(geaendert), ueberzaehlig=len(ueberzaehlig))
        for relativ in neu + geaendert:
            ziel = dst / relativ
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / relativ, ziel)
        for relativ in ueberzaehlig:
            (dst / relativ).unlink(missing_ok=True)
        return ok("dir.sync", zusammenfassung, payload=payload,
                  von=str(src), nach=str(dst), neu=len(neu),
                  geaendert=len(geaendert), geloescht=len(ueberzaehlig))

    def files_organize_by_extension(path: str = ".", dry_run: bool = True) -> ToolResult:
        """Das Beispiel aus Punkt 30: „Räume meinen Downloads-Ordner auf."
        Zeigt erst, was passieren würde."""
        root = need_dir(path)
        plan: list[tuple[Path, Path]] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_file():
                continue
            ordner = root / (entry.suffix.lstrip(".").lower() or "ohne_endung")
            if ordner == entry.parent:
                continue
            plan.append((entry, ordner / entry.name))
        payload = table([[p.name, q.parent.name] for p, q in plan[:120]],
                        ["datei", "nach"])
        if dry_run:
            return planned("files.organize.by_extension",
                           f"{len(plan)} Dateien würden nach Endung einsortiert",
                           payload=payload or "(nichts zu tun)",
                           wurzel=str(root), dateien=len(plan))
        verschoben = 0
        for quelle, ziel in plan:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            if ziel.exists():
                continue
            shutil.move(str(quelle), str(ziel))
            verschoben += 1
        return ok("files.organize.by_extension",
                  f"{verschoben} von {len(plan)} Dateien einsortiert", payload=payload,
                  wurzel=str(root), verschoben=verschoben, geplant=len(plan))

    # ════════════════════════════════════════════════════════════ Archive
    def archive_zip_create(path: str, sources: str, compress: bool = True) -> ToolResult:
        ziel = ws.resolve(path)
        eintraege = [ws.resolve(s.strip()) for s in (sources or "").split(",") if s.strip()]
        if not eintraege:
            raise ToolError("sources ist leer. Erwartet werden Pfade, durch Komma getrennt.")
        modus = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        ziel.parent.mkdir(parents=True, exist_ok=True)
        anzahl = 0
        with zipfile.ZipFile(ziel, "w", modus) as archiv:
            for quelle in eintraege:
                if quelle.is_dir():
                    for found in walk(quelle):
                        archiv.write(found, found.relative_to(quelle.parent).as_posix())
                        anzahl += 1
                elif quelle.is_file():
                    archiv.write(quelle, quelle.name)
                    anzahl += 1
                else:
                    raise ToolError(f"Existiert nicht: {quelle}")
        return ok("archive.zip.create",
                  f"{anzahl} Einträge in {ziel.name} ({human_bytes(ziel.stat().st_size)})",
                  pfad=str(ziel), eintraege=anzahl, bytes=ziel.stat().st_size)

    def archive_zip_extract(path: str, destination: str = "",
                            dry_run: bool = False) -> ToolResult:
        archiv_pfad = need_file(path)
        ziel = ws.resolve(destination) if destination else archiv_pfad.with_suffix("")
        if not zipfile.is_zipfile(archiv_pfad):
            raise ToolError(f"{archiv_pfad.name} ist kein ZIP-Archiv.")
        with zipfile.ZipFile(archiv_pfad) as archiv:
            namen = archiv.namelist()
            # Zip-Slip: ein Eintrag wie "../../etc/passwd" würde beim Entpacken
            # aus dem Zielordner ausbrechen. Geprüft wird vor dem Schreiben.
            for name in namen:
                if os.path.isabs(name) or ".." in Path(name).parts:
                    raise ToolError(f"Archiv enthält einen Ausbruchspfad: {name}. "
                                    "Nichts wurde entpackt.")
            if dry_run:
                return planned("archive.zip.extract",
                               f"{len(namen)} Einträge würden nach {ziel} entpackt",
                               payload="\n".join(namen[:120]),
                               archiv=str(archiv_pfad), ziel=str(ziel), eintraege=len(namen))
            ziel.mkdir(parents=True, exist_ok=True)
            archiv.extractall(ziel)
        return ok("archive.zip.extract", f"{len(namen)} Einträge entpackt nach {ziel.name}",
                  archiv=str(archiv_pfad), ziel=str(ziel), eintraege=len(namen))

    def archive_zip_list(path: str, limit: int = 200) -> ToolResult:
        archiv_pfad = need_file(path)
        if not zipfile.is_zipfile(archiv_pfad):
            raise ToolError(f"{archiv_pfad.name} ist kein ZIP-Archiv.")
        with zipfile.ZipFile(archiv_pfad) as archiv:
            infos = archiv.infolist()
        rows = [[human_bytes(i.file_size), i.filename] for i in infos[:int(limit or 200)]]
        return ok("archive.zip.list", f"{len(infos)} Einträge in {archiv_pfad.name}",
                  payload=table(rows, ["groesse", "name"]),
                  pfad=str(archiv_pfad), eintraege=len(infos),
                  bytes_entpackt=sum(i.file_size for i in infos))

    def archive_tar_create(path: str, sources: str, compression: str = "gz") -> ToolResult:
        ziel = ws.resolve(path)
        eintraege = [ws.resolve(s.strip()) for s in (sources or "").split(",") if s.strip()]
        if not eintraege:
            raise ToolError("sources ist leer.")
        if compression not in ("", "gz", "bz2", "xz"):
            raise ToolError(f"Unbekannte Kompression: {compression}. Möglich: gz, bz2, xz, leer")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        anzahl = 0
        with tarfile.open(ziel, f"w:{compression}" if compression else "w") as archiv:
            for quelle in eintraege:
                if not quelle.exists():
                    raise ToolError(f"Existiert nicht: {quelle}")
                archiv.add(quelle, arcname=quelle.name)
                anzahl += 1
        return ok("archive.tar.create",
                  f"{anzahl} Einträge in {ziel.name} ({human_bytes(ziel.stat().st_size)})",
                  pfad=str(ziel), eintraege=anzahl, bytes=ziel.stat().st_size)

    def archive_tar_extract(path: str, destination: str = "",
                            dry_run: bool = False) -> ToolResult:
        archiv_pfad = need_file(path)
        ziel = ws.resolve(destination) if destination else archiv_pfad.parent
        try:
            archiv = tarfile.open(archiv_pfad)
        except tarfile.TarError as exc:
            raise ToolError(f"Kein lesbares tar-Archiv: {exc}") from exc
        with archiv:
            namen = archiv.getnames()
            for name in namen:
                if os.path.isabs(name) or ".." in Path(name).parts:
                    raise ToolError(f"Archiv enthält einen Ausbruchspfad: {name}. "
                                    "Nichts wurde entpackt.")
            if dry_run:
                return planned("archive.tar.extract",
                               f"{len(namen)} Einträge würden nach {ziel} entpackt",
                               payload="\n".join(namen[:120]),
                               archiv=str(archiv_pfad), ziel=str(ziel), eintraege=len(namen))
            ziel.mkdir(parents=True, exist_ok=True)
            # filter="data" verweigert Symlinks und absolute Pfade zusätzlich
            # auf Bibliotheksebene (Python 3.12+); die eigene Prüfung oben
            # bleibt, damit es auch auf älteren Fassungen hält.
            try:
                archiv.extractall(ziel, filter="data")
            except TypeError:  # pragma: no cover - Python < 3.12
                archiv.extractall(ziel)
        return ok("archive.tar.extract", f"{len(namen)} Einträge entpackt nach {ziel.name}",
                  archiv=str(archiv_pfad), ziel=str(ziel), eintraege=len(namen))

    def archive_tar_list(path: str, limit: int = 200) -> ToolResult:
        archiv_pfad = need_file(path)
        try:
            archiv = tarfile.open(archiv_pfad)
        except tarfile.TarError as exc:
            raise ToolError(f"Kein lesbares tar-Archiv: {exc}") from exc
        with archiv:
            members = archiv.getmembers()
        rows = [[human_bytes(m.size), m.name] for m in members[:int(limit or 200)]]
        return ok("archive.tar.list", f"{len(members)} Einträge in {archiv_pfad.name}",
                  payload=table(rows, ["groesse", "name"]),
                  pfad=str(archiv_pfad), eintraege=len(members),
                  bytes_entpackt=sum(m.size for m in members))

    def archive_inspect(path: str) -> ToolResult:
        """Was ist das für ein Archiv, und was steckt drin -- ohne vorher
        wissen zu müssen, ob es ZIP oder TAR ist."""
        archiv_pfad = need_file(path)
        if zipfile.is_zipfile(archiv_pfad):
            return archive_zip_list(path, limit=60)
        if tarfile.is_tarfile(archiv_pfad):
            return archive_tar_list(path, limit=60)
        with open(archiv_pfad, "rb") as fh:
            head = fh.read(16)
        if head.startswith(b"\x1f\x8b"):
            return ok("archive.inspect", f"{archiv_pfad.name}: gzip (Einzeldatei)",
                      pfad=str(archiv_pfad), format="gzip")
        raise ToolError(f"{archiv_pfad.name} ist kein erkanntes Archiv "
                        "(geprüft: zip, tar, gzip).")

    def archive_gzip_compress(path: str, level: int = 6) -> ToolResult:
        src = need_file(path)
        dst = src.with_name(src.name + ".gz")
        if dst.exists():
            raise ToolError(f"Existiert schon: {dst}")
        with open(src, "rb") as quelle, gzip.open(dst, "wb",
                                                  compresslevel=max(1, min(int(level or 6), 9))) as ziel:
            shutil.copyfileobj(quelle, ziel)
        vorher, nachher = src.stat().st_size, dst.stat().st_size
        return ok("archive.gzip.compress",
                  f"{human_bytes(vorher)} → {human_bytes(nachher)} "
                  f"({100 - nachher / max(vorher, 1) * 100:.0f} % kleiner)",
                  von=str(src), nach=str(dst), bytes_vorher=vorher, bytes_nachher=nachher)

    def archive_gzip_decompress(path: str) -> ToolResult:
        src = need_file(path)
        if src.suffix != ".gz":
            raise ToolError(f"Erwartet eine .gz-Datei, bekommen: {src.name}")
        dst = src.with_suffix("")
        if dst.exists():
            raise ToolError(f"Existiert schon: {dst}")
        with gzip.open(src, "rb") as quelle, open(dst, "wb") as ziel:
            shutil.copyfileobj(quelle, ziel)
        return ok("archive.gzip.decompress", f"Entpackt nach {dst.name}",
                  von=str(src), nach=str(dst), bytes=dst.stat().st_size)

    # ═══════════════════════════════════════════════════════ Registrierung
    _p = text("Pfad, relativ zum Arbeitsbereich oder absolut")
    return [
        # ── Grundlagen ────────────────────────────────────────────────────
        Tool("files.copy", "Kopiert eine Datei an einen anderen Ort.",
             params("source", "destination", source=_p, destination=_p,
                    overwrite=flag("Vorhandenes Ziel überschreiben")),
             files_copy, level=P.WRITE, tags=("datei", "kopieren"), undoable=True,
             returns="Quelle, Ziel und Bytezahl der Kopie",
             phrases=("kopiere die Datei", "mach eine Kopie von", "copy file"),
             examples=({"source": "notizen.txt", "destination": "sicherung/"},)),
        Tool("files.rename", "Benennt eine Datei oder einen Ordner um (gleicher Ordner).",
             params("path", "new_name", path=_p, new_name=text("Neuer Dateiname ohne Pfad")),
             files_rename, level=P.WRITE, tags=("datei", "umbenennen"), undoable=True,
             phrases=("benenne um", "nenn die datei", "rename")),
        Tool("files.exists", "Prüft, ob ein Pfad existiert, und was dort liegt.",
             params("path", path=_p), files_exists, level=P.SAFE,
             tags=("datei", "pruefen"), phrases=("gibt es die datei", "existiert")),
        Tool("files.info", "Alle Eckdaten einer Datei: Größe, Typ, Zeiten, Rechte.",
             params("path", path=_p), files_info, level=P.SAFE,
             tags=("datei", "metadaten"), returns="Pfad, Größe, MIME, Zeitstempel, Rechte",
             phrases=("was ist das für eine datei", "dateiinfo", "details zur datei")),
        Tool("files.size", "Größe einer einzelnen Datei in Bytes.",
             params("path", path=_p), files_size, level=P.SAFE,
             tags=("datei", "groesse"), phrases=("wie groß ist die datei",)),
        Tool("files.hash", "Prüfsumme einer Datei (md5, sha1, sha256, sha512).",
             params("path", path=_p,
                    algorithm=text("md5, sha1, sha256 (Vorgabe) oder sha512")),
             files_hash, level=P.SAFE, tags=("datei", "hash", "pruefsumme"),
             phrases=("hash der datei", "prüfsumme", "sha256 von")),
        Tool("files.hash.compare", "Vergleicht zwei Dateien über ihre Prüfsumme.",
             params("path_a", "path_b", path_a=_p, path_b=_p, algorithm=STR),
             files_hash_compare, level=P.SAFE, tags=("datei", "hash", "vergleich"),
             phrases=("sind die dateien gleich", "checksums vergleichen")),
        Tool("files.touch", "Legt eine leere Datei an oder frischt ihren Zeitstempel auf.",
             params("path", path=_p), files_touch, level=P.WRITE,
             tags=("datei", "anlegen"), undoable=True),
        Tool("files.append_line", "Hängt eine Zeile an eine Textdatei an.",
             params("path", "line", path=_p, line=text("Die anzuhängende Zeile")),
             files_append_line, level=P.WRITE, tags=("datei", "schreiben"), undoable=True),

        # ── Inhalt ────────────────────────────────────────────────────────
        Tool("files.head", "Die ersten N Zeilen einer Datei.",
             params("path", path=_p, lines=integer("Anzahl Zeilen, Vorgabe 20")),
             files_head, level=P.SAFE, tags=("datei", "lesen"),
             phrases=("anfang der datei", "erste zeilen")),
        Tool("files.tail", "Die letzten N Zeilen einer Datei — auch bei großen Logs.",
             params("path", path=_p, lines=integer("Anzahl Zeilen, Vorgabe 20")),
             files_tail, level=P.SAFE, tags=("datei", "lesen", "log"),
             phrases=("ende der datei", "letzte zeilen", "log anschauen")),
        Tool("files.lines", "Einen Zeilenbereich einer Datei mit Zeilennummern.",
             params("path", path=_p, start=integer("Erste Zeile, Vorgabe 1"),
                    end=integer("Letzte Zeile")),
             files_lines, level=P.SAFE, tags=("datei", "lesen")),
        Tool("files.line_count", "Zählt die Zeilen einer Datei.",
             params("path", path=_p), files_line_count, level=P.SAFE,
             tags=("datei", "zaehlen"), phrases=("wie viele zeilen",)),
        Tool("files.grep", "Sucht ein Textmuster in Dateien und zeigt die Fundstellen.",
             params("pattern", pattern=text("Regulärer Ausdruck oder Text"),
                    path=_p, glob=text("Dateimuster, z. B. '*.py'"),
                    ignore_case=flag("Groß/Klein ignorieren (Vorgabe: ja)"),
                    limit=INT),
             files_grep, level=P.SAFE, tags=("suche", "text", "grep"),
             returns="Datei, Zeilennummer und Textstelle je Treffer",
             phrases=("such im code nach", "wo steht", "finde den text")),
        Tool("files.replace_text", "Ersetzt Text in einer Datei. Kann einen Probelauf.",
             params("path", "search", path=_p, search=text("Gesuchter Text"),
                    replace=text("Ersatztext"), regex=flag("search als Regex lesen"),
                    dry_run=DRY),
             files_replace_text, level=P.WRITE, tags=("datei", "ersetzen"),
             undoable=True, dry_run=True,
             phrases=("ersetze in der datei", "such und ersetze")),
        Tool("files.compare", "Zeigt die Unterschiede zwischen zwei Textdateien.",
             params("path_a", "path_b", path_a=_p, path_b=_p, context=INT),
             files_compare, level=P.SAFE, tags=("vergleich", "diff"),
             phrases=("was ist anders", "unterschied zwischen den dateien", "diff")),
        Tool("files.type.detect", "Erkennt den Dateityp an den ersten Bytes, nicht nur an der Endung.",
             params("path", path=_p), files_type_detect, level=P.SAFE,
             tags=("datei", "typ", "mime"),
             phrases=("was für ein dateityp", "mime type")),
        Tool("files.encoding.detect", "Findet heraus, in welcher Zeichenkodierung eine Datei lesbar ist.",
             params("path", path=_p), files_encoding_detect, level=P.SAFE,
             tags=("datei", "kodierung"), phrases=("encoding", "zeichensatz")),
        Tool("files.timestamps.read", "Zeitstempel einer Datei: geändert, Zugriff, Status.",
             params("path", path=_p), files_timestamps_read, level=P.SAFE,
             tags=("datei", "zeit")),
        Tool("files.timestamps.set", "Setzt den Änderungszeitstempel einer Datei.",
             params("path", path=_p,
                    modified=text("'JJJJ-MM-TT HH:MM:SS', leer = jetzt")),
             files_timestamps_set, level=P.WRITE, tags=("datei", "zeit")),
        Tool("files.permissions.read", "Liest die Zugriffsrechte einer Datei.",
             params("path", path=_p), files_permissions_read, level=P.SAFE,
             tags=("datei", "rechte"), phrases=("welche rechte hat die datei",)),
        Tool("files.permissions.change", "Ändert die Zugriffsrechte einer Datei (oktal, z. B. 644).",
             params("path", "mode", path=_p, mode=text("Oktal, z. B. '644' oder '755'")),
             files_permissions_change, level=P.SYSTEM, tags=("datei", "rechte"),
             platforms=("linux", "darwin"),
             phrases=("chmod", "rechte setzen", "datei ausführbar machen")),
        Tool("files.backup", "Legt eine Sicherungskopie neben der Datei an.",
             params("path", path=_p, suffix=text("Endung, Vorgabe '.bak'")),
             files_backup, level=P.WRITE, tags=("datei", "sicherung"), undoable=True,
             phrases=("mach ein backup", "sicherungskopie")),
        Tool("files.temp.create", "Erzeugt eine temporäre Datei im Arbeitsbereich.",
             params(suffix=text("Endung, Vorgabe '.tmp'"), content=text("Inhalt")),
             files_temp_create, level=P.WRITE, tags=("datei", "temporaer"), undoable=True),
        Tool("files.json.read", "Liest eine JSON-Datei, optional nur einen Teilpfad daraus.",
             params("path", path=_p,
                    pointer=text("Pfad im Dokument, z. B. 'server.port'")),
             files_json_read, level=P.SAFE, tags=("json", "datei", "lesen"),
             phrases=("lies das json", "was steht in der config")),
        Tool("files.json.write", "Schreibt formatiertes JSON in eine Datei.",
             params("path", "data", path=_p, data=text("Das JSON als Text"), indent=INT),
             files_json_write, level=P.WRITE, tags=("json", "datei", "schreiben"),
             undoable=True),
        Tool("files.csv.preview", "Zeigt die ersten Zeilen einer CSV-Datei als Tabelle.",
             params("path", path=_p, rows=INT, delimiter=text("Trennzeichen, sonst geraten")),
             files_csv_preview, level=P.SAFE, tags=("csv", "tabelle")),
        Tool("files.csv.columns", "Listet die Spaltennamen einer CSV-Datei.",
             params("path", path=_p, delimiter=STR), files_csv_columns, level=P.SAFE,
             tags=("csv", "tabelle")),

        # ── Suchen im Dateibaum ───────────────────────────────────────────
        Tool("files.large.find", "Findet die größten Dateien unter einem Ordner.",
             params(path=_p, min_mb=text("Mindestgröße in MB, Vorgabe 100"), limit=INT),
             files_large_find, level=P.SAFE, tags=("suche", "groesse", "aufraeumen"),
             returns="Liste aus Größe und Pfad, größte zuerst",
             phrases=("große dateien finden", "was belegt den platz",
                      "such alle dateien über 2 gb")),
        Tool("files.old.find", "Findet Dateien, die lange nicht angefasst wurden.",
             params(path=_p, days=integer("Alter in Tagen, Vorgabe 365"), limit=INT),
             files_old_find, level=P.SAFE, tags=("suche", "alter", "aufraeumen"),
             phrases=("alte dateien", "was liegt hier schon ewig")),
        Tool("files.recent.find", "Findet zuletzt geänderte Dateien.",
             params(path=_p, hours=integer("Zeitraum in Stunden, Vorgabe 24"), limit=INT),
             files_recent_find, level=P.SAFE, tags=("suche", "zeit"),
             phrases=("was habe ich zuletzt geändert", "neueste dateien")),
        Tool("files.empty.find", "Findet leere Dateien.",
             params(path=_p, limit=INT), files_empty_find, level=P.SAFE,
             tags=("suche", "aufraeumen")),
        Tool("files.duplicate.find",
             "Findet inhaltsgleiche Dateien über Größe und Prüfsumme.",
             params(path=_p, limit=INT), files_duplicate_find, level=P.SAFE,
             tags=("suche", "duplikate", "aufraeumen"),
             returns="Gruppen gleicher Dateien und der dadurch belegte Platz",
             phrases=("duplikate finden", "doppelte dateien", "was liegt doppelt rum")),
        Tool("files.count.by_extension", "Zählt Dateien und Platz je Dateiendung.",
             params(path=_p, limit=INT), files_count_by_extension, level=P.SAFE,
             tags=("statistik", "aufraeumen"),
             phrases=("was für dateien liegen hier", "verteilung der dateitypen")),

        # ── Pfade ─────────────────────────────────────────────────────────
        Tool("files.path.info", "Zerlegt einen Pfad in Ordner, Name, Stamm und Endung.",
             params("path", path=_p), files_path_info, level=P.SAFE, tags=("pfad",)),
        Tool("files.path.relative", "Rechnet einen Pfad relativ zu einem anderen aus.",
             params("path", path=_p, base=_p), files_path_relative, level=P.SAFE,
             tags=("pfad",)),
        Tool("files.symlink.create", "Legt einen symbolischen Link an.",
             params("path", "target", path=text("Der neue Link"), target=text("Das Ziel")),
             files_symlink_create, level=P.WRITE, tags=("symlink", "pfad")),
        Tool("files.symlink.read", "Prüft, ob ein Pfad ein Symlink ist, und worauf er zeigt.",
             params("path", path=_p), files_symlink_read, level=P.SAFE,
             tags=("symlink", "pfad")),

        # ── Ordner ────────────────────────────────────────────────────────
        Tool("dir.create", "Legt einen Ordner an, samt fehlender Elternordner.",
             params("path", path=_p), dir_create, level=P.WRITE,
             tags=("ordner", "anlegen"), phrases=("erstelle einen ordner", "mkdir")),
        Tool("dir.delete", "Löscht einen Ordner. Nicht-leere nur mit recursive=true.",
             params("path", path=_p,
                    recursive=flag("Auch mit Inhalt löschen"), dry_run=DRY),
             dir_delete, level=P.CRITICAL, tags=("ordner", "loeschen"), dry_run=True,
             phrases=("lösche den ordner", "ordner entfernen")),
        Tool("dir.copy", "Kopiert einen Ordner samt Inhalt.",
             params("source", "destination", source=_p, destination=_p, dry_run=DRY),
             dir_copy, level=P.WRITE, tags=("ordner", "kopieren"), dry_run=True),
        Tool("dir.move", "Verschiebt oder benennt einen Ordner um.",
             params("source", "destination", source=_p, destination=_p),
             dir_move, level=P.WRITE, tags=("ordner", "verschieben")),
        Tool("dir.tree", "Zeigt den Ordnerbaum bis zu einer bestimmten Tiefe.",
             params(path=_p, depth=integer("Tiefe, Vorgabe 2"), limit=INT),
             dir_tree, level=P.SAFE, tags=("ordner", "uebersicht"),
             phrases=("zeig mir die ordnerstruktur", "wie ist das projekt aufgebaut")),
        Tool("dir.size", "Gesamtgröße eines Ordners samt Unterordnern.",
             params(path=_p), dir_size, level=P.SAFE, tags=("ordner", "groesse"),
             phrases=("wie groß ist der ordner",)),
        Tool("dir.usage.breakdown",
             "Zeigt, welcher Unterordner wie viel Platz belegt.",
             params(path=_p, limit=INT), dir_usage_breakdown, level=P.SAFE,
             tags=("ordner", "groesse", "aufraeumen"),
             returns="Größe, Anteil und Name je Unterordner, größter zuerst",
             phrases=("was frisst meinen speicherplatz", "welcher ordner ist so groß")),
        Tool("dir.empty.find", "Findet leere Ordner.",
             params(path=_p, limit=INT), dir_empty_find, level=P.SAFE,
             tags=("ordner", "aufraeumen")),
        Tool("dir.compare", "Vergleicht zwei Ordner: nur links, nur rechts, verschieden.",
             params("path_a", "path_b", path_a=_p, path_b=_p), dir_compare,
             level=P.SAFE, tags=("ordner", "vergleich"),
             phrases=("vergleiche die ordner", "was fehlt im zweiten ordner")),
        Tool("dir.sync",
             "Gleicht einen Ordner auf einen anderen ab. Standardmäßig nur als Probelauf.",
             params("source", "destination", source=_p, destination=_p,
                    delete=flag("Im Ziel überzählige Dateien entfernen"), dry_run=DRY),
             dir_sync, level=P.WRITE, tags=("ordner", "sync", "sicherung"), dry_run=True,
             phrases=("synchronisiere die ordner", "spiegle den ordner")),
        Tool("files.organize.by_extension",
             "Sortiert lose Dateien eines Ordners in Unterordner je Endung. Erst als Probelauf.",
             params(path=_p, dry_run=DRY), files_organize_by_extension,
             level=P.WRITE, tags=("ordner", "aufraeumen"), dry_run=True,
             phrases=("räum den ordner auf", "sortiere die downloads",
                      "räume meinen downloads-ordner auf")),

        # ── Archive ───────────────────────────────────────────────────────
        Tool("archive.zip.create", "Packt Dateien oder Ordner in ein ZIP-Archiv.",
             params("path", "sources", path=text("Das zu erzeugende Archiv"),
                    sources=text("Pfade, durch Komma getrennt"),
                    compress=flag("Komprimieren (Vorgabe: ja)")),
             archive_zip_create, level=P.WRITE, tags=("archiv", "zip", "packen"),
             phrases=("pack das in ein zip", "zip erstellen")),
        Tool("archive.zip.extract", "Entpackt ein ZIP-Archiv. Prüft auf Ausbruchspfade.",
             params("path", path=text("Das Archiv"),
                    destination=text("Zielordner, leer = neben dem Archiv"), dry_run=DRY),
             archive_zip_extract, level=P.WRITE, tags=("archiv", "zip", "entpacken"),
             dry_run=True, phrases=("entpack das zip", "zip auspacken")),
        Tool("archive.zip.list", "Listet den Inhalt eines ZIP-Archivs, ohne zu entpacken.",
             params("path", path=STR, limit=INT), archive_zip_list, level=P.SAFE,
             tags=("archiv", "zip"), phrases=("was ist im zip drin",)),
        Tool("archive.tar.create", "Packt Dateien in ein tar-Archiv (gz, bz2, xz oder roh).",
             params("path", "sources", path=STR, sources=STR,
                    compression=text("gz (Vorgabe), bz2, xz oder leer")),
             archive_tar_create, level=P.WRITE, tags=("archiv", "tar", "packen")),
        Tool("archive.tar.extract", "Entpackt ein tar-Archiv. Prüft auf Ausbruchspfade.",
             params("path", path=STR, destination=STR, dry_run=DRY),
             archive_tar_extract, level=P.WRITE, tags=("archiv", "tar", "entpacken"),
             dry_run=True),
        Tool("archive.tar.list", "Listet den Inhalt eines tar-Archivs.",
             params("path", path=STR, limit=INT), archive_tar_list, level=P.SAFE,
             tags=("archiv", "tar")),
        Tool("archive.inspect", "Erkennt das Archivformat und zeigt den Inhalt.",
             params("path", path=STR), archive_inspect, level=P.SAFE,
             tags=("archiv", "pruefen"), phrases=("was ist das für ein archiv",)),
        Tool("archive.gzip.compress", "Komprimiert eine einzelne Datei mit gzip.",
             params("path", path=STR, level=integer("1–9, Vorgabe 6")),
             archive_gzip_compress, level=P.WRITE, tags=("archiv", "gzip")),
        Tool("archive.gzip.decompress", "Entpackt eine .gz-Datei.",
             params("path", path=STR), archive_gzip_decompress, level=P.WRITE,
             tags=("archiv", "gzip")),
    ]


# ══════════════════════════════════════════════════════════════ Kleinkram

def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_mtime(path: Path) -> bool:
    try:
        path.stat()
    except OSError:
        return False
    return True


def _sniff_delimiter(raw: str) -> str:
    """Trennzeichen aus der ersten Zeile raten. ``csv.Sniffer`` wirft bei
    kurzen Dateien gern -- dann lieber selbst zählen als scheitern."""
    first = (raw.splitlines() or [""])[0]
    counts = {sep: first.count(sep) for sep in (",", ";", "\t", "|")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else ","
