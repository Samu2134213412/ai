"""Das Such-Pack: search.files läuft gegen einen echten Dateibaum. search.apps
läuft plattformabhängig -- unter Linux gegen echte, selbst angelegte
.desktop-Dateien (kein Mock, echte Dateien im XDG-Format)."""

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


@pytest.fixture
def baum(workspace):
    (workspace / "bericht_2026.txt").write_text("x", encoding="utf-8")
    (workspace / "rechnung_maerz.pdf").write_text("x", encoding="utf-8")
    unter = workspace / "projekt"
    unter.mkdir()
    (unter / "readme.md").write_text("x", encoding="utf-8")
    (unter / "notizen.txt").write_text("x", encoding="utf-8")
    ausgeschlossen = workspace / "node_modules"
    ausgeschlossen.mkdir()
    (ausgeschlossen / "sollte_nicht_gefunden_werden.txt").write_text("x", encoding="utf-8")
    return workspace


def test_search_files_findet_exakten_namen(tools, baum):
    res = erfolg(tools("search.files", query="readme.md"))
    assert res.evidence["anzahl"] >= 1
    assert "readme.md" in res.payload


def test_search_files_unscharfe_suche(tools, baum):
    res = erfolg(tools("search.files", query="bericht2026"))
    assert "bericht_2026.txt" in res.payload


def test_search_files_ignoriert_node_modules(tools, baum):
    res = erfolg(tools("search.files", query="sollte_nicht_gefunden_werden"))
    assert res.evidence["anzahl"] == 0


def test_search_files_kein_treffer(tools, baum):
    res = erfolg(tools("search.files", query="xyzxyzxyz_gibtsnicht"))
    assert res.evidence["anzahl"] == 0


def test_search_files_leerer_suchbegriff_wird_abgelehnt(tools, baum):
    fehler(tools("search.files", query=""))


def test_search_files_begrenzt_ergebnisse(tools, baum):
    # "e" steckt in allen vier angelegten Dateinamen -- mehr Treffer als das
    # Limit, damit der Test das Begrenzen wirklich prüft und nicht zufällig
    # gleich viele Treffer wie Limit hat.
    res = erfolg(tools("search.files", query="e", limit=2))
    assert res.evidence["anzahl"] == 4
    datenzeilen = res.payload.splitlines()[2:]  # ohne Kopfzeile + Trennstrich
    assert len(datenzeilen) == 2


# ═══════════════════════════════════════════════════════════════ search.apps
def test_linux_apps_liest_echte_desktop_dateien(tmp_path):
    from jarvis.tools.packs.search import linux_apps

    ordner = tmp_path / "applications"
    ordner.mkdir()
    (ordner / "firefox.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=firefox %u\nType=Application\n", encoding="utf-8")
    (ordner / "editor.desktop").write_text(
        "[Desktop Entry]\nName=Mein Editor\nExec=/usr/bin/editor\nType=Application\n",
        encoding="utf-8")

    ergebnis = linux_apps(100, ordner=[ordner])
    assert ["Firefox", "firefox"] in ergebnis
    assert ["Mein Editor", "/usr/bin/editor"] in ergebnis


def test_linux_apps_ohne_name_wird_uebersprungen(tmp_path):
    from jarvis.tools.packs.search import linux_apps

    ordner = tmp_path / "applications"
    ordner.mkdir()
    (ordner / "kaputt.desktop").write_text("[Desktop Entry]\nExec=irgendwas\n", encoding="utf-8")

    assert linux_apps(100, ordner=[ordner]) == []


def test_macos_apps_liest_echte_app_buendel(tmp_path):
    from jarvis.tools.packs.search import macos_apps

    ordner = tmp_path / "Applications"
    ordner.mkdir()
    (ordner / "Beispiel.app").mkdir()

    ergebnis = macos_apps(100, ordner=[ordner])
    assert ergebnis[0][0] == "Beispiel"


def test_windows_apps_liest_echte_verknuepfungen(tmp_path):
    from jarvis.tools.packs.search import windows_apps

    ordner = tmp_path / "Programs"
    ordner.mkdir()
    (ordner / "Rechner.lnk").write_bytes(b"\x00")

    ergebnis = windows_apps(100, ordner=[ordner])
    assert ergebnis[0][0] == "Rechner"


def test_search_apps_lehnt_unbekannte_plattform_nicht_ab_bei_bekannter(tools):
    # Auf der tatsaechlichen Testplattform (Linux) muss der Aufruf zumindest
    # nicht mit "Unbekannte Plattform" scheitern -- ob etwas gefunden wird,
    # haengt vom System ab, auf dem der Test laeuft.
    res = tools("search.apps", limit=5)
    assert res.ok
