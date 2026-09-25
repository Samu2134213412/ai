"""Der ganze Zug — mit einem Modell, das lügt.

Das ist die eigentliche Regressionsprüfung dieses Projekts. Der Vorgänger
meldete eine erstellte ``gaming.txt``, die es nie gab. Hier wird genau dieses
Verhalten eines Modells simuliert, und geprüft wird beides:

* was der Nutzer zu sehen bekommt, und
* was auf der Festplatte liegt.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis import guard
from jarvis.agent import Agent
from jarvis.autonomy import AutonomyLevel
from jarvis.ollama import ChatTurn, OllamaError, ToolCall
from jarvis.permissions import PermissionGate, PermissionPolicy

#: Diese Datei prüft den Zug (Router/Modell/Wächter/Verlauf), nicht das
#: Permission-System -- das hat seine eigene, ausführliche Prüfung in
#: test_permissions.py und die Verzahnung in test_agent_security.py. Ohne
#: diese durchlässige Police würde jeder WRITE/SYSTEM-Aufruf hier bis zum
#: Timeout auf eine nie kommende Bestätigung warten.
_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, events=None):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    gate = PermissionGate(policy=_DURCHLAESSIG, emit=emit)
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate)


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


async def test_leere_modellantwort_ohne_werkzeug_ist_keine_stumme_antwort(
        config, store, registry, fake_ollama):
    """Ein 'denkendes' Modell kann ohne Werkzeugaufruf leeren Text liefern --
    z. B. wenn der Kontext für die eigentliche Antwort nicht mehr reichte.
    Das darf nicht als leere Sprechblase im Verlauf landen."""
    model = fake_ollama([ChatTurn(text="")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("Wie spät ist es ungefähr in Berlin?")

    assert reply.text.strip() != ""
    assert reply.provenance == guard.TALK
    assert reply.blocked is False


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
async def test_code_modus_aendert_die_datei_wirklich(
        config, store, registry, workspace, fake_ollama):
    """Der Code-Modus ist bewusst vom Nutzer gewählt -- eindeutiger als jedes
    erkannte Muster im Text. Er geht daher direkt an das Code-Modell, mit
    Jarvis' eigenen Werkzeugen, und prüft danach nach."""
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("read_file", {"path": str(ziel)})]),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_code("Lass f() 42 zurückgeben")

    assert ziel.read_text(encoding="utf-8") == "def f():\n    return 42\n"
    assert reply.provenance == guard.TOOL
    assert "modul.py" in reply.text
    assert "Syntax geprüft" in reply.text


async def test_code_modus_meldet_kaputte_syntax_statt_erfolg(
        config, store, registry, workspace, fake_ollama):
    """Das Modell sagt "fertig", die geschriebene Datei ist aber kaputt.
    Dann ist das Ergebnis ein Fehlschlag -- kein Erfolg mit Fußnote."""
    ziel = workspace / "kaputt.py"
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f(:\n    return\n"})]),
        ChatTurn(text="Alles erledigt!"),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_code("Bau die Funktion")

    assert reply.provenance == guard.FAIL
    # Der Wächter ersetzt die Zusammenfassung durch seine eigene ehrliche
    # Fassung -- die den Grund trotzdem beim Namen nennt.
    assert "kaputt.py" in reply.text
    assert "invalid syntax" in reply.text
    assert "Alles erledigt" not in reply.text


async def test_code_modus_merkt_sich_echte_aenderungen_im_wissensnetz(
        config, store, registry, workspace, fake_ollama):
    """Der eigentliche Fehler, den dieser Test nachbildet: der Code-Modus
    konnte frühere Arbeit nicht "lesen", weil er nie etwas darüber im
    Langzeitgedächtnis ablegte -- ``_run_tool_loop`` ruft vor jedem Auftrag
    zwar schon ``store.context_for()`` ab (wie im Chat), aber ohne einen
    Eintrag, den das findet, bleibt der Abruf leer. Nach einer echten
    Dateiänderung muss jetzt ein "projekt"-Knoten mit dem echten Pfad im
    Wissensnetz stehen -- demselben, das der Nutzer in der Oberfläche sieht
    und von Hand bearbeiten kann."""
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    agent = make_agent(config, store, registry, model)

    await agent.handle_code("Lass f() 42 zurückgeben")

    treffer = store.search("f() 42 zurückgeben")
    assert treffer, "kein Wissensnetz-Eintrag für die echte Änderung angelegt"
    projekt = treffer[0]
    assert projekt.kind == "projekt"
    assert str(ziel) in projekt.text


async def test_code_modus_ohne_dateiaenderung_legt_nichts_ab(
        config, store, registry, fake_ollama):
    """Nur eine Frage, keine echte Änderung -- keine Projekt-Erinnerung.
    Sonst würde das Wissensnetz mit leeren Einträgen zumüllen."""
    model = fake_ollama([ChatTurn(text="Sieht gut aus, keine Änderung nötig.")])
    agent = make_agent(config, store, registry, model)
    vorher = len(store.all())

    await agent.handle_code("Schau dir die Datei an")

    assert len(store.all()) == vorher


async def test_code_modus_findet_vorige_arbeit_beim_naechsten_auftrag(
        config, store, registry, workspace, fake_ollama):
    """Der eigentliche Nutzen im Zusammenspiel: ein zweiter Code-Auftrag mit
    verwandtem Wortlaut bekommt die zuvor gespeicherte Projekt-Erinnerung
    tatsächlich in den Kontext gereicht -- also genau das, was als "kann
    nicht lesen, was ich vorher geschrieben habe" gemeldet wurde."""
    ziel = workspace / "rechner.py"
    ziel.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    erster_lauf = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def add(a, b):\n    return a + b  # v2\n"})]),
        ChatTurn(text="Kommentar ergänzt."),
    ])
    agent = make_agent(config, store, registry, erster_lauf)
    await agent.handle_code("Kommentiere die Funktion in rechner.py")

    gesehene_systemnachrichten: list[str] = []

    class AufzeichnendesModell:
        async def chat(self, messages, tools=None):
            gesehene_systemnachrichten.extend(
                m["content"] for m in messages if m["role"] == "system")
            return ChatTurn(text="(nur geprüft, was das Modell zu sehen bekommt)")

    agent.code_client = AufzeichnendesModell()
    await agent.handle_code("Arbeite weiter an rechner.py")

    assert any("rechner.py" in block for block in gesehene_systemnachrichten), (
        "die frühere Arbeit an rechner.py wurde dem Modell nicht als Kontext gereicht")


async def test_code_modus_ohne_werkzeugaufruf_behauptet_nichts(
        config, store, registry, fake_ollama):
    """Das Modell redet nur und ruft kein Werkzeug auf. Dann darf am Ende
    keine Änderung gemeldet werden -- der Wächter greift wie überall."""
    model = fake_ollama([ChatTurn(text="Ich habe die Datei angepasst.")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_code("Ändere irgendwas")

    assert reply.provenance != guard.TOOL
    assert reply.blocked is True
    assert "angepasst" not in reply.text


async def test_code_modus_bekommt_nur_die_code_werkzeuge(
        config, store, registry, fake_ollama):
    """Ein Code-Auftrag braucht Dateien und Suche, nicht den ganzen Katalog.
    Weniger Werkzeuge heißt mehr Platz für den eigentlichen Code."""
    from jarvis import coder
    model = fake_ollama([ChatTurn(text="nichts zu tun")])
    agent = make_agent(config, store, registry, model)

    await agent.handle_code("Schau dir das Projekt an")

    assert model.tool_schemas, "Es wurden gar keine Werkzeuge mitgeschickt"
    angeboten = {s["function"]["name"] for s in model.tool_schemas[0]}
    assert "read_file" in angeboten and "write_file" in angeboten
    assert angeboten <= set(coder.CODE_TOOLS)
    assert "memory_add" not in angeboten
    assert len(angeboten) < len(registry)


async def test_code_modus_meldet_ein_nicht_erreichbares_modell_ehrlich(
        config, store, registry):
    class ToterDraht:
        async def chat(self, messages, tools=None):
            from jarvis.ollama import OllamaError
            raise OllamaError("Verbindung abgelehnt")

    agent = make_agent(config, store, registry, ToterDraht())

    reply = await agent.handle_code("Bau was")

    assert reply.provenance == guard.FAIL
    assert "Code-Modell ist nicht erreichbar" in reply.text


async def test_verlauf_bleibt_erhalten(config, store, registry, fake_ollama):
    model = fake_ollama([ChatTurn(text="Hallo."), ChatTurn(text="Ja.")])
    agent = make_agent(config, store, registry, model)

    await agent.handle("Hi")
    await agent.handle("Alles gut?")

    rollen = [m["role"] for m in model.calls[1]]
    assert rollen.count("user") == 2      # die erste Frage ist noch dabei


# ═══════════════════════════════════════════════════════════ Fokus-Modus
#: Anders als ``_DURCHLAESSIG`` oben: die echte Vorgabe-Policy
#: (confirm_write=True). Nur damit beweist ein Test, dass Fokus-Modus
#: tatsächlich etwas bewirkt -- mit der durchlässigen Policy würde ein WRITE
#: auch ganz ohne Fokus-Modus sofort durchlaufen.
_STRENG = PermissionPolicy(confirm_read=False, confirm_write=True, confirm_system=True,
                           confirmation_timeout=0.05)


def make_strict_agent(config, store, registry, model, events=None):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    gate = PermissionGate(policy=_STRENG, emit=emit)
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate)


async def test_ohne_fokus_modus_wartet_write_auf_eine_bestaetigung_die_nie_kommt(
        config, store, registry, workspace, fake_ollama):
    """Die Gegenprobe: ohne Fokus-Modus gilt die normale, strenge Policy --
    niemand bestätigt, also läuft die Bestätigung in die Zeitüberschreitung
    und write_file schlägt fehl. Beweist, dass der folgende Fokus-Modus-Test
    tatsächlich etwas Echtes umgeht, statt gegen eine ohnehin durchlässige
    Policy zu laufen."""
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    agent = make_strict_agent(config, store, registry, model)

    reply = await agent.handle_code("Lass f() 42 zurückgeben", focus=False)

    assert reply.provenance == guard.FAIL
    assert ziel.read_text(encoding="utf-8") == "def f():\n    return 1\n"  # unverändert


async def test_fokus_modus_schreibt_ohne_auf_bestaetigung_zu_warten(
        config, store, registry, workspace, fake_ollama):
    """Der eigentliche Prüfpunkt: derselbe strenge Aufbau wie eben, aber mit
    focus=True -- die Datei entsteht sofort, ohne permission.requested."""
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    events: list = []
    agent = make_strict_agent(config, store, registry, model, events)

    reply = await agent.handle_code("Lass f() 42 zurückgeben", focus=True)

    assert reply.provenance == guard.TOOL
    assert ziel.read_text(encoding="utf-8") == "def f():\n    return 42\n"
    angefragt = [k for k, _ in events if k.startswith("permission.")]
    assert angefragt == [], f"Fokus-Modus hätte keine Bestätigung anfragen dürfen: {angefragt}"


async def test_focus_mode_schalter_wirkt_auch_ohne_expliziten_parameter(
        config, store, registry, workspace, fake_ollama):
    """set_focus_mode() ist der interaktive Schalter -- handle_code() ohne
    focus=... folgt ihm."""
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    agent = make_strict_agent(config, store, registry, model)

    an = await agent.set_focus_mode(True)
    assert an is True
    reply = await agent.handle_code("Lass f() 42 zurückgeben")

    assert reply.provenance == guard.TOOL
    assert ziel.read_text(encoding="utf-8") == "def f():\n    return 42\n"


async def test_set_focus_mode_meldet_den_zustand_als_ereignis(config, store, registry):
    events: list = []
    agent = make_strict_agent(config, store, registry, model=None, events=events)

    await agent.set_focus_mode(True)
    await agent.set_focus_mode(False)

    fokus_ereignisse = [p for k, p in events if k == "focus_mode"]
    assert fokus_ereignisse == [{"an": True}, {"an": False}]


# ═════════════════════════════════════════════════════ Erweiterungsmodus
async def test_erweiterungsmodus_braucht_autonomiestufe_3(config, store, registry, fake_ollama):
    """Vorgabe ist Stufe 2 (LOCAL_ACTIONS) -- eine unbeaufsichtigte,
    bestätigungsfreie Dauerschleife braucht mindestens dieselbe Stufe wie
    eigenständige Zielverfolgung."""
    model = fake_ollama([])
    agent = make_agent(config, store, registry, model)

    reply = await agent.start_extension_mode()

    assert "Stufe 3" in reply.text
    assert agent.extension_status is None


async def test_erweiterungsmodus_plant_und_erledigt_eine_echte_aufgabe(
        config, store, registry, workspace, fake_ollama, monkeypatch):
    import jarvis.agent as agent_module
    monkeypatch.setattr(agent_module, "_EXTENSION_PAUSE_SECONDS", 30.0)
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    ziel = workspace / "modul.py"
    ziel.write_text("def f():\n    return 1\n", encoding="utf-8")

    planer = fake_ollama([ChatTurn(text="Lass f() in modul.py 42 zurückgeben.")])
    coder_modell = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel), "content": "def f():\n    return 42\n"})]),
        ChatTurn(text="Rückgabewert angepasst."),
    ])
    events: list = []
    agent = make_agent(config, store, registry, planer, events)
    agent.code_client = coder_modell

    reply = await agent.start_extension_mode()
    assert "gestartet" in reply.text
    assert agent.extension_status is not None
    runner = next(iter(agent._runners))

    for _ in range(300):
        if any(k == "message" for k, _ in events):
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("keine Runde des Erweiterungsmodus beobachtet")

    agent.stop_extension_mode()
    await asyncio.wait_for(runner, timeout=2)

    assert ziel.read_text(encoding="utf-8") == "def f():\n    return 42\n"
    nachrichten = [p for k, p in events if k == "message"]
    assert nachrichten[0]["provenance"] == guard.TOOL
    aufgaben = [p for k, p in events if k == "extension.task"]
    assert aufgaben and "42" in aufgaben[0]["auftrag"]
    assert agent.extension_status is None


async def test_erweiterungsmodus_stoppt_nach_wiederholten_fehlschlaegen(
        config, store, registry, fake_ollama, monkeypatch):
    import jarvis.agent as agent_module
    monkeypatch.setattr(agent_module, "_EXTENSION_PAUSE_SECONDS", 0.0)
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    # Immer "keine Aufgabe" -- nie echter Fortschritt, muss also nach
    # _EXTENSION_FAILURE_LIMIT Runden von selbst anhalten.
    planer = fake_ollama([ChatTurn(text="KEINE AUFGABE")] * 10)
    events: list = []
    agent = make_agent(config, store, registry, planer, events)

    await agent.start_extension_mode()
    runner = next(iter(agent._runners))
    await asyncio.wait_for(runner, timeout=5)

    gestoppt = [p for k, p in events if k == "extension.stopped"]
    assert gestoppt
    assert str(agent_module._EXTENSION_FAILURE_LIMIT) in gestoppt[0]["grund"]
    assert agent.extension_status is None


async def test_stop_extension_mode_unterbricht_die_wartezeit_statt_sie_abzusitzen(
        config, store, registry, fake_ollama, monkeypatch):
    import jarvis.agent as agent_module
    # Absichtlich lang -- ohne einen echten, unterbrechbaren Abbruch würde
    # dieser Test entsprechend lange brauchen, statt in Millisekunden fertig
    # zu sein.
    monkeypatch.setattr(agent_module, "_EXTENSION_PAUSE_SECONDS", 30.0)
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    planer = fake_ollama([ChatTurn(text="KEINE AUFGABE")])
    agent = make_agent(config, store, registry, planer)

    await agent.start_extension_mode()
    runner = next(iter(agent._runners))
    await asyncio.sleep(0.05)  # eine Runde durchlaufen lassen, jetzt in der Pause
    assert agent.extension_status is not None

    assert agent.stop_extension_mode() is True
    await asyncio.wait_for(runner, timeout=2)  # nicht erst nach 30s

    assert agent.extension_status is None


async def test_start_extension_mode_lehnt_doppelten_start_ab(
        config, store, registry, fake_ollama, monkeypatch):
    import jarvis.agent as agent_module
    monkeypatch.setattr(agent_module, "_EXTENSION_PAUSE_SECONDS", 30.0)
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    planer = fake_ollama([ChatTurn(text="KEINE AUFGABE")])
    agent = make_agent(config, store, registry, planer)

    await agent.start_extension_mode()
    laeuft_schon = len(agent._runners)
    zweite = await agent.start_extension_mode()

    assert "läuft schon" in zweite.text
    assert len(agent._runners) == laeuft_schon  # kein zweiter Runner entstanden

    agent.stop_extension_mode()
    await asyncio.wait_for(next(iter(agent._runners)), timeout=2)


async def test_plan_extension_task_erkennt_keine_aufgabe(config, store, registry, fake_ollama):
    planer = fake_ollama([ChatTurn(text="KEINE AUFGABE")])
    agent = make_agent(config, store, registry, planer)

    assert await agent._plan_extension_task() == ""


async def test_plan_extension_task_gibt_den_vorschlag_zurueck(config, store, registry, fake_ollama):
    planer = fake_ollama([ChatTurn(text="  Schreibe einen Test für die Pfadprüfung.  ")])
    agent = make_agent(config, store, registry, planer)

    assert await agent._plan_extension_task() == "Schreibe einen Test für die Pfadprüfung."
