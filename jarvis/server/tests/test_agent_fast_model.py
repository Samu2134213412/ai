"""Das schnelle, zweite Modell: Jarvis entscheidet selbst, welches Modell
eine Nachricht bekommt.

Ohne ``fast_client`` läuft alles wie vorher über das Hauptmodell (siehe
test_agent.py) -- das ist hier bewusst nicht nochmal geprüft. Diese Datei
prüft nur das Neue: dass eine einfache Frage tatsächlich beim kleinen Modell
landet, eine komplexe Aufgabe beim großen bleibt, ein nicht erreichbares
schnelles Modell nicht die ganze Antwort kostet -- und dass eine Lüge des
kleinen Modells vom Wächter genauso abgefangen wird wie eine des großen.
"""

from __future__ import annotations

import pytest

from jarvis import guard
from jarvis.agent import Agent
from jarvis.ollama import ChatTurn
from jarvis.permissions import PermissionGate, PermissionPolicy

_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, fast_model=None):
    async def emit(kind, payload):
        pass
    gate = PermissionGate(policy=_DURCHLAESSIG, emit=emit)
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate,
                fast_client=fast_model)


async def test_einfache_frage_geht_ans_schnelle_modell(config, store, registry, fake_ollama):
    hauptmodell = fake_ollama([ChatTurn(text="DIES DARF NIE BENUTZT WERDEN")])
    schnelles_modell = fake_ollama([ChatTurn(text="Die Hauptstadt von Frankreich ist Paris.")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=schnelles_modell)

    reply = await agent.handle("Was ist die Hauptstadt von Frankreich?")

    assert hauptmodell.calls == []
    assert len(schnelles_modell.calls) == 1
    # Ohne Werkzeugschema -- das kleine Modell bekommt gar nicht erst die
    # Gelegenheit, unzuverlässig ein Werkzeug aufzurufen.
    assert schnelles_modell.tool_schemas[0] == []
    assert reply.text == "Die Hauptstadt von Frankreich ist Paris."
    assert reply.provenance == guard.TALK


async def test_komplexe_aufgabe_bleibt_beim_hauptmodell(config, store, registry, fake_ollama):
    hauptmodell = fake_ollama([ChatTurn(text="Klar, hier ist ein Ansatz für das Skript.")])
    schnelles_modell = fake_ollama([ChatTurn(text="DIES DARF NIE BENUTZT WERDEN")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=schnelles_modell)

    reply = await agent.handle("Schreib mir ein Python-Skript, das Primzahlen berechnet")

    assert schnelles_modell.calls == []
    assert len(hauptmodell.calls) == 1
    assert reply.text == "Klar, hier ist ein Ansatz für das Skript."


async def test_schnelles_modell_nicht_erreichbar_faellt_auf_hauptmodell_zurueck(
        config, store, registry, fake_ollama):
    from jarvis.ollama import OllamaError

    class _KaputtesModell:
        calls: list = []

        async def chat(self, messages, tools=None):
            raise OllamaError("Ollama nicht erreichbar")

    hauptmodell = fake_ollama([ChatTurn(text="Paris.")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=_KaputtesModell())

    reply = await agent.handle("Was ist die Hauptstadt von Frankreich?")

    assert len(hauptmodell.calls) == 1
    assert reply.text == "Paris."
    assert reply.provenance == guard.TALK


async def test_leere_antwort_vom_schnellen_modell_faellt_auf_hauptmodell_zurueck(
        config, store, registry, fake_ollama):
    hauptmodell = fake_ollama([ChatTurn(text="Paris.")])
    schnelles_modell = fake_ollama([ChatTurn(text="   ")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=schnelles_modell)

    reply = await agent.handle("Was ist die Hauptstadt von Frankreich?")

    assert len(schnelles_modell.calls) == 1
    assert len(hauptmodell.calls) == 1
    assert reply.text == "Paris."


async def test_luege_des_schnellen_modells_wird_ebenso_abgefangen(
        config, store, registry, workspace, fake_ollama):
    """Dieselbe Grundregel des Projekts gilt für jedes Modell gleich."""
    hauptmodell = fake_ollama([ChatTurn(text="DIES DARF NIE BENUTZT WERDEN")])
    schnelles_modell = fake_ollama([ChatTurn(
        text="Ich habe die Datei gaming.txt für dich erstellt.")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=schnelles_modell)

    reply = await agent.handle("Kannst du mir kurz helfen?")

    assert reply.blocked is True
    assert reply.text == guard.REFUSAL
    assert reply.provenance == guard.FAIL
    assert list(workspace.iterdir()) == []


async def test_ohne_konfiguriertes_schnelles_modell_bleibt_alles_beim_hauptmodell(
        config, store, registry, fake_ollama):
    """Kein fast_client heißt: Feature ist aus, keine Verhaltensänderung."""
    hauptmodell = fake_ollama([ChatTurn(text="Paris.")])
    agent = make_agent(config, store, registry, hauptmodell, fast_model=None)

    reply = await agent.handle("Was ist die Hauptstadt von Frankreich?")

    assert len(hauptmodell.calls) == 1
    assert reply.text == "Paris."
