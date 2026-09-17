"""Goal Manager: die äußere Hülle (Priorität, Deadline, Bedingungen,
Budget) um die bestehende Task-Ausführung herum -- keine zweite
Ausführungsmaschine, siehe docs/JARVIS.md §8.2."""

from __future__ import annotations

import pytest

from jarvis.goals import Goal, GoalBudget, GoalManager, GoalStatus


@pytest.fixture
def manager() -> GoalManager:
    gm = GoalManager(":memory:")
    yield gm
    gm.close()


def test_create_setzt_sinnvolle_defaults(manager: GoalManager):
    goal = manager.create("Verbessere Jarvis Voice")
    assert goal.status is GoalStatus.PENDING
    assert goal.priority == 0
    assert goal.progress == 0.0
    assert goal.subtasks == []
    assert goal.budget == GoalBudget()


def test_create_mit_bedingungen_und_prioritaet(manager: GoalManager):
    goal = manager.create(
        "Mach das Jarvis-Projekt schneller", priority=5,
        success_conditions=["Startzeit < 2s"], failure_conditions=["Tests schlagen fehl"])
    assert goal.priority == 5
    assert goal.success_conditions == ["Startzeit < 2s"]
    assert goal.failure_conditions == ["Tests schlagen fehl"]


def test_get_findet_gespeichertes_goal_wieder(manager: GoalManager):
    goal = manager.create("Ziel")
    goal.subtasks.append("task-1")
    goal.status = GoalStatus.RUNNING
    goal.progress = 40.0
    manager.save(goal)

    wieder = manager.get(goal.id)
    assert wieder is not None
    assert wieder.status is GoalStatus.RUNNING
    assert wieder.progress == 40.0
    assert wieder.subtasks == ["task-1"]


def test_unbekannte_id_gibt_none(manager: GoalManager):
    assert manager.get("nie-gesehen") is None


def test_list_liefert_nach_prioritaet_dann_neuestem_sortiert(manager: GoalManager):
    niedrig = manager.create("Niedrig", priority=1)
    hoch = manager.create("Hoch", priority=9)
    ids = [g.id for g in manager.list()]
    assert ids[0] == hoch.id
    assert niedrig.id in ids


def test_list_filtert_nach_status(manager: GoalManager):
    a = manager.create("Erstes")
    a.status = GoalStatus.FAILED
    manager.save(a)
    manager.create("Zweites")

    gescheiterte = manager.list(status=GoalStatus.FAILED)
    assert len(gescheiterte) == 1
    assert gescheiterte[0].id == a.id


def test_unterziele_ueber_parent_goal_auffindbar(manager: GoalManager):
    eltern = manager.create("Großes Ziel")
    kind1 = manager.create("Teilziel A", parent_goal=eltern.id)
    kind2 = manager.create("Teilziel B", parent_goal=eltern.id)
    manager.create("Unabhängiges Ziel")

    kinder = manager.children(eltern.id)
    assert {k.id for k in kinder} == {kind1.id, kind2.id}


def test_budget_defaults_entsprechen_dem_beispiel_der_aufgabenstellung():
    budget = GoalBudget()
    assert budget.max_steps == 50
    assert budget.max_runtime_minutes == 30
    assert budget.max_retries == 3


def test_budget_roundtrip_ueber_dict():
    budget = GoalBudget(max_steps=10, max_runtime_minutes=5, max_retries=1, max_tool_calls=20)
    wieder = GoalBudget.from_dict(budget.as_dict())
    assert wieder == budget


def test_working_memory_wird_mitgespeichert(manager: GoalManager):
    goal = manager.create("Ziel")
    goal.working_memory = {"letzter_fehler": "Port belegt", "plan": ["A", "B"]}
    manager.save(goal)
    wieder = manager.get(goal.id)
    assert wieder.working_memory == {"letzter_fehler": "Port belegt", "plan": ["A", "B"]}


def test_persistiert_ueber_einen_neustart_hinweg(tmp_path):
    path = tmp_path / "goals.sqlite3"
    manager = GoalManager(path)
    goal = manager.create("Ziel", priority=3)
    manager.close()

    wieder = GoalManager(path)
    geladen = wieder.get(goal.id)
    assert geladen is not None
    assert geladen.priority == 3
    wieder.close()
