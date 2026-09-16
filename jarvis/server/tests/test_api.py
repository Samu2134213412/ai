"""HTTP und WebSocket — inklusive des Falls, dass beide Geräte dasselbe sehen."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from jarvis.app import create_app
from jarvis.config import Config
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.tools.base import Tool, ToolResult


@pytest.fixture
def client(config, monkeypatch, fake_ollama, workspace):
    """Server mit einem vorgegebenen Modell statt einem echten Ollama."""
    app = create_app(config)
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "aus_dem_test.txt"), "content": "ok"})]),
        ChatTurn(text="Die Datei liegt bereit."),
    ])
    app.state.agent.client = model
    app.state.model = model
    # Ein gefälschtes codepilot_task, um den Code-Modus zu prüfen, ohne
    # echtes CodePilot zu brauchen.
    app.state.registry.add(Tool(
        "codepilot_task", "", {"type": "object", "properties": {}},
        lambda task, project_id="": ToolResult(
            tool="codepilot_task", ok=True,
            summary="CodePilot fertig: 1 Datei geändert", evidence={"dateien": 1})))
    with TestClient(app) as test_client:
        test_client.app_state = app.state
        yield test_client


# ══════════════════════════════════════════════════════════════ Status
def test_health_ist_ohne_token_erreichbar(client):
    body = client.get("/api/health").json()
    assert body["model"]
    assert any(w["name"] == "write_file" and w["status"] == "ok"
               for w in body["werkzeuge"])


def test_geplante_werkzeuge_stehen_als_fehlend_drin(client):
    werkzeuge = {w["name"]: w["status"] for w in client.get("/api/health").json()["werkzeuge"]}
    assert werkzeuge["screen_capture"] == "none"
    assert werkzeuge["run_command"] == "none"      # shell ist aus


def test_oberflaeche_wird_ausgeliefert(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "JARVIS" in res.text


# ══════════════════════════════════════════════════════════════ Zugang
def test_token_wird_erzwungen_wenn_gesetzt(config):
    config.token = "geheim"
    with TestClient(create_app(config)) as unauth:
        assert unauth.get("/api/memory").status_code == 401
        assert unauth.get("/api/memory", params={"token": "geheim"}).status_code == 200
        assert unauth.get("/api/memory",
                          headers={"Authorization": "Bearer geheim"}).status_code == 200


def test_offener_bind_ohne_token_wird_abgelehnt_nicht_geoeffnet(config):
    """Aus dem Netz erreichbar und ohne Token: 503, nicht offen."""
    config.host = "0.0.0.0"  # noqa: S104 - genau das ist der Prüffall
    config.token = ""
    with TestClient(create_app(config)) as open_client:
        assert open_client.get("/api/memory").status_code == 503
    assert any("kein token" in p.lower() for p in config.validate())


# ══════════════════════════════════════════════════════════════ Gedächtnis
def test_gedaechtnis_lesen_und_schreiben(client):
    graph = {"nodes": [{"id": "a", "label": "Kaffee", "cat": "vorliebe", "text": "schwarz"},
                       {"id": "b", "label": "Tee", "cat": "vorliebe", "text": ""}],
             "links": [["a", "b"]]}
    assert client.put("/api/memory", json=graph).json()["gespeichert"] == 2
    zurueck = client.get("/api/memory").json()
    assert {n["label"] for n in zurueck["nodes"]} == {"Kaffee", "Tee"}
    assert zurueck["links"] == [["a", "b"]]


def test_kanten_ins_nichts_werden_verworfen(client):
    graph = {"nodes": [{"id": "a", "label": "Allein", "cat": "fakt"}],
             "links": [["a", "gibtsnicht"]]}
    client.put("/api/memory", json=graph)
    assert client.get("/api/memory").json()["links"] == []


def test_gedaechtnissuche(client):
    client.put("/api/memory", json={
        "nodes": [{"id": "a", "label": "Lieblingseditor", "cat": "vorliebe",
                   "text": "Der Nutzer arbeitet mit VS Code"}], "links": []})
    treffer = client.get("/api/memory/search", params={"q": "Lieblingseditor"}).json()["treffer"]
    assert treffer and treffer[0]["label"] == "Lieblingseditor"


# ══════════════════════════════════════════════════════════════ Ein Zug
def test_code_modus_ueber_http_geht_am_chat_modell_vorbei(client):
    body = client.post("/api/command",
                       json={"text": "bau was", "mode": "code"}).json()
    assert body["provenance"] == "tool"
    assert "CodePilot fertig" in body["text"]
    assert body["evidence"][0]["tool"] == "codepilot_task"


def test_kommando_ueber_http_liefert_beleg(client, workspace):
    body = client.post("/api/command", json={"text": "leg was an"}).json()
    assert body["provenance"] == "tool"
    assert body["evidence"][0]["tool"] == "write_file"
    assert (workspace / "aus_dem_test.txt").read_text(encoding="utf-8") == "ok"


def test_websocket_meldet_zustand_und_antwort(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert "gedaechtnis" in hello

        ws.send_json({"type": "command", "text": "leg was an"})
        kinds, message = [], None
        for _ in range(30):
            frame = ws.receive_json()
            kinds.append(frame["type"])
            if frame["type"] == "message" and frame.get("who") == "jarvis":
                message = frame
                break
        assert "state" in kinds          # der Kern hat den Zustand gewechselt
        assert "tool.started" in kinds   # und ein Werkzeug lief wirklich
        assert message["provenance"] == "tool"


def test_code_modus_ueber_websocket(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "command", "text": "bau was", "mode": "code"})
        antwort = None
        for _ in range(30):
            frame = ws.receive_json()
            if frame["type"] == "message" and frame.get("who") == "jarvis":
                antwort = frame
                break
        assert antwort is not None
        assert antwort["provenance"] == "tool"
        assert "CodePilot fertig" in antwort["text"]


def test_beide_geraete_sehen_denselben_zug(client):
    """Ein Zug geht an alle offenen Verbindungen — PC und Handy zugleich."""
    with client.websocket_connect("/ws") as pc, client.websocket_connect("/ws") as handy:
        pc.receive_json()
        handy.receive_json()
        pc.send_json({"type": "command", "text": "leg was an"})

        def warte_auf_antwort(ws):
            for _ in range(30):
                frame = ws.receive_json()
                if frame["type"] == "message" and frame.get("who") == "jarvis":
                    return frame
            return None

        am_pc = warte_auf_antwort(pc)
        am_handy = warte_auf_antwort(handy)
        assert am_pc is not None and am_handy is not None
        assert am_pc["text"] == am_handy["text"]


def test_unerwarteter_fehler_bleibt_nicht_stumm(client):
    """Der Zug läuft als Hintergrund-Task (fire-and-forget) -- eine
    unerwartete Ausnahme darin darf nicht lautlos verschwinden, sonst starrt
    der Nutzer für immer auf 'Denke'."""
    async def kaputt(text):
        raise RuntimeError("überraschung")
    client.app_state.agent.handle = kaputt

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "command", "text": "Hallo"})
        antwort = None
        for _ in range(30):
            frame = ws.receive_json()
            if frame["type"] == "message" and frame.get("who") == "jarvis":
                antwort = frame
                break
        assert antwort is not None
        assert antwort["provenance"] == "fail"
        assert "überraschung" in antwort["text"]


def test_websocket_ohne_token_wird_geschlossen(config):
    config.token = "geheim"
    with TestClient(create_app(config)) as unauth:
        with pytest.raises(Exception):
            with unauth.websocket_connect("/ws") as ws:
                ws.receive_json()
