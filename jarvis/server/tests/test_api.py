"""HTTP und WebSocket — inklusive des Falls, dass beide Geräte dasselbe sehen."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from jarvis.app import create_app
from jarvis.config import Config
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.permissions import PermissionPolicy
from jarvis.tools.base import Tool, ToolResult


@pytest.fixture
def client(config, monkeypatch, fake_ollama, workspace):
    """Server mit einem vorgegebenen Modell statt einem echten Ollama."""
    app = create_app(config)
    # Diese Datei prüft HTTP/WebSocket/Wächter, nicht das Permission-System
    # selbst (siehe test_permissions.py und test_agent_security.py) --
    # WRITE/SYSTEM laufen hier deshalb ohne Bestätigungs-Round-Trip durch.
    app.state.permission_gate.policy = PermissionPolicy(
        confirm_read=False, confirm_write=False, confirm_system=False)
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "aus_dem_test.txt"), "content": "ok"})]),
        ChatTurn(text="Die Datei liegt bereit."),
    ])
    app.state.agent.client = model
    app.state.model = model
    # Der Code-Modus benutzt seit dem Ausbau von CodePilot ein eigenes
    # Modell (``agent.code_client``). Hier bekommt es seine eigene Abfolge,
    # damit ein Code-Zug den Chat-Zug nicht aus dem Takt bringt.
    code_model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "aus_dem_code_modus.py"),
            "content": "def f():\n    return 1\n"})]),
        ChatTurn(text="Funktion angelegt."),
    ])
    app.state.agent.code_client = code_model
    app.state.code_model = code_model
    with TestClient(app) as test_client:
        test_client.app_state = app.state
        yield test_client


# ══════════════════════════════════════════════════════════════ Status
def test_health_ist_ohne_token_erreichbar(client):
    body = client.get("/api/health").json()
    assert body["model"]
    assert any(w["name"] == "write_file" and w["status"] == "ok"
               for w in body["werkzeuge"])


def test_health_nennt_chat_und_code_modell(client):
    """Beide Modelle gehen direkt an Ollama -- seit CodePilot raus ist, gibt
    es keine Kette mehr dazwischen, über die etwas 'via' laufen könnte."""
    modelle = client.get("/api/health").json()["modelle"]
    assert len(modelle) == 2
    assert all(m["via"] == "Ollama · direkt" for m in modelle)
    assert modelle[1]["id"] == "qwen3-coder:30b"


def test_health_traegt_whisper_configured(client):
    assert client.get("/api/health").json()["whisper_configured"] is False


# ══════════════════════════════════════════════════════════ Speech-to-Text
def test_whisper_schluessel_setzen_und_wieder_loeschen(client):
    gesetzt = client.put("/api/whisper/key", json={"api_key": "sk-test"}).json()
    assert gesetzt == {"konfiguriert": True}
    assert client.get("/api/health").json()["whisper_configured"] is True
    assert client.app_state.whisper.api_key == "sk-test"

    geloescht = client.put("/api/whisper/key", json={"api_key": "  "}).json()
    assert geloescht == {"konfiguriert": False}
    assert client.get("/api/health").json()["whisper_configured"] is False


def test_whisper_ohne_schluessel_meldet_ehrlich_den_fehler(client):
    res = client.post("/api/whisper/transcribe",
                      files={"audio": ("a.webm", b"\x00\x01", "audio/webm")})
    assert res.status_code == 502
    assert "Schlüssel" in res.json()["detail"]


def test_whisper_echtes_ergebnis_kommt_beim_client_an(client):
    client.app_state.whisper.api_key = "sk-test"

    def gefaelscht(audio, filename, content_type):
        assert audio == b"\x00\x01"
        return "mach eine Notiz"
    client.app_state.whisper.transcribe = gefaelscht

    res = client.post("/api/whisper/transcribe",
                      files={"audio": ("a.webm", b"\x00\x01", "audio/webm")})
    assert res.status_code == 200
    assert res.json() == {"text": "mach eine Notiz"}


def test_geplante_werkzeuge_stehen_als_fehlend_drin(client):
    werkzeuge = {w["name"]: w["status"] for w in client.get("/api/health").json()["werkzeuge"]}
    assert werkzeuge["screen_capture"] == "none"
    assert werkzeuge["run_command"] == "none"      # shell ist aus


def test_oberflaeche_wird_ausgeliefert(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "JARVIS" in res.text


def test_manifest_wird_ausgeliefert(client):
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Jarvis Core"
    assert body["display"] == "standalone"
    assert any(icon["sizes"] == "512x512" for icon in body["icons"])


def test_service_worker_wird_ausgeliefert(client):
    res = client.get("/service-worker.js")
    assert res.status_code == 200
    assert "CACHE" in res.text


def test_icon_wird_ausgeliefert(client):
    res = client.get("/icons/icon-192.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


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
def test_code_modus_ueber_http_geht_am_chat_modell_vorbei(client, workspace):
    body = client.post("/api/command",
                       json={"text": "bau was", "mode": "code"}).json()
    assert body["provenance"] == "tool"
    # Das Chat-Modell wurde nicht einmal gefragt.
    assert client.app_state.model.calls == []
    assert (workspace / "aus_dem_code_modus.py").exists()
    assert body["evidence"][0]["tool"] == "write_file"
    assert "aus_dem_code_modus.py" in body["text"]


def test_makro_modus_ueber_http_fuehrt_gespeichertes_makro_aus(client, workspace):
    """'macro' geht weder ans Chat- noch ans Code-Modell -- 'text' ist hier
    der Makroname, kein Auftrag zum Planen."""
    client.app_state.registry.call("automation.macro.create", {
        "name": "testlauf", "steps": [
            {"id": "s1", "kind": "tool", "tool": "write_file",
             "arguments": {"path": str(workspace / "aus_dem_makro.txt"),
                          "content": "vom makro"}}]})

    body = client.post("/api/command", json={"text": "testlauf", "mode": "macro"}).json()

    assert body["provenance"] == "tool"
    assert client.app_state.model.calls == []
    assert (workspace / "aus_dem_makro.txt").read_text(encoding="utf-8") == "vom makro"


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
        assert "aus_dem_code_modus.py" in antwort["text"]


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


def test_audit_log_ueber_http(client, workspace):
    client.post("/api/command", json={"text": "leg was an"})
    eintraege = client.get("/api/audit", params={"tool": "write_file"}).json()["eintraege"]
    assert len(eintraege) == 1
    assert eintraege[0]["erfolg"] is True
    assert eintraege[0]["stufe"] == "WRITE"


def test_undo_ueber_http_stellt_wieder_her(client, workspace):
    client.post("/api/command", json={"text": "leg was an"})
    ziel = workspace / "aus_dem_test.txt"
    assert ziel.exists()

    eintraege = client.get("/api/undo").json()["eintraege"]
    assert eintraege and eintraege[0]["rueckgaengig_gemacht"] is False

    rueckgaengig = client.post("/api/undo", json={}).json()
    assert "entfernt" in rueckgaengig["ergebnis"]
    assert not ziel.exists()


def test_undo_ohne_aufzeichnung_gibt_400(client):
    res = client.post("/api/undo", json={})
    assert res.status_code == 400


# ══════════════════════════════════════════════════════ Werkzeuge (Punkt 47)
def test_tools_ohne_suche_zeigt_den_katalog(client):
    body = client.get("/api/tools", params={"limit": 5}).json()
    assert len(body["werkzeuge"]) == 5
    assert body["gesamt_im_katalog"] > 300
    assert "git" in body["kategorien"]


def test_tools_mit_suche_liefert_dieselbe_rangfolge_wie_im_chat(client):
    body = client.get("/api/tools", params={"q": "git commit"}).json()
    assert body["werkzeuge"][0]["id"] == "git.commit"
    assert "punkte" in body["werkzeuge"][0]


def test_tools_kategorie_filter(client):
    body = client.get("/api/tools", params={"category": "git", "limit": 100}).json()
    assert body["werkzeuge"]
    assert all(w["kategorie"] == "git" for w in body["werkzeuge"])


def test_tool_favorisieren_taucht_im_katalog_auf(client):
    client.post("/api/tools/write_file/favorite")
    treffer = client.get("/api/tools", params={"q": "write_file"}).json()["werkzeuge"]
    ziel = next(w for w in treffer if w["id"] == "write_file")
    assert ziel["favorit"] is True


def test_tool_abschalten_und_wieder_anschalten_ueber_http(client):
    res = client.post("/api/tools/write_file/disable", json={"reason": "testweise"})
    assert res.status_code == 200
    treffer = client.get("/api/tools", params={"q": "write_file"}).json()["werkzeuge"]
    assert next(w for w in treffer if w["id"] == "write_file")["abgeschaltet"] is True

    client.post("/api/tools/write_file/enable")
    treffer2 = client.get("/api/tools", params={"q": "write_file"}).json()["werkzeuge"]
    assert next(w for w in treffer2 if w["id"] == "write_file")["abgeschaltet"] is False


def test_tool_wirklich_abgeschaltet_ueber_http_wirkt_auch_im_chat(client, workspace):
    """Derselbe Weg wie jarvis.tools.disable, nur über HTTP -- muss also
    auch denselben Effekt auf einen echten Zug haben: die Datei entsteht
    nicht, und der Beleg nennt den echten Grund."""
    client.post("/api/tools/write_file/disable")
    body = client.post("/api/command", json={"text": "leg was an"}).json()
    assert body["provenance"] == "fail"
    assert "abgeschaltet" in body["evidence"][0]["summary"]
    assert not (workspace / "aus_dem_test.txt").exists()


def test_unbekanntes_werkzeug_ueber_http_ist_404(client):
    res = client.post("/api/tools/das.gibt.es.nicht/favorite")
    assert res.status_code == 404


def test_unfavorite_ohne_vorherigen_favorit_ist_409(client):
    res = client.post("/api/tools/write_file/unfavorite")
    assert res.status_code == 409


def test_sich_selbst_abschalten_ueber_http_ist_verboten(client):
    res = client.post("/api/tools/jarvis.tools.enable/disable")
    assert res.status_code == 400


def test_tool_disable_ueber_http_loest_alias_auf(client):
    client.post("/api/tools/get_system_info/disable")
    treffer = client.get("/api/tools", params={"q": "system.info"}).json()["werkzeuge"]
    ziel = next(w for w in treffer if w["id"] == "system.info")
    assert ziel["abgeschaltet"] is True


def test_permission_resolve_unbekannte_anfrage(client):
    res = client.post("/api/permission/resolve",
                      json={"request_id": "nie-gestellt", "approved": True})
    assert res.json() == {"gefunden": False}


def test_ereignis_liefert_einen_vorschlag_mit_bestaetigbarer_id(client):
    """Die id aus der Antwort muss dieselbe sein, die ``/api/proactive`` kennt
    -- sonst laeuft jede Zustimmung ins Leere."""
    antwort = client.post("/api/events", json={
        "kind": "process.crashed", "severity": "warning",
        "payload": {"name": "Minecraft-Server"}}).json()

    assert antwort["reaktion"] == "vorschlag"
    vorschlag = antwort["vorschlag"]
    assert "Minecraft-Server" in vorschlag["ziel"]
    # Unklare Ursache -> Jarvis fragt (Punkt 9).
    assert vorschlag["braucht_zustimmung"] is True

    offen = client.get("/api/events").json()["offene_vorschlaege"]
    assert [v["id"] for v in offen] == [vorschlag["id"]]

    # Ablehnen heisst: nichts passiert, und der Vorschlag ist weg.
    abgelehnt = client.post(f"/api/proactive/{vorschlag['id']}",
                            json={"approved": False}).json()
    assert abgelehnt == {"gestartet": False, "ziel": None}
    assert client.get("/api/events").json()["offene_vorschlaege"] == []


def test_ereignis_ohne_regel_loest_nichts_aus(client):
    antwort = client.post("/api/events", json={"kind": "nichts.bekanntes"}).json()
    assert antwort["reaktion"] == "keine"
    assert antwort["vorschlag"] is None
    assert antwort["ereignis"]["art"] == "nichts.bekanntes"


def test_unbekannter_vorschlag_gibt_404(client):
    res = client.post("/api/proactive/nie-vorgeschlagen", json={"approved": True})
    assert res.status_code == 404


def test_steuerung_eines_nicht_laufenden_ziels_gibt_409(client):
    """Ehrlich statt hoeflich: was nicht laeuft, laesst sich nicht pausieren."""
    ziel = client.app.state.goals.create("nur abgelegt, laeuft nicht")
    res = client.post(f"/api/goals/{ziel.id}/pause")
    assert res.status_code == 409
    assert client.post("/api/goals/gibtsnicht/cancel").status_code == 404


def _warte_auf_ziel(test_client, goal_id: str, endstati=("completed", "failed",
                                                          "blocked", "cancelled")) -> dict:
    """Der Agent-Modus antwortet seit Autonomy V1 sofort und arbeitet im
    Hintergrund weiter -- also wird auf den echten Endzustand gewartet, statt
    ihn anzunehmen."""
    for _ in range(200):
        ziel = test_client.get(f"/api/goals/{goal_id}").json()
        if ziel["status"] in endstati:
            return ziel
        time.sleep(0.02)
    raise AssertionError(f"Ziel {goal_id} ist nicht fertig geworden: {ziel['status']}")


def test_agent_modus_zerlegt_und_fuehrt_aus(config, fake_ollama, workspace):
    """Eigene App-Instanz: der Agent-Modus braucht eine andere Abfolge von
    Modell-Antworten als die anderen HTTP-Tests in dieser Datei.

    Seit Autonomy V1 läuft ein Ziel im Hintergrund (Punkt 7). Die Antwort auf
    ``/api/command`` ist deshalb bewusst nur eine Zwischenmeldung ohne
    Werkzeugbeleg -- sie behauptet nichts über ein Ergebnis. Das Ergebnis
    steht danach im Ziel und in der Aufgabe."""
    config.autonomy_level = 3  # Zielverfolgung erfordert Autonomiestufe 3
    app = create_app(config)
    app.state.permission_gate.policy = PermissionPolicy(
        confirm_read=False, confirm_write=False, confirm_system=False)
    model = fake_ollama([
        ChatTurn(text='["Systeminfo lesen"]'),                  # Planner
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),  # Schritt 1
        ChatTurn(text="System geprüft."),
    ])
    app.state.agent.client = model

    with TestClient(app) as test_client:
        body = test_client.post(
            "/api/command", json={"text": "Prüfe das System", "mode": "agent"}).json()
        assert body["provenance"] == "talk"  # Zwischenmeldung, kein Ergebnis
        assert "Prüfe das System" in body["text"]

        ziele = test_client.get("/api/goals").json()["ziele"]
        assert len(ziele) == 1
        ziel = _warte_auf_ziel(test_client, ziele[0]["id"])
        assert ziel["status"] == "completed"
        assert ziel["fortschritt"] == 1.0

        aufgaben = test_client.get("/api/tasks").json()["aufgaben"]
        assert len(aufgaben) == 1
        assert aufgaben[0]["status"] == "completed"
        assert aufgaben[0]["schritte"][0]["status"] == "done"
        assert aufgaben[0]["id"] in ziel["unteraufgaben"]

        einzeln = test_client.get(f"/api/tasks/{aufgaben[0]['id']}").json()
        assert einzeln["id"] == aufgaben[0]["id"]

        assert test_client.get("/api/tasks/nie-gesehen").status_code == 404


def test_websocket_ohne_token_wird_geschlossen(config):
    config.token = "geheim"
    with TestClient(create_app(config)) as unauth:
        with pytest.raises(Exception):
            with unauth.websocket_connect("/ws") as ws:
                ws.receive_json()
