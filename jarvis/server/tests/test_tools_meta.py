"""jarvis.tools.* -- Introspektion über den eigenen Werkzeugkasten (Punkt 36).

Läuft gegen die echte, fertige Registry (mit Discovery/History, siehe
build_registry()) -- kein Mock: das Ziel dieser Werkzeuge ist ja genau,
Auskunft über die echte Registry zu geben.
"""

from __future__ import annotations

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


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


def test_registry_traegt_den_meta_pack_ohne_fehler(tools):
    assert tools.registry.pack_errors == {}
    assert "jarvis.tools.search" in tools.registry


def test_tools_search_findet_git_werkzeuge(tools):
    res = erfolg(tools("jarvis.tools.search", query="git commit"))
    assert "git.commit" in res.payload


def test_tools_search_index_kennt_auch_sich_selbst(tools):
    """Der Suchindex wird nach dem Bauen der jarvis.tools.*-Werkzeuge neu
    aufgebaut (siehe build_registry) -- sonst fände jarvis.tools.search nie
    sich selbst oder die anderen Meta-Werkzeuge."""
    res = erfolg(tools("jarvis.tools.search", query="werkzeug favorit markieren"))
    assert "jarvis.tools.favorite" in res.payload


def test_tools_info_zeigt_details(tools):
    res = erfolg(tools("jarvis.tools.info", name="write_file"))
    assert res.payload["id"] == "write_file"
    assert res.payload["favorit"] is False
    assert res.payload["abgeschaltet"] is False
    assert "verfuegbarkeit" in res.payload


def test_tools_info_unbekanntes_werkzeug_ist_ehrlicher_fehlschlag(tools):
    fehler(tools("jarvis.tools.info", name="das.gibt.es.nicht"))


def test_tools_list_ohne_filter_zeigt_alle(tools):
    res = erfolg(tools("jarvis.tools.list"))
    assert res.evidence["anzahl"] == len(tools.registry)


def test_tools_list_mit_kategorie_filtert(tools):
    res = erfolg(tools("jarvis.tools.list", category="git"))
    assert res.evidence["anzahl"] > 0
    assert res.evidence["anzahl"] < len(tools.registry)
    assert "git." in res.payload


def test_favorit_setzen_und_wieder_entfernen(tools):
    erfolg(tools("jarvis.tools.favorite", name="write_file"))
    liste = erfolg(tools("jarvis.tools.favorites"))
    assert "write_file" in liste.payload

    erfolg(tools("jarvis.tools.unfavorite", name="write_file"))
    liste2 = erfolg(tools("jarvis.tools.favorites"))
    assert "write_file" not in liste2.payload


def test_favorit_ueber_alias_wird_auf_den_echten_namen_aufgeloest(tools):
    """'get_system_info' ist ein Alias von 'system.info' -- der Favorit muss
    unter dem echten Namen landen, sonst findet ihn discovery._boosts() nie."""
    erfolg(tools("jarvis.tools.favorite", name="get_system_info"))
    liste = erfolg(tools("jarvis.tools.favorites"))
    assert "system.info" in liste.payload
    assert "get_system_info" not in liste.payload


def test_unfavorite_ohne_vorherigen_favorit_ist_ehrlicher_fehlschlag(tools):
    fehler(tools("jarvis.tools.unfavorite", name="write_file"))


def test_favorite_unbekanntes_werkzeug_wird_abgelehnt(tools):
    fehler(tools("jarvis.tools.favorite", name="das.gibt.es.nicht"))


def test_abschalten_und_wieder_anschalten(tools):
    erfolg(tools("jarvis.tools.disable", name="write_file", reason="testweise"))
    info = erfolg(tools("jarvis.tools.info", name="write_file"))
    assert info.payload["abgeschaltet"] is True

    erfolg(tools("jarvis.tools.enable", name="write_file"))
    info2 = erfolg(tools("jarvis.tools.info", name="write_file"))
    assert info2.payload["abgeschaltet"] is False


def test_sich_selbst_abschalten_ist_verboten(tools):
    """Sonst gäbe es über das Modell keinen Weg mehr zurück."""
    res = fehler(tools("jarvis.tools.disable", name="jarvis.tools.enable"))
    assert "lässt sich nicht abschalten" in res.summary


def test_enable_ohne_vorheriges_abschalten_ist_ehrlicher_fehlschlag(tools):
    fehler(tools("jarvis.tools.enable", name="write_file"))


def test_history_und_stats_bleiben_leer_ohne_aufrufe(tools):
    verlauf = erfolg(tools("jarvis.tools.history"))
    assert verlauf.evidence["anzahl"] == 0
    stats = erfolg(tools("jarvis.tools.stats"))
    assert stats.evidence["anzahl"] == 0
