"""Die Tool-Registry als Katalog: Metadaten, Aliase, Kategorien, Probelauf.

Kein einzelner Test hier ruft jedes Werkzeug mit echten Argumenten auf --
das übernehmen die einzelnen Pack-Tests (``test_tools_*.py``), jeweils mit
einem zum Werkzeug passenden Aufbau (ein echtes Git-Repository für
``git.py``, ein echter Dateibaum für ``fs.py``, …). Ein einziger
"ruf-alles-mit-Beispielargumenten-auf"-Test wäre hier keine echte Prüfung:
nur 1 von 398 Werkzeugen trägt überhaupt ``examples`` (Aufgabenstellung
Punkt 40 verbietet genau das -- eine Prüfung, die nur so aussieht, als
prüfe sie etwas). ``conftest.py`` zählt stattdessen mit, welche Werkzeuge
über eine gesamte Testsitzung hinweg NIE über ``Registry.call`` liefen, und
meldet das am Ende als Bericht (kein Fehlschlag -- manche Werkzeuge sind
absichtlich nur über einen laufenden Dienst oder destruktiv prüfbar).

Was hier tatsächlich geprüft wird: dass jedes Werkzeug in sich konsistent
ist -- Schema passt zur Implementierung, Berechtigungsstufe zu Undo/Probelauf,
und jede angegebene Abhängigkeit existiert wirklich als Probe.
"""

from __future__ import annotations

import inspect

import pytest

from jarvis.permissions import PermissionLevel
from jarvis.tools import build_registry
from jarvis.tools.base import Registry, Tool, ToolResult
from jarvis.tools.catalog import Availability, availability, dependency_report


def _dummy(**_kwargs) -> ToolResult:
    return ToolResult(tool="x", ok=True, summary="ok")


def make_tool(name: str, **kwargs) -> Tool:
    return Tool(name, "Beschreibung", {"type": "object", "properties": {}},
                _dummy, **kwargs)


# ═════════════════════════════════════════════════════ Metadaten am Tool
def test_kategorie_kommt_aus_dem_gepunkteten_namen():
    tool = make_tool("system.gpu.temperature")
    assert tool.category == "system"
    assert tool.subcategory == "gpu"


def test_alter_flacher_name_bekommt_kategorie_core():
    assert make_tool("write_file").category == "core"
    assert make_tool("write_file").subcategory == ""


def test_ausdrueckliche_kategorie_schlaegt_die_ableitung():
    tool = make_tool("system.gpu.temperature", category="hardware")
    assert tool.category == "hardware"


def test_risiko_ist_dasselbe_wie_die_stufe_keine_zweite_skala():
    assert make_tool("a.b", level=PermissionLevel.SAFE).risk == "LOW"
    assert make_tool("a.b", level=PermissionLevel.SYSTEM).risk == "MEDIUM"
    assert make_tool("a.b", level=PermissionLevel.CRITICAL).risk == "HIGH"


def test_katalogeintrag_enthaelt_alles_was_die_oberflaeche_braucht():
    tool = make_tool("files.copy", tags=("datei",), aliases=("copy_file",),
                     phrases=("kopiere die datei",), undoable=True, dry_run=True,
                     requires=("git",), platforms=("linux",))
    eintrag = tool.as_dict()
    assert eintrag["id"] == "files.copy"
    assert eintrag["kategorie"] == "files"
    assert eintrag["tags"] == ["datei"]
    assert eintrag["aliase"] == ["copy_file"]
    assert eintrag["rueckgaengig"] is True
    assert eintrag["probelauf"] is True
    assert eintrag["benoetigt"] == ["git"]
    assert eintrag["plattformen"] == ["linux"]


# ═══════════════════════════════════════════════════════════════ Aliase
def test_werkzeug_ist_unter_seinem_alias_erreichbar():
    registry = Registry()
    registry.add(make_tool("files.write", aliases=("write_file",)))
    assert "write_file" in registry
    assert registry.resolve("write_file") == "files.write"
    assert registry.get("write_file").name == "files.write"


def test_alias_der_mit_einem_echten_namen_kollidiert_fliegt_auf():
    registry = Registry()
    registry.add(make_tool("write_file"))
    with pytest.raises(ValueError, match="Alias kollidiert"):
        registry.add(make_tool("files.write", aliases=("write_file",)))


def test_derselbe_alias_zweimal_fliegt_auf():
    registry = Registry()
    registry.add(make_tool("a.eins", aliases=("kurz",)))
    with pytest.raises(ValueError, match="Alias doppelt"):
        registry.add(make_tool("a.zwei", aliases=("kurz",)))


def test_doppelter_werkzeugname_fliegt_weiterhin_auf():
    registry = Registry()
    registry.add(make_tool("a.eins"))
    with pytest.raises(ValueError, match="doppelt registriert"):
        registry.add(make_tool("a.eins"))


# ══════════════════════════════════════════════════════ Kategorien/Zähler
def test_kategorien_werden_gezaehlt_nicht_hartkodiert(config, store):
    registry = build_registry(config, store)
    kategorien = registry.categories()
    assert sum(kategorien.values()) == len(registry)
    assert kategorien["files"] > 20, "Das Datei-Pack ist nicht geladen"


def test_by_category_filtert(config, store):
    registry = build_registry(config, store)
    archive = registry.by_category("archive")
    assert archive and all(t.category == "archive" for t in archive)


def test_schemas_lassen_sich_eingrenzen(config, store):
    """Der Kern des Ganzen: bei hunderten Werkzeugen darf nicht mehr der
    komplette Katalog in jede Modellanfrage."""
    registry = build_registry(config, store)
    alle = registry.schemas()
    wenige = registry.schemas(only=["read_file", "files.hash", "gibtsnicht"])
    assert len(alle) == len(registry)
    assert [s["function"]["name"] for s in wenige] == ["read_file", "files.hash"]


def test_eingrenzung_versteht_aliase(config, store):
    registry = build_registry(config, store)
    registry.add(make_tool("test.alias.ziel", aliases=("kurzform",)))
    schemas = registry.schemas(only=["kurzform"])
    assert [s["function"]["name"] for s in schemas] == ["test.alias.ziel"]


# ═══════════════════════════════════════════════════════════ Selbstdiagnose
def test_unpassende_plattform_wird_gemeldet_statt_versprochen():
    tool = make_tool("system.x", platforms=("plan9",))
    state, grund = availability(tool)
    assert state is Availability.UNSUPPORTED_PLATFORM
    assert "plan9" in grund


def test_fehlende_abhaengigkeit_wird_gemeldet_mit_installationshinweis():
    tool = make_tool("media.x", requires=("gibtsnicht_als_probe",))
    state, _ = availability(tool)
    assert state is Availability.MISSING_DEPENDENCY


def test_kritische_werkzeuge_melden_bestaetigungspflicht():
    state, _ = availability(make_tool("x.y", level=PermissionLevel.CRITICAL))
    assert state is Availability.PERMISSION_REQUIRED


def test_dependency_report_nennt_installationswege():
    report = dependency_report()
    assert report and all({"schluessel", "vorhanden", "installation"} <= set(r)
                          for r in report)
    ffmpeg = next(r for r in report if r["schluessel"] == "ffmpeg")
    assert ffmpeg["installation"]


# ══════════════════════════════════════════════════════════════ Probelauf
def test_probelauf_bei_einem_werkzeug_ohne_probelauf_aendert_nichts(config, store,
                                                                    workspace):
    """Punkt 30: Wer „zeig mir erst, was passieren würde" sagt, will nicht,
    dass es stattdessen passiert."""
    registry = build_registry(config, store)
    ziel = workspace / "darf-nicht-entstehen.txt"
    result = registry.call("write_file", {"path": str(ziel), "content": "x",
                                          "dry_run": True})
    assert result.ok is False
    assert "Probelauf" in result.summary
    assert not ziel.exists()


def test_probelauf_bei_einem_werkzeug_mit_probelauf_laeuft_durch(config, store,
                                                                 workspace):
    registry = build_registry(config, store)
    (workspace / "a.txt").write_text("hallo welt", encoding="utf-8")
    result = registry.call("files.replace_text",
                           {"path": str(workspace / "a.txt"), "search": "hallo",
                            "replace": "tschüss", "dry_run": True})
    assert result.ok is True
    assert result.evidence["probelauf"] is True
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "hallo welt"


# ═══════════════════════════════════ Der Test gegen Attrappen (Punkt 40/60)
def test_jedes_werkzeug_hat_vollstaendige_metadaten(config, store):
    registry = build_registry(config, store)
    maengel = []
    for tool in registry:
        if not tool.description.strip():
            maengel.append(f"{tool.name}: keine Beschreibung")
        if tool.parameters.get("type") != "object":
            maengel.append(f"{tool.name}: kein Objekt-Schema")
        if not isinstance(tool.parameters.get("properties"), dict):
            maengel.append(f"{tool.name}: keine properties")
        for pflicht in tool.parameters.get("required", []):
            if pflicht not in tool.parameters["properties"]:
                maengel.append(f"{tool.name}: Pflichtfeld '{pflicht}' fehlt im Schema")
    assert not maengel, "\n".join(maengel)


def test_schema_und_implementierung_passen_zusammen(config, store):
    """Ein Schema, das einen Parameter verspricht, den die Funktion nicht
    annimmt, führt zu einem TypeError beim ersten echten Aufruf -- also hier
    statt beim Nutzer."""
    registry = build_registry(config, store)
    maengel = []
    for tool in registry:
        signature = inspect.signature(tool.run)
        akzeptiert = set(signature.parameters)
        beliebig = any(p.kind is inspect.Parameter.VAR_KEYWORD
                       for p in signature.parameters.values())
        if beliebig:
            continue
        for name in tool.parameters.get("properties", {}):
            if name not in akzeptiert:
                maengel.append(f"{tool.name}: Schema kennt '{name}', die Funktion nicht")
        for name, parameter in signature.parameters.items():
            if parameter.default is inspect.Parameter.empty \
                    and name not in tool.parameters.get("required", []):
                maengel.append(f"{tool.name}: '{name}' ist Pflicht, "
                               "steht aber nicht in required")
    assert not maengel, "\n".join(maengel)


def test_kein_werkzeug_verspricht_undo_ohne_veraendernd_zu_sein(config, store):
    registry = build_registry(config, store)
    falsch = [t.name for t in registry
              if t.undoable and t.level < PermissionLevel.WRITE]
    assert not falsch, f"Lesende Werkzeuge brauchen kein Undo: {falsch}"


def test_dry_run_flag_und_parameter_stimmen_ueberein(config, store):
    """Ein Werkzeug, das ``dry_run=True`` meldet, muss den Parameter auch
    annehmen -- sonst verspricht der Katalog etwas, das beim Aufruf scheitert."""
    registry = build_registry(config, store)
    falsch = []
    for tool in registry:
        akzeptiert = "dry_run" in inspect.signature(tool.run).parameters
        if tool.dry_run and not akzeptiert:
            falsch.append(f"{tool.name}: meldet Probelauf, nimmt ihn aber nicht an")
        if akzeptiert and not tool.dry_run:
            falsch.append(f"{tool.name}: nimmt dry_run an, meldet es aber nicht")
    assert not falsch, "\n".join(falsch)


def test_jede_angegebene_abhaengigkeit_existiert_als_probe(config, store):
    """``requires=("ffmepg",)`` (Tippfehler) würde sonst nie MISSING_DEPENDENCY
    melden, sondern erst beim echten Aufruf scheitern -- availability() kennt
    nur bekannte PROBES-Schlüssel, ein unbekannter Schlüssel fällt durch."""
    from jarvis.tools.catalog import PROBES
    registry = build_registry(config, store)
    unbekannt = [f"{t.name}: {schluessel!r}" for t in registry
                for schluessel in t.requires if schluessel not in PROBES]
    assert not unbekannt, "Unbekannte Probe-Schlüssel:\n" + "\n".join(unbekannt)
