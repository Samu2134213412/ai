"""Das Zwischenablage-Pack: ohne grafische Sitzung (kein DISPLAY, kein
xclip/xsel/wl-clipboard) bleibt es bei der ehrlichen Fehlermeldung --
genau der Zustand dieser Sandbox. Läuft irgendwo eine echte Desktop-Sitzung
mit einem der bekannten Werkzeuge, laufen die markierten Tests live mit."""

from __future__ import annotations

import shutil

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult
from jarvis.tools.packs.clipboard import _lese_befehl, _schreib_befehl


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


_hat_werkzeug = _lese_befehl() is not None and _schreib_befehl() is not None
braucht_werkzeug = pytest.mark.skipif(not _hat_werkzeug,
                                      reason="kein Zwischenablage-Werkzeug in dieser Sitzung")


def test_ohne_werkzeug_meldet_read_das_ehrlich(tools):
    if _hat_werkzeug:
        pytest.skip("hier ist tatsächlich ein Zwischenablage-Werkzeug vorhanden")
    res = fehler(tools("clipboard.read"))
    assert "zwischenablage" in res.summary.lower() or "grafische sitzung" in res.summary.lower()


def test_ohne_werkzeug_meldet_write_das_ehrlich(tools):
    if _hat_werkzeug:
        pytest.skip("hier ist tatsächlich ein Zwischenablage-Werkzeug vorhanden")
    fehler(tools("clipboard.write", text="hallo"))


@braucht_werkzeug
def test_write_dann_read_liefert_denselben_text(tools):
    erfolg(tools("clipboard.write", text="Jarvis-Test-Inhalt"))
    gelesen = erfolg(tools("clipboard.read"))
    assert gelesen.payload == "Jarvis-Test-Inhalt"


@braucht_werkzeug
def test_clear_leert_wirklich(tools):
    erfolg(tools("clipboard.write", text="etwas"))
    erfolg(tools("clipboard.clear"))
    gelesen = erfolg(tools("clipboard.read"))
    assert gelesen.payload == "(leer)"


@braucht_werkzeug
def test_has_content(tools):
    erfolg(tools("clipboard.clear"))
    leer = erfolg(tools("clipboard.has_content"))
    assert leer.evidence["vorhanden"] is False

    erfolg(tools("clipboard.write", text="x"))
    voll = erfolg(tools("clipboard.has_content"))
    assert voll.evidence["vorhanden"] is True
