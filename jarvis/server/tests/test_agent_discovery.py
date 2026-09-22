"""Discovery/History im echten Zug (Punkt 35/36): eine eingegrenzte
Werkzeugauswahl statt des vollen Katalogs, ein abgeschaltetes Werkzeug, das
wirklich nicht läuft, und ein Verlaufseintrag nach jedem echten Aufruf."""

from __future__ import annotations

import asyncio

from jarvis.agent import Agent
from jarvis.autonomy import AutonomyLevel
from jarvis.goals import GoalStatus
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.permissions import PermissionGate, PermissionPolicy

_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, events=None):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    gate = PermissionGate(policy=_DURCHLAESSIG, emit=emit)
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate)


async def warte_bis(bedingung, versuche: int = 400, pause: float = 0.01):
    for _ in range(versuche):
        if bedingung():
            return
        await asyncio.sleep(pause)
    raise AssertionError("Der erwartete Zustand ist nie eingetreten.")


# ═══════════════════════════════════════════════ Werkzeugauswahl im Zug
async def test_chat_schickt_nicht_den_ganzen_katalog(config, store, registry, fake_ollama):
    model = fake_ollama([ChatTurn(text="nichts zu tun")])
    agent = make_agent(config, store, registry, model)

    await agent.handle("Sag mir einfach hallo")

    assert model.tool_schemas, "Es wurden gar keine Werkzeuge mitgeschickt"
    angeboten = model.tool_schemas[0]
    assert len(angeboten) < len(registry)


async def test_chat_findet_ein_werkzeug_per_suche_und_ruft_es_auf(
        config, store, registry, fake_ollama, workspace):
    """'committe das' soll git.commit in die Auswahl bringen, obwohl es
    nicht in discovery.CORE_TOOLS steht."""
    model = fake_ollama([
        ChatTurn(tool_calls=[ToolCall("git.status", {})]),
        ChatTurn(text="Status geprüft."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle("wie ist der git status gerade")

    # Ob der echte 'git status' hier gelingt, hängt davon ab, ob der
    # Testordner ein Git-Repository ist -- darum geht es nicht. Interessant
    # ist nur, dass git.status überhaupt zur Auswahl stand und aufgerufen
    # wurde (also ein Beleg entstand, kein leeres Gespräch).
    assert reply.results and reply.results[0].tool == "git.status"
    angeboten = {s["function"]["name"] for s in model.tool_schemas[0]}
    assert "git.status" in angeboten


async def test_zielverfolgung_schickt_ebenfalls_eine_eingegrenzte_auswahl(
        config, store, registry, fake_ollama, workspace):
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    model = fake_ollama([
        ChatTurn(text='["Datei anlegen"]'),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "a.txt"), "content": "x"})]),
        ChatTurn(text="fertig"),
    ])
    agent = make_agent(config, store, registry, model)

    ziel, _ = await agent.start_goal("leg eine datei mit dem inhalt x an")
    await warte_bis(lambda: agent.goals.get(ziel.id).status is GoalStatus.COMPLETED)

    assert model.tool_schemas
    assert all(len(s) < len(registry) for s in model.tool_schemas)


# ═══════════════════════════════════════════════ Abschalten (Punkt 26)
async def test_abgeschaltetes_werkzeug_laeuft_wirklich_nicht(
        config, store, registry, workspace):
    agent = make_agent(config, store, registry, model=None)
    registry.call("jarvis.tools.disable", {"name": "write_file", "reason": "test"})

    result = await agent._run_tool("write_file", {
        "path": str(workspace / "sollte_nicht_entstehen.txt"), "content": "x"})

    assert result.ok is False
    assert "abgeschaltet" in result.summary
    assert not (workspace / "sollte_nicht_entstehen.txt").exists()


async def test_wieder_angeschaltetes_werkzeug_laeuft_wieder(
        config, store, registry, workspace):
    agent = make_agent(config, store, registry, model=None)
    registry.call("jarvis.tools.disable", {"name": "write_file"})
    registry.call("jarvis.tools.enable", {"name": "write_file"})

    ziel = workspace / "b.txt"
    result = await agent._run_tool("write_file", {"path": str(ziel), "content": "x"})

    assert result.ok is True
    assert ziel.read_text(encoding="utf-8") == "x"


async def test_abschalten_gilt_auch_ueber_einen_alias(config, store, registry, workspace):
    """'get_system_info' ist ein Alias von 'system.info' -- abgeschaltet
    unter dem einen Namen muss auch unter dem anderen gesperrt sein."""
    agent = make_agent(config, store, registry, model=None)
    registry.call("jarvis.tools.disable", {"name": "system.info"})

    result = await agent._run_tool("get_system_info", {})
    assert result.ok is False
    assert "abgeschaltet" in result.summary


# ═══════════════════════════════════════════════ Verlauf (Punkt 36)
async def test_echter_aufruf_landet_in_der_werkzeug_historie(
        config, store, registry, workspace):
    agent = make_agent(config, store, registry, model=None)
    ziel = workspace / "c.txt"

    result = await agent._run_tool("write_file", {"path": str(ziel), "content": "x"},
                                   request_text="leg c.txt an")

    assert result.ok is True
    eintraege = agent.tool_history.list()
    assert len(eintraege) == 1
    assert eintraege[0].tool == "write_file"
    assert eintraege[0].request == "leg c.txt an"


async def test_verweigerte_berechtigung_landet_nicht_in_der_werkzeug_historie(
        config, store, registry):
    """Anders als das Audit Log: eine Verweigerung hat keine echte Dauer und
    sagt nichts über die Zuverlässigkeit des Werkzeugs selbst aus."""
    from jarvis.autonomy import AutonomyLevel
    config.autonomy_level = int(AutonomyLevel.NONE)
    agent = make_agent(config, store, registry, model=None)

    await agent._run_tool("write_file", {"path": "x.txt", "content": "x"})

    assert agent.tool_history.list() == []


async def test_echter_aufruf_hebt_das_werkzeug_im_suchranking(
        config, store, registry, workspace):
    agent = make_agent(config, store, registry, model=None)
    vorher = agent.discovery.search("verzeichnis")

    await agent._run_tool("list_dir", {"path": str(workspace)})

    nachher = agent.discovery.search("verzeichnis")
    platz_vorher = next(i for i, h in enumerate(vorher) if h.tool.name == "list_dir")
    platz_nachher = next(i for i, h in enumerate(nachher) if h.tool.name == "list_dir")
    assert platz_nachher <= platz_vorher
