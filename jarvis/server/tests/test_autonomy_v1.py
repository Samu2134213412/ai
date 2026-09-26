"""Autonomy V1 -- die dreizehn Verhaltensweisen aus Punkt 24 der
Aufgabenstellung, jede an ihrer eigenen Stelle geprüft:

    Goal -> Subgoals · Tool success · Tool failure · Retry ·
    Verification failure · Loop Detection · Task cancellation ·
    Task pause/resume · Permission request · Undo · Event trigger ·
    Background Task · Agent completes multi-step task

Bewusst über den **echten** Weg (``Agent``, ``GoalManager``, ``Watchdog``,
``VerificationEngine``) statt über nachgebaute Einzelteile: die Module haben
ihre eigenen Tests (test_goals/test_watchdog/test_verification/...), hier geht
es darum, dass sie in der Zielverfolgung tatsächlich zusammen greifen.

Die Autonomiestufe steht in diesen Tests auf 3 (Zielverfolgung) -- die Stufen
selbst prüft test_autonomy.py.
"""

from __future__ import annotations

import asyncio


from jarvis import guard
from jarvis.agent import Agent
from jarvis.autonomy import AutonomyLevel
from jarvis.events import Event, EventBus, ProactiveEngine, Rule
from jarvis.goals import GoalBudget, GoalStatus
from jarvis.ollama import ChatTurn, ToolCall
from jarvis.permissions import PermissionGate, PermissionPolicy
from jarvis.tasks import StepStatus, TaskStatus
from jarvis.tools.base import ToolResult
from jarvis.verification import VerificationEngine

_DURCHLAESSIG = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)


def make_agent(config, store, registry, model, events=None, *, max_step_retries=2,
               verification=None, policy=_DURCHLAESSIG):
    async def emit(kind, payload):
        if events is not None:
            events.append((kind, payload))
    config.autonomy_level = int(AutonomyLevel.GOAL_PURSUIT)
    return Agent(config, store, registry, model, emit=emit,
                 permission_gate=PermissionGate(policy=policy, emit=emit),
                 max_step_retries=max_step_retries, verification=verification)


async def warte_bis(bedingung, versuche: int = 400, pause: float = 0.01):
    """Kooperatives Warten auf einen Zustand, der in einem Hintergrund-Task
    entsteht -- kein fester ``sleep``, und ein Fehlschlag statt eines Hängers."""
    for _ in range(versuche):
        if bedingung():
            return
        await asyncio.sleep(pause)
    raise AssertionError("Der erwartete Zustand ist nie eingetreten.")


class SteuerndesModell:
    """Ein Modell, das bei einer bestimmten Anfrage in das laufende Ziel
    eingreift -- so wird aus "der Nutzer drückt irgendwann Stopp" ein
    deterministischer Test ohne Zeitfenster."""

    def __init__(self, turns, bei_anfrage: int, eingriff):
        self.turns = list(turns)
        self.bei_anfrage = bei_anfrage
        self.eingriff = eingriff
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(list(messages))
        if len(self.calls) == self.bei_anfrage:
            self.eingriff()
        return self.turns.pop(0) if self.turns else ChatTurn(text="(nichts mehr)")

    async def health(self):
        from jarvis.ollama import Health
        return Health(online=True, version="test", models=[], model_present=True)


# ═══════════════════════════════════════════════════ 1 Goal -> Subgoals
async def test_ziel_wird_in_teilschritte_zerlegt(config, store, registry, fake_ollama):
    model = fake_ollama([
        ChatTurn(text='["Logs lesen", "Prozesse prüfen", "Ergebnis melden"]'),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]), ChatTurn(text="a"),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]), ChatTurn(text="b"),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]), ChatTurn(text="c"),
    ])
    agent = make_agent(config, store, registry, model)

    await agent.handle_agent_task("Finde heraus, warum der Server abstürzt")

    ziel = agent.goals.list()[0]
    assert ziel.subtasks, "Das Ziel verweist auf keine Aufgabe"
    aufgabe = agent.tasks.get(ziel.subtasks[0])
    assert [s.description for s in aufgabe.steps] == [
        "Logs lesen", "Prozesse prüfen", "Ergebnis melden"]


# ══════════════════════════════════════════════════════ 2 Tool success
async def test_erfolgreiches_werkzeug_macht_das_ziel_fertig(
        config, store, registry, workspace, fake_ollama):
    ziel_datei = workspace / "beleg.txt"
    model = fake_ollama([
        ChatTurn(text='["Datei anlegen"]'),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel_datei), "content": "echt"})]),
        ChatTurn(text="Datei angelegt."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_agent_task("Lege die Datei an")

    assert reply.provenance == guard.TOOL
    assert ziel_datei.read_text(encoding="utf-8") == "echt"
    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.COMPLETED
    assert ziel.progress == 1.0


# ══════════════════════════════════════════════════════ 3 Tool failure
async def test_gescheitertes_werkzeug_wird_ehrlich_gemeldet(
        config, store, registry, fake_ollama):
    """Auch wenn das Modell "erledigt" sagt: ohne erfolgreiches Werkzeug gibt
    es keinen Erfolg zu melden."""
    turns = [ChatTurn(text='["Datei lesen"]')]
    for _ in range(3):  # max_step_retries=2 -> drei Versuche
        turns.append(ChatTurn(tool_calls=[ToolCall("read_file", {"path": "weg.txt"})]))
        turns.append(ChatTurn(text="Alles erledigt!"))  # die Lüge
        turns.append(ChatTurn(text="(keine Alternativen)"))  # DecisionEngine
    agent = make_agent(config, store, registry, fake_ollama(turns))

    reply = await agent.handle_agent_task("Lies die Datei")

    assert reply.provenance == guard.FAIL
    assert "Alles erledigt" not in reply.text
    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.FAILED
    assert ziel.error


# ═══════════════════════════════════════════════════════════ 4 Retry
async def test_retry_waehlt_einen_anderen_ansatz_und_merkt_sich_die_lehre(
        config, store, registry, fake_ollama):
    model = fake_ollama([
        ChatTurn(text='["Etwas herausfinden"]'),
        ChatTurn(tool_calls=[ToolCall("read_file", {"path": "weg.txt"})]),
        ChatTurn(text="Ging nicht."),
        ChatTurn(text='[{"beschreibung": "Systeminfo lesen", "werkzeug": "get_system_info", '
                      '"erfolgswahrscheinlichkeit": 0.9, "kosten": 0.1, "risiko": "LOW", '
                      '"zeit": 0.1}]'),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]),
        ChatTurn(text="Jetzt geklappt."),
    ])
    events: list = []
    agent = make_agent(config, store, registry, model, events)

    reply = await agent.handle_agent_task("Finde etwas heraus")

    assert reply.provenance == guard.TOOL
    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.COMPLETED
    # Die Abwägung ist protokolliert (Punkt 3: "Die Entscheidung muss geloggt werden").
    assert [k for k, _ in events].count("decision.made") == 1
    assert agent.decisions.log.list(goal_id=ziel.id)
    # Experience Learning (Punkt 15): die Lehre liegt im Gedächtnis ...
    lehren = [m for m in store.search("Erfahrung", 10) if m.kind == "erfahrung"]
    assert lehren, "Nach einem geglückten Neuversuch wurde nichts gelernt"
    # ... aber sie ersetzt keine Aktion: der Erfolg steht trotzdem auf echten
    # Werkzeugergebnissen, nicht auf der Erinnerung.
    assert reply.results and any(r.ok for r in reply.results)


# ═══════════════════════════════════════════════ 5 Verification failure
async def test_fehlgeschlagene_nachpruefung_laesst_den_schritt_scheitern(
        config, store, registry, fake_ollama):
    """Das Werkzeug meldet Erfolg -- die unabhängige Nachprüfung widerspricht.
    Dann gilt der Schritt als gescheitert (Punkt 5)."""
    async def luegner(arguments, result, run_tool):
        return ToolResult(tool="verify:get_system_info", ok=False,
                          summary="Nachprüfung widerspricht dem gemeldeten Erfolg")

    turns = [ChatTurn(text='["Systeminfo lesen"]')]
    for _ in range(2):
        turns.append(ChatTurn(tool_calls=[ToolCall("get_system_info", {})]))
        turns.append(ChatTurn(text="Hat geklappt."))
        turns.append(ChatTurn(text="(keine Alternativen)"))
    agent = make_agent(config, store, registry, fake_ollama(turns), max_step_retries=1,
                       verification=VerificationEngine({"get_system_info": luegner}))

    reply = await agent.handle_agent_task("Prüf das System")

    assert reply.provenance == guard.FAIL
    assert agent.goals.list()[0].status is GoalStatus.FAILED
    aufgabe = agent.tasks.list()[0]
    assert aufgabe.steps[0].status is StepStatus.FAILED
    assert "Nachprüfung" in aufgabe.steps[0].error


async def test_ohne_nachpruefung_zaehlt_das_werkzeugergebnis(
        config, store, registry, workspace, fake_ollama):
    """Die Gegenprobe: derselbe Ablauf mit der echten Verification Engine --
    write_file wird über ein echtes read_file bestätigt und gilt dann."""
    ziel_datei = workspace / "geprueft.txt"
    model = fake_ollama([
        ChatTurn(text='["Datei anlegen"]'),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel_datei), "content": "inhalt"})]),
        ChatTurn(text="Angelegt."),
    ])
    agent = make_agent(config, store, registry, model)

    reply = await agent.handle_agent_task("Leg die Datei an")

    assert reply.provenance == guard.TOOL
    # Die Nachprüfung hat wirklich stattgefunden: ein eigener read_file-Eintrag
    # im Audit Log, ausgelöst von niemandem sonst.
    assert [e for e in agent.audit.query(tool="read_file", limit=10)]


# ═══════════════════════════════════════════════════ 6 Loop Detection
async def test_schritt_budget_stoppt_ein_ziel_das_nicht_fertig_wird(
        config, store, registry, fake_ollama):
    """Punkt 18/19: Bei Überschreitung hält Jarvis an und sagt es -- statt
    weiterzulaufen, bis irgendwer den Stecker zieht."""
    turns = [ChatTurn(text='["A", "B", "C", "D", "E"]')]
    for _ in range(5):
        turns.append(ChatTurn(tool_calls=[ToolCall("get_system_info", {})]))
        turns.append(ChatTurn(text="ok"))
    agent = make_agent(config, store, registry, fake_ollama(turns))

    reply = await agent.handle_agent_task("Tu fünf Dinge", budget=GoalBudget(max_steps=2))

    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.BLOCKED
    assert "Schritt-Limit" in ziel.error
    assert "angehalten" in reply.text.lower()
    aufgabe = agent.tasks.get(ziel.subtasks[0])
    assert aufgabe.status is TaskStatus.FAILED
    assert [s.status for s in aufgabe.steps][:2] == [StepStatus.DONE, StepStatus.DONE]


async def test_watchdog_erkennt_dieselbe_fehlschlagende_aktion(
        config, store, registry, fake_ollama):
    """Die Wiederholungserkennung wird vom echten ``_run_tool_loop`` gefüttert
    -- der Watchdog sieht die Aufrufe, nicht nur seine eigenen Tests."""
    from jarvis.watchdog import Watchdog

    turns = []
    for _ in range(4):
        turns.append(ChatTurn(tool_calls=[ToolCall("read_file", {"path": "weg.txt"})]))
    agent = make_agent(config, store, registry, fake_ollama(turns))
    watchdog = Watchdog()

    await agent._run_tool_loop("Lies die Datei", request_text="test", watchdog=watchdog)

    assert watchdog.tool_call_count >= 3
    verdict = watchdog.verdict()
    assert verdict.ok is False
    assert "wiederholt" in verdict.reason.lower() or "fehler" in verdict.reason.lower()


# ═══════════════════════════════════════════════════ 7 Task cancellation
async def test_abbruch_stoppt_das_ziel_bevor_das_werkzeug_laeuft(
        config, store, registry, workspace, fake_ollama):
    """Der Abbruch greift am nächsten Haltepunkt -- und der liegt **vor** der
    Ausführung, nicht mittendrin. Die Datei darf also nicht entstehen."""
    ziel_datei = workspace / "nie.txt"
    agent = make_agent(config, store, registry, None)
    agent.client = SteuerndesModell(
        turns=[ChatTurn(text='["Datei anlegen"]'),
               ChatTurn(tool_calls=[ToolCall("write_file", {
                   "path": str(ziel_datei), "content": "darf nicht"})])],
        bei_anfrage=2,                      # während der Schritt geplant wird
        eingriff=lambda: agent.cancel_goal(reason="Nutzer: \"Stopp.\""))

    reply = await agent.handle_agent_task("Leg die Datei an")

    assert not ziel_datei.exists(), "Trotz Abbruch wurde die Aktion ausgeführt"
    assert "Abgebrochen" in reply.text
    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.CANCELLED
    assert agent.tasks.list()[0].status is TaskStatus.CANCELLED
    assert agent.active_goals == []  # aufgeräumt


async def test_stopp_im_gespraech_bricht_ein_laufendes_ziel_ab(
        config, store, registry, fake_ollama):
    """Punkt 22: "Stopp." mitten im Gespräch, ohne Ziel-ID."""
    agent = make_agent(config, store, registry, fake_ollama([]))
    ziel, _ = agent._open_goal("läuft gerade")

    antwort = await agent.handle("Stopp.")

    assert antwort is not None
    assert "Angehalten" in antwort.text
    assert agent._controls[ziel.id].cancel_event.is_set()


async def test_ohne_laufendes_ziel_ist_weiter_ein_ganz_normales_wort(
        config, store, registry, fake_ollama):
    """Gegenprobe: die Steuerworte dürfen das normale Gespräch nicht kapern."""
    agent = make_agent(config, store, registry, fake_ollama([ChatTurn(text="Klar.")]))
    antwort = await agent.handle("Mach weiter mit der Geschichte von vorhin")
    assert antwort.text == "Klar."


# ═══════════════════════════════════════════════════ 8 Task pause/resume
async def test_pause_haelt_an_und_weiter_macht_fertig(
        config, store, registry, workspace, fake_ollama):
    ziel_datei = workspace / "nach_der_pause.txt"
    agent = make_agent(config, store, registry, None)
    agent.client = SteuerndesModell(
        turns=[ChatTurn(text='["Datei anlegen"]'),
               ChatTurn(tool_calls=[ToolCall("write_file", {
                   "path": str(ziel_datei), "content": "später"})]),
               ChatTurn(text="Angelegt.")],
        bei_anfrage=2,
        eingriff=lambda: agent.pause_goal())

    lauf = asyncio.ensure_future(agent.handle_agent_task("Leg die Datei an"))
    ziel_id = await _erstes_ziel(agent)

    await warte_bis(lambda: agent.goals.get(ziel_id).status is GoalStatus.WAITING)
    assert not lauf.done()
    assert not ziel_datei.exists(), "Trotz Pause wurde weitergearbeitet"

    agent.resume_goal()
    reply = await asyncio.wait_for(lauf, timeout=10)

    assert reply.provenance == guard.TOOL
    assert ziel_datei.read_text(encoding="utf-8") == "später"
    assert agent.goals.get(ziel_id).status is GoalStatus.COMPLETED


async def _erstes_ziel(agent: Agent, versuche: int = 400) -> str:
    for _ in range(versuche):
        ziele = agent.goals.list()
        if ziele:
            return ziele[0].id
        await asyncio.sleep(0.01)
    raise AssertionError("Es wurde nie ein Ziel angelegt.")


# ═══════════════════════════════════════════════════ 9 Permission request
async def test_hohe_stufe_fragt_auch_in_der_zielverfolgung_nach(
        config, store, registry, workspace, fake_ollama):
    """Autonomie hebelt das Permission-System nicht aus (Punkt 23): Ein
    WRITE-Aufruf wartet auch innerhalb eines Ziels auf die Bestätigung."""
    ziel_datei = workspace / "gefragt.txt"
    events: list = []
    model = fake_ollama([
        ChatTurn(text='["Datei anlegen"]'),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel_datei), "content": "nur mit Erlaubnis"})]),
        ChatTurn(text="Angelegt."),
    ])
    agent = make_agent(config, store, registry, model, events,
                       policy=PermissionPolicy(confirm_write=True))

    lauf = asyncio.ensure_future(agent.handle_agent_task("Leg die Datei an"))
    for _ in range(400):
        if agent.permission_gate.pending:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("Es kam nie eine Berechtigungsanfrage an.")

    assert not ziel_datei.exists()  # noch nichts passiert
    agent.permission_gate.resolve(agent.permission_gate.pending[0], True)
    reply = await asyncio.wait_for(lauf, timeout=10)

    assert reply.provenance == guard.TOOL
    assert ziel_datei.read_text(encoding="utf-8") == "nur mit Erlaubnis"
    assert any(k == "permission.requested" for k, _ in events)


async def test_verweigerte_berechtigung_laesst_das_ziel_ehrlich_scheitern(
        config, store, registry, workspace, fake_ollama):
    ziel_datei = workspace / "verweigert.txt"
    turns = [ChatTurn(text='["Datei anlegen"]')]
    for _ in range(2):
        turns.append(ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel_datei), "content": "x"})]))
        turns.append(ChatTurn(text="Erledigt!"))
        turns.append(ChatTurn(text="(keine Alternativen)"))
    agent = make_agent(config, store, registry, fake_ollama(turns), max_step_retries=1,
                       policy=PermissionPolicy(confirm_write=True))

    async def alles_ablehnen():
        for _ in range(800):
            for request_id in list(agent.permission_gate.pending):
                agent.permission_gate.resolve(request_id, False)
            await asyncio.sleep(0.005)

    ablehner = asyncio.ensure_future(alles_ablehnen())
    reply = await asyncio.wait_for(agent.handle_agent_task("Leg die Datei an"), timeout=15)
    ablehner.cancel()

    assert reply.provenance == guard.FAIL
    assert not ziel_datei.exists()
    assert agent.goals.list()[0].status is GoalStatus.FAILED


# ═══════════════════════════════════════════════════════════════ 10 Undo
async def test_was_ein_ziel_geschrieben_hat_laesst_sich_ruecknehmen(
        config, store, registry, workspace, fake_ollama):
    ziel_datei = workspace / "rueckgaengig.txt"
    model = fake_ollama([
        ChatTurn(text='["Datei anlegen"]'),
        ChatTurn(tool_calls=[ToolCall("write_file", {
            "path": str(ziel_datei), "content": "wieder weg"})]),
        ChatTurn(text="Angelegt."),
    ])
    agent = make_agent(config, store, registry, model)

    await agent.handle_agent_task("Leg die Datei an")
    assert ziel_datei.exists()

    zusammenfassung = agent.undo.undo()

    assert not ziel_datei.exists()
    assert "entfernt" in zusammenfassung or "zurück" in zusammenfassung


# ═══════════════════════════════════════════════════════ 11 Event trigger
async def test_ereignis_erreicht_den_bus_und_wird_zum_vorschlag():
    bus = EventBus()
    gesehen: list[Event] = []

    async def zuhoerer(event):
        gesehen.append(event)

    bus.subscribe(zuhoerer)
    event = await bus.publish(Event(kind="process.crashed", severity="warning",
                                    source="watcher", payload={"name": "minecraft"}))

    assert gesehen == [event]
    assert list(bus.recent) == [event]

    vorschlag = ProactiveEngine().react(event, AutonomyLevel.GOAL_PURSUIT)
    assert vorschlag is not None
    assert "minecraft" in vorschlag.goal
    # Unklare Ursache -> Jarvis fragt, er handelt nicht (Punkt 9).
    assert vorschlag.needs_approval is True


async def test_bekannte_sichere_ursache_darf_ab_stufe_4_selbst_handeln():
    engine = ProactiveEngine([Rule(name="Bekannt", kind="disk.low", known_cause=True,
                                   goal="Räume {mount} auf")])
    event = Event(kind="disk.low", payload={"mount": "/"})

    assert engine.react(event, AutonomyLevel.PROACTIVE).needs_approval is False
    # Eine Stufe darunter wird trotz bekannter Ursache gefragt.
    assert engine.react(event, AutonomyLevel.GOAL_PURSUIT).needs_approval is True


async def test_ereignis_ohne_passende_regel_loest_nichts_aus():
    assert ProactiveEngine().react(
        Event(kind="irgendwas.egal"), AutonomyLevel.PROACTIVE) is None


async def test_wiederholt_scheiterndes_werkzeug_meldet_sich_selbst(
        config, store, registry, workspace, fake_ollama):
    """Das eine proaktive Beispiel, das ohne fehlende Sensoren auskommt:
    dreimal derselbe Fehlschlag ist eine beobachtbare Tatsache."""
    agent = make_agent(config, store, registry, fake_ollama([]))
    agent.bus = EventBus()
    gemeldet: list[Event] = []

    async def mitschreiben(event):
        gemeldet.append(event)

    agent.bus.subscribe(mitschreiben)

    for _ in range(4):
        await agent._run_tool("read_file", {"path": "gibtsnicht.txt"})
    assert len(gemeldet) == 1, "Aus einer Serie wurde Dauerfeuer"
    assert gemeldet[0].kind == "tool.failing"
    assert gemeldet[0].payload["tool"] == "read_file"

    # Ein Erfolg DESSELBEN Werkzeugs setzt die Serie zurück -- der Erfolg
    # eines anderen Werkzeugs sagt über dieses hier nichts aus.
    (workspace / "da.txt").write_text("da", encoding="utf-8")
    await agent._run_tool("get_system_info", {})
    assert agent._failure_streak.get("read_file") == 4
    await agent._run_tool("read_file", {"path": str(workspace / "da.txt")})
    assert agent._failure_streak.get("read_file") is None


async def test_ohne_bus_meldet_der_agent_nichts_und_faellt_nicht_um(
        config, store, registry, fake_ollama):
    agent = make_agent(config, store, registry, fake_ollama([]))
    for _ in range(4):
        result = await agent._run_tool("read_file", {"path": "gibtsnicht.txt"})
    assert result.ok is False  # ganz normal gescheitert, kein Absturz


async def test_ein_kaputter_zuhoerer_stoppt_die_anderen_nicht():
    bus = EventBus()
    gesehen: list[Event] = []

    async def kaputt(_event):
        raise RuntimeError("Melder defekt")

    async def heil(event):
        gesehen.append(event)

    bus.subscribe(kaputt)
    bus.subscribe(heil)
    await bus.publish(Event(kind="test"))
    assert len(gesehen) == 1


# ═══════════════════════════════════════════════════════ 12 Background Task
async def test_ziel_laeuft_im_hintergrund_und_jarvis_bleibt_ansprechbar(
        config, store, registry, workspace, fake_ollama):
    """Punkt 7: Die Antwort kommt sofort und behauptet **nichts** über ein
    Ergebnis -- gearbeitet wird daneben weiter."""
    ziel_datei = workspace / "im_hintergrund.txt"
    agent = make_agent(config, store, registry, None)
    weiter = asyncio.Event()

    class WartendesModell(SteuerndesModell):
        async def chat(self, messages, tools=None):
            self.calls.append(list(messages))
            if len(self.calls) == 2:
                await weiter.wait()
            return self.turns.pop(0) if self.turns else ChatTurn(text="(nichts mehr)")

    agent.client = WartendesModell(
        turns=[ChatTurn(text='["Datei anlegen"]'),
               ChatTurn(tool_calls=[ToolCall("write_file", {
                   "path": str(ziel_datei), "content": "fertig"})]),
               ChatTurn(text="Angelegt.")],
        bei_anfrage=0, eingriff=lambda: None)

    ziel, reply = await agent.start_goal("Leg die Datei an")

    assert ziel is not None
    assert reply.provenance == guard.TALK          # Zwischenmeldung, kein Beleg
    assert not ziel_datei.exists()                 # es läuft ja noch
    await warte_bis(lambda: len(agent.client.calls) >= 2)
    assert agent.goals.get(ziel.id).status in (GoalStatus.PLANNING, GoalStatus.RUNNING)

    weiter.set()
    await warte_bis(lambda: agent.goals.get(ziel.id).status is GoalStatus.COMPLETED)
    assert ziel_datei.read_text(encoding="utf-8") == "fertig"


# ═══════════════════════════════ 13 Agent completes multi-step task
async def test_mehrschrittiger_auftrag_wird_vollstaendig_erledigt(
        config, store, registry, workspace, fake_ollama):
    a, b = workspace / "eins.txt", workspace / "zwei.txt"
    model = fake_ollama([
        ChatTurn(text='["System prüfen", "Erste Datei", "Zweite Datei"]'),
        ChatTurn(tool_calls=[ToolCall("get_system_info", {})]), ChatTurn(text="geprüft"),
        ChatTurn(tool_calls=[ToolCall("write_file", {"path": str(a), "content": "1"})]),
        ChatTurn(text="eins da"),
        ChatTurn(tool_calls=[ToolCall("write_file", {"path": str(b), "content": "2"})]),
        ChatTurn(text="zwei da"),
    ])
    events: list = []
    agent = make_agent(config, store, registry, model, events)

    reply = await agent.handle_agent_task("Richte das Projekt ein")

    assert reply.provenance == guard.TOOL
    assert a.read_text(encoding="utf-8") == "1"
    assert b.read_text(encoding="utf-8") == "2"

    ziel = agent.goals.list()[0]
    assert ziel.status is GoalStatus.COMPLETED
    assert ziel.progress == 1.0
    aufgabe = agent.tasks.get(ziel.subtasks[0])
    assert all(s.status is StepStatus.DONE for s in aufgabe.steps)
    # Working Memory (Punkt 14): der nahe Verlauf steht am Ziel.
    assert len(ziel.working_memory["verlauf"]) == 3
    assert ziel.working_memory["weltzustand"]["ollama_erreichbar"] is True
    # Punkt 21: gemeldet wird der Zielverlauf, nicht jeder Mini-Schritt.
    kinds = [k for k, _ in events]
    assert kinds.count("task.step.finished") == 3
    assert kinds.count("goal.finished") == 1
