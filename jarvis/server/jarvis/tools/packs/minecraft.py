"""Tool Pack: Minecraft-Server.

Aufgabenstellung Punkt 20: **keine destruktiven Weltänderungen ohne
ausdrückliche Freigabe.** Ein RCON-Kommando kann alles Mögliche anrichten
(``/fill`` löscht ganze Regionen, ``/op`` vergibt Admin-Rechte) -- und lässt
sich als Text nicht sicher in "harmlos" und "gefährlich" einteilen. Deshalb:
* die häufigen, klar umrissenen Aktionen (Spieler kicken/bannen, Whitelist,
  Broadcast, Op/Deop) stehen als eigene, benannte Werkzeuge mit dem jeweils
  passenden Risiko;
* das rohe ``minecraft.command`` bleibt als Fluchtweg erhalten, aber auf
  CRITICAL -- es verlangt damit **immer** eine ausdrückliche Bestätigung,
  unabhängig davon, was der Text enthält.

``minecraft.stop`` geht ausdrücklich über RCON ("stop"), nicht per
Prozess-Kill -- ein SIGKILL mitten im Weltspeichern ist genau die Art von
Datenverlust, vor der Punkt 20 schützen soll.

Der RCON-Client unten ist eigener, kleiner Code (Source-RCON-Protokoll,
das Minecraft verwendet) statt einer weiteren Abhängigkeit -- das Protokoll
ist ein paar Dutzend Zeilen, ein Paket dafür wäre mehr Fläche als Nutzen.
"""

from __future__ import annotations

import re
import socket
import struct
import time
from pathlib import Path

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import integer, ok, params, table, text

MAX_OUTPUT = 8_000
_IDENT = re.compile(r"^[A-Za-z0-9_]{1,32}$")  # Minecraft-Spielernamen


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


# ══════════════════════════════════════════════════════════ RCON (Source-Protokoll)
_AUTH = 3
_AUTH_RESPONSE = 2
_EXEC = 2
_RESPONSE_VALUE = 0


class RconError(ToolError):
    """RCON-spezifischer Fehlschlag -- bleibt ein ToolError, damit der
    normale Fehlerpfad greift, ohne dass Aufrufer zwei Ausnahmen kennen müssen."""


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    puffer = b""
    while len(puffer) < n:
        stueck = sock.recv(n - len(puffer))
        if not stueck:
            raise RconError("RCON-Verbindung wurde während des Lesens geschlossen.")
        puffer += stueck
    return puffer


def _rcon_pack(request_id: int, packet_type: int, payload: str) -> bytes:
    body = payload.encode("utf-8") + b"\x00\x00"
    rumpf = struct.pack("<ii", request_id, packet_type) + body
    return struct.pack("<i", len(rumpf)) + rumpf


def _rcon_read(sock: socket.socket) -> tuple[int, int, str]:
    (laenge,) = struct.unpack("<i", _recv_exact(sock, 4))
    if not 10 <= laenge <= 1 << 20:
        raise RconError(f"Unplausible RCON-Paketlänge: {laenge}")
    rumpf = _recv_exact(sock, laenge)
    request_id, packet_type = struct.unpack("<ii", rumpf[:8])
    text_wert = rumpf[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, text_wert


def rcon_command(host: str, port: int, password: str, command: str,
                 timeout: float = 5.0) -> str:
    """Baut eine eigene Verbindung auf, führt genau einen Befehl aus, trennt
    wieder -- RCON-Sitzungen über mehrere Werkzeugaufrufe offenzuhalten wäre
    zusätzlicher Zustand für einen Nutzen, den ein einzelner Admin-Befehl
    nicht braucht."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_rcon_pack(1, _AUTH, password))
            # Minecraft schickt vor der eigentlichen AUTH-Antwort noch ein
            # leeres RESPONSE_VALUE-Paket -- eine bekannte Eigenheit seiner
            # RCON-Umsetzung, kein Fehler im Protokoll.
            req_id, ptype, _ = _rcon_read(sock)
            if ptype == _RESPONSE_VALUE:
                req_id, ptype, _ = _rcon_read(sock)
            if req_id == -1:
                raise RconError("RCON-Authentifizierung fehlgeschlagen (Passwort falsch?).")
            sock.sendall(_rcon_pack(2, _EXEC, command))
            _, _, antwort = _rcon_read(sock)
            return antwort
    except (OSError, socket.timeout) as exc:
        raise RconError(f"RCON nicht erreichbar unter {host}:{port} ({exc}).") from exc
    except struct.error as exc:
        raise RconError(f"Unlesbare RCON-Antwort: {exc}") from exc


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def server_ordner(raw: str) -> Path:
        pfad = ws.resolve(raw)
        if not pfad.is_dir():
            raise ToolError(f"Ordner existiert nicht: {pfad}")
        return pfad

    def properties_lesen(ordner: Path) -> dict[str, str]:
        datei = ordner / "server.properties"
        if not datei.is_file():
            raise ToolError(f"Keine server.properties in {ordner}")
        werte: dict[str, str] = {}
        for zeile in datei.read_text(encoding="utf-8", errors="replace").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            schluessel, _, wert = zeile.partition("=")
            werte[schluessel.strip()] = wert.strip()
        return werte

    def rcon_von(server_dir: str, password: str = "", port: int = 0):
        ordner = server_ordner(server_dir)
        eig = properties_lesen(ordner)
        if eig.get("enable-rcon", "false").lower() != "true" and not (password and port):
            raise ToolError("RCON ist in server.properties nicht aktiviert "
                            "(enable-rcon=true setzen) -- oder host/port/password "
                            "hier ausdrücklich angeben.")
        rcon_port = int(port) if port else int(eig.get("rcon.port", 25575) or 25575)
        rcon_pw = password or eig.get("rcon.password", "")
        if not rcon_pw:
            raise ToolError("Kein RCON-Passwort gefunden (rcon.password in "
                            "server.properties leer) -- password hier angeben.")
        return "127.0.0.1", rcon_port, rcon_pw

    def spielername(name: str) -> str:
        n = (name or "").strip()
        if not _IDENT.match(n):
            raise ToolError(f"Kein gültiger Minecraft-Spielername: {name!r}")
        return n

    # ══════════════════════════════════════════════════════════ Lesend
    def mc_status(server_dir: str) -> ToolResult:
        ordner = server_ordner(server_dir)
        pid_datei = ordner / ".jarvis-minecraft.pid"
        laeuft_laut_pid = False
        if pid_datei.is_file():
            try:
                pid = int(pid_datei.read_text().strip())
                import os
                os.kill(pid, 0)
                laeuft_laut_pid = True
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                laeuft_laut_pid = False
        rcon_ok = False
        try:
            host, port, pw = rcon_von(server_dir)
            rcon_command(host, port, pw, "list", timeout=3)
            rcon_ok = True
        except ToolError:
            rcon_ok = False
        if rcon_ok:
            zustand = "läuft (RCON antwortet)"
        elif laeuft_laut_pid:
            zustand = "Prozess läuft, RCON antwortet nicht (noch startend oder deaktiviert)"
        else:
            zustand = "nicht erreichbar"
        return ok("minecraft.status", zustand, laeuft=rcon_ok or laeuft_laut_pid,
                  rcon_erreichbar=rcon_ok)

    def mc_players_list(server_dir: str, password: str = "", port: int = 0) -> ToolResult:
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, "list")
        return ok("minecraft.players.list", antwort.strip() or "(keine Antwort)",
                  payload=antwort)

    def mc_performance(server_dir: str, password: str = "", port: int = 0) -> ToolResult:
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, "tps")
        return ok("minecraft.performance", antwort.strip() or
                  "(keine Antwort -- 'tps' kennt nicht jede Server-Software)",
                  payload=antwort)

    def mc_server_properties_read(server_dir: str) -> ToolResult:
        ordner = server_ordner(server_dir)
        werte = properties_lesen(ordner)
        zeilen = "\n".join(f"{k}={v}" for k, v in sorted(werte.items()))
        return ok("minecraft.server.properties.read", f"{len(werte)} Einstellung(en)",
                  payload=zeilen, anzahl=len(werte))

    def mc_logs_tail(server_dir: str, lines: int = 40) -> ToolResult:
        ordner = server_ordner(server_dir)
        datei = ordner / "logs" / "latest.log"
        if not datei.is_file():
            raise ToolError(f"Kein Log gefunden: {datei}")
        zeilen = datei.read_text(encoding="utf-8", errors="replace").splitlines()
        n = max(1, min(int(lines or 40), 1000))
        auszug = zeilen[-n:]
        return ok("minecraft.logs.tail", f"Letzte {len(auszug)} Zeile(n)",
                  payload=_clip("\n".join(auszug)), zeilen=len(auszug))

    _MUSTER = (
        (re.compile(r"OutOfMemoryError"), "Dem Server ist der Arbeitsspeicher ausgegangen "
         "-- mehr RAM zuteilen (-Xmx) oder Server/Mods verkleinern."),
        (re.compile(r"Address already in use"), "Der Server-Port ist schon belegt -- läuft "
         "eventuell bereits eine zweite Instanz?"),
        (re.compile(r"Watchdog"), "Der Watchdog hat den Server wegen Überlastung beendet "
         "(ein Tick brauchte zu lange) -- oft ein Zeichen für ein hängendes Plugin/Mod."),
        (re.compile(r"Exception in thread"), "Eine unbehandelte Ausnahme -- Einzelheiten "
         "stehen in der folgenden Zeile im Log."),
        (re.compile(r"Corrupt"), "Ein beschädigter Weltbestandteil wurde erkannt -- vor dem "
         "nächsten Start ein Backup einspielen, statt weiterzumachen."),
    )

    def mc_crash_analyze(server_dir: str) -> ToolResult:
        ordner = server_ordner(server_dir)
        crash_ordner = ordner / "crash-reports"
        berichte = sorted(crash_ordner.glob("*.txt")) if crash_ordner.is_dir() else []
        log = ordner / "logs" / "latest.log"
        fundstellen: list[str] = []
        quelltext = ""
        if berichte:
            quelltext = berichte[-1].read_text(encoding="utf-8", errors="replace")
        elif log.is_file():
            quelltext = log.read_text(encoding="utf-8", errors="replace")[-20_000:]
        for muster, erklaerung in _MUSTER:
            if muster.search(quelltext):
                fundstellen.append(f"{muster.pattern}: {erklaerung}")
        if not quelltext:
            return ok("minecraft.crash.analyze", "Weder Crash-Report noch Log gefunden",
                      payload="(nichts zu analysieren)")
        summary = (f"{len(fundstellen)} bekannte(s) Muster erkannt" if fundstellen
                  else "Kein bekanntes Absturzmuster erkannt -- Log manuell prüfen")
        return ok("minecraft.crash.analyze", summary,
                  payload="\n".join(fundstellen) or "(kein Treffer)",
                  quelle=str(berichte[-1]) if berichte else str(log),
                  funde=len(fundstellen))

    def mc_backup_list(server_dir: str, backup_dir: str = "") -> ToolResult:
        ordner = ws.resolve(backup_dir) if backup_dir else server_ordner(server_dir) / "backups"
        if not ordner.is_dir():
            return ok("minecraft.backup.list", "Kein Backup-Ordner vorhanden", payload="(keine)")
        dateien = sorted(ordner.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        rows = [[d.name, f"{d.stat().st_size / 1_048_576:.1f} MB"] for d in dateien]
        return ok("minecraft.backup.list", f"{len(dateien)} Backup(s)",
                  payload=table(rows, headers=["Datei", "Größe"]), anzahl=len(dateien))

    # ══════════════════════════════════════════════════════════ WRITE
    def mc_server_properties_set(server_dir: str, key: str, value: str) -> ToolResult:
        ordner = server_ordner(server_dir)
        datei = ordner / "server.properties"
        werte = properties_lesen(ordner)
        k = (key or "").strip()
        if not k:
            raise ToolError("Kein Schlüssel angegeben.")
        werte[k] = (value or "").strip()
        zeilen = [f"{sk}={sv}" for sk, sv in sorted(werte.items())]
        datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        return ok("minecraft.server.properties.set", f"{k} = {werte[k]} "
                  "(wirkt erst nach einem Neustart)", schluessel=k, wert=werte[k])

    def mc_whitelist_add(server_dir: str, name: str, password: str = "",
                         port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, f"whitelist add {spieler}")
        return ok("minecraft.whitelist.add", antwort.strip() or f"{spieler} zur Whitelist "
                  "hinzugefügt", spieler=spieler, payload=antwort)

    def mc_whitelist_remove(server_dir: str, name: str, password: str = "",
                            port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, f"whitelist remove {spieler}")
        return ok("minecraft.whitelist.remove", antwort.strip() or f"{spieler} von der "
                  "Whitelist entfernt", spieler=spieler, payload=antwort)

    def mc_broadcast(server_dir: str, message: str, password: str = "",
                     port: int = 0) -> ToolResult:
        nachricht = (message or "").strip()
        if not nachricht:
            raise ToolError("Keine Nachricht angegeben.")
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, f"say {nachricht}")
        return ok("minecraft.broadcast", f"Gesendet: {nachricht}", payload=antwort)

    def mc_player_kick(server_dir: str, name: str, reason: str = "", password: str = "",
                       port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        befehl = f"kick {spieler}" + (f" {reason.strip()}" if reason.strip() else "")
        antwort = rcon_command(host, p, pw, befehl)
        return ok("minecraft.player.kick", antwort.strip() or f"{spieler} gekickt",
                  spieler=spieler, payload=antwort)

    def mc_backup_create(server_dir: str, backup_dir: str = "") -> ToolResult:
        ordner = server_ordner(server_dir)
        welt = properties_lesen(ordner).get("level-name", "world")
        welt_pfad = ordner / welt
        if not welt_pfad.is_dir():
            raise ToolError(f"Weltordner nicht gefunden: {welt_pfad}")
        ziel_ordner = ws.resolve(backup_dir) if backup_dir else ordner / "backups"
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        zeitstempel = time.strftime("%Y%m%d-%H%M%S")
        ziel = ziel_ordner / f"{welt}-{zeitstempel}.tar.gz"
        import tarfile
        with tarfile.open(ziel, "w:gz") as tar:
            tar.add(welt_pfad, arcname=welt)
        groesse = ziel.stat().st_size
        return ok("minecraft.backup.create", f"Backup erstellt: {ziel.name} "
                  f"({groesse / 1_048_576:.1f} MB)", pfad=str(ziel), bytes=groesse)

    # ══════════════════════════════════════════════════════════ SYSTEM
    def mc_start(server_dir: str, jar: str = "server.jar", memory_mb: int = 2048) -> ToolResult:
        ordner = server_ordner(server_dir)
        jar_pfad = ordner / (jar or "server.jar")
        if not jar_pfad.is_file():
            raise ToolError(f"Server-JAR nicht gefunden: {jar_pfad}")
        eula = ordner / "eula.txt"
        if not eula.is_file() or "eula=true" not in eula.read_text(encoding="utf-8").lower():
            raise ToolError("eula.txt fehlt oder eula=true ist nicht gesetzt -- der Server "
                            "würde sofort wieder beenden. Erst die Minecraft-EULA lesen und "
                            "zustimmen, dann eula=true eintragen.")
        pid_datei = ordner / ".jarvis-minecraft.pid"
        if pid_datei.is_file():
            try:
                import os
                os.kill(int(pid_datei.read_text().strip()), 0)
                raise ToolError("Läuft laut PID-Datei bereits -- erst minecraft.stop, "
                                "oder die veraltete .jarvis-minecraft.pid entfernen.")
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass
        import subprocess
        log_datei = open(ordner / "jarvis-start.log", "ab")  # noqa: SIM115 - bleibt geöffnet
        prozess = subprocess.Popen(  # noqa: S603 - feste Argumentliste, kein Shell
            ["java", f"-Xmx{int(memory_mb)}M", f"-Xms{int(memory_mb)}M", "-jar",
             str(jar_pfad), "nogui"],
            cwd=str(ordner), stdout=log_datei, stderr=subprocess.STDOUT,
            start_new_session=True)
        pid_datei.write_text(str(prozess.pid), encoding="utf-8")
        # Kurz nachsehen statt sofort "gestartet" zu behaupten: ein fehlendes
        # eula.txt oder ein kaputtes JAR beendet den Prozess sofort wieder.
        time.sleep(2.0)
        if prozess.poll() is not None:
            pid_datei.unlink(missing_ok=True)
            raise ToolError(f"Java-Prozess ist sofort beendet (Exit {prozess.returncode}) "
                            f"-- siehe {ordner / 'jarvis-start.log'}")
        return ok("minecraft.start", f"Gestartet (PID {prozess.pid}), Protokoll folgt in "
                  "jarvis-start.log", pid=prozess.pid, jar=str(jar_pfad))

    def mc_stop(server_dir: str, password: str = "", port: int = 0) -> ToolResult:
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, "stop")
        ordner = server_ordner(server_dir)
        (ordner / ".jarvis-minecraft.pid").unlink(missing_ok=True)
        return ok("minecraft.stop", "Stopp über RCON gesendet (speichert die Welt vor dem "
                  "Beenden)", payload=antwort)

    def mc_player_ban(server_dir: str, name: str, reason: str = "", password: str = "",
                      port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        befehl = f"ban {spieler}" + (f" {reason.strip()}" if reason.strip() else "")
        antwort = rcon_command(host, p, pw, befehl)
        return ok("minecraft.player.ban", antwort.strip() or f"{spieler} gebannt",
                  spieler=spieler, payload=antwort)

    def mc_op_add(server_dir: str, name: str, password: str = "", port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, f"op {spieler}")
        return ok("minecraft.op.add", antwort.strip() or f"{spieler} ist jetzt Operator",
                  spieler=spieler, payload=antwort)

    def mc_op_remove(server_dir: str, name: str, password: str = "", port: int = 0) -> ToolResult:
        spieler = spielername(name)
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, f"deop {spieler}")
        return ok("minecraft.op.remove", antwort.strip() or f"{spieler} ist kein Operator mehr",
                  spieler=spieler, payload=antwort)

    # ══════════════════════════════════════════════════════════ CRITICAL
    def mc_command(server_dir: str, command: str, password: str = "",
                   port: int = 0) -> ToolResult:
        befehl = (command or "").strip()
        if not befehl:
            raise ToolError("Kein Befehl angegeben.")
        host, p, pw = rcon_von(server_dir, password, port)
        antwort = rcon_command(host, p, pw, befehl)
        return ok("minecraft.command", antwort.strip() or f"'{befehl}' gesendet, keine "
                  "Textantwort", befehl=befehl, payload=antwort)

    _sd = text("Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich)")
    _rcon_extra = dict(
        password=text("RCON-Passwort, leer = aus server.properties lesen"),
        port=integer("RCON-Port, leer = aus server.properties lesen"))

    return [
        # ── Lesend ──────────────────────────────────────────────────────
        Tool("minecraft.status", "Ob der Server läuft (Prozess) und über RCON antwortet.",
             params("server_dir", server_dir=_sd), mc_status, level=P.READ,
             tags=("minecraft", "status")),
        Tool("minecraft.players.list", "Wer gerade online ist.",
             params("server_dir", server_dir=_sd, **_rcon_extra), mc_players_list,
             level=P.READ, tags=("minecraft", "spieler")),
        Tool("minecraft.performance", "Server-Performance (TPS), sofern die Server-Software "
             "das unterstützt (Paper/Spigot; vanilla kennt den Befehl nicht).",
             params("server_dir", server_dir=_sd, **_rcon_extra), mc_performance,
             level=P.READ, tags=("minecraft", "performance")),
        Tool("minecraft.server.properties.read", "Alle Einstellungen aus server.properties.",
             params("server_dir", server_dir=_sd), mc_server_properties_read, level=P.READ,
             tags=("minecraft", "konfiguration")),
        Tool("minecraft.logs.tail", "Die letzten Zeilen des Server-Logs.",
             params("server_dir", server_dir=_sd, lines=integer("Anzahl, Vorgabe 40")),
             mc_logs_tail, level=P.READ, tags=("minecraft", "log")),
        Tool("minecraft.crash.analyze", "Sucht im letzten Crash-Report/Log nach bekannten "
             "Absturzursachen.",
             params("server_dir", server_dir=_sd), mc_crash_analyze, level=P.READ,
             tags=("minecraft", "log", "diagnose"),
             phrases=("warum ist der server abgestürzt", "crash analysieren")),
        Tool("minecraft.backup.list", "Vorhandene Weltsicherungen.",
             params("server_dir", server_dir=_sd,
                    backup_dir=text("Backup-Ordner, leer = <server>/backups")),
             mc_backup_list, level=P.READ, tags=("minecraft", "backup")),

        # ── WRITE ───────────────────────────────────────────────────────
        Tool("minecraft.server.properties.set", "Ändert eine Einstellung in "
             "server.properties (wirkt erst nach einem Neustart).",
             params("server_dir", "key", "value", server_dir=_sd, key=text("Schlüssel"),
                    value=text("Neuer Wert")),
             mc_server_properties_set, level=P.WRITE, tags=("minecraft", "konfiguration")),
        Tool("minecraft.whitelist.add", "Setzt einen Spieler auf die Whitelist.",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    **_rcon_extra), mc_whitelist_add, level=P.WRITE,
             tags=("minecraft", "whitelist")),
        Tool("minecraft.whitelist.remove", "Entfernt einen Spieler von der Whitelist.",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    **_rcon_extra), mc_whitelist_remove, level=P.WRITE,
             tags=("minecraft", "whitelist")),
        Tool("minecraft.broadcast", "Schickt eine Nachricht an alle Spieler.",
             params("server_dir", "message", server_dir=_sd, message=text("Nachricht"),
                    **_rcon_extra), mc_broadcast, level=P.WRITE, tags=("minecraft", "chat"),
             phrases=("sag den spielern", "broadcast an den server")),
        Tool("minecraft.player.kick", "Wirft einen Spieler vom Server.",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    reason=text("Begründung"), **_rcon_extra), mc_player_kick, level=P.WRITE,
             tags=("minecraft", "spieler")),
        Tool("minecraft.backup.create", "Sichert den Weltordner als .tar.gz.",
             params("server_dir", server_dir=_sd,
                    backup_dir=text("Zielordner, leer = <server>/backups")),
             mc_backup_create, level=P.WRITE, tags=("minecraft", "backup"),
             phrases=("sicher die minecraft welt", "mach ein backup vom server")),

        # ── SYSTEM ──────────────────────────────────────────────────────
        Tool("minecraft.start", "Startet den Server-Prozess (java -jar ... nogui).",
             params("server_dir", server_dir=_sd, jar=text("JAR-Datei, Vorgabe server.jar"),
                    memory_mb=integer("Arbeitsspeicher in MB, Vorgabe 2048")),
             mc_start, level=P.SYSTEM, requires=("java",), tags=("minecraft",),
             timeout=30.0, phrases=("starte den minecraft server",)),
        Tool("minecraft.stop", "Beendet den Server geordnet über RCON (speichert die Welt).",
             params("server_dir", server_dir=_sd, **_rcon_extra), mc_stop, level=P.SYSTEM,
             tags=("minecraft",), phrases=("stoppe den minecraft server",)),
        Tool("minecraft.player.ban", "Bannt einen Spieler vom Server.",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    reason=text("Begründung"), **_rcon_extra), mc_player_ban, level=P.SYSTEM,
             tags=("minecraft", "spieler")),
        Tool("minecraft.op.add", "Macht einen Spieler zum Operator (Admin-Rechte).",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    **_rcon_extra), mc_op_add, level=P.SYSTEM, tags=("minecraft", "rechte")),
        Tool("minecraft.op.remove", "Entzieht einem Spieler die Operator-Rechte.",
             params("server_dir", "name", server_dir=_sd, name=text("Minecraft-Name"),
                    **_rcon_extra), mc_op_remove, level=P.SYSTEM, tags=("minecraft", "rechte")),

        # ── CRITICAL ────────────────────────────────────────────────────
        Tool("minecraft.command", "Sendet einen beliebigen Admin-Befehl über RCON -- "
             "verlangt deshalb immer eine ausdrückliche Bestätigung (Punkt 20: ein "
             "Text-Befehl lässt sich nicht sicher in harmlos/gefährlich einteilen).",
             params("server_dir", "command", server_dir=_sd,
                    command=text("z. B. '/gamemode creative Name'"), **_rcon_extra),
             mc_command, level=P.CRITICAL, tags=("minecraft", "rcon")),
    ]
