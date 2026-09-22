"""Das Such-Pack: search.files läuft gegen einen echten Dateibaum. search.apps
läuft plattformabhängig -- unter Linux gegen echte, selbst angelegte
.desktop-Dateien (kein Mock, echte Dateien im XDG-Format). search.web läuft
gegen einen echten, lokalen Fake-SearXNG-Server (siehe test_websearch.py für
die ausführliche Prüfung des Clients selbst). search.apps.open startet
echte, harmlose Prozesse (python3 -c "pass")."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.config import SearchConfig
from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


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


@pytest.fixture
def baum(workspace):
    (workspace / "bericht_2026.txt").write_text("x", encoding="utf-8")
    (workspace / "rechnung_maerz.pdf").write_text("x", encoding="utf-8")
    unter = workspace / "projekt"
    unter.mkdir()
    (unter / "readme.md").write_text("x", encoding="utf-8")
    (unter / "notizen.txt").write_text("x", encoding="utf-8")
    ausgeschlossen = workspace / "node_modules"
    ausgeschlossen.mkdir()
    (ausgeschlossen / "sollte_nicht_gefunden_werden.txt").write_text("x", encoding="utf-8")
    return workspace


def test_search_files_findet_exakten_namen(tools, baum):
    res = erfolg(tools("search.files", query="readme.md"))
    assert res.evidence["anzahl"] >= 1
    assert "readme.md" in res.payload


def test_search_files_unscharfe_suche(tools, baum):
    res = erfolg(tools("search.files", query="bericht2026"))
    assert "bericht_2026.txt" in res.payload


def test_search_files_ignoriert_node_modules(tools, baum):
    res = erfolg(tools("search.files", query="sollte_nicht_gefunden_werden"))
    assert res.evidence["anzahl"] == 0


def test_search_files_kein_treffer(tools, baum):
    res = erfolg(tools("search.files", query="xyzxyzxyz_gibtsnicht"))
    assert res.evidence["anzahl"] == 0


def test_search_files_leerer_suchbegriff_wird_abgelehnt(tools, baum):
    fehler(tools("search.files", query=""))


def test_search_files_begrenzt_ergebnisse(tools, baum):
    # "e" steckt in allen vier angelegten Dateinamen -- mehr Treffer als das
    # Limit, damit der Test das Begrenzen wirklich prüft und nicht zufällig
    # gleich viele Treffer wie Limit hat.
    res = erfolg(tools("search.files", query="e", limit=2))
    assert res.evidence["anzahl"] == 4
    datenzeilen = res.payload.splitlines()[2:]  # ohne Kopfzeile + Trennstrich
    assert len(datenzeilen) == 2


# ═══════════════════════════════════════════════════════════════ search.apps
def test_linux_apps_liest_echte_desktop_dateien(tmp_path):
    from jarvis.tools.packs.search import linux_apps

    ordner = tmp_path / "applications"
    ordner.mkdir()
    (ordner / "firefox.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=firefox %u\nType=Application\n", encoding="utf-8")
    (ordner / "editor.desktop").write_text(
        "[Desktop Entry]\nName=Mein Editor\nExec=/usr/bin/editor\nType=Application\n",
        encoding="utf-8")

    ergebnis = linux_apps(100, ordner=[ordner])
    assert ["Firefox", "firefox"] in ergebnis
    assert ["Mein Editor", "/usr/bin/editor"] in ergebnis


def test_linux_apps_ohne_name_wird_uebersprungen(tmp_path):
    from jarvis.tools.packs.search import linux_apps

    ordner = tmp_path / "applications"
    ordner.mkdir()
    (ordner / "kaputt.desktop").write_text("[Desktop Entry]\nExec=irgendwas\n", encoding="utf-8")

    assert linux_apps(100, ordner=[ordner]) == []


def test_macos_apps_liest_echte_app_buendel(tmp_path):
    from jarvis.tools.packs.search import macos_apps

    ordner = tmp_path / "Applications"
    ordner.mkdir()
    (ordner / "Beispiel.app").mkdir()

    ergebnis = macos_apps(100, ordner=[ordner])
    assert ergebnis[0][0] == "Beispiel"


def test_windows_apps_liest_echte_verknuepfungen(tmp_path):
    from jarvis.tools.packs.search import windows_apps

    ordner = tmp_path / "Programs"
    ordner.mkdir()
    (ordner / "Rechner.lnk").write_bytes(b"\x00")

    ergebnis = windows_apps(100, ordner=[ordner])
    assert ergebnis[0][0] == "Rechner"


def test_search_apps_lehnt_unbekannte_plattform_nicht_ab_bei_bekannter(tools):
    # Auf der tatsaechlichen Testplattform (Linux) muss der Aufruf zumindest
    # nicht mit "Unbekannte Plattform" scheitern -- ob etwas gefunden wird,
    # haengt vom System ab, auf dem der Test laeuft.
    res = tools("search.apps", limit=5)
    assert res.ok


# ═══════════════════════════════════════════════════════ search.apps.open
def test_apps_open_startet_ein_echtes_programm(tools, workspace):
    beleg = workspace / "gestartet.txt"
    res = erfolg(tools("search.apps.open", path=sys.executable,
                       arguments=["-c", f"open({str(beleg)!r}, 'w').close()"]))
    assert res.evidence["pid"] > 0
    for _ in range(50):
        if beleg.exists():
            break
        time.sleep(0.05)
    assert beleg.exists()


def test_apps_open_probelauf_startet_nichts(tools, workspace):
    beleg = workspace / "sollte_nicht_entstehen.txt"
    res = tools("search.apps.open", path=sys.executable,
               arguments=["-c", f"open({str(beleg)!r}, 'w').close()"], dry_run=True)
    assert res.ok
    assert res.evidence.get("probelauf") is True
    assert not beleg.exists()


def test_apps_open_ohne_pfad_wird_abgelehnt(tools):
    fehler(tools("search.apps.open", path=""))


def test_apps_open_unbekanntes_programm_meldet_ehrlichen_fehler(tools):
    fehler(tools("search.apps.open", path="dieses-programm-gibt-es-ganz-sicher-nicht"))


# ══════════════════════════════════════════════════════════════ search.web
def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_fake_searxng(antwort: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_GET(self):
            roh = json.dumps(antwort).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

    port = freier_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_search_web_ohne_konfiguration_meldet_das_ehrlich(tools):
    res = fehler(tools("search.web", query="irgendwas"))
    assert "eingerichtet" in res.summary


def test_search_web_leerer_suchbegriff_wird_abgelehnt(tools):
    fehler(tools("search.web", query=""))


def test_search_web_liefert_echte_treffer(config, store, workspace):
    server, port = starte_fake_searxng({"results": [
        {"title": "Ein echter Treffer", "url": "https://beispiel.test",
         "content": "Ein Ausschnitt"}]})
    try:
        config.search = SearchConfig(searxng_url=f"http://127.0.0.1:{port}")
        registry = build_registry(config, store)
        res = erfolg(registry.call("search.web", {"query": "testbegriff"}))
        assert res.evidence["anzahl"] == 1
        assert "Ein echter Treffer" in res.payload
        assert "beispiel.test" in res.payload
    finally:
        server.shutdown()
