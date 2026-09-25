"""Decision Engine: Kandidaten abwägen -- Erfolgswahrscheinlichkeit, Kosten,
Risiko, Zeit, und echte bisherige Erfahrung aus dem Audit Log (Punkt 3)."""

from __future__ import annotations

import json

from jarvis.audit import AuditLog
from jarvis.decision import DecisionEngine, DecisionLog, _parse_candidates
from jarvis.permissions import PermissionLevel


def _kandidaten_json(*kandidaten: dict) -> str:
    return json.dumps(list(kandidaten))


def test_parse_extrahiert_gueltige_kandidaten():
    text = _kandidaten_json(
        {"beschreibung": "Logs analysieren", "werkzeug": "read_file",
         "erfolgswahrscheinlichkeit": 0.6, "kosten": 0.2, "risiko": "LOW", "zeit": 0.2})
    kandidaten = _parse_candidates(text)
    assert len(kandidaten) == 1
    assert kandidaten[0].tool == "read_file"
    assert kandidaten[0].risk == "LOW"


def test_parse_ignoriert_kandidaten_ohne_beschreibung():
    text = _kandidaten_json({"werkzeug": "read_file", "erfolgswahrscheinlichkeit": 0.9})
    assert _parse_candidates(text) == []


def test_parse_faellt_bei_kaputtem_json_auf_leere_liste_zurueck():
    assert _parse_candidates("das ist kein JSON") == []


def test_parse_normalisiert_unbekanntes_risiko_auf_medium():
    text = _kandidaten_json({"beschreibung": "x", "risiko": "SEHR HOCH"})
    assert _parse_candidates(text)[0].risk == "MEDIUM"


async def test_waehlt_hoechsten_score_bei_erreichbarem_modell(fake_ollama):
    model = fake_ollama([_kandidaten_json(
        {"beschreibung": "Riskant und langsam", "werkzeug": None,
         "erfolgswahrscheinlichkeit": 0.5, "kosten": 0.9, "risiko": "HIGH", "zeit": 0.9},
        {"beschreibung": "Sicher und schnell", "werkzeug": None,
         "erfolgswahrscheinlichkeit": 0.9, "kosten": 0.1, "risiko": "LOW", "zeit": 0.1},
    )])
    engine = DecisionEngine(model)
    decision = await engine.choose("Programm startet nicht")
    assert decision.chosen.description == "Sicher und schnell"


async def test_ohne_brauchbare_antwort_ein_neutraler_kandidat_statt_erfundener_auswahl(
        fake_ollama):
    model = fake_ollama(["kein JSON, kein Plan"])
    engine = DecisionEngine(model)
    decision = await engine.choose("Etwas Undefiniertes")
    assert len(decision.candidates) == 1
    assert decision.chosen.description == "Etwas Undefiniertes"


async def test_kandidaten_mit_nicht_existierendem_werkzeug_werden_verworfen(fake_ollama):
    model = fake_ollama([_kandidaten_json(
        {"beschreibung": "Erfundenes Werkzeug", "werkzeug": "gibt_es_nicht",
         "erfolgswahrscheinlichkeit": 0.99, "kosten": 0.0, "risiko": "LOW", "zeit": 0.0},
        {"beschreibung": "Echtes Werkzeug", "werkzeug": "read_file",
         "erfolgswahrscheinlichkeit": 0.5, "kosten": 0.5, "risiko": "MEDIUM", "zeit": 0.5},
    )])
    engine = DecisionEngine(model)
    decision = await engine.choose("Problem", registry_names={"read_file"})
    assert decision.chosen.tool == "read_file"


async def test_bisherige_erfahrung_aus_dem_audit_log_beeinflusst_die_wahl(fake_ollama, tmp_path):
    audit = AuditLog(tmp_path / "protokoll.sqlite3")
    for _ in range(5):
        audit.record(tool="start_process", level=PermissionLevel.SYSTEM, arguments={},
                    ok=False, summary="Port belegt")
    for _ in range(5):
        audit.record(tool="run_diagnostics", level=PermissionLevel.READ, arguments={},
                    ok=True, summary="ok")
    model = fake_ollama([_kandidaten_json(
        {"beschreibung": "Direkt neu starten", "werkzeug": "start_process",
         "erfolgswahrscheinlichkeit": 0.5, "kosten": 0.3, "risiko": "MEDIUM", "zeit": 0.3},
        {"beschreibung": "Erst Diagnose", "werkzeug": "run_diagnostics",
         "erfolgswahrscheinlichkeit": 0.5, "kosten": 0.3, "risiko": "MEDIUM", "zeit": 0.3},
    )])
    engine = DecisionEngine(model, audit=audit)
    decision = await engine.choose("Server startet nicht")
    assert decision.chosen.tool == "run_diagnostics"


async def test_entscheidung_wird_geloggt(fake_ollama, tmp_path):
    log = DecisionLog(tmp_path / "entscheidungen.sqlite3")
    model = fake_ollama([_kandidaten_json({"beschreibung": "Einzige Option"})])
    engine = DecisionEngine(model, log=log)
    decision = await engine.choose("Problem", goal_id="goal-1")

    gespeichert = log.list(goal_id="goal-1")
    assert len(gespeichert) == 1
    assert gespeichert[0]["id"] == decision.id
    assert gespeichert[0]["gewaehlt"]["beschreibung"] == "Einzige Option"
