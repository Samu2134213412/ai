"""Tool Pack: Docker.

Kleine, benannte Operatoren statt eines ``docker(args)``-Durchreichers: jedes
Werkzeug baut eine feste ``docker``-Kommandozeile, nur Namen/Pfade/Zahlen
kommen vom Aufrufer. ``docker.run``/``docker.exec`` bauen ihre Argumentliste
ebenfalls aus festen Teilen zusammen -- kein roher, vom Modell diktierter
Flag-String, der z. B. ``--privileged`` einschleusen könnte.

Sicherheitsstufen: Anzeigen ist READ, ein Container starten/stoppen/bauen ist
SYSTEM (verändert laufende Prozesse, kann Netzwerk-/Volume-Zugriff haben),
endgültig entfernende Aktionen (Container/Volume löschen, prune) sind
CRITICAL -- mit echtem Probelauf bei ``docker.prune``.
"""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Any

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, run_process
from ._base import LIST, flag, integer, ok, params, planned, table, text

MAX_OUTPUT = 20_000
DOCKER_TIMEOUT = 60.0


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


def _kein_flag(value: str, label: str) -> str:
    wert = (value or "").strip()
    if not wert:
        raise ToolError(f"{label} fehlt.")
    if wert.startswith("-"):
        raise ToolError(f"{label} darf nicht mit '-' beginnen: {wert!r}")
    return wert


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def docker(args: list[str], timeout: float = DOCKER_TIMEOUT):
        return run_process(["docker", *args], timeout=timeout)

    def lauf(args: list[str], tool: str, summary: str, timeout: float = DOCKER_TIMEOUT,
             **evidence: Any) -> ToolResult:
        res = docker(args, timeout)
        out, err = (res.stdout or "").strip(), (res.stderr or "").strip()
        if res.returncode != 0:
            raise ToolError(_clip(err or out or
                                  f"'docker {' '.join(args)}' fehlgeschlagen "
                                  f"(Exit {res.returncode})"))
        return ok(tool, summary, payload=_clip(out or err) or None, **evidence)

    # ══════════════════════════════════════════════════════════ Lesend
    def docker_ps(all: bool = False, limit: int = 50) -> ToolResult:
        args = ["ps", "--format",
               "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]
        if all:
            args.append("-a")
        res = docker(args)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker ps fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        zeilen = zeilen[:max(1, int(limit or 50))]
        rows = [z.split("\t") for z in zeilen]
        return ok("docker.ps", f"{len(rows)} Container",
                  payload=table(rows, headers=["ID", "Name", "Image", "Status", "Ports"]),
                  anzahl=len(rows))

    def docker_images(limit: int = 50) -> ToolResult:
        res = docker(["images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker images fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()][:max(1, int(limit or 50))]
        rows = [z.split("\t") for z in zeilen]
        return ok("docker.images", f"{len(rows)} Image(s)",
                  payload=table(rows, headers=["Repository", "Tag", "ID", "Größe"]),
                  anzahl=len(rows))

    def docker_inspect(name: str) -> ToolResult:
        n = _kein_flag(name, "name")
        res = docker(["inspect", n])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or f"'{n}' nicht gefunden").strip()))
        try:
            daten = jsonlib.loads(res.stdout or "[]")
        except ValueError:
            daten = None
        kurz = daten[0] if isinstance(daten, list) and daten else {}
        return ok("docker.inspect", f"Details zu {n}", payload=_clip(res.stdout.strip()),
                  status=(kurz.get("State") or {}).get("Status", ""))

    def docker_logs(name: str, lines: int = 100) -> ToolResult:
        n = _kein_flag(name, "name")
        res = docker(["logs", "--tail", str(max(1, min(int(lines or 100), 2000))), n])
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Logs von '{n}' nicht abrufbar"))
        return ok("docker.logs", f"Letzte Zeilen von {n}", payload=_clip(out) or "(leer)")

    def docker_stats(limit: int = 20) -> ToolResult:
        res = docker(["stats", "--no-stream", "--format",
                      "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"], timeout=15)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker stats fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()][:max(1, int(limit or 20))]
        rows = [z.split("\t") for z in zeilen]
        return ok("docker.stats", f"{len(rows)} Container",
                  payload=table(rows, headers=["Name", "CPU", "Speicher", "Netzwerk"]),
                  anzahl=len(rows))

    def docker_volumes_list() -> ToolResult:
        res = docker(["volume", "ls", "--format", "{{.Name}}\t{{.Driver}}"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker volume ls fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        rows = [z.split("\t") for z in zeilen]
        return ok("docker.volumes.list", f"{len(rows)} Volume(s)",
                  payload=table(rows, headers=["Name", "Treiber"]), anzahl=len(rows))

    def docker_networks_list() -> ToolResult:
        res = docker(["network", "ls", "--format", "{{.Name}}\t{{.Driver}}\t{{.Scope}}"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker network ls fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        rows = [z.split("\t") for z in zeilen]
        return ok("docker.networks.list", f"{len(rows)} Netzwerk(e)",
                  payload=table(rows, headers=["Name", "Treiber", "Bereich"]), anzahl=len(rows))

    def docker_compose_ps(path: str) -> ToolResult:
        projekt = ws.resolve(path)
        res = run_process(["docker", "compose", "ps", "--format", "json"], timeout=20,
                          cwd=str(projekt))
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "docker compose ps fehlgeschlagen").strip()))
        return ok("docker.compose.ps", f"Status für {projekt.name}",
                  payload=_clip((res.stdout or "").strip()) or "(keine Dienste)")

    # ══════════════════════════════════════════════════════════ SYSTEM
    def docker_start(name: str) -> ToolResult:
        n = _kein_flag(name, "name")
        return lauf(["start", n], "docker.start", f"Gestartet: {n}", container=n)

    def docker_stop(name: str, timeout_sekunden: int = 10) -> ToolResult:
        n = _kein_flag(name, "name")
        return lauf(["stop", "-t", str(max(0, int(timeout_sekunden or 10))), n],
                   "docker.stop", f"Gestoppt: {n}", container=n)

    def docker_restart(name: str) -> ToolResult:
        n = _kein_flag(name, "name")
        return lauf(["restart", n], "docker.restart", f"Neu gestartet: {n}", container=n)

    def docker_run(image: str, name: str = "", ports: list[str] | None = None,
                   volumes: list[str] | None = None, env: dict[str, str] | None = None,
                   command: list[str] | None = None, detach: bool = True) -> ToolResult:
        img = _kein_flag(image, "image")
        args = ["run"]
        args.append("-d" if detach else "-it")
        if name:
            args += ["--name", _kein_flag(name, "name")]
        for p in ports or []:
            args += ["-p", str(p)]
        for v in volumes or []:
            args += ["-v", str(ws.resolve(v.split(":", 1)[0])) +
                    (":" + v.split(":", 1)[1] if ":" in v else "")]
        for k, v in (env or {}).items():
            args += ["-e", f"{_kein_flag(k, 'env-Name')}={v}"]
        args.append(img)
        if command:
            args += list(command)
        return lauf(args, "docker.run", f"Container aus {img} gestartet"
                    + (f" als {name}" if name else ""), timeout=120.0, image=img)

    def docker_exec(name: str, command: list[str]) -> ToolResult:
        n = _kein_flag(name, "name")
        if not command:
            raise ToolError("Es wurde kein Befehl angegeben.")
        args = ["exec", n, *command]
        return lauf(args, "docker.exec", f"Befehl in {n} ausgeführt", container=n)

    def docker_build(path: str, tag: str, dockerfile: str = "Dockerfile") -> ToolResult:
        projekt = ws.resolve(path)
        t = _kein_flag(tag, "tag")
        args = ["build", "-t", t, "-f", dockerfile, "."]
        res = run_process(["docker", *args], timeout=600, cwd=str(projekt))
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Build von {t} fehlgeschlagen"))
        return ok("docker.build", f"Image gebaut: {t}", payload=_clip(out), tag=t)

    def docker_compose_up(path: str, timeout: int = 0) -> ToolResult:
        projekt = ws.resolve(path)
        t = max(20.0, min(float(timeout or 120), 900.0))
        res = run_process(["docker", "compose", "up", "-d"], timeout=t, cwd=str(projekt))
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or "docker compose up fehlgeschlagen"))
        return ok("docker.compose.up", f"Dienste gestartet in {projekt.name}", payload=_clip(out))

    def docker_compose_down(path: str) -> ToolResult:
        projekt = ws.resolve(path)
        res = run_process(["docker", "compose", "down"], timeout=120, cwd=str(projekt))
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or "docker compose down fehlgeschlagen"))
        return ok("docker.compose.down", f"Dienste gestoppt in {projekt.name}", payload=_clip(out))

    # ══════════════════════════════════════════════════════════ CRITICAL
    def docker_remove(name: str, force: bool = False) -> ToolResult:
        n = _kein_flag(name, "name")
        args = ["rm"] + (["-f"] if force else []) + [n]
        return lauf(args, "docker.remove", f"Container entfernt: {n}", container=n)

    def docker_volume_remove(name: str) -> ToolResult:
        n = _kein_flag(name, "name")
        return lauf(["volume", "rm", n], "docker.volume.remove", f"Volume entfernt: {n}",
                   volume=n)

    def docker_prune(dry_run: bool = False) -> ToolResult:
        if dry_run:
            vorschau = docker(["system", "df", "-v"], timeout=20)
            return planned("docker.prune", "Würde gestoppte Container, ungenutzte "
                          "Netzwerke/Images/Build-Cache entfernen",
                          payload=_clip((vorschau.stdout or "").strip()) or None)
        res = docker(["system", "prune", "-f"], timeout=120)
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or "docker system prune fehlgeschlagen"))
        return ok("docker.prune", "Aufgeräumt", payload=_clip(out) or None)

    _n = text("Container-Name oder -ID")

    return [
        # ── Lesend ──────────────────────────────────────────────────────
        Tool("docker.ps", "Laufende (oder alle) Container.",
             params(all=flag("Auch gestoppte Container zeigen"), limit=integer("Vorgabe 50")),
             docker_ps, level=P.READ, requires=("docker",), tags=("docker",),
             phrases=("welche container laufen", "docker ps")),
        Tool("docker.images", "Lokal vorhandene Images.",
             params(limit=integer("Vorgabe 50")), docker_images, level=P.READ,
             requires=("docker",), tags=("docker", "image")),
        Tool("docker.inspect", "Alle Details zu einem Container oder Image als JSON.",
             params("name", name=_n), docker_inspect, level=P.READ, requires=("docker",),
             tags=("docker",)),
        Tool("docker.logs", "Die letzten Log-Zeilen eines Containers.",
             params("name", name=_n, lines=integer("Vorgabe 100")), docker_logs,
             level=P.READ, requires=("docker",), tags=("docker", "log")),
        Tool("docker.stats", "Aktuelle CPU-/Speicher-/Netzwerknutzung laufender Container.",
             params(limit=integer("Vorgabe 20")), docker_stats, level=P.READ,
             requires=("docker",), tags=("docker", "performance")),
        Tool("docker.volumes.list", "Vorhandene Docker-Volumes.",
             params(), docker_volumes_list, level=P.READ, requires=("docker",),
             tags=("docker", "volume")),
        Tool("docker.networks.list", "Vorhandene Docker-Netzwerke.",
             params(), docker_networks_list, level=P.READ, requires=("docker",),
             tags=("docker", "netzwerk")),
        Tool("docker.compose.ps", "Status der Dienste eines Compose-Projekts.",
             params("path", path=text("Ordner mit docker-compose.yml")), docker_compose_ps,
             level=P.READ, requires=("docker",), tags=("docker", "compose")),

        # ── SYSTEM ──────────────────────────────────────────────────────
        Tool("docker.start", "Startet einen gestoppten Container.",
             params("name", name=_n), docker_start, level=P.SYSTEM, requires=("docker",),
             tags=("docker",)),
        Tool("docker.stop", "Stoppt einen laufenden Container.",
             params("name", name=_n, timeout_sekunden=integer("Vorgabe 10")), docker_stop,
             level=P.SYSTEM, requires=("docker",), tags=("docker",)),
        Tool("docker.restart", "Startet einen Container neu.",
             params("name", name=_n), docker_restart, level=P.SYSTEM, requires=("docker",),
             tags=("docker",)),
        Tool("docker.run", "Startet einen neuen Container aus einem Image.",
             params("image", image=text("Image-Name, z. B. nginx:latest"),
                    name=text("Container-Name, optional"),
                    ports=LIST, volumes=LIST,
                    env={"type": "object", "description": "{VARIABLE: wert, ...}"},
                    command={"type": "array", "items": {"type": "string"},
                            "description": "Befehl im Container, optional"},
                    detach=flag("Im Hintergrund laufen lassen, Vorgabe true")),
             docker_run, level=P.SYSTEM, requires=("docker",), tags=("docker",),
             timeout=120.0, phrases=("starte einen container", "docker run")),
        Tool("docker.exec", "Führt einen Befehl in einem laufenden Container aus.",
             params("name", "command", name=_n,
                    command={"type": "array", "items": {"type": "string"},
                            "description": "Programm mit Argumenten"}),
             docker_exec, level=P.SYSTEM, requires=("docker",), tags=("docker",)),
        Tool("docker.build", "Baut ein Image aus einem Dockerfile.",
             params("path", "tag", path=text("Ordner mit dem Dockerfile"),
                    tag=text("Image-Name:Tag"),
                    dockerfile=text("Dateiname, Vorgabe Dockerfile")),
             docker_build, level=P.SYSTEM, requires=("docker",), tags=("docker", "image"),
             timeout=600.0),
        Tool("docker.compose.up", "Startet alle Dienste eines Compose-Projekts.",
             params("path", path=text("Ordner mit docker-compose.yml"),
                    timeout=integer("Sekunden, Vorgabe 120")), docker_compose_up,
             level=P.SYSTEM, requires=("docker",), tags=("docker", "compose"), timeout=120.0),
        Tool("docker.compose.down", "Stoppt und entfernt alle Dienste eines Compose-Projekts.",
             params("path", path=text("Ordner mit docker-compose.yml")), docker_compose_down,
             level=P.SYSTEM, requires=("docker",), tags=("docker", "compose")),

        # ── CRITICAL ────────────────────────────────────────────────────
        Tool("docker.remove", "Entfernt einen Container endgültig.",
             params("name", name=_n, force=flag("Auch einen laufenden Container entfernen")),
             docker_remove, level=P.CRITICAL, requires=("docker",), tags=("docker", "loeschen")),
        Tool("docker.volume.remove", "Löscht ein Volume samt seiner Daten.",
             params("name", name=text("Volume-Name")), docker_volume_remove,
             level=P.CRITICAL, requires=("docker",), tags=("docker", "volume", "loeschen")),
        Tool("docker.prune", "Entfernt gestoppte Container, ungenutzte Netzwerke/Images/"
             "Build-Cache.",
             params(dry_run=flag("Nur zeigen, was betroffen wäre")), docker_prune,
             level=P.CRITICAL, requires=("docker",), tags=("docker", "loeschen"), dry_run=True),
    ]
