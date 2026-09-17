"""Planner: ein brauchbarer Plan aus dem Modell, oder ehrlich ein Schritt."""

from __future__ import annotations

import json

from jarvis import planner
from jarvis.ollama import ChatTurn, OllamaError


async def test_parst_eine_saubere_json_liste(fake_ollama):
    model = fake_ollama([ChatTurn(
        text='["Repository prüfen", "Dependencies installieren", "Starten"]')])
    steps = await planner.plan(model, "Bring das Projekt zum Laufen")
    assert steps == ["Repository prüfen", "Dependencies installieren", "Starten"]


async def test_json_mit_text_drumherum_wird_trotzdem_gefunden(fake_ollama):
    model = fake_ollama([ChatTurn(
        text='Klar, hier ist der Plan:\n["Erstens", "Zweitens"]\nViel Erfolg!')])
    steps = await planner.plan(model, "Mach was")
    assert steps == ["Erstens", "Zweitens"]


async def test_kaputtes_json_faellt_auf_einen_schritt_zurueck(fake_ollama):
    model = fake_ollama([ChatTurn(text="Das mache ich gerne für dich!")])
    steps = await planner.plan(model, "Bau eine Website")
    assert steps == ["Bau eine Website"]


async def test_leere_liste_faellt_zurueck(fake_ollama):
    model = fake_ollama([ChatTurn(text="[]")])
    steps = await planner.plan(model, "Ziel")
    assert steps == ["Ziel"]


async def test_leeres_ziel_ergibt_keine_schritte(fake_ollama):
    model = fake_ollama([ChatTurn(text='["irrelevant"]')])
    assert await planner.plan(model, "   ") == []


async def test_zu_viele_schritte_werden_gekappt(fake_ollama):
    model = fake_ollama([ChatTurn(text=json.dumps([f"Schritt {i}" for i in range(20)]))])
    steps = await planner.plan(model, "Große Aufgabe", max_steps=5)
    assert len(steps) == 5


async def test_nicht_erreichbares_modell_faellt_ehrlich_zurueck():
    class Kaputt:
        async def chat(self, messages, tools=None):
            raise OllamaError("nicht erreichbar")

    steps = await planner.plan(Kaputt(), "Ziel")
    assert steps == ["Ziel"]


async def test_liste_aus_zahlen_wird_zu_strings(fake_ollama):
    """Robust gegen ein Modell, das keine reinen Strings liefert."""
    model = fake_ollama([ChatTurn(text="[1, 2, 3]")])
    steps = await planner.plan(model, "Ziel")
    assert steps == ["1", "2", "3"]
