"""Systemwerkzeuge.

``psutil`` ist optional. Fehlt es, meldet Jarvis das — und erfindet keine
Auslastungswerte. Eine Oberfläche, die Messwerte erfindet, wäre derselbe Fehler
wie ein Modell, das Dateien erfindet.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
from pathlib import Path

from ..permissions import PermissionLevel
from .base import Tool, ToolError, ToolResult

try:  # pragma: no cover - hängt von der Installation ab
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_NO_PSUTIL = ("Dafür fehlt das Paket 'psutil'. Ohne es kann ich die Auslastung "
              "nicht messen und rate sie nicht. Installation: pip install psutil")

GB = 1024 ** 3


def get_system_info() -> ToolResult:
    uname = platform.uname()
    info = {
        "system": f"{uname.system} {uname.release}",
        "rechner": socket.gethostname(),
        "architektur": uname.machine,
        "prozessor": uname.processor or uname.machine,
        "python": platform.python_version(),
        "kerne": os.cpu_count() or 0,
    }
    lines = [f"{k}: {v}" for k, v in info.items()]
    return ToolResult(tool="get_system_info", ok=True,
                      summary=f"{info['system']} auf {info['rechner']}",
                      evidence=info, payload="\n".join(lines))


def get_cpu_info() -> ToolResult:
    if psutil is None:
        raise ToolError(_NO_PSUTIL)
    percent = psutil.cpu_percent(interval=0.4)
    freq = psutil.cpu_freq()
    evidence = {
        "auslastung_prozent": round(percent, 1),
        "kerne_physisch": psutil.cpu_count(logical=False) or 0,
        "kerne_logisch": psutil.cpu_count(logical=True) or 0,
    }
    if freq:
        evidence["takt_mhz"] = round(freq.current)
    return ToolResult(tool="get_cpu_info", ok=True,
                      summary=f"CPU-Auslastung {percent:.0f} %",
                      evidence=evidence,
                      payload="\n".join(f"{k}: {v}" for k, v in evidence.items()))


def get_ram_info() -> ToolResult:
    if psutil is None:
        raise ToolError(_NO_PSUTIL)
    mem = psutil.virtual_memory()
    evidence = {
        "gesamt_gb": round(mem.total / GB, 1),
        "belegt_gb": round(mem.used / GB, 1),
        "frei_gb": round(mem.available / GB, 1),
        "auslastung_prozent": round(mem.percent, 1),
    }
    return ToolResult(
        tool="get_ram_info", ok=True,
        summary=f"{evidence['belegt_gb']} von {evidence['gesamt_gb']} GB belegt "
                f"({evidence['auslastung_prozent']:.0f} %)",
        evidence=evidence,
        payload="\n".join(f"{k}: {v}" for k, v in evidence.items()))


def get_disk_info(path: str = "") -> ToolResult:
    target = Path(path).expanduser() if path else Path(Path.home().anchor or "/")
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        raise ToolError(f"Laufwerk nicht lesbar: {target} ({exc})") from exc
    evidence = {
        "pfad": str(target),
        "gesamt_gb": round(usage.total / GB, 1),
        "belegt_gb": round(usage.used / GB, 1),
        "frei_gb": round(usage.free / GB, 1),
        "auslastung_prozent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
    }
    return ToolResult(
        tool="get_disk_info", ok=True,
        summary=f"{evidence['frei_gb']} GB frei auf {target}",
        evidence=evidence,
        payload="\n".join(f"{k}: {v}" for k, v in evidence.items()))


def list_processes(limit: int = 12) -> ToolResult:
    if psutil is None:
        raise ToolError(_NO_PSUTIL)
    limit = max(1, min(int(limit or 12), 60))
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            mb = (info["memory_info"].rss / (1024 ** 2)) if info.get("memory_info") else 0
            rows.append((mb, info.get("pid"), info.get("name") or "?"))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(reverse=True)
    top = rows[:limit]
    lines = [f"{pid:>7}  {mb:8.0f} MB  {name}" for mb, pid, name in top]
    return ToolResult(
        tool="list_processes", ok=True,
        summary=f"{len(rows)} laufende Prozesse, die {len(top)} größten gelistet",
        evidence={"prozesse_gesamt": len(rows), "gelistet": len(top)},
        payload="\n".join(lines))


def telemetry() -> dict:
    """Live-Werte für die Oberfläche. Ohne psutil: leeres Dict, keine Erfindung."""
    if psutil is None:
        return {}
    out: dict = {}
    try:
        out["cpu"] = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        out["ram"] = {"used": round(mem.used / GB, 1), "total": round(mem.total / GB, 1)}
        usage = shutil.disk_usage(Path(Path.home().anchor or "/"))
        out["disk"] = round(usage.used / usage.total * 100, 1) if usage.total else 0
    except Exception:  # noqa: BLE001 - Telemetrie darf den Server nie stören
        return out
    return out


def build() -> list[Tool]:
    empty = {"type": "object", "properties": {}, "required": []}
    return [
        Tool("get_system_info", "Betriebssystem, Rechnername, Architektur, Kernzahl.",
             empty, get_system_info, level=PermissionLevel.READ, category="system",
             aliases=("system.info",), tags=("system", "info"),
             phrases=("was für ein system", "systeminfo", "welches betriebssystem")),
        Tool("get_cpu_info", "Aktuelle CPU-Auslastung, Kernzahl und Takt.",
             empty, get_cpu_info, level=PermissionLevel.READ, category="system",
             aliases=("system.cpu.usage",), tags=("system", "cpu", "auslastung"),
             requires=("psutil",),
             phrases=("wie ausgelastet ist die cpu", "cpu auslastung",
                      "prozessor auslastung")),
        Tool("get_ram_info", "Belegter und freier Arbeitsspeicher in GB.",
             empty, get_ram_info, level=PermissionLevel.READ, category="system",
             aliases=("system.ram.usage",), tags=("system", "ram", "speicher"),
             requires=("psutil",),
             phrases=("wie viel ram ist frei", "arbeitsspeicher", "ram auslastung")),
        Tool("get_disk_info", "Freier und belegter Speicherplatz eines Laufwerks.",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
             get_disk_info, level=PermissionLevel.READ, category="system",
             aliases=("system.disk.usage",), tags=("system", "disk", "speicherplatz"),
             phrases=("wie viel platz ist frei", "festplatte voll",
                      "speicherplatz")),
        Tool("list_processes", "Die speicherhungrigsten laufenden Prozesse.",
             {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []},
             list_processes, level=PermissionLevel.READ, category="system",
             aliases=("system.process.memory_top",),
             tags=("system", "prozess", "speicher"), requires=("psutil",),
             phrases=("was frisst meinen ram", "welche prozesse laufen",
                      "speicherhungrige prozesse")),
    ]
