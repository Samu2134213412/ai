"""Tool Pack: System, Prozesse und Hardware.

Zwei Regeln bestimmen hier alles:

**1. Nichts erfinden.** ``psutil`` ist optional. Fehlt es, meldet das
Werkzeug das -- es rät keine Auslastung. Dasselbe gilt für Sensoren, die
es auf dieser Maschine schlicht nicht gibt: eine GPU-Temperatur, die kein
Treiber hergibt, wird nicht geschätzt, sondern als nicht verfügbar
gemeldet.

**2. Plattform-Ehrlichkeit.** Ein großer Teil dieser Werkzeuge ist
betriebssystemabhängig -- Dienste, Fenster, Clipboard, Bluetooth. Jedes
davon deklariert seine ``platforms``, und die Selbstdiagnose
(``catalog.availability``) meldet ``UNSUPPORTED_PLATFORM``, **bevor**
jemand es aufruft. Entwickelt und getestet wurde auf Linux, Zielsystem ist
Windows 11; es wäre gelogen, beides als gleich erprobt auszugeben.

Verändernde Werkzeuge (Prozess beenden, Dienst neu starten,
Umgebungsvariable setzen) tragen SYSTEM oder CRITICAL und laufen damit
durch das bestehende Permission-System.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import sys
import time
from pathlib import Path

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, current_platform, run_process
from ._base import (BOOL, INT, NO_PARAMS, STR, flag, human_bytes, integer, ok,
                    params, table, text)

try:  # pragma: no cover - hängt von der Installation ab
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_NO_PSUTIL = ("Dafür fehlt das Paket 'psutil'. Ohne es kann ich das nicht "
              "messen und rate es nicht. Installation: pip install psutil")

GB = 1024 ** 3
MB = 1024 ** 2

WINDOWS = ("windows",)
LINUX = ("linux",)
UNIX = ("linux", "darwin")


def _psutil():
    if psutil is None:
        raise ToolError(_NO_PSUTIL)
    return psutil


def _proc(pid: int):
    p = _psutil()
    try:
        return p.Process(int(pid))
    except p.NoSuchProcess as exc:
        raise ToolError(f"Es gibt keinen Prozess mit der PID {pid}.") from exc
    except (ValueError, TypeError) as exc:
        raise ToolError(f"Keine gültige PID: {pid}") from exc


def _guard(func, *, what: str):
    """Führt eine psutil-Abfrage aus und macht aus einer verweigerten
    Berechtigung eine verständliche Meldung statt eines Stacktrace."""
    p = _psutil()
    try:
        return func()
    except p.AccessDenied as exc:
        raise ToolError(f"Keine Berechtigung für {what}. Auf Windows hilft oft "
                        "ein Start als Administrator.") from exc


def build(ctx: ToolContext) -> list[Tool]:
    # ══════════════════════════════════════════════════════════════ CPU
    def cpu_usage(interval: float = 0.4, per_core: bool = False) -> ToolResult:
        p = _psutil()
        spanne = max(0.05, min(float(interval or 0.4), 5.0))
        if per_core:
            werte = p.cpu_percent(interval=spanne, percpu=True)
            return ok("system.cpu.usage_per_core",
                      f"{len(werte)} Kerne, Spitze {max(werte):.0f} %",
                      payload=table([[i, f"{v:.1f} %"] for i, v in enumerate(werte)],
                                    ["kern", "auslastung"]),
                      kerne=len(werte), spitze=round(max(werte), 1),
                      mittel=round(sum(werte) / len(werte), 1))
        wert = p.cpu_percent(interval=spanne)
        return ok("system.cpu.usage", f"CPU-Auslastung {wert:.0f} %",
                  auslastung_prozent=round(wert, 1))

    def cpu_cores() -> ToolResult:
        p = _psutil()
        werte = {"physisch": p.cpu_count(logical=False) or 0,
                 "logisch": p.cpu_count(logical=True) or 0}
        return ok("system.cpu.cores",
                  f"{werte['physisch']} physische, {werte['logisch']} logische Kerne",
                  **werte)

    def cpu_frequency() -> ToolResult:
        p = _psutil()
        freq = p.cpu_freq()
        if not freq:
            raise ToolError("Dieses System meldet keine CPU-Taktfrequenz.")
        return ok("system.cpu.frequency", f"{freq.current:.0f} MHz",
                  aktuell_mhz=round(freq.current), min_mhz=round(freq.min or 0),
                  max_mhz=round(freq.max or 0))

    def cpu_times() -> ToolResult:
        p = _psutil()
        t = p.cpu_times_percent(interval=0.4)
        werte = {k: round(v, 1) for k, v in t._asdict().items() if v}
        return ok("system.cpu.times",
                  f"user {werte.get('user', 0)} %, system {werte.get('system', 0)} %",
                  payload=table([[k, f"{v} %"] for k, v in werte.items()],
                                ["art", "anteil"]), **werte)

    def cpu_load() -> ToolResult:
        if not hasattr(os, "getloadavg"):
            raise ToolError("Load Average gibt es auf diesem System nicht "
                            "(das ist eine Unix-Kennzahl).")
        eins, fuenf, fuenfzehn = os.getloadavg()
        kerne = os.cpu_count() or 1
        return ok("system.cpu.load",
                  f"Load {eins:.2f} / {fuenf:.2f} / {fuenfzehn:.2f} bei {kerne} Kernen",
                  load_1=round(eins, 2), load_5=round(fuenf, 2),
                  load_15=round(fuenfzehn, 2), kerne=kerne,
                  ausgelastet=eins >= kerne)

    def cpu_model() -> ToolResult:
        name = platform.processor() or platform.machine()
        # Unter Linux steht der Klartextname nur in /proc/cpuinfo --
        # platform.processor() gibt dort oft nur die Architektur zurück.
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.is_file():
            for line in cpuinfo.read_text(errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    break
        return ok("system.cpu.model", name or "unbekannt", modell=name,
                  architektur=platform.machine())

    # ══════════════════════════════════════════════════════════════ RAM
    def ram_usage() -> ToolResult:
        p = _psutil()
        m = p.virtual_memory()
        return ok("system.ram.usage",
                  f"{m.used / GB:.1f} von {m.total / GB:.1f} GB belegt "
                  f"({m.percent:.0f} %)",
                  gesamt_gb=round(m.total / GB, 1), belegt_gb=round(m.used / GB, 1),
                  frei_gb=round(m.available / GB, 1),
                  auslastung_prozent=round(m.percent, 1))

    def swap_usage() -> ToolResult:
        p = _psutil()
        s = p.swap_memory()
        if not s.total:
            return ok("system.swap.usage", "Kein Auslagerungsspeicher eingerichtet",
                      gesamt_gb=0.0)
        return ok("system.swap.usage",
                  f"{s.used / GB:.1f} von {s.total / GB:.1f} GB Swap belegt",
                  gesamt_gb=round(s.total / GB, 1), belegt_gb=round(s.used / GB, 1),
                  auslastung_prozent=round(s.percent, 1))

    def ram_top(limit: int = 10) -> ToolResult:
        p = _psutil()
        grenze = max(1, min(int(limit or 10), 100))
        rows = []
        for proc in p.process_iter(["pid", "name", "memory_info"]):
            try:
                info = proc.info
                rss = info["memory_info"].rss if info.get("memory_info") else 0
                rows.append((rss, info["pid"], info.get("name") or "?"))
            except (p.NoSuchProcess, p.AccessDenied):
                continue
        rows.sort(reverse=True)
        top = rows[:grenze]
        return ok("system.ram.top", f"Die {len(top)} speicherhungrigsten Prozesse",
                  payload=table([[pid, human_bytes(rss), name] for rss, pid, name in top],
                                ["pid", "speicher", "name"]),
                  prozesse=len(rows),
                  spitzenreiter=top[0][2] if top else None)

    # ═════════════════════════════════════════════════════════ Datenträger
    def disk_usage(path: str = "") -> ToolResult:
        ziel = Path(path).expanduser() if path else Path(Path.home().anchor or "/")
        try:
            u = shutil.disk_usage(ziel)
        except OSError as exc:
            raise ToolError(f"Laufwerk nicht lesbar: {ziel} ({exc})") from exc
        return ok("system.disk.usage", f"{u.free / GB:.1f} GB frei auf {ziel}",
                  pfad=str(ziel), gesamt_gb=round(u.total / GB, 1),
                  belegt_gb=round(u.used / GB, 1), frei_gb=round(u.free / GB, 1),
                  auslastung_prozent=round(u.used / u.total * 100, 1) if u.total else 0)

    def disk_partitions() -> ToolResult:
        p = _psutil()
        rows = []
        for part in p.disk_partitions(all=False):
            try:
                u = shutil.disk_usage(part.mountpoint)
                rows.append([part.device, part.mountpoint, part.fstype,
                             f"{u.total / GB:.0f} GB",
                             f"{u.used / u.total * 100:.0f} %" if u.total else "—"])
            except OSError:
                rows.append([part.device, part.mountpoint, part.fstype, "—", "—"])
        return ok("system.disk.partitions", f"{len(rows)} Datenträger",
                  payload=table(rows, ["geraet", "eingehaengt", "format",
                                       "groesse", "belegt"]),
                  anzahl=len(rows))

    def disk_io() -> ToolResult:
        p = _psutil()
        io = p.disk_io_counters()
        if not io:
            raise ToolError("Dieses System meldet keine Datenträger-Zähler.")
        return ok("system.disk.io",
                  f"{human_bytes(io.read_bytes)} gelesen, "
                  f"{human_bytes(io.write_bytes)} geschrieben (seit dem Start)",
                  gelesen_bytes=io.read_bytes, geschrieben_bytes=io.write_bytes,
                  lesevorgaenge=io.read_count, schreibvorgaenge=io.write_count)

    def disk_smart(device: str = "") -> ToolResult:
        """SMART-Werte über ``smartctl``. Ohne das Programm gibt es keine --
        geschätzt wird hier nichts."""
        if not shutil.which("smartctl"):
            raise ToolError("Dafür fehlt 'smartctl' (Paket smartmontools). "
                            "SMART-Werte lassen sich ohne es nicht auslesen.")
        if not device:
            raise ToolError("Es wurde kein Gerät angegeben, z. B. /dev/sda.")
        res = run_process(["smartctl", "-H", "-A", device], timeout=30)
        if res.returncode and not res.stdout:
            raise ToolError(f"smartctl schlug fehl: {res.stderr.strip()[:200]}")
        gesund = "PASSED" in res.stdout
        return ok("system.disk.smart",
                  f"{device}: {'gesund (PASSED)' if gesund else 'siehe Ausgabe'}",
                  payload=res.stdout[:4000], geraet=device, bestanden=gesund)

    # ══════════════════════════════════════════════════════════════ GPU
    def gpu_info() -> ToolResult:
        """Liest die GPU über das Herstellerwerkzeug. Gibt es keines, ist die
        ehrliche Antwort 'nicht auslesbar' -- keine geschätzte Temperatur."""
        if shutil.which("nvidia-smi"):
            res = run_process([
                "nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,"
                "memory.used,memory.total", "--format=csv,noheader,nounits"], timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                rows = [ [t.strip() for t in line.split(",")]
                         for line in res.stdout.strip().splitlines()]
                erste = rows[0]
                return ok("system.gpu.info",
                          f"{erste[0]}: {erste[1]} °C, {erste[2]} % ausgelastet, "
                          f"{erste[3]}/{erste[4]} MB",
                          payload=table(rows, ["name", "temp_c", "last_%",
                                               "vram_mb", "vram_gesamt_mb"]),
                          quelle="nvidia-smi", gpus=len(rows),
                          temperatur_c=float(erste[1]) if erste[1].replace(".", "").isdigit() else None)
        if shutil.which("rocm-smi"):
            res = run_process(["rocm-smi", "--showtemp", "--showuse",
                               "--showmemuse"], timeout=20)
            if res.returncode == 0 and res.stdout.strip():
                return ok("system.gpu.info", "AMD-GPU über rocm-smi ausgelesen",
                          payload=res.stdout[:4000], quelle="rocm-smi")
        raise ToolError(
            "Die GPU lässt sich auf diesem Rechner nicht auslesen: weder "
            "'nvidia-smi' noch 'rocm-smi' ist vorhanden. Für eine AMD-Karte "
            "unter Windows liefert das Adrenalin-Overlay die Werte; ein "
            "Wert wird hier nicht geschätzt.")

    def gpu_temperature() -> ToolResult:
        result = gpu_info()
        temp = result.evidence.get("temperatur_c")
        if temp is None:
            raise ToolError("Das GPU-Werkzeug hat keine Temperatur gemeldet. "
                            f"Ausgabe: {(result.payload or '')[:200]}")
        return ok("system.gpu.temperature", f"GPU-Temperatur {temp:.0f} °C",
                  temperatur_c=temp, quelle=result.evidence.get("quelle"))

    def sensors_temperatures() -> ToolResult:
        p = _psutil()
        if not hasattr(p, "sensors_temperatures"):
            raise ToolError("Temperatursensoren meldet psutil auf diesem System nicht.")
        werte = p.sensors_temperatures()
        if not werte:
            raise ToolError("Es sind keine Temperatursensoren lesbar. Unter "
                            "Windows liefert psutil hier grundsätzlich nichts.")
        rows = [[name, s.label or "—", f"{s.current:.0f} °C"]
                for name, sensoren in werte.items() for s in sensoren]
        hoechste = max((s.current for sensoren in werte.values() for s in sensoren),
                       default=0)
        return ok("system.sensors.temperatures",
                  f"{len(rows)} Sensoren, höchste {hoechste:.0f} °C",
                  payload=table(rows, ["quelle", "bezeichnung", "temperatur"]),
                  sensoren=len(rows), hoechste_c=round(hoechste, 1))

    def sensors_fans() -> ToolResult:
        p = _psutil()
        if not hasattr(p, "sensors_fans"):
            raise ToolError("Lüfterdrehzahlen meldet psutil auf diesem System nicht.")
        werte = p.sensors_fans()
        if not werte:
            raise ToolError("Es sind keine Lüftersensoren lesbar.")
        rows = [[name, f.label or "—", f"{f.current} U/min"]
                for name, luefter in werte.items() for f in luefter]
        return ok("system.sensors.fans", f"{len(rows)} Lüfter",
                  payload=table(rows, ["quelle", "bezeichnung", "drehzahl"]),
                  luefter=len(rows))

    def battery_status() -> ToolResult:
        p = _psutil()
        akku = p.sensors_battery() if hasattr(p, "sensors_battery") else None
        if akku is None:
            return ok("system.battery", "Kein Akku vorhanden (Standrechner)",
                      akku=False)
        rest = ("wird geladen" if akku.power_plugged
                else f"{akku.secsleft // 60} Minuten Restlaufzeit"
                if akku.secsleft and akku.secsleft > 0 else "Restlaufzeit unbekannt")
        return ok("system.battery", f"{akku.percent:.0f} % — {rest}",
                  akku=True, ladung_prozent=round(akku.percent, 1),
                  am_netz=bool(akku.power_plugged))

    # ════════════════════════════════════════════════════════════ Prozesse
    def process_list(limit: int = 25, sort: str = "cpu",
                     name_contains: str = "") -> ToolResult:
        p = _psutil()
        grenze = max(1, min(int(limit or 25), 300))
        schluessel = (sort or "cpu").lower()
        if schluessel not in ("cpu", "memory", "name", "pid"):
            raise ToolError("sort ist cpu, memory, name oder pid.")
        rows = []
        for proc in p.process_iter(["pid", "name", "cpu_percent", "memory_info",
                                    "username", "status"]):
            try:
                info = proc.info
                name = info.get("name") or "?"
                if name_contains and name_contains.lower() not in name.lower():
                    continue
                rows.append({
                    "pid": info["pid"], "name": name,
                    "cpu": info.get("cpu_percent") or 0.0,
                    "memory": info["memory_info"].rss if info.get("memory_info") else 0,
                    "status": info.get("status") or "?",
                    "user": info.get("username") or "?"})
            except (p.NoSuchProcess, p.AccessDenied):
                continue
        umgekehrt = schluessel in ("cpu", "memory")
        rows.sort(key=lambda r: r[schluessel], reverse=umgekehrt)
        top = rows[:grenze]
        return ok("system.process.list",
                  f"{len(rows)} Prozesse, die {len(top)} nach {schluessel} gelistet",
                  payload=table([[r["pid"], f"{r['cpu']:.1f}",
                                  human_bytes(r["memory"]), r["status"], r["name"]]
                                 for r in top],
                                ["pid", "cpu_%", "speicher", "status", "name"]),
                  gesamt=len(rows), gelistet=len(top))

    def process_find(name: str) -> ToolResult:
        p = _psutil()
        if not name:
            raise ToolError("Es wurde kein Name angegeben.")
        treffer = []
        for proc in p.process_iter(["pid", "name", "exe", "create_time"]):
            try:
                if name.lower() in (proc.info.get("name") or "").lower():
                    treffer.append([proc.info["pid"], proc.info.get("name"),
                                    time.strftime("%H:%M:%S",
                                                  time.localtime(proc.info.get("create_time") or 0))])
            except (p.NoSuchProcess, p.AccessDenied):
                continue
        return ok("system.process.find", f"{len(treffer)} Prozesse passen zu '{name}'",
                  payload=table(treffer, ["pid", "name", "gestartet"]) if treffer
                  else "(nichts gefunden)",
                  treffer=len(treffer), laeuft=bool(treffer))

    def process_info(pid: int) -> ToolResult:
        p = _psutil()
        proc = _proc(pid)
        try:
            with proc.oneshot():
                werte = {
                    "pid": proc.pid, "name": proc.name(), "status": proc.status(),
                    "gestartet": time.strftime("%Y-%m-%d %H:%M:%S",
                                               time.localtime(proc.create_time())),
                    "cpu_prozent": round(proc.cpu_percent(interval=0.2), 1),
                    "speicher": human_bytes(proc.memory_info().rss),
                    "threads": proc.num_threads(),
                }
                try:
                    werte["programm"] = proc.exe()
                    werte["ordner"] = proc.cwd()
                except p.AccessDenied:
                    werte["programm"] = "(keine Berechtigung)"
        except p.NoSuchProcess as exc:
            raise ToolError(f"Der Prozess {pid} ist inzwischen beendet.") from exc
        return ok("system.process.info", f"{werte['name']} (PID {pid}), {werte['status']}",
                  payload="\n".join(f"{k}: {v}" for k, v in werte.items()), **werte)

    def process_children(pid: int) -> ToolResult:
        proc = _proc(pid)
        kinder = [[c.pid, c.name()] for c in proc.children(recursive=True)]
        return ok("system.process.children", f"{len(kinder)} Kindprozesse von PID {pid}",
                  payload=table(kinder, ["pid", "name"]) if kinder else "(keine)",
                  anzahl=len(kinder))

    def process_kill(pid: int, force: bool = False) -> ToolResult:
        p = _psutil()
        proc = _proc(pid)
        name = proc.name()
        (proc.kill if force else proc.terminate)()
        try:
            proc.wait(timeout=5)
        except p.TimeoutExpired:
            raise ToolError(
                f"{name} (PID {pid}) hat auf das Signal nicht reagiert. "
                "Mit force=true lässt er sich hart beenden.") from None
        # Der Beleg wird nachgeprüft, nicht angenommen.
        if p.pid_exists(pid) and _still_same(p, pid, name):
            raise ToolError(f"{name} (PID {pid}) läuft nach dem Beenden weiter.")
        return ok("system.process.kill",
                  f"{name} (PID {pid}) beendet{' (hart)' if force else ''}",
                  pid=int(pid), name=name, hart=bool(force))

    def process_suspend(pid: int) -> ToolResult:
        proc = _proc(pid)
        proc.suspend()
        return ok("system.process.suspend", f"{proc.name()} (PID {pid}) angehalten",
                  pid=int(pid), status=proc.status())

    def process_resume(pid: int) -> ToolResult:
        proc = _proc(pid)
        proc.resume()
        return ok("system.process.resume", f"{proc.name()} (PID {pid}) fortgesetzt",
                  pid=int(pid), status=proc.status())

    def process_priority(pid: int, level: str = "normal") -> ToolResult:
        p = _psutil()
        proc = _proc(pid)
        stufen = {"niedrig": 10, "unter_normal": 5, "normal": 0,
                  "ueber_normal": -5, "hoch": -10}
        if level not in stufen:
            raise ToolError(f"level ist eines von: {', '.join(stufen)}")
        vorher = proc.nice()
        _guard(lambda: proc.nice(stufen[level]), what="das Ändern der Priorität")
        return ok("system.process.priority",
                  f"{proc.name()}: Priorität {level}", pid=int(pid),
                  vorher=str(vorher), nachher=str(proc.nice()))

    def process_open_files(pid: int, limit: int = 30) -> ToolResult:
        proc = _proc(pid)
        dateien = _guard(proc.open_files, what="die offenen Dateien dieses Prozesses")
        rows = [[f.path] for f in dateien[:max(1, int(limit or 30))]]
        return ok("system.process.open_files",
                  f"{len(dateien)} offene Dateien von PID {pid}",
                  payload=table(rows, ["pfad"]) if rows else "(keine)",
                  anzahl=len(dateien))

    def process_tree(limit: int = 60) -> ToolResult:
        p = _psutil()
        knoten: dict[int, list[int]] = {}
        namen: dict[int, str] = {}
        for proc in p.process_iter(["pid", "ppid", "name"]):
            try:
                knoten.setdefault(proc.info["ppid"], []).append(proc.info["pid"])
                namen[proc.info["pid"]] = proc.info.get("name") or "?"
            except (p.NoSuchProcess, p.AccessDenied):
                continue
        lines: list[str] = []

        def zeichne(pid: int, tiefe: int) -> None:
            if len(lines) >= max(1, int(limit or 60)) or tiefe > 6:
                return
            lines.append(f"{'  ' * tiefe}{pid:>7}  {namen.get(pid, '?')}")
            for kind in sorted(knoten.get(pid, []))[:20]:
                zeichne(kind, tiefe + 1)

        for wurzel in sorted(knoten.get(0, [])) or sorted(namen)[:1]:
            zeichne(wurzel, 0)
        return ok("system.process.tree", f"{len(namen)} Prozesse insgesamt",
                  payload="\n".join(lines), prozesse=len(namen))

    # ═══════════════════════════════════════════════════════════ Dienste
    def service_list(limit: int = 40) -> ToolResult:
        system = current_platform()
        if system == "windows":
            p = _psutil()
            rows = []
            for dienst in list(p.win_service_iter())[:max(1, int(limit or 40))]:
                try:
                    info = dienst.as_dict()
                    rows.append([info["name"], info["status"], info["start_type"]])
                except Exception:  # noqa: BLE001 - einzelne Dienste verweigern
                    continue
            return ok("system.service.list", f"{len(rows)} Dienste",
                      payload=table(rows, ["name", "status", "start"]), anzahl=len(rows))
        if not shutil.which("systemctl"):
            raise ToolError("Weder Windows-Dienste noch systemd vorhanden.")
        res = run_process(["systemctl", "list-units", "--type=service",
                           "--no-pager", "--plain", "--no-legend"], timeout=20)
        zeilen = [l for l in res.stdout.splitlines() if l.strip()][:int(limit or 40)]
        rows = [l.split(None, 4)[:4] for l in zeilen]
        return ok("system.service.list", f"{len(rows)} Dienste",
                  payload=table(rows, ["einheit", "geladen", "aktiv", "zustand"]),
                  anzahl=len(rows))

    def service_status(name: str) -> ToolResult:
        if not name:
            raise ToolError("Es wurde kein Dienstname angegeben.")
        if current_platform() == "windows":
            p = _psutil()
            try:
                dienst = p.win_service_get(name)
                info = dienst.as_dict()
            except Exception as exc:  # noqa: BLE001
                raise ToolError(f"Dienst '{name}' nicht gefunden: {exc}") from exc
            return ok("system.service.status", f"{name}: {info['status']}",
                      payload="\n".join(f"{k}: {v}" for k, v in info.items()),
                      name=name, status=info["status"],
                      laeuft=info["status"] == "running")
        if not shutil.which("systemctl"):
            raise ToolError("systemd ist hier nicht vorhanden.")
        res = run_process(["systemctl", "is-active", name], timeout=10)
        zustand = res.stdout.strip() or "unbekannt"
        detail = run_process(["systemctl", "status", name, "--no-pager", "-n", "5"],
                             timeout=10)
        return ok("system.service.status", f"{name}: {zustand}",
                  payload=detail.stdout[:2000], name=name, status=zustand,
                  laeuft=zustand == "active")

    def _systemctl(action: str, name: str) -> ToolResult:
        if not name:
            raise ToolError("Es wurde kein Dienstname angegeben.")
        if not shutil.which("systemctl"):
            raise ToolError("systemd ist hier nicht vorhanden.")
        res = run_process(["systemctl", action, name], timeout=60)
        if res.returncode:
            raise ToolError(f"systemctl {action} {name} schlug fehl: "
                            f"{(res.stderr or res.stdout).strip()[:300]}")
        # Nachprüfen statt annehmen.
        zustand = run_process(["systemctl", "is-active", name], timeout=10).stdout.strip()
        erwartet = "inactive" if action == "stop" else "active"
        if action != "stop" and zustand != "active":
            raise ToolError(f"{name} ist nach '{action}' nicht aktiv, sondern "
                            f"'{zustand}'.")
        return ok(f"system.service.{action}", f"{name}: {action} ausgeführt, "
                  f"Zustand jetzt '{zustand}'", name=name, zustand=zustand,
                  erwartet=erwartet)

    def service_start(name: str) -> ToolResult:
        return _systemctl("start", name)

    def service_stop(name: str) -> ToolResult:
        return _systemctl("stop", name)

    def service_restart(name: str) -> ToolResult:
        return _systemctl("restart", name)

    def service_logs(name: str, lines: int = 40) -> ToolResult:
        if not shutil.which("journalctl"):
            raise ToolError("journalctl ist hier nicht vorhanden.")
        res = run_process(["journalctl", "-u", name, "-n",
                           str(max(1, min(int(lines or 40), 500))),
                           "--no-pager"], timeout=30)
        if res.returncode and not res.stdout:
            raise ToolError(f"journalctl schlug fehl: {res.stderr.strip()[:200]}")
        return ok("system.service.logs", f"Letzte Zeilen von {name}",
                  payload=res.stdout[:8000], dienst=name)

    # ═══════════════════════════════════════════════════════════ Umgebung
    def system_info() -> ToolResult:
        u = platform.uname()
        werte = {"system": f"{u.system} {u.release}", "version": u.version[:60],
                 "rechner": socket.gethostname(), "architektur": u.machine,
                 "python": platform.python_version(),
                 "kerne": os.cpu_count() or 0}
        return ok("system.info", f"{werte['system']} auf {werte['rechner']}",
                  payload="\n".join(f"{k}: {v}" for k, v in werte.items()), **werte)

    def system_uptime() -> ToolResult:
        p = _psutil()
        seit = p.boot_time()
        dauer = time.time() - seit
        tage, rest = divmod(int(dauer), 86400)
        stunden, rest = divmod(rest, 3600)
        return ok("system.uptime",
                  f"Läuft seit {tage} Tagen, {stunden} Stunden, {rest // 60} Minuten",
                  sekunden=int(dauer), tage=tage,
                  gestartet=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seit)))

    def env_list(filter: str = "", limit: int = 60) -> ToolResult:
        """Werte, deren Name nach Geheimnis aussieht, werden ersetzt. Eine
        Umgebungsvariable im Klartext auszugeben ist die einfachste Art, ein
        Token in einen Chatverlauf zu bekommen."""
        rows = []
        for key, value in sorted(os.environ.items()):
            if filter and filter.lower() not in key.lower():
                continue
            if any(h in key.lower() for h in ("token", "secret", "key", "password",
                                              "passwd", "credential", "auth")):
                value = "«verborgen»"
            rows.append([key, value[:80]])
        return ok("system.env.list", f"{len(rows)} Umgebungsvariablen",
                  payload=table(rows[:max(1, int(limit or 60))], ["name", "wert"]),
                  anzahl=len(rows))

    def env_get(name: str) -> ToolResult:
        if not name:
            raise ToolError("Es wurde kein Name angegeben.")
        wert = os.environ.get(name)
        if wert is None:
            return ok("system.env.get", f"{name} ist nicht gesetzt",
                      name=name, gesetzt=False)
        if any(h in name.lower() for h in ("token", "secret", "key", "password")):
            return ok("system.env.get", f"{name} ist gesetzt (Wert verborgen)",
                      name=name, gesetzt=True, verborgen=True, zeichen=len(wert))
        return ok("system.env.get", f"{name} = {wert}", payload=wert,
                  name=name, gesetzt=True)

    def env_set(name: str, value: str) -> ToolResult:
        """Nur für diesen Serverprozess. Dauerhaft setzen geht über die
        Systemeinstellungen -- das hier vorzutäuschen wäre falsch."""
        if not name:
            raise ToolError("Es wurde kein Name angegeben.")
        vorher = os.environ.get(name)
        os.environ[name] = value or ""
        return ok("system.env.set",
                  f"{name} gesetzt (nur für den laufenden Jarvis-Prozess, "
                  "nicht dauerhaft)",
                  name=name, war_gesetzt=vorher is not None)

    def user_info() -> ToolResult:
        p = _psutil()
        werte = {"benutzer": os.environ.get("USER") or os.environ.get("USERNAME") or "?",
                 "heim": str(Path.home()), "arbeitsordner": os.getcwd(),
                 "admin": _is_admin()}
        angemeldet = [[u.name, u.terminal or "—",
                       time.strftime("%Y-%m-%d %H:%M", time.localtime(u.started))]
                      for u in p.users()] if hasattr(p, "users") else []
        return ok("system.user.info", f"Angemeldet als {werte['benutzer']}",
                  payload=table(angemeldet, ["name", "terminal", "seit"])
                  if angemeldet else None, **werte)

    def python_info() -> ToolResult:
        return ok("system.python.info", f"Python {platform.python_version()}",
                  version=platform.python_version(),
                  programm=sys.executable,
                  implementierung=platform.python_implementation(),
                  virtualenv=bool(os.environ.get("VIRTUAL_ENV")))

    def boot_time() -> ToolResult:
        p = _psutil()
        seit = p.boot_time()
        return ok("system.boot_time",
                  time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seit)),
                  unix=round(seit, 1))

    # ═════════════════════════════════════════════════════════════ Windows
    def win_powershell(command: str, timeout: int = 60) -> ToolResult:
        """Der eine Weg zu den Windows-Werkzeugen, die es unter Linux nicht
        gibt. Bewusst **ein** Werkzeug mit einem Befehl als Argument statt
        zwanzig einzelner: jedes davon liefe ohnehin über PowerShell, und so
        sieht das Permission-System genau einen klar benannten Eingriff."""
        if current_platform() != "windows":
            raise ToolError("PowerShell gibt es nur unter Windows.")
        if not command.strip():
            raise ToolError("Es wurde kein Befehl angegeben.")
        res = run_process(["powershell", "-NoProfile", "-NonInteractive",
                           "-Command", command],
                          timeout=max(5, min(int(timeout or 60), 300)))
        if res.returncode:
            raise ToolError(f"PowerShell endete mit Code {res.returncode}: "
                            f"{(res.stderr or res.stdout).strip()[:300]}")
        return ok("system.windows.powershell", f"Befehl ausgeführt (Code 0)",
                  payload=res.stdout[:8000], exit_code=res.returncode)

    def startup_programs() -> ToolResult:
        if current_platform() != "windows":
            raise ToolError("Autostart-Einträge liest dieses Werkzeug nur unter "
                            "Windows. Unter Linux ist 'systemctl list-unit-files "
                            "--state=enabled' das Gegenstück.")
        res = run_process(["powershell", "-NoProfile", "-Command",
                           "Get-CimInstance Win32_StartupCommand | "
                           "Select-Object Name,Command,Location | Format-Table -Auto"],
                          timeout=60)
        if res.returncode:
            raise ToolError(f"Abfrage schlug fehl: {res.stderr.strip()[:200]}")
        return ok("system.startup.list", "Autostart-Einträge gelesen",
                  payload=res.stdout[:6000])

    return [
        # ── CPU ───────────────────────────────────────────────────────────
        Tool("system.cpu.usage", "Aktuelle CPU-Auslastung in Prozent.",
             params(interval=text("Messdauer in Sekunden, Vorgabe 0.4"),
                    per_core=flag("Je Kern statt gesamt")),
             cpu_usage, level=P.READ, requires=("psutil",),
             aliases=("get_cpu_info",),
             tags=("cpu", "auslastung"), returns="Auslastung in Prozent",
             phrases=("wie ausgelastet ist die cpu", "cpu last", "warum laggt mein pc")),
        Tool("system.cpu.cores", "Anzahl physischer und logischer CPU-Kerne.",
             NO_PARAMS, cpu_cores, level=P.READ, requires=("psutil",), tags=("cpu",)),
        Tool("system.cpu.frequency", "Aktueller und maximaler CPU-Takt.",
             NO_PARAMS, cpu_frequency, level=P.READ, requires=("psutil",),
             tags=("cpu", "takt")),
        Tool("system.cpu.times", "Wie sich die CPU-Zeit verteilt (user, system, idle).",
             NO_PARAMS, cpu_times, level=P.READ, requires=("psutil",), tags=("cpu",)),
        Tool("system.cpu.load", "Load Average der letzten 1, 5 und 15 Minuten.",
             NO_PARAMS, cpu_load, level=P.READ, platforms=UNIX, tags=("cpu", "last")),
        Tool("system.cpu.model", "Modellbezeichnung des Prozessors.",
             NO_PARAMS, cpu_model, level=P.READ, tags=("cpu", "hardware"),
             phrases=("welche cpu habe ich", "was für ein prozessor")),

        # ── Speicher ──────────────────────────────────────────────────────
        Tool("system.ram.usage", "Belegter und freier Arbeitsspeicher.",
             NO_PARAMS, ram_usage, level=P.READ, requires=("psutil",),
             aliases=("get_ram_info",), tags=("ram", "speicher"),
             phrases=("wie viel ram ist frei", "arbeitsspeicher voll")),
        Tool("system.swap.usage", "Belegung des Auslagerungsspeichers.",
             NO_PARAMS, swap_usage, level=P.READ, requires=("psutil",),
             tags=("ram", "swap")),
        Tool("system.ram.top", "Welche Prozesse den meisten Speicher belegen.",
             params(limit=INT), ram_top, level=P.READ, requires=("psutil",),
             tags=("ram", "prozess"),
             phrases=("was frisst meinen ram", "speicherhungrige prozesse")),

        # ── Datenträger ───────────────────────────────────────────────────
        Tool("system.disk.usage", "Freier und belegter Platz eines Laufwerks.",
             params(path=text("Pfad oder Laufwerk, leer = Systemlaufwerk")),
             disk_usage, level=P.READ, aliases=("get_disk_info",),
             tags=("disk", "speicherplatz"),
             phrases=("wie viel platz ist frei", "festplatte voll")),
        Tool("system.disk.partitions", "Alle eingehängten Datenträger mit Belegung.",
             NO_PARAMS, disk_partitions, level=P.READ, requires=("psutil",),
             tags=("disk", "hardware")),
        Tool("system.disk.io", "Gelesene und geschriebene Bytes seit dem Systemstart.",
             NO_PARAMS, disk_io, level=P.READ, requires=("psutil",), tags=("disk",)),
        Tool("system.disk.smart", "SMART-Gesundheitswerte eines Datenträgers.",
             params("device", device=text("z. B. /dev/sda oder \\\\.\\PhysicalDrive0")),
             disk_smart, level=P.READ, tags=("disk", "hardware", "smart")),

        # ── GPU und Sensoren ──────────────────────────────────────────────
        Tool("system.gpu.info", "GPU-Name, Temperatur, Auslastung und VRAM.",
             NO_PARAMS, gpu_info, level=P.READ, tags=("gpu", "hardware"),
             returns="Werte aus nvidia-smi oder rocm-smi",
             phrases=("gpu auslastung", "grafikkarte", "vram")),
        Tool("system.gpu.temperature", "Temperatur der Grafikkarte.",
             NO_PARAMS, gpu_temperature, level=P.READ, tags=("gpu", "temperatur"),
             phrases=("wie heiß ist meine grafikkarte", "gpu temperatur",
                      "grafikkarte temperatur")),
        Tool("system.sensors.temperatures", "Alle lesbaren Temperatursensoren.",
             NO_PARAMS, sensors_temperatures, level=P.READ, requires=("psutil",),
             platforms=LINUX, tags=("temperatur", "hardware"),
             phrases=("wie warm ist der rechner", "temperaturen")),
        Tool("system.sensors.fans", "Lüfterdrehzahlen, soweit lesbar.",
             NO_PARAMS, sensors_fans, level=P.READ, requires=("psutil",),
             platforms=LINUX, tags=("luefter", "hardware")),
        Tool("system.battery", "Akkustand und ob das Gerät am Netz hängt.",
             NO_PARAMS, battery_status, level=P.READ, requires=("psutil",),
             tags=("akku", "hardware")),

        # ── Prozesse ──────────────────────────────────────────────────────
        Tool("system.process.list", "Laufende Prozesse, sortierbar nach CPU oder Speicher.",
             params(limit=INT, sort=text("cpu (Vorgabe), memory, name oder pid"),
                    name_contains=text("Nur Prozesse, deren Name das enthält")),
             process_list, level=P.READ, requires=("psutil",),
             aliases=("list_processes",), tags=("prozess",),
             phrases=("welche prozesse laufen", "task manager", "was läuft gerade")),
        Tool("system.process.find", "Sucht laufende Prozesse nach Namen.",
             params("name", name=text("Teil des Prozessnamens")),
             process_find, level=P.READ, requires=("psutil",), tags=("prozess", "suche"),
             phrases=("läuft chrome", "ist der server gestartet")),
        Tool("system.process.info", "Alle Eckdaten zu einem Prozess.",
             params("pid", pid=integer("Die Prozess-ID")),
             process_info, level=P.READ, requires=("psutil",), tags=("prozess",)),
        Tool("system.process.children", "Die Kindprozesse eines Prozesses.",
             params("pid", pid=INT), process_children, level=P.READ,
             requires=("psutil",), tags=("prozess",)),
        Tool("system.process.tree", "Der Prozessbaum des Systems.",
             params(limit=INT), process_tree, level=P.READ, requires=("psutil",),
             tags=("prozess", "uebersicht")),
        Tool("system.process.open_files", "Welche Dateien ein Prozess offen hat.",
             params("pid", pid=INT, limit=INT), process_open_files, level=P.READ,
             requires=("psutil",), tags=("prozess", "datei"),
             phrases=("wer blockiert die datei",)),
        Tool("system.process.kill", "Beendet einen Prozess und prüft nach, ob er weg ist.",
             params("pid", pid=INT, force=flag("Hart beenden statt freundlich fragen")),
             process_kill, level=P.CRITICAL, requires=("psutil",),
             tags=("prozess", "beenden"),
             phrases=("beende den prozess", "kill", "programm abschießen")),
        Tool("system.process.suspend", "Hält einen Prozess an (er läuft nicht weiter).",
             params("pid", pid=INT), process_suspend, level=P.SYSTEM,
             requires=("psutil",), tags=("prozess",)),
        Tool("system.process.resume", "Setzt einen angehaltenen Prozess fort.",
             params("pid", pid=INT), process_resume, level=P.SYSTEM,
             requires=("psutil",), tags=("prozess",)),
        Tool("system.process.priority", "Ändert die Priorität eines Prozesses.",
             params("pid", pid=INT,
                    level=text("niedrig, unter_normal, normal, ueber_normal, hoch")),
             process_priority, level=P.SYSTEM, requires=("psutil",),
             tags=("prozess", "prioritaet")),

        # ── Dienste ───────────────────────────────────────────────────────
        Tool("system.service.list", "Die Systemdienste mit ihrem Zustand.",
             params(limit=INT), service_list, level=P.READ, tags=("dienst",),
             phrases=("welche dienste laufen", "services")),
        Tool("system.service.status", "Zustand eines einzelnen Dienstes.",
             params("name", name=text("Name des Dienstes")),
             service_status, level=P.READ, tags=("dienst",)),
        Tool("system.service.start", "Startet einen Dienst und prüft nach.",
             params("name", name=STR), service_start, level=P.SYSTEM,
             platforms=LINUX, requires=("systemctl",), tags=("dienst",)),
        Tool("system.service.stop", "Stoppt einen Dienst.",
             params("name", name=STR), service_stop, level=P.SYSTEM,
             platforms=LINUX, requires=("systemctl",), tags=("dienst",)),
        Tool("system.service.restart", "Startet einen Dienst neu und prüft nach.",
             params("name", name=STR), service_restart, level=P.SYSTEM,
             platforms=LINUX, requires=("systemctl",), tags=("dienst",),
             phrases=("starte den dienst neu",)),
        Tool("system.service.logs", "Die letzten Logzeilen eines Dienstes.",
             params("name", name=STR, lines=INT), service_logs, level=P.READ,
             platforms=LINUX, tags=("dienst", "log"),
             phrases=("zeig mir die logs", "warum ist der dienst abgestürzt")),

        # ── Umgebung ──────────────────────────────────────────────────────
        Tool("system.info", "Betriebssystem, Rechnername, Architektur, Kernzahl.",
             NO_PARAMS, system_info, level=P.READ, aliases=("get_system_info",),
             tags=("system", "info"),
             phrases=("was für ein system", "systeminfo")),
        Tool("system.uptime", "Wie lange der Rechner schon läuft.",
             NO_PARAMS, system_uptime, level=P.READ, requires=("psutil",),
             tags=("system",), phrases=("wie lange läuft der rechner", "uptime")),
        Tool("system.boot_time", "Wann der Rechner gestartet wurde.",
             NO_PARAMS, boot_time, level=P.READ, requires=("psutil",), tags=("system",)),
        Tool("system.env.list",
             "Die Umgebungsvariablen. Geheimnisverdächtige Werte werden verborgen.",
             params(filter=text("Nur Namen, die das enthalten"), limit=INT),
             env_list, level=P.READ, tags=("umgebung",)),
        Tool("system.env.get", "Eine einzelne Umgebungsvariable.",
             params("name", name=STR), env_get, level=P.READ, tags=("umgebung",)),
        Tool("system.env.set",
             "Setzt eine Umgebungsvariable — nur für den laufenden Jarvis-Prozess.",
             params("name", "value", name=STR, value=STR), env_set, level=P.SYSTEM,
             tags=("umgebung",)),
        Tool("system.user.info", "Angemeldeter Benutzer, Heimverzeichnis, Rechte.",
             NO_PARAMS, user_info, level=P.READ, tags=("benutzer",)),
        Tool("system.python.info", "Python-Version und Interpreterpfad.",
             NO_PARAMS, python_info, level=P.READ, tags=("python", "umgebung")),

        # ── Windows ───────────────────────────────────────────────────────
        Tool("system.windows.powershell",
             "Führt einen PowerShell-Befehl aus (nur Windows).",
             params("command", command=text("Der PowerShell-Befehl"), timeout=INT),
             win_powershell, level=P.CRITICAL, platforms=WINDOWS,
             requires=("powershell",), tags=("windows", "shell"),
             returns="Die Standardausgabe des Befehls"),
        Tool("system.startup.list", "Programme, die beim Anmelden starten (Windows).",
             NO_PARAMS, startup_programs, level=P.READ, platforms=WINDOWS,
             requires=("powershell",), tags=("windows", "autostart"),
             phrases=("was startet automatisch", "autostart")),
    ]


def _still_same(p, pid: int, name: str) -> bool:
    """Eine PID kann nach dem Beenden sofort neu vergeben werden. Deshalb
    zählt nur, ob dort noch **derselbe** Prozess läuft."""
    try:
        return p.Process(pid).name() == name
    except Exception:  # noqa: BLE001 - weg ist weg
        return False


def _is_admin() -> bool:
    if current_platform() == "windows":  # pragma: no cover - nur unter Windows
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False
