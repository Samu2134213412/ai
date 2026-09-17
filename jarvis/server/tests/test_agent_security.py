"""Die Verzahnung: Permission-System, Audit Log und Undo, verkabelt in
``Agent._run_tool`` -- mit der echten, sicheren Standardrichtlinie (kein
Test-Bypass wie in ``test_agent.py``/``test_api.py``). Das Modul-Verhalten
selbst ist schon in test_permissions.py/test_audit.py/test_undo.py
ausführlich geprüft; hier geht es nur darum, dass die drei Systeme über den
einen Durchlauf in ``agent.py`` tatsächlich zusammenarbeiten.
"""

from __future__ import annotations

import asyncio

from jarvis import guard
from jarvis.agent import Agent
from jarvis.ollama import ChatTurn


async def _bis_ausstehend(agent: Agent, versuche: int = 50) -> str:
    """Wartet, bis genau eine Berechtigungsanfrage aussteht, und gibt ihre id
    zurück. Kooperatives Warten statt sleep(fest), weil der Task, der auf die
    Bestätigung wartet, erst ein paar Event-Loop-Durchläufe braucht."""
    for _ in range(versuche):
        if agent.permission_gate.pending:
            return agent.permission_gate.pending[0]
        await asyncio.sleep(0)
    raise AssertionError("Es kam nie eine Berechtigungsanfrage an.")


async def test_write_file_wartet_mit_der_echten_standardrichtlinie(
        config, store, registry, workspace, fake_ollama):
    """Ohne expliziten Bypass: ein WRITE-Aufruf über den Router blockiert
    tatsächlich, bis eine Bestätigung eintrifft -- er läuft nicht einfach durch."""
    events: list[tuple[str, dict]] = []

    async def emit(kind, payload):
        events.append((kind, payload))

    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = Agent(config, store, registry, model, emit=emit)  # kein permission_gate übergeben

    task = asyncio.ensure_future(agent.handle(
        f"Erstelle eine Datei in {workspace} namens test.txt mit dem Inhalt Hallo"))
    request_id = await _bis_ausstehend(agent)
    assert not task.done()
    assert not (workspace / "test.txt").exists()  # noch nichts passiert

    agent.permission_gate.resolve(request_id, True)
    reply = await task

    assert reply.provenance == guard.TOOL
    assert (workspace / "test.txt").read_text(encoding="utf-8") == "Hallo"
    assert any(k == "permission.requested" for k, _ in events)
    assert any(k == "permission.approved" for k, _ in events)


async def test_abgelehnte_aktion_wird_ehrlich_gemeldet_und_nichts_passiert(
        config, store, registry, workspace, fake_ollama):
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = Agent(config, store, registry, model)

    task = asyncio.ensure_future(agent.handle(
        f"Erstelle eine Datei in {workspace} namens verweigert.txt mit dem Inhalt X"))
    request_id = await _bis_ausstehend(agent)
    agent.permission_gate.resolve(request_id, False)
    reply = await task

    assert reply.provenance == guard.FAIL
    assert "nicht bestätigt" in reply.text
    assert not (workspace / "verweigert.txt").exists()


async def test_lesen_braucht_trotz_sicherer_standardrichtlinie_keine_bestaetigung(
        config, store, registry, workspace, fake_ollama):
    (workspace / "vorhanden.txt").write_text("Inhalt", encoding="utf-8")
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = Agent(config, store, registry, model)

    reply = await agent.handle(f"lies {workspace / 'vorhanden.txt'}")

    assert agent.permission_gate.pending == []
    assert reply.provenance == guard.TOOL


async def test_erfolgreiche_aktion_landet_im_audit_log_und_ist_rueckgaengig_machbar(
        config, store, registry, workspace, fake_ollama):
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = Agent(config, store, registry, model)
    target = workspace / "protokolliert.txt"

    task = asyncio.ensure_future(agent.handle(
        f"Erstelle eine Datei in {workspace} namens protokolliert.txt mit dem Inhalt Y"))
    request_id = await _bis_ausstehend(agent)
    agent.permission_gate.resolve(request_id, True)
    await task

    assert target.exists()

    eintraege = agent.audit.query(tool="write_file")
    assert len(eintraege) == 1
    assert eintraege[0].ok is True
    assert eintraege[0].level.label == "WRITE"
    assert "protokolliert.txt" in eintraege[0].request

    zusammenfassung = agent.undo.undo()
    assert not target.exists()
    assert "entfernt" in zusammenfassung


async def test_verweigerte_aktion_landet_ebenfalls_im_audit_log(
        config, store, registry, workspace, fake_ollama):
    model = fake_ollama([ChatTurn(text="darf nie gebraucht werden")])
    agent = Agent(config, store, registry, model)

    task = asyncio.ensure_future(agent.handle(
        f"Erstelle eine Datei in {workspace} namens nie.txt mit dem Inhalt Z"))
    request_id = await _bis_ausstehend(agent)
    agent.permission_gate.resolve(request_id, False)
    await task

    eintraege = agent.audit.query(tool="write_file", ok=False)
    assert len(eintraege) == 1
    assert "nicht bestätigt" in eintraege[0].summary
