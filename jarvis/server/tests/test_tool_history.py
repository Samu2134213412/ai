"""ToolHistory (Punkt 36): Aufrufe, Kennzahlen, Favoriten, Abschalten --
sowie das Schwärzen geheim wirkender Argumente (Punkt 51)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.tools.history import REDACTED, ToolHistory, redact


def test_redact_ersetzt_geheim_wirkende_schluessel():
    raw = {"path": "x.txt", "api_key": "sk-echt-geheim", "Password": "hunter2"}
    out = redact(raw)
    assert out["path"] == "x.txt"
    assert out["api_key"] == REDACTED
    assert out["Password"] == REDACTED


def test_redact_kuerzt_lange_werte():
    lang = "x" * 500
    out = redact({"content": lang})
    assert len(out["content"]) < 500
    assert out["content"].endswith("…")


def test_redact_laesst_zahlen_und_bool_unveraendert():
    out = redact({"n": 5, "flag": True, "nix": None})
    assert out == {"n": 5, "flag": True, "nix": None}


@pytest.fixture
def history() -> ToolHistory:
    h = ToolHistory(":memory:")
    yield h
    h.close()


def test_record_und_list(history):
    history.record(tool="write_file", arguments={"path": "a.txt"}, ok=True,
                   summary="geschrieben", duration_ms=12, level="WRITE",
                   request="leg was an")
    eintraege = history.list()
    assert len(eintraege) == 1
    assert eintraege[0].tool == "write_file"
    assert eintraege[0].ok is True
    assert eintraege[0].arguments == {"path": "a.txt"}


def test_record_schwaerzt_geheimnisse_beim_schreiben(history):
    history.record(tool="net.request", arguments={"url": "x", "api_key": "sk-geheim"},
                   ok=True, summary="ok")
    assert history.list()[0].arguments["api_key"] == REDACTED


def test_list_neueste_zuerst(history):
    history.record(tool="a", arguments={}, ok=True, summary="1")
    history.record(tool="b", arguments={}, ok=True, summary="2")
    namen = [e.tool for e in history.list()]
    assert namen == ["b", "a"]


def test_list_filtert_nach_werkzeug_und_erfolg(history):
    history.record(tool="a", arguments={}, ok=True, summary="ok")
    history.record(tool="a", arguments={}, ok=False, summary="fehler")
    history.record(tool="b", arguments={}, ok=True, summary="ok")
    assert len(history.list(tool="a")) == 2
    assert len(history.list(ok=True)) == 2
    assert len(history.list(tool="a", ok=False)) == 1


def test_keep_begrenzt_die_ablage(history):
    history.keep = 3
    for i in range(10):
        history.record(tool=f"t{i}", arguments={}, ok=True, summary="ok")
    assert len(history.list(limit=100)) == 3
    # Die neuesten drei bleiben.
    assert {e.tool for e in history.list(limit=100)} == {"t7", "t8", "t9"}


def test_stats_zaehlt_aufrufe_und_erfolgsquote(history):
    history.record(tool="a", arguments={}, ok=True, summary="ok", duration_ms=10)
    history.record(tool="a", arguments={}, ok=True, summary="ok", duration_ms=20)
    history.record(tool="a", arguments={}, ok=False, summary="fehler", duration_ms=30)
    stats = history.stats()
    a = next(s for s in stats if s["werkzeug"] == "a")
    assert a["aufrufe"] == 3
    assert a["erfolge"] == 2
    assert a["erfolgsquote"] == pytest.approx(2 / 3, rel=1e-3)
    assert a["dauer_ms"] == 20


def test_recent_tools_nach_letzter_benutzung(history):
    history.record(tool="a", arguments={}, ok=True, summary="ok")
    history.record(tool="b", arguments={}, ok=True, summary="ok")
    history.record(tool="a", arguments={}, ok=True, summary="ok")
    assert history.recent_tools()[0] == "a"
    assert set(history.recent_tools()) == {"a", "b"}


def test_favoriten_setzen_doppelt_ist_kein_fehler(history):
    assert history.favorite("write_file") is True
    assert history.favorite("write_file") is True  # ON CONFLICT DO NOTHING
    assert history.favorites() == ["write_file"]


def test_favorit_entfernen(history):
    history.favorite("write_file")
    assert history.unfavorite("write_file") is True
    assert history.favorites() == []
    assert history.unfavorite("write_file") is False


def test_abschalten_und_wieder_anschalten(history):
    assert history.disabled() == {}
    history.disable("write_file", reason="testweise")
    assert history.disabled() == {"write_file": "testweise"}
    assert history.enable("write_file") is True
    assert history.disabled() == {}
    assert history.enable("write_file") is False


def test_ueberlebt_einen_neustart(tmp_path: Path):
    pfad = tmp_path / "verlauf.sqlite3"
    h1 = ToolHistory(pfad)
    h1.record(tool="a", arguments={}, ok=True, summary="ok")
    h1.favorite("a")
    h1.close()

    h2 = ToolHistory(pfad)
    assert len(h2.list()) == 1
    assert h2.favorites() == ["a"]
    h2.close()
