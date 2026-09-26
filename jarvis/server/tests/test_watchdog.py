"""Watchdog: Budgets und Wiederholungserkennung, damit Selbstkorrektur nicht
zur Endlosschleife wird (Punkte 18/19)."""

from __future__ import annotations

import time

from jarvis.goals import GoalBudget
from jarvis.watchdog import Watchdog


def test_darf_zu_beginn_weitermachen():
    wd = Watchdog(budget=GoalBudget())
    assert wd.verdict().ok is True


def test_schritt_limit_greift():
    wd = Watchdog(budget=GoalBudget(max_steps=2))
    wd.note_step()
    wd.note_step()
    wd.note_step()
    verdict = wd.verdict()
    assert verdict.ok is False
    assert "Schritt-Limit" in verdict.reason


def test_werkzeugaufruf_limit_greift():
    wd = Watchdog(budget=GoalBudget(max_tool_calls=2))
    for _ in range(3):
        wd.note_tool_call("read_file", {"path": "a"}, ok=True, summary="ok")
    verdict = wd.verdict()
    assert verdict.ok is False
    assert "Werkzeugaufruf-Limit" in verdict.reason


def test_zeitlimit_greift():
    wd = Watchdog(budget=GoalBudget(max_runtime_minutes=0.0001), started_at=time.time() - 10)
    verdict = wd.verdict()
    assert verdict.ok is False
    assert "Zeitlimit" in verdict.reason


def test_erkennt_dieselbe_fehlgeschlagene_aktion_wiederholt():
    wd = Watchdog()
    for _ in range(3):
        wd.note_tool_call("start_process", {"name": "server"}, ok=False, summary="Port belegt")
    verdict = wd.verdict()
    assert verdict.ok is False
    assert "wiederholt" in verdict.reason


def test_verschiedene_fehlgeschlagene_aktionen_loesen_keine_loop_erkennung_aus():
    wd = Watchdog()
    wd.note_tool_call("start_process", {"name": "server"}, ok=False, summary="Port belegt")
    wd.note_tool_call("list_processes", {}, ok=True, summary="ok")
    wd.note_tool_call("start_process", {"name": "server", "port": 25566}, ok=True, summary="läuft")
    assert wd.verdict().ok is True


def test_erkennt_denselben_fehler_bei_unterschiedlichen_argumenten():
    wd = Watchdog()
    wd.note_tool_call("start_process", {"name": "a"}, ok=False, summary="Port belegt")
    wd.note_tool_call("start_process", {"name": "b"}, ok=False, summary="Port belegt")
    wd.note_tool_call("start_process", {"name": "c"}, ok=False, summary="Port belegt")
    verdict = wd.verdict()
    assert verdict.ok is False
    assert "Derselbe Fehler" in verdict.reason


def test_erfolgreiche_aufrufe_zwischendrin_setzen_die_zaehlung_zurueck():
    wd = Watchdog()
    wd.note_tool_call("x", {}, ok=False, summary="nein")
    wd.note_tool_call("x", {}, ok=False, summary="nein")
    wd.note_tool_call("x", {}, ok=True, summary="doch")
    assert wd.verdict().ok is True
