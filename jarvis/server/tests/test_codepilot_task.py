"""Was `codepilot_task` zurückmeldet — vor allem, wenn etwas schiefgeht.

Anlass: ein Auftrag endete beim Nutzer mit „Status: failed", 0 Werkzeug-
aufrufen und sonst nichts. CodePilot kannte den Grund und legte ihn auch ab,
aber diese Brücke reichte ihn nicht durch. Ein Fehlschlag ohne Begründung ist
fast so schlecht wie ein erfundener Erfolg: der Nutzer weiß nicht, was er
tun soll.

Geprüft wird gegen einen echten HTTP-Server, der CodePilots Antworten
nachbildet — kein gefälschter Client, damit auch die Anfragen selbst stimmen.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.tools.base import ToolError
from jarvis.tools.codepilot import CodePilotLink, build


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_fake_codepilot(sitzung: dict, ereignisse: list[dict]) -> tuple[HTTPServer, int]:
    """Ein Miniserver, der genau die Endpunkte bedient, die die Brücke nutzt."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # keine Testausgabe
            pass

        def _sende(self, daten, status=200):
            roh = json.dumps(daten).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

        def do_GET(self):
            if self.path == "/api/health":
                self._sende({"service": "codepilot-remote", "version": "test"})
            elif self.path == "/api/status":
                self._sende({"claude": {"available": True},
                             "ollama": {"available": True},
                             "model": {"available": True}})
            elif self.path.startswith("/api/sessions/") and "/events" in self.path:
                self._sende({"events": ereignisse, "last_seq": len(ereignisse)})
            elif self.path.startswith("/api/sessions/") and "/changes" in self.path:
                self._sende({"files": [], "total_added": 0, "total_removed": 0})
            elif self.path.startswith("/api/sessions/"):
                self._sende({"session": sitzung})
            else:
                self._sende({}, 404)

        def do_POST(self):
            if self.path == "/api/sessions":
                self._sende({"session": {"id": sitzung["id"]}})
            else:
                self._sende({}, 404)

    port = freier_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


@pytest.fixture
def fake_codepilot():
    erzeugte: list[HTTPServer] = []

    def starten(sitzung, ereignisse=()):
        server, port = starte_fake_codepilot(sitzung, list(ereignisse))
        erzeugte.append(server)
        return CodePilotLink(url=f"http://127.0.0.1:{port}", token="t",
                             project_id="p", timeout=20)

    yield starten
    for server in erzeugte:
        server.shutdown()


def werkzeug(link):
    return {t.name: t for t in build(link)}["codepilot_task"]


# ══════════════════════════════════════════════════════════ Fehlschlag
def test_gescheiterter_auftrag_nennt_den_grund(fake_codepilot):
    """Genau der Fall aus dem Bericht: failed, 0 Werkzeugaufrufe, kein Grund."""
    link = fake_codepilot(
        {"id": "s1", "status": "failed",
         "error": "Claude Code exited with code 1\nAPI Error: 404 model not found"},
        [{"type": "session.failed",
          "payload": {"result": "Claude Code exited with code 1\n"
                                "API Error: 404 model not found"}}])

    ergebnis = werkzeug(link).run(task="mach ein browsergame")

    assert ergebnis.ok is False
    assert "404 model not found" in ergebnis.summary
    assert "404 model not found" in ergebnis.payload
    assert ergebnis.evidence["status"] == "failed"


def test_grund_aus_der_sitzung_reicht_auch_ohne_ereignis(fake_codepilot):
    link = fake_codepilot({"id": "s2", "status": "failed",
                           "error": "launch failed: claude not found on PATH"}, [])

    ergebnis = werkzeug(link).run(task="bau was")

    assert ergebnis.ok is False
    assert "claude not found on PATH" in ergebnis.summary


def test_doppelte_gruende_erscheinen_nur_einmal(fake_codepilot):
    grund = "API Error: 404"
    link = fake_codepilot({"id": "s3", "status": "failed", "error": grund},
                          [{"type": "session.failed", "payload": {"result": grund}}])

    ergebnis = werkzeug(link).run(task="bau was")

    assert ergebnis.payload.count(grund) == 1


def test_ohne_grund_bleibt_es_ehrlich_vage(fake_codepilot):
    link = fake_codepilot({"id": "s4", "status": "failed"}, [])

    ergebnis = werkzeug(link).run(task="bau was")

    assert ergebnis.ok is False
    assert "nicht abgeschlossen" in ergebnis.summary
    assert "Grund:" not in ergebnis.summary   # nichts erfinden


# ══════════════════════════════════════════════════════════ Erfolgsfall
def test_abgeschlossener_auftrag_meldet_erfolg(fake_codepilot):
    link = fake_codepilot(
        {"id": "s5", "status": "completed"},
        [{"type": "tool.finished", "payload": {}},
         {"type": "assistant.message", "payload": {"text": "Fertig."}}])

    ergebnis = werkzeug(link).run(task="bau was")

    assert ergebnis.ok is True
    assert ergebnis.evidence["werkzeugaufrufe"] == 1
    assert ergebnis.evidence["codepilot"] == "lief bereits"


def test_nicht_eingerichtet_bleibt_eine_absage():
    link = CodePilotLink(url="http://127.0.0.1:1", token="", project_id="")
    with pytest.raises(ToolError, match="nicht eingerichtet"):
        werkzeug(link).run(task="bau was")
