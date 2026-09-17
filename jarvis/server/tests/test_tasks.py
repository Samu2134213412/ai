"""Task Manager: anlegen, fortschreiben, als Verlauf wiederfinden."""

from __future__ import annotations

import pytest

from jarvis.tasks import StepStatus, Task, TaskManager, TaskStatus


@pytest.fixture
def manager() -> TaskManager:
    tm = TaskManager(":memory:")
    yield tm
    tm.close()


def test_create_zerlegt_in_schritte(manager: TaskManager):
    task = manager.create("Bring dieses GitHub-Projekt zum Laufen",
                          ["Repository prüfen", "Dependencies installieren", "Projekt starten"])
    assert len(task.steps) == 3
    assert task.status is TaskStatus.QUEUED
    assert all(s.status is StepStatus.PENDING for s in task.steps)
    assert task.steps[0].description == "Repository prüfen"


def test_leere_schrittliste_wird_zu_einem_schritt_aus_dem_ziel(manager: TaskManager):
    task = manager.create("Irgendwas tun", [])
    assert len(task.steps) == 1
    assert task.steps[0].description == "Irgendwas tun"


def test_get_findet_die_gespeicherte_task_wieder(manager: TaskManager):
    task = manager.create("Ziel", ["Schritt 1"])
    wieder = manager.get(task.id)
    assert wieder is not None
    assert wieder.goal == "Ziel"
    assert wieder.steps[0].description == "Schritt 1"


def test_unbekannte_id_gibt_none(manager: TaskManager):
    assert manager.get("nie-gesehen") is None


def test_save_schreibt_aenderungen_fort(manager: TaskManager):
    task = manager.create("Ziel", ["Schritt 1", "Schritt 2"])
    task.steps[0].status = StepStatus.DONE
    task.steps[0].result_summary = "erledigt"
    task.status = TaskStatus.RUNNING
    manager.save(task)

    wieder = manager.get(task.id)
    assert wieder.steps[0].status is StepStatus.DONE
    assert wieder.steps[0].result_summary == "erledigt"
    assert wieder.status is TaskStatus.RUNNING


def test_current_step_ist_der_erste_offene(manager: TaskManager):
    task = manager.create("Ziel", ["A", "B", "C"])
    task.steps[0].status = StepStatus.DONE
    assert task.current_step().description == "B"


def test_current_step_none_wenn_alles_fertig(manager: TaskManager):
    task = manager.create("Ziel", ["A"])
    task.steps[0].status = StepStatus.DONE
    assert task.current_step() is None


def test_list_liefert_neueste_zuerst(manager: TaskManager):
    a = manager.create("Erste", ["x"])
    b = manager.create("Zweite", ["x"])
    ids = [t.id for t in manager.list()]
    assert ids[:2] == [b.id, a.id]


def test_list_filtert_nach_status(manager: TaskManager):
    a = manager.create("Erste", ["x"])
    a.status = TaskStatus.FAILED
    manager.save(a)
    manager.create("Zweite", ["x"])

    gescheiterte = manager.list(status=TaskStatus.FAILED)
    assert len(gescheiterte) == 1
    assert gescheiterte[0].id == a.id


def test_persistiert_ueber_einen_neustart_hinweg(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    manager = TaskManager(path)
    task = manager.create("Ziel", ["A", "B"])
    manager.close()

    wieder = TaskManager(path)
    geladen = wieder.get(task.id)
    assert geladen is not None
    assert len(geladen.steps) == 2
    wieder.close()
