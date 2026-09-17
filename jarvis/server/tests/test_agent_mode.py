"""Agent Mode: Planner zerlegt, Executor führt aus, Fehler werden mit einem
neuen Versuch behandelt statt sofort aufzugeben -- mit einem Retry-Limit,
damit daraus keine Endlosschleife wird."""

from __future__ import annotations

from jarvis import guard
from jarvis.agent import Agent
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.permissions import PermissionGate, PermissionPolicy
from jarvis.tasks import StepStatus, TaskStatus

_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, events=None, max_step_retries=2):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    gate = PermissionGate(policy=_DURCHLAESSIG, emit=emit)
    # Diese Datei testet die Goal-Ausführung selbst (Planner/Executor/Retry),
    # nicht die Autonomiestufen (siehe test_autonomy.py) -- Stufe 3 schaltet
    # eigenständige Zielverfolgung frei, ohne die sonst jeder Aufruf hier mit
    # der ehrlichen Absage aus autonomy.py enden würde.
    config.autonomy_level = 3
    return Agent(config, store, registry, model, emit=emit, permission_gate=gate,
                max_step_retries=max_step_retries)


async def test_mehrstufiger_plan_wird_vollstaendig_abgearbeitet(
        config, store, registry, workspace, fake_ollama):
    model = fake_ollama([
        ChatTurn(text='["Systeminfo lesen", "Datei anlegen"]'),  # Planner
        # Schritt 1
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),
        ChatTurn(text="System geprüft."),
        # Schritt 2
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(workspace / "ergebnis.txt"), "content": "fertig"})]),
        ChatTurn(text="Datei angelegt."),
    ])
    events: list = []
    agent = make_agent(config, store, registry, model, events)

    reply = await agent.handle_agent_task("Bring das Projekt zum Laufen")

    assert reply.provenance == guard.TOOL
    assert (workspace / "ergebnis.txt").read_text(encoding="utf-8") == "fertig"

    kinds = [k for k, _ in events]
    assert kinds.count("task.step.started") == 2
    assert kinds.count("task.step.finished") == 2
    assert "task.created" in kinds
    assert "task.finished" in kinds

    task = agent.tasks.get([p for k, p in events if k == "task.created"][0]["id"])
    assert task.status is TaskStatus.COMPLETED
    assert all(s.status is StepStatus.DONE for s in task.steps)


async def test_gescheiterter_schritt_bekommt_einen_neuen_versuch(
        config, store, registry, fake_ollama):
    """Erster Versuch scheitert (Datei existiert nicht), zweiter Versuch mit
    anderem Werkzeug gelingt -- Error Recovery, keine sofortige Aufgabe."""
    model = fake_ollama([
        ChatTurn(text='["Etwas herausfinden"]'),                          # Planner
        ChatTurn(tool_calls=[ToolCall("read_file", {"path": "gibtsnicht.txt"})]),  # Versuch 1
        ChatTurn(text="Das hat nicht geklappt."),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),           # Versuch 2
        ChatTurn(text="Jetzt geklappt."),
    ])
    events: list = []
    agent = make_agent(config, store, registry, model, events)

    reply = await agent.handle_agent_task("Finde etwas heraus")

    assert reply.provenance == guard.TOOL
    retries = [p for k, p in events if k == "task.step.retry"]
    assert len(retries) == 1
    assert "gibtsnicht" in retries[0]["fehler"] or "existiert nicht" in retries[0]["fehler"]

    task_id = [p for k, p in events if k == "task.created"][0]["id"]
    task = agent.tasks.get(task_id)
    assert task.status is TaskStatus.COMPLETED
    assert task.steps[0].status is StepStatus.DONE
    assert task.steps[0].retries == 1


async def test_retry_limit_verhindert_endlosschleife(config, store, registry, fake_ollama):
    """Scheitert ein Schritt dauerhaft, gibt es irgendwann ehrlich auf --
    mit genau max_step_retries + 1 Versuchen, nicht unendlich vielen."""
    turns = [ChatTurn(text='["Unmögliches tun"]')]  # Planner
    for _ in range(2):  # max_step_retries=1 -> zwei Versuche insgesamt
        turns.append(ChatTurn(tool_calls=[ToolCall("read_file", {"path": "nie-da.txt"})]))
        turns.append(ChatTurn(text="Ging nicht."))
    model = fake_ollama(turns)
    events: list = []
    agent = make_agent(config, store, registry, model, events, max_step_retries=1)

    reply = await agent.handle_agent_task("Tu etwas Unmögliches")

    assert reply.provenance == guard.FAIL
    assert "gescheitert" in reply.text

    task_id = [p for k, p in events if k == "task.created"][0]["id"]
    task = agent.tasks.get(task_id)
    assert task.status is TaskStatus.FAILED
    assert task.steps[0].status is StepStatus.FAILED
    assert task.steps[0].retries == 2  # zwei Versuche gezählt, dann aufgegeben
    assert model.calls  # es wurde tatsächlich (endlich oft) angefragt, nicht unendlich


async def test_leeres_ziel_ist_keine_aufgabe(config, store, registry, fake_ollama):
    agent = make_agent(config, store, registry, fake_ollama([]))
    reply = await agent.handle_agent_task("   ")
    assert reply.provenance == guard.TALK
    assert reply.text == ""


async def test_planer_ohne_brauchbare_antwort_fuehrt_trotzdem_einen_schritt_aus(
        config, store, registry, fake_ollama):
    """Liefert das Modell keinen Plan, wird der Auftrag als ein einziger
    Schritt behandelt -- kein Absturz, kein vorgetäuschter Plan."""
    model = fake_ollama([
        ChatTurn(text="Klar, mache ich!"),                    # Planner liefert kein JSON
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),
        ChatTurn(text="Erledigt."),
    ])
    events: list = []
    agent = make_agent(config, store, registry, model, events)

    reply = await agent.handle_agent_task("Sag mir was über das System")

    assert reply.provenance == guard.TOOL
    task_id = [p for k, p in events if k == "task.created"][0]["id"]
    task = agent.tasks.get(task_id)
    assert len(task.steps) == 1
    assert task.steps[0].description == "Sag mir was über das System"
