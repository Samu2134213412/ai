"""Das Entwicklungs-Pack: Python echt, Node echt (wo installiert), der Rest
ohne externe Abhängigkeit.

``ruff`` ist in dieser Umgebung nicht installiert -- getestet wird deshalb die
ehrliche, hilfreiche Fehlermeldung dafür (Punkt 55), nicht ein erfundener
Erfolg. Ein Test, der ``pip install ruff`` bräuchte, wäre vom Internet
abhängig und damit keiner (siehe test_tools_net.py).
"""

from __future__ import annotations

import json
import shutil
import sys

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


_hat_node = shutil.which("node") is not None and shutil.which("npm") is not None
braucht_node = pytest.mark.skipif(not _hat_node, reason="Node.js/npm nicht installiert")


# ═══════════════════════════════════════════════════════════════ python.*
def test_python_version_meldet_den_eigenen_interpreter(tools):
    res = erfolg(tools("python.version"))
    assert "Python" in res.payload
    assert res.evidence["interpreter"] == sys.executable


def test_syntax_check_gueltiger_und_ungueltiger_code(tools, workspace):
    gut = workspace / "gut.py"
    gut.write_text("def f():\n    return 1\n", encoding="utf-8")
    erfolg(tools("python.syntax_check", path="gut.py"))

    schlecht = workspace / "schlecht.py"
    schlecht.write_text("def f(:\n    return\n", encoding="utf-8")
    res = fehler(tools("python.syntax_check", path="schlecht.py"))
    assert "Zeile" in res.summary


def test_syntax_check_ohne_pruefregel_meldet_das_ehrlich(tools, workspace):
    (workspace / "bild.png").write_bytes(b"\x89PNG")
    fehler(tools("python.syntax_check", path="bild.png"))


def test_packages_list_enthaelt_pytest(tools):
    res = erfolg(tools("python.packages.list"))
    assert "pytest" in res.payload.lower()


def test_venv_create_und_install_darin(tools, workspace):
    erfolg(tools("python.venv.create", path="testvenv"))
    venv_python = str(workspace / "testvenv" /
                      ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
    liste = erfolg(tools("python.packages.list", python=venv_python))
    # Eine frische venv hat höchstens pip/setuptools -- auf keinen Fall pytest.
    assert "pytest" not in liste.payload.lower()


def test_venv_create_verweigert_nicht_leeren_zielordner(tools, workspace):
    (workspace / "belegt").mkdir()
    (workspace / "belegt" / "datei.txt").write_text("x", encoding="utf-8")
    fehler(tools("python.venv.create", path="belegt"))


def test_package_install_ohne_interpreter_wird_abgelehnt(tools):
    """Ohne ausdrücklichen Ziel-Interpreter würde Jarvis' eigene Umgebung
    verändert -- das verlangt das Werkzeug deshalb explizit."""
    res = fehler(tools("python.package.install", package="irgendwas", python=""))
    assert "python" in res.summary.lower()


def test_lint_ohne_ruff_gibt_hilfreiche_fehlermeldung(tools, workspace):
    (workspace / "code.py").write_text("import os\n", encoding="utf-8")
    res = fehler(tools("python.lint", path="code.py"))
    assert "ruff" in res.summary.lower()
    assert "python.package.install" in res.summary


def test_format_ohne_ruff_gibt_hilfreiche_fehlermeldung(tools, workspace):
    (workspace / "code.py").write_text("x=1\n", encoding="utf-8")
    res = fehler(tools("python.format", path="code.py"))
    assert "ruff" in res.summary.lower()
    assert "python.package.install" in res.summary


def test_requirements_freeze_schreibt_datei(tools, workspace):
    erfolg(tools("python.requirements.freeze", path="req.txt", python=sys.executable))
    inhalt = (workspace / "req.txt").read_text(encoding="utf-8")
    assert "pytest" in inhalt.lower()


def test_test_lauf_gegen_ein_eigenes_kleines_projekt(tools, workspace):
    projekt = workspace / "miniprojekt"
    projekt.mkdir()
    (projekt / "test_beispiel.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    res = tools("python.test", path="miniprojekt")
    assert res.ok, res.payload
    assert res.evidence["exit_code"] == 0


def test_test_lauf_meldet_fehlschlag_ehrlich(tools, workspace):
    projekt = workspace / "miniprojekt2"
    projekt.mkdir()
    (projekt / "test_beispiel.py").write_text(
        "def test_kaputt():\n    assert 1 == 2\n", encoding="utf-8")
    res = tools("python.test", path="miniprojekt2")
    assert not res.ok
    assert res.evidence["exit_code"] != 0


# ═══════════════════════════════════════════════════════════════ node.*/npm.*
@braucht_node
def test_node_und_npm_version(tools):
    n = erfolg(tools("node.version"))
    assert n.payload.startswith("v")
    m = erfolg(tools("npm.version"))
    assert m.payload


@braucht_node
def test_node_init_add_script_run(tools, workspace):
    erfolg(tools("node.init", path="nodeprojekt"))
    manifest = json.loads((workspace / "nodeprojekt" / "package.json").read_text())
    assert manifest["name"]

    daten = json.loads((workspace / "nodeprojekt" / "package.json").read_text())
    daten["scripts"] = {"gruss": "node -e \"console.log('hallo')\""}
    (workspace / "nodeprojekt" / "package.json").write_text(
        json.dumps(daten), encoding="utf-8")

    res = erfolg(tools("node.script.run", path="nodeprojekt", script="gruss"))
    assert "hallo" in res.payload


@braucht_node
def test_node_script_run_unbekanntes_skript_wird_abgelehnt(tools, workspace):
    erfolg(tools("node.init", path="nodeprojekt2"))
    res = fehler(tools("node.script.run", path="nodeprojekt2", script="gibtsnicht"))
    assert "gibtsnicht" in res.summary


@braucht_node
def test_node_init_verweigert_wenn_package_json_existiert(tools, workspace):
    erfolg(tools("node.init", path="nodeprojekt3"))
    fehler(tools("node.init", path="nodeprojekt3"))


# ═══════════════════════════════════════════════════════════════ dev.*
def test_project_detect_erkennt_python_und_git(tools, workspace):
    (workspace / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (workspace / ".git").mkdir()
    res = erfolg(tools("dev.project.detect", path="."))
    assert "Python" in res.payload
    assert "Git" in res.payload


def test_project_detect_leerer_ordner_meldet_das_ehrlich(tools, workspace):
    (workspace / "leer").mkdir()
    res = erfolg(tools("dev.project.detect", path="leer"))
    assert res.evidence["projekttypen"] == []


def test_stats_zaehlt_dateien_und_zeilen(tools, workspace):
    (workspace / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (workspace / "b.py").write_text("z = 3\n", encoding="utf-8")
    (workspace / "c.md").write_text("# Titel\n", encoding="utf-8")
    res = erfolg(tools("dev.stats", path="."))
    assert res.evidence["dateien"] >= 3
    assert ".py" in res.payload


def test_env_list_schwaerzt_geheimnisse(tools, monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_API_KEY", "sehr-geheim-123")
    monkeypatch.setenv("JARVIS_TEST_PLAIN", "sichtbar")
    res = erfolg(tools("dev.env.list", filter="JARVIS_TEST"))
    assert "sehr-geheim-123" not in res.payload
    assert "***" in res.payload
    assert "sichtbar" in res.payload


def test_changelog_entry_legt_datei_an_und_ergaenzt(tools, workspace):
    erfolg(tools("dev.changelog.entry", path="CHANGELOG.md",
                 entry="Erstes Feature", heading="1.0"))
    inhalt = (workspace / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "1.0" in inhalt and "Erstes Feature" in inhalt

    erfolg(tools("dev.changelog.entry", path="CHANGELOG.md",
                 entry="Zweites Feature", heading="1.0"))
    inhalt2 = (workspace / "CHANGELOG.md").read_text(encoding="utf-8")
    assert inhalt2.count("## 1.0") == 1
    assert "Zweites Feature" in inhalt2


# ═══════════════════════════════════════════════════════════════ Sicherheit
def test_pfad_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools):
    fehler(tools("dev.project.detect", path="/etc"))


def test_paketname_mit_fuehrendem_bindestrich_wird_abgelehnt(tools):
    res = fehler(tools("python.package.install", package="--index-url=evil",
                       python=sys.executable))
    assert "Paketname" in res.summary
