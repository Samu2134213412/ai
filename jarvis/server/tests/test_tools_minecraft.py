"""Das Minecraft-Pack: RCON gegen einen echten, protokollkonformen Test-
server im Prozess (Source-RCON, dasselbe Protokoll wie Minecraft) -- kein
Mock des Clients, sondern ein echtes Gegenüber, das dieselben Bytes spricht.
Dateibasierte Werkzeuge (server.properties, Logs, Backups, Crash-Analyse)
laufen gegen echte, synthetisch angelegte Dateien.
"""

from __future__ import annotations

import socket
import struct
import threading

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult
from jarvis.tools.packs.minecraft import RconError, rcon_command

_AUTH = 3
_AUTH_RESPONSE = 2
_EXEC = 2
_RESPONSE_VALUE = 0


def _pack(request_id: int, packet_type: int, payload: str) -> bytes:
    body = payload.encode("utf-8") + b"\x00\x00"
    rumpf = struct.pack("<ii", request_id, packet_type) + body
    return struct.pack("<i", len(rumpf)) + rumpf


def _read(sock: socket.socket) -> tuple[int, int, str]:
    (laenge,) = struct.unpack("<i", sock.recv(4))
    rumpf = b""
    while len(rumpf) < laenge:
        rumpf += sock.recv(laenge - len(rumpf))
    request_id, packet_type = struct.unpack("<ii", rumpf[:8])
    return request_id, packet_type, rumpf[8:-2].decode("utf-8", errors="replace")


class FakeRconServer:
    """Ein winziger, echter RCON-Server -- spricht das Source-RCON-Protokoll
    so, wie Minecraft es tut (leeres RESPONSE_VALUE vor der AUTH-Antwort),
    inklusive der Eigenheit, auf die Minecraft-Befehle mit einer festen
    Textantwort zu reagieren."""

    def __init__(self, password: str = "geheim"):
        self.password = password
        self.antworten: dict[str, str] = {
            "list": "There are 2 of a max of 20 players online: Alice, Bob",
            "tps": "TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0",
        }
        self.empfangen: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._lauf, daemon=True)
        self._thread.start()

    def _lauf(self) -> None:
        # rcon_command() oeffnet fuer JEDEN Befehl eine eigene Verbindung
        # (siehe sein Docstring) -- der Testserver muss also fortlaufend
        # neue Verbindungen annehmen, nicht nur eine einzige am Anfang.
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bediene, args=(conn,), daemon=True).start()

    def _bediene(self, conn: socket.socket) -> None:
        with conn:
            req_id, ptype, passwort = _read(conn)
            assert ptype == _AUTH
            conn.sendall(_pack(req_id, _RESPONSE_VALUE, ""))
            if passwort != self.password:
                conn.sendall(_pack(-1, _AUTH_RESPONSE, ""))
                return
            conn.sendall(_pack(req_id, _AUTH_RESPONSE, ""))
            while True:
                try:
                    req_id, ptype, befehl = _read(conn)
                except (OSError, struct.error):
                    return
                self.empfangen.append(befehl)
                basis = befehl.split()[0] if befehl.split() else ""
                antwort = self.antworten.get(befehl, self.antworten.get(basis, ""))
                conn.sendall(_pack(req_id, _RESPONSE_VALUE, antwort))

    def close(self) -> None:
        self._sock.close()


@pytest.fixture
def rcon_server():
    server = FakeRconServer()
    yield server
    server.close()


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


# ═══════════════════════════════════════════════════ RCON-Client, direkt
def test_rcon_command_echte_antwort(rcon_server):
    antwort = rcon_command("127.0.0.1", rcon_server.port, "geheim", "list")
    assert "Alice" in antwort
    assert rcon_server.empfangen == ["list"]


def test_rcon_command_falsches_passwort(rcon_server):
    with pytest.raises(RconError, match="[Pp]asswort"):
        rcon_command("127.0.0.1", rcon_server.port, "falsch", "list")


def test_rcon_command_nicht_erreichbar():
    with pytest.raises(RconError):
        rcon_command("127.0.0.1", 1, "x", "list", timeout=1)


# ═══════════════════════════════════════════════ Werkzeuge über RCON
@pytest.fixture
def server_dir(workspace, rcon_server):
    ordner = workspace / "mcserver"
    ordner.mkdir()
    (ordner / "server.properties").write_text(
        f"enable-rcon=true\nrcon.port={rcon_server.port}\nrcon.password=geheim\n"
        "level-name=world\n", encoding="utf-8")
    return ordner


def test_players_list(tools, server_dir, rcon_server):
    res = erfolg(tools("minecraft.players.list", server_dir="mcserver"))
    assert "Alice" in res.payload


def test_performance(tools, server_dir):
    res = erfolg(tools("minecraft.performance", server_dir="mcserver"))
    assert "20.0" in res.payload


def test_status_rcon_erreichbar(tools, server_dir):
    res = erfolg(tools("minecraft.status", server_dir="mcserver"))
    assert res.evidence["rcon_erreichbar"] is True


def test_status_ohne_laufenden_server(tools, workspace):
    ordner = workspace / "totmc"
    ordner.mkdir()
    (ordner / "server.properties").write_text(
        "enable-rcon=true\nrcon.port=1\nrcon.password=x\n", encoding="utf-8")
    res = erfolg(tools("minecraft.status", server_dir="totmc"))
    assert res.evidence["laeuft"] is False


def test_whitelist_add_remove(tools, server_dir, rcon_server):
    rcon_server.antworten["whitelist add Steve"] = "Added Steve to the whitelist"
    res = erfolg(tools("minecraft.whitelist.add", server_dir="mcserver", name="Steve"))
    assert "Steve" in res.payload
    assert "whitelist add Steve" in rcon_server.empfangen


def test_ungueltiger_spielername_wird_abgelehnt(tools, server_dir):
    fehler(tools("minecraft.whitelist.add", server_dir="mcserver", name="; rm -rf /"))
    fehler(tools("minecraft.player.kick", server_dir="mcserver", name="mit leerzeichen"))


def test_broadcast(tools, server_dir, rcon_server):
    erfolg(tools("minecraft.broadcast", server_dir="mcserver", message="Hallo Welt"))
    assert "say Hallo Welt" in rcon_server.empfangen


def test_op_add_remove(tools, server_dir, rcon_server):
    erfolg(tools("minecraft.op.add", server_dir="mcserver", name="Steve"))
    erfolg(tools("minecraft.op.remove", server_dir="mcserver", name="Steve"))
    assert "op Steve" in rcon_server.empfangen
    assert "deop Steve" in rcon_server.empfangen


def test_command_roh(tools, server_dir, rcon_server):
    rcon_server.antworten["gamemode creative Steve"] = "Set Steve's game mode to Creative"
    res = erfolg(tools("minecraft.command", server_dir="mcserver",
                       command="gamemode creative Steve"))
    assert "Creative" in res.payload


def test_command_ohne_text_wird_abgelehnt(tools, server_dir):
    fehler(tools("minecraft.command", server_dir="mcserver", command=""))


def test_stop_sendet_ueber_rcon_und_entfernt_pid_datei(tools, server_dir, rcon_server):
    (server_dir / ".jarvis-minecraft.pid").write_text("999999", encoding="utf-8")
    erfolg(tools("minecraft.stop", server_dir="mcserver"))
    assert "stop" in rcon_server.empfangen
    assert not (server_dir / ".jarvis-minecraft.pid").exists()


def test_rcon_ohne_konfiguration_meldet_das_ehrlich(tools, workspace):
    ordner = workspace / "nrcon"
    ordner.mkdir()
    (ordner / "server.properties").write_text("enable-rcon=false\n", encoding="utf-8")
    fehler(tools("minecraft.players.list", server_dir="nrcon"))


# ═══════════════════════════════════════════════ Dateibasierte Werkzeuge
def test_server_properties_read_und_write(tools, server_dir):
    gelesen = erfolg(tools("minecraft.server.properties.read", server_dir="mcserver"))
    assert "enable-rcon" in gelesen.payload

    erfolg(tools("minecraft.server.properties.set", server_dir="mcserver",
                 key="motd", value="Willkommen"))
    inhalt = (server_dir / "server.properties").read_text(encoding="utf-8")
    assert "motd=Willkommen" in inhalt


def test_logs_tail(tools, server_dir):
    logs = server_dir / "logs"
    logs.mkdir()
    (logs / "latest.log").write_text("\n".join(f"Zeile {i}" for i in range(100)),
                                     encoding="utf-8")
    res = erfolg(tools("minecraft.logs.tail", server_dir="mcserver", lines=10))
    assert res.evidence["zeilen"] == 10
    assert "Zeile 99" in res.payload


def test_crash_analyze_erkennt_out_of_memory(tools, server_dir):
    logs = server_dir / "logs"
    logs.mkdir()
    (logs / "latest.log").write_text(
        "Normaler Start\njava.lang.OutOfMemoryError: Java heap space\n", encoding="utf-8")
    res = erfolg(tools("minecraft.crash.analyze", server_dir="mcserver"))
    assert res.evidence["funde"] >= 1
    assert "Arbeitsspeicher" in res.payload


def test_crash_analyze_ohne_bekanntes_muster(tools, server_dir):
    logs = server_dir / "logs"
    logs.mkdir()
    (logs / "latest.log").write_text("Alles normal, Server läuft.\n", encoding="utf-8")
    res = erfolg(tools("minecraft.crash.analyze", server_dir="mcserver"))
    assert res.evidence["funde"] == 0


def test_backup_create_und_list(tools, server_dir):
    welt = server_dir / "world"
    welt.mkdir()
    (welt / "level.dat").write_bytes(b"\x00" * 100)
    res = erfolg(tools("minecraft.backup.create", server_dir="mcserver"))
    assert res.evidence["bytes"] > 0

    liste = erfolg(tools("minecraft.backup.list", server_dir="mcserver"))
    assert liste.evidence["anzahl"] == 1


def test_start_ohne_eula_schlaegt_ehrlich_fehl(tools, server_dir):
    (server_dir / "server.jar").write_bytes(b"kein echtes jar")
    fehler(tools("minecraft.start", server_dir="mcserver"))


def test_start_ohne_jar_schlaegt_ehrlich_fehl(tools, server_dir):
    (server_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    fehler(tools("minecraft.start", server_dir="mcserver", jar="nicht_da.jar"))


# ═══════════════════════════════════════════════ Sicherheit
def test_pfad_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools):
    fehler(tools("minecraft.status", server_dir="/etc"))
