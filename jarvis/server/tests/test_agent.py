"""Der ganze Zug — mit einem Modell, das lügt.

Das ist die eigentliche Regressionsprüfung dieses Projekts. Der Vorgänger
meldete eine erstellte ``gaming.txt``, die es nie gab. Hier wird genau dieses
Verhalten eines Modells simuliert, und geprüft wird beides:

* was der Nutzer zu sehen bekommt, und
* was auf der Festplatte liegt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis import guard
from jarvis.agent import Agent
from jarvis.ollama import ChatTurn, OllamaError, ToolCall


def make_agent(config, store, registry, model, events=None):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    return Agent(config, store, registry, model, emit=emit)


# ═══════════════════════════════════════════ das historische Fehlverhalten
async def test_modell_luegt_ueber_datei_nutzer_bekommt_absage(
        config, store, registry, workspace, fake_ollama):
    """Modell behauptet die Datei, ruft aber kein Werkzeug auf."""
    model = fake_ollama([ChatTurn(
        text="Die Datei gaming.txt wurde auf dem Desktop erstellt.")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("Leg mir was für Gaming an")

    assert reply.blocked is True
    assert reply.text == guard.REFUSAL
    assert reply.provenance == guard.FAIL
    # Und die Festplatte bestätigt es: nichts entstanden.
    assert list(workspace.iterdir()) == []


async def test_modell_luegt_ueber_befehl_nutzer_bekommt_absage(
        config, store, registry, fake_ollama):
    model = fake_ollama([ChatTurn(
        text="Die Überprüfung des Moduls ist erfolgreich abgeschlossen.")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("prüf mal memory.py")

    assert reply.blocked is True
    assert reply.text == guard.REFUSAL


async def test_verworfener_text_wird_gemeldet(config, store, registry, fake_ollama):
    """Der Wächter arbeitet nicht heimlich — das Ereignis ist beobachtbar."""
    events: list = []
    model = fake_ollama([ChatTurn(text="Ich habe die Datei erstellt.")])
    agent = make_agent(config, store, registry, model, events)

    await agent.handle("mach was")

    blocked = [p for k, p in events if k == "guard.blocked"]
    assert len(blocked) == 1
    assert "Ich habe die Datei erstellt." == blocked[0]["verworfen"]


# ═══════════════════════════════════════════════════ der ehrliche Weg
async def test_echter_werkzeugaufruf_erzeugt_datei_und_beleg(
        config, store, registry, workspace, fake_ollama):
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "notizen.txt"), "content": "Milch\nBrot"})]),
        ChatTurn(text="Die Datei notizen.txt liegt bereit."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("schreib mir eine Einkaufsliste")

    assert reply.provenance == guard.TOOL
    assert reply.blocked is False
    assert len(reply.results) == 1
    assert reply.results[0].ok is True
    # Der Beleg stimmt mit der Festplatte überein.
    target = workspace / "notizen.txt"
    assert target.read_text(encoding="utf-8") == "Milch\nBrot"
    assert reply.results[0].evidence["bytes"] == target.stat().st_size


async def test_fehlschlag_des_werkzeugs_schlaegt_auf_die_antwort_durch(
        config, store, registry, fake_ollama):
    """Werkzeug scheitert, Modell beschönigt — der echte Fehler gewinnt.

    Die Nachricht trägt bewusst keinen Dateinamen, sonst greift der Router und
    das Modell käme gar nicht erst zu Wort.
    """
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("read_file", {"path": "gibtsnicht.txt"})]),
        ChatTurn(text="Alles erledigt, ich habe die Datei gelesen."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("Schau mal nach, was in meiner Konfiguration steht")

    assert reply.provenance == guard.FAIL
    assert reply.blocked is True
    assert "existiert nicht" in reply.text


async def test_router_fehlschlag_meldet_den_echten_fehler(
        config, store, registry, fake_ollama):
    """Scheitert ein Direktbefehl, gibt es nichts zu beschönigen — und
    nichts zu verwerfen, weil das Modell gar nicht gefragt wurde."""
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("lies gibtsnicht.txt")

    assert model.calls == []
    assert reply.provenance == guard.FAIL
    assert reply.blocked is False
    assert "existiert nicht" in reply.text


async def test_erfundener_werkzeugname_wird_dem_modell_zurueckgemeldet(
        config, store, registry, fake_ollama):
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("mach_mal_screenshot", {})]),
        ChatTurn(text="Dafür habe ich kein Werkzeug."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("screenshot bitte")

    assert reply.provenance == guard.TALK
    # Das Modell hat die echte Werkzeugliste gesehen, statt stillschweigend
    # weiterzumachen.
    letzte = model.calls[-1]
    tool_antwort = [m for m in letzte if m.get("role") == "tool"][-1]
    assert "existiert nicht" in tool_antwort["content"]
    assert "write_file" in tool_antwort["content"]


async def test_reine_frage_braucht_kein_werkzeug(config, store, registry, fake_ollama):
    model = fake_ollama([ChatTurn(text="Python ist eine Programmiersprache.")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("Was ist Python?")

    assert reply.provenance == guard.TALK
    assert reply.blocked is False
    assert reply.text == "Python ist eine Programmiersprache."


# ═══════════════════════════════════════════════ Router, Gedächtnis, Ausfall
async def test_router_umgeht_das_modell_vollstaendig(
        config, store, registry, workspace, fake_ollama):
    """Ein eindeutiger Befehl wird ausgeführt, ohne das Modell zu fragen."""
    model = fake_ollama([ChatTurn(text="das darf nie gebraucht werden")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle(
        f"Erstelle eine Datei in {workspace} namens test.txt mit dem Inhalt Hallo Welt")

    assert model.calls == []          # das Modell wurde nicht einmal befragt
    assert reply.provenance == guard.TOOL
    assert (workspace / "test.txt").read_text(encoding="utf-8") == "Hallo Welt"


async def test_erinnerungen_landen_im_kontext(config, store, registry, fake_ollama):
    store.add(label="Lieblingseditor", kind="vorliebe", text="Der Nutzer arbeitet mit VS Code.")
    model = fake_ollama([ChatTurn(text="Alles klar.")])
    agent = make_agent(config, store, registry, model)

    await agent.handle("Womit arbeite ich am liebsten, welcher Lieblingseditor?")

    system_bloecke = [m["content"] for m in model.calls[0] if m["role"] == "system"]
    assert any("VS Code" in b for b in system_bloecke)


async def test_ollama_ausfall_wird_als_fehler_gemeldet_nicht_verschwiegen(
        config, store, registry):
    class Kaputt:
        async def chat(self, messages, tools=None):
            raise OllamaError("Verbindung abgelehnt")

    agent = make_agent(config, store, registry, Kaputt())
    reply = await agent.handle("Hallo")

    assert reply.provenance == guard.FAIL
    assert "nicht erreichbar" in reply.text


# ═════════════════════════════════════════════════════════ Code-Modus
async def test_code_modus_geht_direkt_ans_werkzeug_ohne_modell_zu_fragen(
        config, store, registry, fake_ollama):
    """Der Code-Modus ist bewusst vom Nutzer gewählt -- eindeutiger als jedes
    erkannte Muster im Text. Er geht daher immer direkt an codepilot_task,
    ohne das Chat-Modell überhaupt zu befragen."""
    from jarvis.tools.base import Tool, ToolResult
    registry.add(Tool("codepilot_task", "", {"type": "object", "properties": {}},
                      lambda task, project_id="": ToolResult(
                          tool="codepilot_task", ok=True,
                          summary="CodePilot fertig: 1 Datei geändert",
                          evidence={"dateien": 1})))
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_code("Schreib einen Test für die Pfadprüfung")

    assert model.calls == []
    assert reply.provenance == guard.TOOL
    assert reply.blocked is False
    assert "CodePilot fertig" in reply.text


async def test_code_modus_ohne_codepilot_ist_eine_ehrliche_absage(
        config, store, registry, fake_ollama):
    """registry hat standardmäßig kein codepilot_task, weil in der Test-
    Konfiguration kein CodePilot eingerichtet ist."""
    model = fake_ollama([])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_code("Bau mir eine Funktion, die X macht")

    assert model.calls == []
    assert reply.provenance == guard.FAIL
    assert "codepilot_task" in reply.text


async def test_code_modus_meldet_einen_echten_fehlschlag_ehrlich(
        config, store, registry, fake_ollama):
    from jarvis.tools.base import Tool, ToolResult
    registry.add(Tool("codepilot_task", "", {"type": "object", "properties": {}},
                      lambda task, project_id="": ToolResult(
                          tool="codepilot_task", ok=False,
                          summary="CodePilot nicht erreichbar")))
    agent = make_agent(config, store, registry, fake_ollama([]))

    reply = await agent.handle_code("Bau was")

    assert reply.provenance == guard.FAIL
    assert "nicht erreichbar" in reply.text


async def test_verlauf_bleibt_erhalten(config, store, registry, fake_ollama):
    model = fake_ollama([ChatTurn(text="Hallo."), ChatTurn(text="Ja.")])
    agent = make_agent(config, store, registry, model)

    await agent.handle("Hi")
    await agent.handle("Alles gut?")

    rollen = [m["role"] for m in model.calls[1]]
    assert rollen.count("user") == 2      # die erste Frage ist noch dabei
