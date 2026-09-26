"""Der Katalog um die Werkzeuge herum: woher sie ihren Kontext bekommen,
wovon sie abhängen, und ob sie hier und jetzt überhaupt laufen können.

Das ist der ehrliche Teil eines großen Werkzeugkastens. Ein Tool, das auf
diesem Rechner nicht funktionieren kann -- falsche Plattform, fehlendes
Programm --, soll das **vorher** sagen, statt beim Aufruf zu scheitern und
den Nutzer raten zu lassen, woran es lag (Aufgabenstellung Punkt 53/54).

Die Probes werden genau einmal ausgeführt und gemerkt. Bei mehreren hundert
Tools darf die Frage „läuft das hier?" nicht jedes Mal einen Prozess starten.
"""

from __future__ import annotations

import dataclasses
import importlib
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..config import Config
from ..memory import MemoryStore
from .base import Tool


class Availability(str, Enum):
    """Punkt 53: der Selbstauskunfts-Zustand eines Werkzeugs."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    DEGRADED = "DEGRADED"


# ══════════════════════════════════════════════════════════ Dependencies

@dataclass(frozen=True)
class Probe:
    """Wie festgestellt wird, ob eine Abhängigkeit da ist -- und was sie ist,
    falls jemand sie nachinstallieren will (Punkt 55)."""

    key: str
    label: str
    #: Prüfung: Programm im PATH (``binary``) oder importierbares Modul (``module``).
    kind: str
    target: str
    install_hint: str = ""
    #: Eigene Suche für ein Programm, das normalerweise NICHT im PATH liegt
    #: (z. B. Guardian im Build-Ordner des Repos). Gibt den gefundenen Pfad
    #: zurück oder "". Gesetzt über ``set_probe_finder``, nicht hier.
    finder: Callable[[], str] | None = None

    def check(self) -> tuple[bool, str]:
        if self.finder is not None:
            found = self.finder()
            return (bool(found), found or "")
        if self.kind == "binary":
            found = shutil.which(self.target)
            return (bool(found), found or "")
        try:
            module = importlib.import_module(self.target)
        except Exception:  # noqa: BLE001 - ein kaputtes Paket ist auch "nicht da"
            return (False, "")
        return (True, getattr(module, "__version__", "") or "vorhanden")


PROBES: dict[str, Probe] = {p.key: p for p in (
    Probe("psutil", "psutil", "module", "psutil", "pip install psutil"),
    Probe("pillow", "Pillow", "module", "PIL", "pip install Pillow"),
    Probe("httpx", "httpx", "module", "httpx", "pip install httpx"),
    Probe("yaml", "PyYAML", "module", "yaml", "pip install PyYAML"),
    Probe("playwright", "Playwright", "module", "playwright",
          "pip install playwright && playwright install chromium"),
    Probe("git", "Git", "binary", "git", "https://git-scm.com/downloads"),
    Probe("ffmpeg", "FFmpeg", "binary", "ffmpeg", "https://ffmpeg.org/download.html"),
    Probe("ffprobe", "FFprobe", "binary", "ffprobe", "Teil von FFmpeg"),
    Probe("docker", "Docker", "binary", "docker", "https://docs.docker.com/get-docker/"),
    Probe("node", "Node.js", "binary", "node", "https://nodejs.org"),
    Probe("npm", "npm", "binary", "npm", "kommt mit Node.js"),
    Probe("nginx", "nginx", "binary", "nginx", "https://nginx.org"),
    Probe("systemctl", "systemd", "binary", "systemctl", "nur auf Linux mit systemd"),
    Probe("powershell", "PowerShell", "binary", "powershell", "nur auf Windows"),
    Probe("tesseract", "Tesseract OCR", "binary", "tesseract",
          "https://github.com/tesseract-ocr/tesseract"),
    Probe("sevenzip", "7-Zip", "binary", "7z", "https://www.7-zip.org"),
    Probe("java", "Java", "binary", "java", "https://adoptium.net"),
    Probe("qrcode", "qrcode", "module", "qrcode", "pip install qrcode"),
    Probe("pyautogui", "PyAutoGUI", "module", "pyautogui", "pip install pyautogui"),
    Probe("guardian", "Guardian", "binary", "guardian",
          "im Ordner guardian/: cargo build --release (Rust: https://rustup.rs), "
          "oder guardian.binary in der jarvis.json"),
)}

#: Ergebnis-Zwischenspeicher, damit dieselbe Frage keinen zweiten Prozess kostet.
_probe_cache: dict[str, tuple[bool, str]] = {}


def probe(key: str) -> tuple[bool, str]:
    """(vorhanden?, Fundstelle/Version). Unbekannte Schlüssel gelten als fehlend
    -- lieber ein Tool zu viel als nicht verfügbar melden als eines zu wenig."""
    if key in _probe_cache:
        return _probe_cache[key]
    spec = PROBES.get(key)
    result = spec.check() if spec else (False, "")
    _probe_cache[key] = result
    return result


def reset_probes() -> None:
    """Nach einer Installation neu messen (und für Tests)."""
    _probe_cache.clear()


def set_probe_finder(key: str, finder: Callable[[], str]) -> None:
    """Hängt einer bekannten Abhängigkeit eine eigene Suche an -- für ein
    Pack, dessen Programm an einer konfigurierbaren Stelle liegt statt im
    PATH. Die Suche läuft bei Bedarf (und nach ``reset_probes`` neu), nicht
    schon beim Anhängen."""
    PROBES[key] = dataclasses.replace(PROBES[key], finder=finder)
    _probe_cache.pop(key, None)


def missing_dependencies(tool: Tool) -> list[str]:
    return [key for key in tool.requires if not probe(key)[0]]


def dependency_report() -> list[dict[str, Any]]:
    """Was da ist, was fehlt, und wie man es bekäme -- die Grundlage für den
    Installations-Assistenten (Punkt 55). Installiert wird hier **nichts**."""
    rows = []
    for key, spec in PROBES.items():
        ok, detail = probe(key)
        rows.append({"schluessel": key, "name": spec.label, "vorhanden": ok,
                     "fundstelle": detail, "installation": spec.install_hint})
    return sorted(rows, key=lambda r: (not r["vorhanden"], r["schluessel"]))


# ══════════════════════════════════════════════════════════ Selbstdiagnose

def current_platform() -> str:
    return platform.system().lower()


def availability(tool: Tool) -> tuple[Availability, str]:
    """Kann dieses Werkzeug hier und jetzt laufen? Mit Begründung.

    ``PERMISSION_REQUIRED`` ist ausdrücklich **kein** Hindernis, sondern ein
    Hinweis: das Tool läuft, verlangt aber eine Bestätigung. Es wird deshalb
    auch nicht aus der Auswahl gefiltert -- das Permission-System entscheidet
    beim Aufruf, nicht der Katalog vorher.
    """
    if tool.platforms and current_platform() not in tool.platforms:
        return (Availability.UNSUPPORTED_PLATFORM,
                f"Läuft nur auf: {', '.join(tool.platforms)} "
                f"(hier: {current_platform()})")
    missing = missing_dependencies(tool)
    if missing:
        hints = "; ".join(
            f"{PROBES[k].label} ({PROBES[k].install_hint})" if k in PROBES else k
            for k in missing)
        return (Availability.MISSING_DEPENDENCY, f"Es fehlt: {hints}")
    if tool.level >= tool.level.CRITICAL:
        return (Availability.PERMISSION_REQUIRED,
                "Läuft, verlangt aber immer eine ausdrückliche Bestätigung.")
    return (Availability.AVAILABLE, "")


def runnable(tool: Tool) -> bool:
    """Würde ein Aufruf überhaupt eine Chance haben? Eine nötige Bestätigung
    zählt als lauffähig."""
    state, _ = availability(tool)
    return state in (Availability.AVAILABLE, Availability.PERMISSION_REQUIRED,
                     Availability.DEGRADED)


# ══════════════════════════════════════════════════════════ ToolContext

@dataclass
class ToolContext:
    """Was ein Tool-Pack braucht, um seine Werkzeuge zu bauen.

    Ein Pack bekommt genau diesen einen Gegenstand und gibt eine Liste von
    ``Tool``s zurück. Damit hängt kein Pack an ``app.py``, an der Registry
    oder aneinander -- die Voraussetzung dafür, dass später auch fremde
    Pakete Werkzeuge beisteuern können (Punkt 38/39).
    """

    config: Config
    store: MemoryStore
    #: ``tools.files.Workspace`` -- als ``Any`` typisiert, weil ein Import
    #: hier einen Ringschluss ergäbe.
    workspace: Any
    home: Path
    #: Beliebige Zusatzdienste, die einzelne Packs brauchen (Undo-Ablage,
    #: Werkzeug-Historie). Packs greifen defensiv darauf zu.
    services: dict[str, Any] = field(default_factory=dict)


#: Die Signatur, die jedes Tool-Pack erfüllt.
PackBuilder = Callable[[ToolContext], list[Tool]]


# ══════════════════════════════════════════════════════════ Hilfen für Packs

def run_process(args: list[str], timeout: float = 30.0, cwd: str | None = None,
                stdin_text: str | None = None) -> subprocess.CompletedProcess:
    """Ein externes Programm aufrufen -- die eine Stelle, an der Packs das tun.

    Bewusst **ohne Shell**: die Argumentliste geht direkt an das Programm,
    also kann kein Dateiname mit Sonderzeichen zu einem zweiten Befehl werden.
    Das ist kein Ersatz für ``tools/shell.py`` (der bewusst eine Allowlist und
    eine eigene Freigabe hat), sondern der Weg für fest verdrahtete Aufrufe
    wie ``git status`` oder ``ffprobe``.
    """
    return subprocess.run(  # noqa: S603 - keine Shell, feste Argumentliste
        args, capture_output=True, text=True, timeout=timeout, cwd=cwd,
        input=stdin_text, check=False, encoding="utf-8", errors="replace")
