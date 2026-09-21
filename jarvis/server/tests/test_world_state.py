"""World State: nur Felder, die wirklich messbar sind (Punkt 13)."""

from __future__ import annotations

from jarvis.goals import GoalManager, GoalStatus
from jarvis.ollama import Health
from jarvis import world_state


def test_snapshot_zaehlt_nur_laufende_ziele():
    goals = GoalManager(":memory:")
    a = goals.create("Läuft")
    a.status = GoalStatus.RUNNING
    goals.save(a)
    b = goals.create("Fertig")
    b.status = GoalStatus.COMPLETED
    goals.save(b)

    state = world_state.snapshot(Health(online=True), goals)
    assert state["aktive_ziele"] == 1
    assert state["ollama_erreichbar"] is True


def test_snapshot_ohne_health_meldet_nicht_erreichbar():
    goals = GoalManager(":memory:")
    state = world_state.snapshot(None, goals)
    assert state["ollama_erreichbar"] is False


def test_as_text_ist_lesbar_ohne_psutil_werte():
    text = world_state.as_text({"system": {}, "ollama_erreichbar": False, "aktive_ziele": 0})
    assert "0 aktive Ziele" in text
    assert "nicht erreichbar" in text
