"""Undo/Rollback: Snapshot vorher, Wiederherstellung auf Zuruf."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.memory import MemoryStore
from jarvis.tools.base import ToolResult
from jarvis.tools.files import Workspace
from jarvis.undo import UndoContext, UndoError, UndoStore


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "arbeitsbereich"
    root.mkdir()
    return root


@pytest.fixture
def ctx(workspace: Path) -> UndoContext:
    store = MemoryStore(":memory:")
    return UndoContext(workspace=Workspace([workspace]), store=store)


@pytest.fixture
def store(ctx: UndoContext) -> MemoryStore:
    return ctx.store


def ok(tool: str, evidence: dict | None = None) -> ToolResult:
    return ToolResult(tool=tool, ok=True, summary="ok", evidence=evidence or {})


def failed(tool: str) -> ToolResult:
    return ToolResult(tool=tool, ok=False, summary="fehlgeschlagen")


# ═══════════════════════════════════════════════════════════ write_file
def test_write_file_neu_angelegt_wird_beim_undo_geloescht(workspace, ctx):
    store_ = UndoStore(":memory:", context=ctx)
    target = workspace / "neu.txt"
    args = {"path": str(target)}

    pre = store_.begin("write_file", args)
    assert pre == {"path": str(target), "existed": False}
    target.write_text("hallo", encoding="utf-8")  # das Werkzeug hätte das getan
    store_.finish("write_file", "Datei geschrieben: neu.txt", pre, ok("write_file"))

    summary = store_.undo()
    assert "entfernt" in summary
    assert not target.exists()


def test_write_file_ueberschrieben_wird_beim_undo_wiederhergestellt(workspace, ctx):
    target = workspace / "bestehend.txt"
    target.write_text("alt", encoding="utf-8")
    store_ = UndoStore(":memory:", context=ctx)
    args = {"path": str(target)}

    pre = store_.begin("write_file", args)
    assert pre["existed"] is True
    target.write_text("neu", encoding="utf-8")
    store_.finish("write_file", "überschrieben", pre, ok("write_file"))

    store_.undo()
    assert target.read_text(encoding="utf-8") == "alt"


# ═══════════════════════════════════════════════════════════ delete_file
def test_geloeschte_datei_wird_wiederhergestellt(workspace, ctx):
    target = workspace / "weg.txt"
    target.write_text("wichtig", encoding="utf-8")
    store_ = UndoStore(":memory:", context=ctx)
    args = {"path": str(target)}

    pre = store_.begin("delete_file", args)
    target.unlink()
    store_.finish("delete_file", "gelöscht", pre, ok("delete_file"))

    store_.undo()
    assert target.read_text(encoding="utf-8") == "wichtig"


def test_wiederherstellung_verweigert_wenn_inzwischen_was_neues_liegt(workspace, ctx):
    target = workspace / "weg.txt"
    target.write_text("original", encoding="utf-8")
    store_ = UndoStore(":memory:", context=ctx)
    pre = store_.begin("delete_file", {"path": str(target)})
    target.unlink()
    store_.finish("delete_file", "gelöscht", pre, ok("delete_file"))

    target.write_text("etwas ganz anderes", encoding="utf-8")
    with pytest.raises(UndoError, match="neue Datei"):
        store_.undo()
    assert target.read_text(encoding="utf-8") == "etwas ganz anderes"  # unangetastet


# ═══════════════════════════════════════════════════════════ move_file
def test_verschobene_datei_wird_zurueckverschoben(workspace, ctx):
    source = workspace / "quelle.txt"
    source.write_text("inhalt", encoding="utf-8")
    dest = workspace / "ziel.txt"
    store_ = UndoStore(":memory:", context=ctx)

    pre = store_.begin("move_file", {"source": str(source), "destination": str(dest)})
    source.rename(dest)
    store_.finish("move_file", "verschoben", pre, ok("move_file", {"nach": str(dest)}))

    store_.undo()
    assert source.read_text(encoding="utf-8") == "inhalt"
    assert not dest.exists()


# ═══════════════════════════════════════════════════════════ memory_add
def test_neu_angelegte_erinnerung_wird_beim_undo_entfernt(store, ctx):
    store_ = UndoStore(":memory:", context=ctx)
    pre = store_.begin("memory_add", {"label": "Test"})
    node = store.add(label="Test", text="etwas", kind="fakt")
    store_.finish("memory_add", "gemerkt", pre, ok("memory_add", {"id": node.id}))

    store_.undo()
    assert store.get(node.id) is None


# ═══════════════════════════════════════════════════════ memory_forget
def test_vergessene_erinnerung_wird_wiederhergestellt(store, ctx):
    node = store.add(label="Kaffee", text="schwarz", kind="vorliebe")
    store_ = UndoStore(":memory:", context=ctx)

    pre = store_.begin("memory_forget", {"id": node.id})
    store.delete(node.id)
    store_.finish("memory_forget", "vergessen", pre, ok("memory_forget"))

    store_.undo()
    wiederhergestellt = store.get(node.id)
    assert wiederhergestellt is not None
    assert wiederhergestellt.label == "Kaffee"
    assert wiederhergestellt.kind == "vorliebe"


def test_vergessene_erinnerung_behaelt_wichtigkeit_und_quelle_beim_wiederherstellen(store, ctx):
    # Ohne das würde Rückgängigmachen die Wichtigkeit/Quelle/Sicherheit
    # stillschweigend auf die Vorgabe zurücksetzen statt sie wirklich
    # wiederherzustellen.
    node = store.add(label="Wichtig", kind="regel", text="nie vergessen",
                     importance=0.9, source="modell", confidence=0.4)
    store_ = UndoStore(":memory:", context=ctx)

    pre = store_.begin("memory_forget", {"id": node.id})
    store.delete(node.id)
    store_.finish("memory_forget", "vergessen", pre, ok("memory_forget"))

    store_.undo()
    wiederhergestellt = store.get(node.id)
    assert wiederhergestellt.importance == 0.9
    assert wiederhergestellt.source == "modell"
    assert wiederhergestellt.confidence == 0.4


# ═══════════════════════════════════════════════════════════ Rahmen
def test_unbekanntes_werkzeug_liefert_keinen_snapshot(ctx):
    store_ = UndoStore(":memory:", context=ctx)
    assert store_.begin("get_cpu_info", {}) is None


def test_ohne_kontext_gibt_es_kein_undo(workspace):
    store_ = UndoStore(":memory:", context=UndoContext())  # kein workspace, kein store
    assert store_.begin("write_file", {"path": str(workspace / "x.txt")}) is None


def test_fehlgeschlagenes_werkzeug_erzeugt_keinen_datensatz(workspace, ctx):
    store_ = UndoStore(":memory:", context=ctx)
    pre = store_.begin("write_file", {"path": str(workspace / "x.txt")})
    record = store_.finish("write_file", "x", pre, failed("write_file"))
    assert record is None
    assert store_.last_undoable() is None


def test_ohne_aufzeichnung_wirft_undo():
    store_ = UndoStore(":memory:")
    with pytest.raises(UndoError, match="nichts"):
        store_.undo()


def test_unbekannte_id_wirft_undo():
    store_ = UndoStore(":memory:")
    with pytest.raises(UndoError, match="Unbekannter"):
        store_.undo("nie-gesehen")


def test_zweimal_rueckgaengig_machen_wirft(workspace, ctx):
    store_ = UndoStore(":memory:", context=ctx)
    target = workspace / "a.txt"
    pre = store_.begin("write_file", {"path": str(target)})
    target.write_text("x", encoding="utf-8")
    record = store_.finish("write_file", "x", pre, ok("write_file"))

    store_.undo(record.id)
    with pytest.raises(UndoError, match="Bereits"):
        store_.undo(record.id)


def test_last_undoable_rutscht_nach_nach_dem_rueckgaengig_machen(workspace, ctx):
    store_ = UndoStore(":memory:", context=ctx)
    for name in ("a.txt", "b.txt"):
        target = workspace / name
        pre = store_.begin("write_file", {"path": str(target)})
        target.write_text("x", encoding="utf-8")
        store_.finish("write_file", name, pre, ok("write_file"))

    assert store_.last_undoable().description == "b.txt"
    store_.undo()
    assert store_.last_undoable().description == "a.txt"


def test_persistiert_ueber_einen_neustart_hinweg(tmp_path, workspace, ctx):
    path = tmp_path / "undo.sqlite3"
    store_ = UndoStore(path, context=ctx)
    target = workspace / "a.txt"
    pre = store_.begin("write_file", {"path": str(target)})
    target.write_text("x", encoding="utf-8")
    store_.finish("write_file", "a.txt", pre, ok("write_file"))
    store_.close()

    wieder = UndoStore(path, context=ctx)
    assert wieder.last_undoable() is not None
    assert wieder.last_undoable().description == "a.txt"
    wieder.close()
