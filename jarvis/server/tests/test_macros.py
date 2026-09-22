"""MacroEngine/MacroStore: reine Logik, unabhängig von Agent getestet -- mit
einem eingespeisten ``run_tool``-Callable, genau wie ``verification.py`` und
``decision.py`` es vorgeben. Kein Mock des Agenten nötig, weil die Engine
den Agenten gar nicht kennt.
"""

from __future__ import annotations

import time

import pytest

from jarvis.macros import MacroEngine, MacroError, MacroStore, auswerten
from jarvis.tools.base import ToolResult


class FakeTools:
    """Ruft vorgegebene Werkzeuge auf und merkt sich jeden Aufruf."""

    def __init__(self, antworten: dict[str, list[ToolResult]] | None = None):
        self.antworten = {k: list(v) for k, v in (antworten or {}).items()}
        self.aufrufe: list[tuple[str, dict]] = []

    async def run_tool(self, name: str, arguments: dict) -> ToolResult:
        self.aufrufe.append((name, dict(arguments)))
        warteschlange = self.antworten.get(name)
        if warteschlange:
            return warteschlange.pop(0)
        return ToolResult(tool=name, ok=True, summary=f"{name} ok", evidence={})


def ok(tool="t", summary="ok", **evidence) -> ToolResult:
    return ToolResult(tool=tool, ok=True, summary=summary, evidence=evidence)


def bad(tool="t", summary="fehlgeschlagen", **evidence) -> ToolResult:
    return ToolResult(tool=tool, ok=False, summary=summary, evidence=evidence)


# ═══════════════════════════════════════════════════════════════ tool-Schritte
async def test_einzelner_werkzeugschritt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"id": "s1", "kind": "tool", "tool": "files.info",
                              "arguments": {"path": "x.txt"}}])
    assert lauf.ok is True
    assert fake.aufrufe == [("files.info", {"path": "x.txt"})]
    assert lauf.results["s1"].ok is True


async def test_fehlgeschlagener_schritt_bricht_ab():
    fake = FakeTools(antworten={"a": [bad()], "b": [ok()]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"id": "s1", "kind": "tool", "tool": "a"},
        {"id": "s2", "kind": "tool", "tool": "b"},
    ])
    assert lauf.ok is False
    assert [n for n, _ in fake.aufrufe] == ["a"]  # b lief nicht mehr


async def test_continue_on_error_laeuft_trotzdem_weiter():
    fake = FakeTools(antworten={"a": [bad()], "b": [ok()]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"id": "s1", "kind": "tool", "tool": "a", "continue_on_error": True},
        {"id": "s2", "kind": "tool", "tool": "b"},
    ])
    assert [n for n, _ in fake.aufrufe] == ["a", "b"]
    assert lauf.results["s1"].ok is False
    assert lauf.results["s2"].ok is True


async def test_schritt_ohne_id_bekommt_einen_ersatznamen():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"kind": "tool", "tool": "a"}])
    assert len(lauf.results) == 1


async def test_unbekannte_schrittart_wird_abgelehnt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    with pytest.raises(MacroError):
        await engine.run([{"kind": "unsinn"}])


async def test_tool_schritt_ohne_tool_feld_wird_abgelehnt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    with pytest.raises(MacroError):
        await engine.run([{"kind": "tool"}])


# ═══════════════════════════════════════════════════════════════ retry
async def test_retry_versucht_bis_zum_erfolg():
    fake = FakeTools(antworten={"a": [bad(), bad(), ok()]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"id": "s1", "kind": "tool", "tool": "a", "retry": 3,
                              "retry_delay": 0}])
    assert lauf.ok is True
    assert len(fake.aufrufe) == 3
    assert lauf.log[0].versuche == 3


async def test_retry_erschoepft_bleibt_fehlgeschlagen():
    fake = FakeTools(antworten={"a": [bad(), bad(), bad()]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"id": "s1", "kind": "tool", "tool": "a", "retry": 2,
                              "retry_delay": 0}])
    assert lauf.ok is False
    assert len(fake.aufrufe) == 3  # 1 Versuch + 2 Wiederholungen


async def test_retry_wartet_wirklich(monkeypatch):
    fake = FakeTools(antworten={"a": [bad(), ok()]})
    engine = MacroEngine(fake.run_tool)
    start = time.monotonic()
    await engine.run([{"id": "s1", "kind": "tool", "tool": "a", "retry": 1,
                       "retry_delay": 0.3}])
    assert time.monotonic() - start >= 0.25


# ═══════════════════════════════════════════════════════════════ if
async def test_if_waehlt_then_zweig():
    fake = FakeTools(antworten={"pruefung": [ok()], "dann": [ok()], "sonst": [ok()]})
    engine = MacroEngine(fake.run_tool)
    await engine.run([
        {"id": "s1", "kind": "tool", "tool": "pruefung"},
        {"kind": "if", "condition": {"step": "s1", "field": "ok", "op": "==", "value": True},
         "then": [{"kind": "tool", "tool": "dann"}],
         "else": [{"kind": "tool", "tool": "sonst"}]},
    ])
    namen = [n for n, _ in fake.aufrufe]
    assert namen == ["pruefung", "dann"]


async def test_if_waehlt_else_zweig():
    fake = FakeTools(antworten={"pruefung": [bad()]})
    engine = MacroEngine(fake.run_tool)
    await engine.run([
        {"id": "s1", "kind": "tool", "tool": "pruefung", "continue_on_error": True},
        {"kind": "if", "condition": {"step": "s1", "field": "ok", "op": "==", "value": True},
         "then": [{"kind": "tool", "tool": "dann"}],
         "else": [{"kind": "tool", "tool": "sonst"}]},
    ])
    namen = [n for n, _ in fake.aufrufe]
    assert namen == ["pruefung", "sonst"]


async def test_if_mit_evidence_feld():
    fake = FakeTools(antworten={"groesse": [ok(groesse=5000)]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"id": "s1", "kind": "tool", "tool": "groesse"},
        {"kind": "if", "condition": {"step": "s1", "field": "evidence.groesse",
                                     "op": ">", "value": 1000},
         "then": [{"kind": "tool", "tool": "gross"}],
         "else": [{"kind": "tool", "tool": "klein"}]},
    ])
    namen = [n for n, _ in fake.aufrufe]
    assert namen == ["groesse", "gross"]


async def test_bedingung_auf_unbekannten_schritt_schlaegt_fehl():
    ergebnisse = {}
    with pytest.raises(MacroError):
        auswerten({"step": "gibtsnicht", "op": "==", "value": True}, ergebnisse)


async def test_bedingung_mit_unbekanntem_operator_schlaegt_fehl():
    ergebnisse = {"s1": ok()}
    with pytest.raises(MacroError):
        auswerten({"step": "s1", "op": "was denn", "value": True}, ergebnisse)


# ═══════════════════════════════════════════════════════════════ loop
async def test_loop_times_wiederholt_genau_so_oft():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    await engine.run([{"kind": "loop", "times": 4, "body": [{"kind": "tool", "tool": "a"}]}])
    assert len(fake.aufrufe) == 4


async def test_loop_while_stoppt_wenn_bedingung_falsch_wird():
    fake = FakeTools(antworten={"pruefung": [ok(), ok(), bad()]})
    engine = MacroEngine(fake.run_tool)
    await engine.run([
        {"kind": "loop",
         "while": {"step": "pruef", "field": "ok", "op": "==", "value": True},
         "max_iterations": 10,
         "body": [{"id": "pruef", "kind": "tool", "tool": "pruefung", "continue_on_error": True},
                 {"kind": "tool", "tool": "arbeit"}]},
    ])
    namen = [n for n, _ in fake.aufrufe]
    # while wird NACH jedem Durchlauf geprüft: "arbeit" läuft also noch im
    # dritten Durchlauf mit, bevor die fehlgeschlagene Prüfung die Schleife
    # danach beendet.
    assert namen.count("arbeit") == 3


async def test_schleife_mit_wiederverwendeter_id_zaehlt_trotzdem_jeden_lauf():
    """Der im Docstring beschriebene Normalfall für 'while': der Rumpf
    verwendet dieselbe id in jedem Durchlauf, damit die Bedingung sie lesen
    kann. ``results`` (nach id) hält dabei bewusst nur das letzte Ergebnis --
    aber ``all_results`` darf die drei tatsächlich gelaufenen Aufrufe nicht
    verlieren, sonst berichtet summary() am Ende "1/1" für einen Lauf, der
    wirklich dreimal ein Werkzeug aufgerufen hat."""
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"kind": "loop", "times": 3, "body": [{"id": "s1", "kind": "tool", "tool": "a"}]},
    ])
    assert len(lauf.results) == 1  # nach id: nur der letzte Durchlauf
    assert len(lauf.all_results) == 3  # tatsächlich gelaufen: alle drei
    assert lauf.summary("m") == "Makro 'm': 3/3 Werkzeugaufrufe, alle erfolgreich"


async def test_loop_ohne_times_und_ohne_while_wird_abgelehnt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    with pytest.raises(MacroError):
        await engine.run([{"kind": "loop", "body": [{"kind": "tool", "tool": "a"}]}])


async def test_endlosschleife_bricht_an_der_obergrenze_ab():
    fake = FakeTools()  # 'pruefung' antwortet immer mit ok() -> while bleibt ewig wahr
    engine = MacroEngine(fake.run_tool)
    with pytest.raises(MacroError, match="Durchläufen"):
        await engine.run([
            {"kind": "loop",
             "while": {"step": "s0", "field": "ok", "op": "==", "value": True},
             "max_iterations": 5,
             "body": [{"id": "s0", "kind": "tool", "tool": "pruefung"}]},
        ])


async def test_max_iterations_wird_auf_die_globale_obergrenze_gedeckelt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    engine.MAX_LOOP_ITERATIONS = 3  # fuer den Test verkleinert
    with pytest.raises(MacroError):
        await engine.run([
            {"kind": "loop",
             "while": {"step": "s0", "field": "ok", "op": "==", "value": True},
             "max_iterations": 1000,  # verlangt mehr, als MAX_LOOP_ITERATIONS erlaubt
             "body": [{"id": "s0", "kind": "tool", "tool": "pruefung"}]},
        ])
    assert len(fake.aufrufe) == 3


# ═══════════════════════════════════════════════════════════════ parallel
async def test_parallel_laeuft_beide_zweige():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"kind": "parallel", "branches": [
            [{"id": "a1", "kind": "tool", "tool": "a"}],
            [{"id": "b1", "kind": "tool", "tool": "b"}],
        ]},
    ])
    assert lauf.ok is True
    assert set(n for n, _ in fake.aufrufe) == {"a", "b"}
    assert "a1" in lauf.results and "b1" in lauf.results
    assert len(lauf.all_results) == 2


async def test_parallel_ist_wirklich_gleichzeitig():
    import asyncio

    reihenfolge = []

    async def langsames_werkzeug(name, arguments):
        wartezeit = arguments.get("dauer", 0)
        await asyncio.sleep(wartezeit)
        reihenfolge.append(name)
        return ToolResult(tool=name, ok=True, summary="ok")

    engine = MacroEngine(langsames_werkzeug)
    start = time.monotonic()
    await engine.run([
        {"kind": "parallel", "branches": [
            [{"kind": "tool", "tool": "langsam", "arguments": {"dauer": 0.3}}],
            [{"kind": "tool", "tool": "schnell", "arguments": {"dauer": 0.05}}],
        ]},
    ])
    dauer = time.monotonic() - start
    # Nacheinander waeren es >= 0.35s; gleichzeitig deutlich weniger.
    assert dauer < 0.32
    assert reihenfolge == ["schnell", "langsam"]


async def test_parallel_ein_fehlschlagender_zweig_macht_das_ergebnis_falsch():
    fake = FakeTools(antworten={"a": [ok()], "b": [bad()]})
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([
        {"kind": "parallel", "branches": [
            [{"kind": "tool", "tool": "a"}],
            [{"kind": "tool", "tool": "b"}],
        ]},
    ])
    assert lauf.ok is False


async def test_parallel_ohne_zweige_ist_ein_no_op():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"kind": "parallel", "branches": []}])
    assert lauf.ok is True


# ═══════════════════════════════════════════════════════════════ wait
async def test_wait_wartet_wirklich():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    start = time.monotonic()
    lauf = await engine.run([{"id": "w1", "kind": "wait", "seconds": 0.3}])
    assert time.monotonic() - start >= 0.25
    assert lauf.log[0].kind == "wait"


async def test_wait_wird_auf_maximum_gedeckelt():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    engine.MAX_WAIT_SECONDS = 0.1
    start = time.monotonic()
    await engine.run([{"kind": "wait", "seconds": 10}])
    assert time.monotonic() - start < 1.0


# ═══════════════════════════════════════════════════════════════ Notbremse
async def test_zu_viele_gesamtschritte_bricht_ab():
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    engine.MAX_STEPS_TOTAL = 5
    with pytest.raises(MacroError, match="Einzelschritte"):
        await engine.run([{"kind": "loop", "times": 100,
                           "body": [{"kind": "tool", "tool": "a"}]}])


# ═══════════════════════════════════════════════════════════════ Zusammenfassung
async def test_summary_ohne_vollzugswort():
    from jarvis import guard
    fake = FakeTools()
    engine = MacroEngine(fake.run_tool)
    lauf = await engine.run([{"id": "s1", "kind": "tool", "tool": "a"}])
    text = lauf.summary("mein_makro")
    assert guard.claims_completion(text) is False


# ═══════════════════════════════════════════════════════════════ MacroStore
@pytest.fixture
def store():
    s = MacroStore(":memory:")
    yield s
    s.close()


def test_store_save_and_get(store):
    definition = store.save("begruessung", [{"kind": "tool", "tool": "a"}], description="Test")
    geladen = store.get_by_name("begruessung")
    assert geladen is not None
    assert geladen.id == definition.id
    assert geladen.steps == [{"kind": "tool", "tool": "a"}]


def test_store_save_ohne_namen_wird_abgelehnt(store):
    with pytest.raises(MacroError):
        store.save("", [{"kind": "tool", "tool": "a"}])


def test_store_save_ohne_schritte_wird_abgelehnt(store):
    with pytest.raises(MacroError):
        store.save("leer", [])


def test_store_save_ueberschreibt_bei_gleichem_namen(store):
    erste = store.save("x", [{"kind": "tool", "tool": "a"}])
    zweite = store.save("x", [{"kind": "tool", "tool": "b"}])
    assert erste.id == zweite.id  # dieselbe Definition, nur aktualisiert
    geladen = store.get_by_name("x")
    assert geladen.steps == [{"kind": "tool", "tool": "b"}]


def test_store_list(store):
    store.save("b", [{"kind": "tool", "tool": "x"}])
    store.save("a", [{"kind": "tool", "tool": "x"}])
    namen = [m.name for m in store.list()]
    assert namen == ["a", "b"]  # alphabetisch


def test_store_delete(store):
    store.save("x", [{"kind": "tool", "tool": "a"}])
    assert store.delete("x") is True
    assert store.get_by_name("x") is None
    assert store.delete("x") is False


def test_store_ueberlebt_neustart(tmp_path):
    pfad = tmp_path / "makros.sqlite3"
    s1 = MacroStore(pfad)
    s1.save("dauerhaft", [{"kind": "tool", "tool": "a"}])
    s1.close()
    s2 = MacroStore(pfad)
    geladen = s2.get_by_name("dauerhaft")
    s2.close()
    assert geladen is not None
    assert geladen.steps == [{"kind": "tool", "tool": "a"}]
