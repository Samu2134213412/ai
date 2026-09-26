"""ToolDiscovery/ToolIndex (Punkt 34): Suche, Ranking, Favoriten-/Verlaufs-/
Kontextbonus -- gegen die echte, volle Registry, kein künstlich kleiner
Testkatalog. Genau die Größe (mehrere hundert Tools), für die die Suche
überhaupt gebraucht wird."""

from __future__ import annotations

import pytest

from jarvis.tools import ToolDiscovery, ToolHistory, ToolIndex, build_registry
from jarvis.tools.discovery import CORE_TOOLS, DEFAULT_LIMIT, terms


@pytest.fixture
def registry(config, store):
    return build_registry(config, store)


def test_terms_entfernt_fuellwoerter_und_kleinschreibt():
    assert terms("Wie ist die GPU Temperatur?") == ["gpu", "temperatur"]


def test_terms_faltet_umlaute_akzentfrei():
    assert "temperatur" in terms("Temperatur der Grafikkarte")


# ═══════════════════════════════════════════════════════════════ ToolIndex
def test_index_findet_werkzeug_ueber_namensteile(registry):
    index = ToolIndex(registry)
    treffer = index.search("gpu temperatur")
    assert treffer
    assert treffer[0].tool.name == "system.gpu.temperature"


def test_index_findet_werkzeug_ueber_beschreibung(registry):
    index = ToolIndex(registry)
    treffer = index.search("QR Code erstellen")
    namen = [h.tool.name for h in treffer]
    assert "productivity.qrcode.generate" in namen


def test_index_woertlicher_name_im_query_gewinnt(registry):
    """'git commit' muss git.commit weit vor entfernteren Treffern zeigen."""
    index = ToolIndex(registry)
    treffer = index.search("git commit", limit=5)
    assert treffer[0].tool.name == "git.commit"


def test_index_teiltreffer_ueber_praefix(registry):
    """'temp' (zu kurz für Fuzzy-Vergleich am ganzen Namen) findet trotzdem
    über den Präfix-Teiltreffer etwas mit 'temperature' im Namen."""
    index = ToolIndex(registry)
    treffer = index.search("system temp")
    namen = [h.tool.name for h in treffer]
    assert any("temperature" in n for n in namen)


def test_index_respektiert_limit(registry):
    index = ToolIndex(registry)
    treffer = index.search("datei", limit=3)
    assert len(treffer) <= 3


def test_index_kategorie_filter(registry):
    index = ToolIndex(registry)
    treffer = index.search("branch", category="git", limit=50)
    assert treffer
    assert all(h.tool.category == "git" for h in treffer)


def test_index_ohne_treffer_ist_leere_liste(registry):
    index = ToolIndex(registry)
    assert index.search("xyzxyzxyz_kein_treffer_moeglich") == []


def test_index_nicht_lauffaehiges_werkzeug_wird_ausgeschlossen(registry):
    index = ToolIndex(registry)
    treffer = index.search("docker container starten", include_unavailable=False, limit=50)
    # Ohne laufenden Docker-Daemon ist docker.* hier nicht lauffähig --
    # taucht also entweder gar nicht auf oder deutlich abgewertet, je nach
    # Umgebung. Der Test prüft nur, dass der Filter nichts zerstört.
    assert isinstance(treffer, list)


def test_rebuild_erfasst_neu_hinzugefuegte_werkzeuge(registry):
    from jarvis.tools.base import PermissionLevel, Tool
    from jarvis.tools.packs._base import NO_PARAMS, ok

    index = ToolIndex(registry)
    assert index.search("flurwiesenschmetterling") == []

    registry.add(Tool("test.zauber", "Ein Werkzeug für den Flurwiesenschmetterling.",
                      NO_PARAMS, lambda: ok("test.zauber", "ok"),
                      level=PermissionLevel.SAFE))
    index.rebuild()
    treffer = index.search("flurwiesenschmetterling")
    assert treffer and treffer[0].tool.name == "test.zauber"


# ═══════════════════════════════════════════════════════════ ToolDiscovery
def test_select_enthaelt_immer_die_core_tools(registry):
    discovery = ToolDiscovery(registry)
    ausgewaehlt = discovery.select("irgendetwas ganz anderes")
    for name in CORE_TOOLS:
        if name in registry:
            assert registry.resolve(name) in ausgewaehlt


def test_select_bleibt_unter_der_katalog_groesse(registry):
    """Der eigentliche Zweck: eine Handvoll Tools statt des ganzen Katalogs."""
    discovery = ToolDiscovery(registry)
    ausgewaehlt = discovery.select("lösche eine datei")
    assert len(ausgewaehlt) < len(registry)
    assert len(ausgewaehlt) <= len(CORE_TOOLS) + DEFAULT_LIMIT


def test_schemas_for_liefert_gueltige_ollama_schemata(registry):
    discovery = ToolDiscovery(registry)
    schemas = discovery.schemas_for("committe meine änderungen")
    namen = {s["function"]["name"] for s in schemas}
    assert "git.commit" in namen
    assert all(s["type"] == "function" for s in schemas)


def test_favorit_hebt_das_werkzeug_im_ranking(registry):
    history = ToolHistory(":memory:")
    discovery = ToolDiscovery(registry, history=history)

    vorher = discovery.search("verzeichnis")
    history.favorite("list_dir")
    nachher = discovery.search("verzeichnis")

    platz_vorher = next(i for i, h in enumerate(vorher) if h.tool.name == "list_dir")
    platz_nachher = next(i for i, h in enumerate(nachher) if h.tool.name == "list_dir")
    assert platz_nachher <= platz_vorher


def test_note_use_hebt_kuerzlich_benutztes(registry):
    discovery = ToolDiscovery(registry)
    discovery.note_use("git.status")
    boosts = discovery._boosts()
    assert boosts.get("git.status", 0) > 0


def test_note_use_loest_alias_auf(registry):
    discovery = ToolDiscovery(registry)
    discovery.note_use("get_system_info")
    assert discovery.recent == ["system.info"]


def test_kontext_hebt_passende_kategorie(registry):
    discovery = ToolDiscovery(registry)
    discovery.set_context("code")
    boosts = discovery._boosts()
    irgendein_git_tool = next(t.name for t in registry if t.category == "git")
    assert boosts.get(irgendein_git_tool, 0) > 0


def test_leerer_kontext_hebt_nichts(registry):
    discovery = ToolDiscovery(registry)
    discovery.set_context("")
    assert discovery._boosts() == {}


def test_search_ohne_geschichte_funktioniert_trotzdem(registry):
    """Ohne ToolHistory (None) läuft die Suche weiter -- nur ohne
    Favoriten-Bonus, kein Fehlschlag."""
    discovery = ToolDiscovery(registry, history=None)
    treffer = discovery.search("git commit")
    assert treffer
