"""Speech-to-Text über Whisper — nur ein echtes Ergebnis wird als Text gemeldet.

Geprüft wird gegen einen echten HTTP-Server, der die Whisper-API nachbildet,
nicht gegen einen gefälschten Client — damit auch die gesendete Anfrage stimmt.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.whisper import WhisperClient, WhisperError


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_fake_whisper(antwort: dict, status: int = 200, gesehen: list | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_POST(self):
            laenge = int(self.headers.get("Content-Length", 0))
            self.rfile.read(laenge)
            if gesehen is not None:
                gesehen.append(dict(self.headers))
            roh = json.dumps(antwort).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

    port = freier_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


@pytest.fixture
def fake_whisper():
    erzeugte: list[HTTPServer] = []

    def starten(antwort, status=200, gesehen=None):
        server, port = starte_fake_whisper(antwort, status, gesehen)
        erzeugte.append(server)
        return WhisperClient(api_key="k", url=f"http://127.0.0.1:{port}/v1")

    yield starten
    for server in erzeugte:
        server.shutdown()


def test_ohne_schluessel_wird_gar_nicht_erst_gerufen():
    client = WhisperClient(api_key="")
    with pytest.raises(WhisperError, match="Schlüssel"):
        client.transcribe(b"irgendwas")


def test_leere_audiodaten_werden_abgelehnt():
    client = WhisperClient(api_key="k")
    with pytest.raises(WhisperError, match="Audiodaten"):
        client.transcribe(b"")


def test_echte_antwort_kommt_durch(fake_whisper):
    gesehen: list = []
    client = fake_whisper({"text": "mach eine Notiz"}, gesehen=gesehen)
    text = client.transcribe(b"\x00\x01echte-bytes", filename="a.webm",
                             content_type="audio/webm")
    assert text == "mach eine Notiz"
    kopf = gesehen[0]
    assert kopf.get("Authorization") == "Bearer k"


def test_ablehnung_der_api_wird_gemeldet_nicht_verschwiegen(fake_whisper):
    client = fake_whisper({"error": {"message": "invalid_api_key"}}, status=401)
    with pytest.raises(WhisperError, match="401"):
        client.transcribe(b"etwas")


def test_leerer_text_zaehlt_nicht_als_erfolg(fake_whisper):
    client = fake_whisper({"text": "   "})
    with pytest.raises(WhisperError, match="leeren Text"):
        client.transcribe(b"etwas")


def test_nicht_erreichbarer_server_wird_gemeldet():
    client = WhisperClient(api_key="k", url="http://127.0.0.1:1")
    with pytest.raises(WhisperError, match="nicht erreichbar"):
        client.transcribe(b"etwas")
