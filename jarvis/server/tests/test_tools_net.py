"""Das Netzwerk-Pack.

Netzwerktests sind heikel: was vom Internet abhängt, ist kein Test, sondern
eine Wette. Geprüft wird deshalb gegen einen **echten HTTP-Server im
Testprozess** (``http.server`` auf localhost) und gegen echte lokale Sockets
-- kein Mock, aber auch keine Abhängigkeit von einer fremden Gegenstelle.

Werkzeuge, die zwingend nach draußen müssen (``net.public.ip``), werden auf
ihr Verhalten *ohne* Internet geprüft: eine ehrliche Absage.
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.permissions import PermissionLevel
from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # ruhig bleiben
        pass

    def _send(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Jarvis-Test", "ja")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/gross":
            return self._send(b"x" * 5000)
        if self.path == "/fehler":
            return self._send(b"weg", 404)
        self._send("Hallo von Jarvis".encode("utf-8"))

    do_HEAD = do_GET


@pytest.fixture(scope="module")
def webserver():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def registry(config, store):
    return build_registry(config, store)


@pytest.fixture
def tools(registry):
    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


# ══════════════════════════════════════════════════════════════════ Namen
def test_localhost_wird_aufgeloest(tools):
    result = erfolg(tools("net.dns.lookup", host="localhost"))
    assert "127.0.0.1" in result.payload or "::1" in result.payload


def test_unaufloesbarer_name_ist_ein_ehrlicher_fehler(tools):
    fehl = tools("net.dns.lookup", host="das-gibt-es-ganz-sicher-nicht.invalid")
    assert fehl.ok is False and "nicht auflösbar" in fehl.summary


def test_hostname_mit_steuerzeichen_wird_abgelehnt(tools):
    """Ein Hostname mit Semikolon wäre der Weg, aus einem Argument einen
    zweiten Befehl zu machen."""
    for boese in ("host; rm -rf /", "a | b", "x`whoami`", "a b"):
        fehl = tools("net.dns.lookup", host=boese)
        assert fehl.ok is False and "gültiger Hostname" in fehl.summary


def test_leerer_host_wird_abgelehnt(tools):
    assert tools("net.ping", host="").ok is False
    assert tools("net.port.check", host="  ", port=80).ok is False


def test_rueckwaertsaufloesung_braucht_eine_echte_ip(tools):
    fehl = tools("net.dns.reverse", ip="keine ip")
    assert fehl.ok is False and "gültige IP" in fehl.summary
    # 127.0.0.1 hat fast immer einen Rückwärtseintrag; wenn nicht, ist die
    # Absage trotzdem ehrlich.
    result = tools("net.dns.reverse", ip="127.0.0.1")
    assert result.ok or "Kein Rückwärtseintrag" in result.summary


# ══════════════════════════════════════════════════════════ Erreichbarkeit
def test_offener_port_wird_als_offen_erkannt(tools, webserver):
    port = int(webserver.rsplit(":", 1)[1])
    result = erfolg(tools("net.port.check", host="127.0.0.1", port=port))
    assert result.evidence["offen"] is True
    assert result.evidence["dauer_ms"] >= 0


def test_geschlossener_port_ist_kein_absturz_sondern_ein_befund(tools):
    """Ein zugemachter Port ist eine Antwort, kein Fehler -- deshalb ok=True
    mit ``offen: False``."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        frei = s.getsockname()[1]
    result = erfolg(tools("net.port.check", host="127.0.0.1", port=frei, timeout=1))
    assert result.evidence["offen"] is False
    assert result.evidence["grund"]


def test_ungueltiger_port_wird_abgelehnt(tools):
    assert tools("net.port.check", host="127.0.0.1", port=0).ok is False
    assert tools("net.port.check", host="127.0.0.1", port=99999).ok is False


def test_ping_auf_localhost(tools):
    result = tools("net.ping", host="127.0.0.1", count=2)
    if result.ok:
        assert result.evidence["antworten"] >= 1
        assert result.evidence["mittel_ms"] >= 0
    else:  # in manchen Containern ist ICMP gesperrt
        assert "antwortet nicht" in result.summary or "kein 'ping'" in result.summary


def test_latenzmessung_gegen_einen_offenen_port(tools, webserver):
    """Die Messung geht gegen 443; lokal gibt es das meist nicht, dann ist
    die Absage ehrlich."""
    result = tools("net.latency.monitor", host="127.0.0.1", samples=2, delay=0)
    assert result.ok or "bei keinem von" in result.summary


# ═════════════════════════════════════════════════════════ Eigener Rechner
def test_lokale_ip_und_hostname(tools):
    ip = erfolg(tools("net.local.ip"))
    assert ip.evidence["ip"].count(".") == 3 or ":" in ip.evidence["ip"]

    name = erfolg(tools("net.hostname"))
    assert name.evidence["rechner"]


def test_adapter_und_offene_ports(tools, webserver):
    adapter = erfolg(tools("net.interfaces"))
    assert adapter.evidence["anzahl"] >= 1

    ports = erfolg(tools("net.local.ports"))
    port = int(webserver.rsplit(":", 1)[1])
    # Der Testserver lauscht wirklich -- er muss in der Liste stehen.
    assert str(port) in ports.payload


def test_verbindungen_und_durchsatz(tools):
    erfolg(tools("net.connections", limit=5))
    verkehr = erfolg(tools("net.traffic"))
    assert verkehr.evidence["empfangen_bytes"] >= 0

    rate = erfolg(tools("net.traffic.rate", seconds=0.5))
    assert rate.evidence["rein_bytes_s"] >= 0
    assert rate.evidence["gemessen_s"] == 0.5


def test_gateway_und_arp_melden_ehrlich(tools):
    """Fehlt das Systemwerkzeug, sagt die Absage welches -- sie verschweigt
    den Grund nicht und erfindet keine Route."""
    for name, gemeint in (("net.gateway", ("route", "lesen")),
                          ("net.arp.table", ("arp", "ip"))):
        result = tools(name)
        if result.ok:
            continue
        assert any(wort in result.summary.lower() for wort in gemeint), \
            f"{name}: Absage nennt den Grund nicht ({result.summary})"


def test_wlan_ohne_werkzeug_sagt_das(tools):
    result = tools("net.wifi.networks")
    assert result.ok or "nmcli" in result.summary or "netsh" in result.summary


# ═══════════════════════════════════════════════════════════════════ HTTP
def test_http_status_gegen_einen_echten_server(tools, webserver):
    result = erfolg(tools("net.http.status", url=webserver))
    assert result.evidence["status"] == 200
    assert result.evidence["erreichbar"] is True
    assert result.evidence["dauer_ms"] >= 0


def test_http_status_meldet_einen_fehlercode_als_solchen(tools, webserver):
    result = erfolg(tools("net.http.status", url=f"{webserver}/fehler"))
    assert result.evidence["status"] == 404
    assert result.evidence["erreichbar"] is False


def test_http_kopfzeilen_und_inhalt(tools, webserver):
    kopf = erfolg(tools("net.http.headers", url=webserver))
    assert "x-jarvis-test" in kopf.payload.lower()

    inhalt = erfolg(tools("net.http.get", url=webserver))
    assert inhalt.payload == "Hallo von Jarvis"
    assert inhalt.evidence["gekuerzt"] is False

    gekuerzt = erfolg(tools("net.http.get", url=f"{webserver}/gross", max_chars=500))
    assert len(gekuerzt.payload) == 500
    assert gekuerzt.evidence["gekuerzt"] is True


def test_nicht_erreichbare_adresse_ist_ein_ehrlicher_fehler(tools):
    fehl = tools("net.http.status", url="http://127.0.0.1:1", timeout=2)
    assert fehl.ok is False and "nicht erreichbar" in fehl.summary


def test_nur_http_und_https(tools):
    for boese in ("file:///etc/passwd", "ftp://host/x"):
        fehl = tools("net.http.get", url=boese)
        assert fehl.ok is False and "Nur http und https" in fehl.summary


def test_download_landet_im_arbeitsbereich(tools, webserver, workspace):
    result = erfolg(tools("net.http.download", url=webserver, path="geladen.txt"))
    ziel = workspace / "geladen.txt"
    assert ziel.read_text(encoding="utf-8") == "Hallo von Jarvis"
    # Der Beleg kommt von der Festplatte, nicht vom Zähler.
    assert result.evidence["bytes"] == ziel.stat().st_size


def test_download_kommt_nicht_aus_dem_arbeitsbereich_heraus(tools, webserver, workspace):
    draussen = str(workspace.parent / "entkommen.txt")
    fehl = tools("net.http.download", url=webserver, path=draussen)
    assert fehl.ok is False and "außerhalb" in fehl.summary
    assert not (workspace.parent / "entkommen.txt").exists()


def test_url_zerlegen(tools):
    result = erfolg(tools("net.url.parse",
                          url="https://example.org:8443/a/b?x=1&y=2#oben"))
    assert result.evidence["host"] == "example.org"
    assert result.evidence["port"] == 8443
    assert result.evidence["parameter"] == 2
    assert "x = 1" in result.payload


def test_zertifikat_gegen_einen_reinen_http_server_schlaegt_ehrlich_fehl(tools,
                                                                        webserver):
    port = int(webserver.rsplit(":", 1)[1])
    fehl = tools("net.ssl.certificate", host="127.0.0.1", port=port, timeout=3)
    assert fehl.ok is False
    assert "nicht erreichbar" in fehl.summary or "nicht gültig" in fehl.summary


# ═══════════════════════════════════════════════════════ Keine Angriffstools
def test_es_gibt_keinen_portscanner(registry):
    """Die Aufgabenstellung verlangt ausdrücklich keine offensiven Werkzeuge.
    Dieser Test hält das fest, damit es niemand versehentlich einbaut."""
    verboten = ("scan", "exploit", "brute", "crack", "inject", "sniff", "spoof")
    for tool in registry:
        for wort in verboten:
            assert wort not in tool.name.lower(), f"{tool.name} klingt offensiv"


def test_veraenderndes_im_netz_traegt_die_richtige_stufe(registry):
    assert registry.get("net.dns.flush").level is PermissionLevel.SYSTEM
    assert registry.get("net.http.download").level is PermissionLevel.WRITE
    assert registry.get("net.port.check").level is PermissionLevel.READ
