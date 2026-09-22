"""Web-Suche über SearXNG/Brave — nur ein echtes Ergebnis wird als Treffer
gemeldet.

Geprüft wird gegen einen echten HTTP-Server, der die jeweilige API
nachbildet, nicht gegen einen gefälschten Client -- damit auch die
gesendete Anfrage stimmt (dieselbe Herangehensweise wie test_whisper.py).
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.websearch import WebSearchClient, WebSearchError


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_fake_server(antwort: dict, status: int = 200, gesehen: list | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_GET(self):
            if gesehen is not None:
                gesehen.append({"path": self.path, "headers": dict(self.headers)})
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
def fake_dienst():
    erzeugte: list[HTTPServer] = []

    def starten(antwort, status=200, gesehen=None):
        server, port = starte_fake_server(antwort, status, gesehen)
        erzeugte.append(server)
        return port

    yield starten
    for server in erzeugte:
        server.shutdown()


def test_ohne_konfiguration_wird_gar_nicht_erst_gerufen():
    client = WebSearchClient()
    assert not client.configured
    with pytest.raises(WebSearchError, match="Keine Web-Suche eingerichtet"):
        client.search("irgendwas")


def test_searxng_liefert_echte_treffer(fake_dienst):
    gesehen: list = []
    port = fake_dienst({"results": [
        {"title": "Erstes Ergebnis", "url": "https://a.example", "content": "Ausschnitt A"},
        {"title": "Zweites Ergebnis", "url": "https://b.example", "content": "Ausschnitt B"},
    ]}, gesehen=gesehen)
    client = WebSearchClient(searxng_url=f"http://127.0.0.1:{port}")

    treffer = client.search("testbegriff", limit=5)

    assert [t.title for t in treffer] == ["Erstes Ergebnis", "Zweites Ergebnis"]
    assert treffer[0].url == "https://a.example"
    assert "q=testbegriff" in gesehen[0]["path"]
    assert "format=json" in gesehen[0]["path"]


def test_searxng_begrenzt_auf_limit(fake_dienst):
    port = fake_dienst({"results": [{"title": f"T{i}", "url": "u", "content": ""}
                                    for i in range(10)]})
    client = WebSearchClient(searxng_url=f"http://127.0.0.1:{port}")
    treffer = client.search("x", limit=3)
    assert len(treffer) == 3


def test_searxng_ablehnung_wird_gemeldet(fake_dienst):
    port = fake_dienst({}, status=403)
    client = WebSearchClient(searxng_url=f"http://127.0.0.1:{port}")
    with pytest.raises(WebSearchError, match="403"):
        client.search("x")


def test_brave_baut_die_richtige_anfrage_und_header(monkeypatch):
    # Brave spricht fest api.search.brave.com an, kein lokal steuerbarer
    # Server wie beim SearXNG-Weg oben -- hier wird deshalb geprüft, WELCHE
    # Anfrage der Client stellen würde, statt eine echte Antwort abzuholen.
    gesehen = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"web": {"results": [
                {"title": "T", "url": "https://x.example", "description": "D"}]}}

    def fake_get(url, params=None, headers=None, timeout=None):
        gesehen["url"] = url
        gesehen["params"] = params
        gesehen["headers"] = headers
        return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    client = WebSearchClient(brave_api_key="mein-schluessel")
    treffer = client.search("testbegriff", limit=4)

    assert treffer[0].title == "T"
    assert gesehen["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert gesehen["params"] == {"q": "testbegriff", "count": 4}
    assert gesehen["headers"]["X-Subscription-Token"] == "mein-schluessel"


def test_searxng_wird_gegenueber_brave_bevorzugt(fake_dienst):
    # Wenn beides eingetragen ist, spricht der Client SearXNG an -- kein
    # Schlüssel, keine dritte Partei. Beleg: der SearXNG-Fake bekommt den
    # Treffer, obwohl auch ein (ungültiger) Brave-Schlüssel gesetzt ist.
    port = fake_dienst({"results": [{"title": "Von SearXNG", "url": "u", "content": ""}]})
    client = WebSearchClient(searxng_url=f"http://127.0.0.1:{port}", brave_api_key="k")

    treffer = client.search("x")

    assert treffer[0].title == "Von SearXNG"


def test_nicht_erreichbarer_dienst_wird_gemeldet():
    client = WebSearchClient(searxng_url="http://127.0.0.1:1")
    with pytest.raises(WebSearchError, match="nicht erreichbar"):
        client.search("x")
