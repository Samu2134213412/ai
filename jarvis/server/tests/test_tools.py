"""Werkzeuge: die Grenzen, innerhalb derer sie wirken, und die Form des Belegs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jarvis.tools import knowledge, shell, system
from jarvis.tools.base import Registry, Tool, ToolError, ToolMissing, ToolResult
from jarvis.tools.files import Workspace, build as build_files


# ══════════════════════════════════════════════════════ Pfad-Containment
def test_pfad_ausserhalb_des_bereichs_wird_abgewiesen(workspace, tmp_path):
    ws = Workspace([workspace])
    with pytest.raises(ToolError, match="außerhalb"):
        ws.resolve(str(tmp_path / "woanders.txt"))


def test_punkt_punkt_wird_aufgeloest_nicht_nur_gefiltert(workspace):
    ws = Workspace([workspace])
    with pytest.raises(ToolError, match="außerhalb"):
        ws.resolve(str(workspace / ".." / "entwischt.txt"))


@pytest.mark.skipif(os.name == "nt", reason="Symlinks brauchen Rechte auf Windows")
def test_symlink_der_hinausfuehrt_wird_abgewiesen(workspace, tmp_path):
    aussen = tmp_path / "aussen"
    aussen.mkdir()
    (workspace / "tuer").symlink_to(aussen, target_is_directory=True)
    ws = Workspace([workspace])
    with pytest.raises(ToolError, match="außerhalb"):
        ws.resolve(str(workspace / "tuer" / "beute.txt"))


def test_relativer_pfad_landet_in_der_ersten_wurzel(workspace):
    ws = Workspace([workspace])
    assert Path(ws.resolve("notiz.txt")).parent == workspace


def test_ohne_freigegebene_wurzel_geht_gar_nichts():
    ws = Workspace([])
    with pytest.raises(ToolError, match="kein Arbeitsbereich"):
        ws.resolve("irgendwas.txt")


# ══════════════════════════════════════════════════════════ Belegform
def test_write_file_liest_die_groesse_von_der_platte(workspace):
    write = {t.name: t for t in build_files(Workspace([workspace]))}["write_file"]
    result = write.run(path=str(workspace / "a.txt"), content="Hällo")
    assert result.ok is True
    assert result.evidence["bytes"] == (workspace / "a.txt").stat().st_size
    assert result.evidence["bytes"] == 6          # ä ist zwei Bytes in UTF-8


def test_delete_file_prueft_nach_dem_loeschen_nach(workspace):
    tools = {t.name: t for t in build_files(Workspace([workspace]))}
    target = workspace / "weg.txt"
    target.write_text("x", encoding="utf-8")
    result = tools["delete_file"].run(path=str(target))
    assert result.ok is True
    assert not target.exists()


def test_fehlende_datei_ist_ein_fehler_kein_erfolg(workspace):
    tools = {t.name: t for t in build_files(Workspace([workspace]))}
    with pytest.raises(ToolError, match="existiert nicht"):
        tools["read_file"].run(path=str(workspace / "nix.txt"))


# ══════════════════════════════════════════════════════════ Registry
def test_registry_verwandelt_absturz_in_ehrliches_ergebnis():
    registry = Registry()

    def explodiert() -> ToolResult:
        raise RuntimeError("kaputt")

    registry.add(Tool("bumm", "", {"type": "object", "properties": {}}, explodiert))
    result = registry.call("bumm", {})
    assert result.ok is False
    assert "kaputt" in result.summary


def test_registry_lehnt_falschen_rueckgabetyp_ab():
    registry = Registry()
    registry.add(Tool("luegner", "", {"type": "object", "properties": {}},
                      lambda: "fertig!"))
    with pytest.raises(TypeError, match="ToolResult"):
        registry.call("luegner", {})


def test_unbekanntes_werkzeug_wirft_toolmissing():
    with pytest.raises(ToolMissing):
        Registry().call("gibtsnicht", {})


def test_falsche_argumente_werden_zum_fehlschlag_nicht_zum_absturz(workspace):
    registry = Registry()
    for tool in build_files(Workspace([workspace])):
        registry.add(tool)
    result = registry.call("write_file", {"voellig": "falsch"})
    assert result.ok is False
    assert "Argumente" in result.summary


# ══════════════════════════════════════════════════════════ Shell-Politik
def test_shell_ist_standardmaessig_aus():
    with pytest.raises(ToolError, match="abgeschaltet"):
        shell.ShellPolicy().check(["python", "-V"])


def test_leere_allowlist_gibt_nichts_frei():
    with pytest.raises(ToolError, match="Allowlist ist leer"):
        shell.ShellPolicy(enabled=True).check(["python"])


def test_programm_ausserhalb_der_allowlist_wird_abgewiesen():
    policy = shell.ShellPolicy(enabled=True, allowlist=["python"])
    with pytest.raises(ToolError, match="nicht auf der Allowlist"):
        policy.check(["rm", "-rf", "/"])


def test_allowlist_greift_auch_bei_vollem_pfad_und_exe():
    policy = shell.ShellPolicy(enabled=True, allowlist=["python"])
    assert policy.check([r"C:\Python311\python.exe", "-V"]) == "python"


def test_verkettung_laeuft_nicht_weil_es_keine_shell_gibt(tmp_path):
    """'echo a && rm -rf x' startet 'echo' mit Argumenten, keine Kette."""
    policy = shell.ShellPolicy(enabled=True, allowlist=["echo"], cwd=tmp_path)
    run = {t.name: t for t in shell.build(policy)}["run_command"]
    result = run.run(command="echo hallo && echo getarnt")
    assert result.ok is True
    # '&&' erscheint als Text in der Ausgabe, wurde also nicht ausgeführt.
    assert "&&" in result.payload


def test_exit_code_ungleich_null_ist_ein_fehlschlag(tmp_path):
    policy = shell.ShellPolicy(enabled=True, allowlist=["python3"], cwd=tmp_path)
    run = {t.name: t for t in shell.build(policy)}["run_command"]
    result = run.run(command="python3 -c \"import sys; sys.exit(3)\"")
    assert result.ok is False
    assert result.evidence["exit_code"] == 3


# ══════════════════════════════════════════════════════════ Systemwerte
def test_systeminfo_meldet_echte_werte():
    result = system.get_system_info()
    assert result.ok is True
    assert result.evidence["kerne"] == (os.cpu_count() or 0)


def test_telemetrie_erfindet_nichts_wenn_psutil_fehlt(monkeypatch):
    monkeypatch.setattr(system, "psutil", None)
    assert system.telemetry() == {}


def test_cpu_ohne_psutil_ist_ein_fehler_keine_schaetzung(monkeypatch):
    monkeypatch.setattr(system, "psutil", None)
    with pytest.raises(ToolError, match="psutil"):
        system.get_cpu_info()


# ══════════════════════════════════════════════════════════ Gedächtnis
def test_memory_add_liest_zurueck_was_es_geschrieben_hat(store):
    add = {t.name: t for t in knowledge.build(store)}["memory_add"]
    result = add.run(label="Kaffee", text="schwarz, ohne Zucker", kind="vorliebe")
    assert result.ok is True
    assert store.get(result.evidence["id"]).label == "Kaffee"


def test_memory_forget_prueft_nach(store):
    tools = {t.name: t for t in knowledge.build(store)}
    node = store.add(label="Vergänglich")
    result = tools["memory_forget"].run(id=node.id)
    assert result.ok is True
    assert store.get(node.id) is None
