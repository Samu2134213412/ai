"""Autonomy Levels: der Rahmen um das Permission-System, nicht dessen Ersatz.

Stufe 0/1 koennen eine Bestaetigungspflicht nur verschaerfen, nie aufheben --
das ist hier bewusst mit einer maximal laxen Policy geprueft, damit klar
ist, dass die Sperre von der Autonomiestufe kommt und nicht zufaellig von
der Policy."""

from __future__ import annotations

import pytest

from jarvis import guard
from jarvis.agent import Agent
from jarvis.autonomy import AutonomyLevel
from jarvis.config import Config
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.permissions import PermissionGate, PermissionPolicy

_LAX = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, events=None):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    gate = PermissionGate(policy=_LAX, emit=emit)
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate)


# ══════════════════════════════════════════════════════ AutonomyLevel/Config
def test_label_deckt_alle_stufen_ab():
    for level in AutonomyLevel:
        assert level.label


def test_from_value_akzeptiert_int_und_lehnt_unbekanntes_ab():
    assert AutonomyLevel.from_value(2) is AutonomyLevel.LOCAL_ACTIONS
    with pytest.raises(ValueError, match="Unbekannte Autonomiestufe"):
        AutonomyLevel.from_value(99)


def test_config_default_ist_sinnvoller_mittlerer_level():
    assert Config().autonomy is AutonomyLevel.LOCAL_ACTIONS


def test_config_autonomy_faellt_bei_ungueltigem_wert_sicher_zurueck():
    cfg = Config()
    cfg.autonomy_level = 99
    assert cfg.autonomy is AutonomyLevel.NONE
    assert any("autonomy_level" in p for p in cfg.validate())


# ══════════════════════════════════════════════════════ Stufe 0: nur reden
async def test_stufe_0_blockiert_jeden_werkzeugaufruf(config, store, registry, workspace):
    config.autonomy_level = 0
    agent = make_agent(config, store, registry, model=None)
    result = await agent._run_tool("write_file", {
        "path": str(workspace / "a.txt"), "content": "x"})
    assert result.ok is False
    assert "Autonomiestufe 0" in result.summary
    assert not (workspace / "a.txt").exists()


async def test_stufe_0_landet_ehrlich_im_audit_log(config, store, registry, workspace):
    config.autonomy_level = 0
    agent = make_agent(config, store, registry, model=None)
    await agent._run_tool("write_file", {"path": str(workspace / "a.txt"), "content": "x"})
    eintraege = agent.audit.query(tool="write_file")
    assert len(eintraege) == 1
    assert eintraege[0].ok is False


# ══════════════════════════════════════ Stufe 1: nur lesende Aktionen automatisch
async def test_stufe_1_laesst_read_only_automatisch_laufen(config, store, registry):
    config.autonomy_level = 1
    agent = make_agent(config, store, registry, model=None)
    result = await agent._run_tool("get_system_info", {})
    assert result.ok is True


async def test_stufe_1_erzwingt_bestaetigung_fuer_write_trotz_laxer_policy(
        config, store, registry, workspace):
    """Die Policy hier ist _LAX (confirm_write=False) -- ohne die
    Autonomiestufe wuerde das sofort durchlaufen. Stufe 1 verlangt trotzdem
    eine Bestaetigung, die hier nie kommt, also laeuft es in den Timeout/die
    Ablehnung."""
    import asyncio

    config.autonomy_level = 1
    agent = make_agent(config, store, registry, model=None)
    agent.permission_gate.policy.confirmation_timeout = 0.05
    result = await agent._run_tool("write_file", {
        "path": str(workspace / "a.txt"), "content": "x"})
    assert result.ok is False
    assert not (workspace / "a.txt").exists()


# ═══════════════════════════════════ Stufe >=3 erst schaltet Zielverfolgung frei
async def test_stufe_unter_3_verweigert_zielverfolgung_hoeflich(
        config, store, registry, fake_ollama):
    config.autonomy_level = 2
    model = fake_ollama([ChatTurn(text="sollte nie aufgerufen werden")])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_agent_task("Räum das Projekt auf")

    assert reply.provenance == guard.TALK
    assert "Autonomiestufe 2" in reply.text
    assert model.calls == []  # der Planer wurde gar nicht erst gefragt


async def test_stufe_3_erlaubt_zielverfolgung(config, store, registry, workspace, fake_ollama):
    config.autonomy_level = 3
    model = fake_ollama([
        ChatTurn(text='["Systeminfo lesen"]'),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),
        ChatTurn(text="geprüft."),
    ])
    agent = make_agent(config, store, registry, model)
    reply = await agent.handle_agent_task("Prüfe das System")
    assert reply.provenance == guard.TOOL
