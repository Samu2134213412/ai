"""Makros im echten Zug: Anlage über das CRUD-Werkzeug (``automation.macro.*``
in ``productivity.py``), Ausführung über ``Agent.run_macro`` -- also über
genau dieselbe ``_run_tool``-Pipeline (Permission-Gate, Undo, Audit) wie jeder
andere Werkzeugaufruf auch. ``macros.py`` selbst hat seine eigene, isolierte
Prüfung in ``test_macros.py`` mit einem eingespeisten Fake-Callable; hier geht
es um die Verkabelung drumherum.
"""

from __future__ import annotations

from pathlib import Path

from jarvis import guard
from jarvis.agent import Agent
from jarvis.autonomy import AutonomyLevel
from jarvis.permissions import PermissionGate, PermissionPolicy

_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model=None):
    gate = PermissionGate(policy=_DURCHLAESSIG, emit=None)
    return Agent(config, store, registry, model, permission_gate=gate,
                macros=registry.macro_store)


def test_registry_traegt_dieselbe_makro_ablage_wie_der_agent(config, store, registry):
    agent = make_agent(config, store, registry)
    assert agent.macros is registry.macro_store


# ══════════════════════════════════════════════════════════ CRUD-Werkzeuge
def test_makro_anlegen_auflisten_ansehen_loeschen(registry):
    angelegt = registry.call("automation.macro.create", {
        "name": "beispiel", "steps": [
            {"id": "s1", "kind": "tool", "tool": "productivity.calculate",
             "arguments": {"expression": "1 + 1"}}],
        "description": "ein Testmakro"})
    assert angelegt.ok is True
    assert angelegt.evidence["anzahl_schritte"] == 1

    liste = registry.call("automation.macro.list", {})
    assert liste.ok is True
    assert "beispiel" in liste.payload

    angesehen = registry.call("automation.macro.get", {"name": "beispiel"})
    assert angesehen.ok is True
    assert angesehen.payload[0]["tool"] == "productivity.calculate"

    geloescht = registry.call("automation.macro.delete", {"name": "beispiel"})
    assert geloescht.ok is True
    nochmal = registry.call("automation.macro.get", {"name": "beispiel"})
    assert nochmal.ok is False


def test_makro_anlegen_lehnt_unbekannte_schrittart_ab(registry):
    ergebnis = registry.call("automation.macro.create", {
        "name": "kaputt", "steps": [{"id": "s1", "kind": "iff"}]})
    assert ergebnis.ok is False
    assert "unbekannte Schrittart" in ergebnis.summary


def test_makro_anlegen_lehnt_tool_schritt_ohne_tool_feld_ab(registry):
    ergebnis = registry.call("automation.macro.create", {
        "name": "kaputt2", "steps": [{"id": "s1", "kind": "tool"}]})
    assert ergebnis.ok is False
    assert "tool" in ergebnis.summary.lower()


def test_makro_loeschen_ohne_treffer_meldet_ehrlichen_fehler(registry):
    ergebnis = registry.call("automation.macro.delete", {"name": "gibts-nicht"})
    assert ergebnis.ok is False


# ══════════════════════════════════════════════════════════ Ausführung
async def test_makro_ausfuehren_ueber_agent(config, store, registry):
    registry.call("automation.macro.create", {
        "name": "rechnen", "steps": [
            {"id": "s1", "kind": "tool", "tool": "productivity.calculate",
             "arguments": {"expression": "2 + 2"}},
            {"id": "s2", "kind": "tool", "tool": "productivity.calculate",
             "arguments": {"expression": "3 * 3"}},
        ]})
    agent = make_agent(config, store, registry)

    reply = await agent.run_macro("rechnen")

    assert reply.provenance == guard.TOOL
    assert len(reply.results) == 2
    assert all(r.ok for r in reply.results)
    assert "2/2" in reply.text


async def test_makro_mit_datei_schreiben_landet_wirklich_auf_platte(
        config, store, registry, workspace: Path):
    ziel = workspace / "aus_dem_makro.txt"
    registry.call("automation.macro.create", {
        "name": "schreiben", "steps": [
            {"id": "s1", "kind": "tool", "tool": "write_file",
             "arguments": {"path": str(ziel), "content": "hallo vom makro"}}]})
    agent = make_agent(config, store, registry)

    reply = await agent.run_macro("schreiben")

    assert reply.provenance == "tool"
    assert ziel.read_text(encoding="utf-8") == "hallo vom makro"


async def test_makro_mit_fehlschlag_meldet_ehrlich(config, store, registry):
    registry.call("automation.macro.create", {
        "name": "kaputtes_werkzeug", "steps": [
            {"id": "s1", "kind": "tool", "tool": "productivity.calculate",
             "arguments": {"expression": "nicht_auswertbar("}}]})
    agent = make_agent(config, store, registry)

    reply = await agent.run_macro("kaputtes_werkzeug")

    assert reply.provenance == "fail"
    assert reply.results[0].ok is False


async def test_unbekanntes_makro_wird_ehrlich_abgelehnt(config, store, registry):
    agent = make_agent(config, store, registry)
    reply = await agent.run_macro("gibt-es-nicht")
    assert reply.provenance == "fail"
    assert "gibt-es-nicht" in reply.text


async def test_makro_bei_autonomiestufe_null_laeuft_nicht(config, store, registry, workspace):
    registry.call("automation.macro.create", {
        "name": "gesperrt", "steps": [
            {"id": "s1", "kind": "tool", "tool": "write_file",
             "arguments": {"path": str(workspace / "sollte_nicht_entstehen.txt"),
                          "content": "x"}}]})
    config.autonomy_level = int(AutonomyLevel.NONE)
    agent = make_agent(config, store, registry)

    reply = await agent.run_macro("gesperrt")

    assert reply.provenance == "talk"
    assert not (workspace / "sollte_nicht_entstehen.txt").exists()


async def test_makro_schleife_ruft_werkzeug_mehrfach_ueber_agent_auf(
        config, store, registry, workspace):
    registry.call("automation.macro.create", {
        "name": "dreimal", "steps": [
            {"id": "l1", "kind": "loop", "times": 3, "body": [
                {"id": "s1", "kind": "tool", "tool": "productivity.calculate",
                 "arguments": {"expression": "1 + 1"}}]}]})
    agent = make_agent(config, store, registry)

    reply = await agent.run_macro("dreimal")

    assert reply.provenance == "tool"
    assert len(reply.results) == 3
