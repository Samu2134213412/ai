"""Verification Engine: eine unabhängige Nachprüfung über einen echten
zweiten Werkzeugaufruf -- nicht nur erneutes Vertrauen auf ToolResult.ok
des ursprünglichen Aufrufs (Punkt 5)."""

from __future__ import annotations

from jarvis.tools.base import ToolResult
from jarvis.verification import VerificationEngine


def make_run_tool(responses: dict[tuple[str, str], ToolResult]):
    """``responses`` ist nach (tool, wichtigstem Argument) geschlüsselt --
    reicht für diese Tests, ohne die volle Argumentliste zu vergleichen."""
    calls: list[tuple[str, dict]] = []

    async def run_tool(name: str, arguments: dict) -> ToolResult:
        calls.append((name, arguments))
        key_arg = arguments.get("path") or arguments.get("query") or ""
        result = responses.get((name, key_arg))
        if result is None:
            raise AssertionError(f"Kein gestubbtes Ergebnis für {name}({key_arg})")
        return result

    return run_tool, calls


async def test_kein_verifizierer_fuer_unbekanntes_werkzeug():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({})
    original = ToolResult(tool="get_system_info", ok=True, summary="ok")
    assert await engine.verify("get_system_info", {}, original, run_tool) is None


async def test_ein_fehlgeschlagenes_original_wird_nicht_verifiziert():
    engine = VerificationEngine()
    run_tool, calls = make_run_tool({})
    original = ToolResult(tool="write_file", ok=False, summary="Schreiben fehlgeschlagen")
    assert await engine.verify("write_file", {"path": "a.txt"}, original, run_tool) is None
    assert calls == []


# ═══════════════════════════════════════════════════════════ write_file
async def test_write_file_verifiziert_ueber_read_file():
    engine = VerificationEngine()
    run_tool, calls = make_run_tool({
        ("read_file", "a.txt"): ToolResult(tool="read_file", ok=True, summary="gelesen",
                                          payload="hallo"),
    })
    original = ToolResult(tool="write_file", ok=True, summary="geschrieben")
    check = await engine.verify(
        "write_file", {"path": "a.txt", "content": "hallo"}, original, run_tool)
    assert check.ok is True
    assert calls == [("read_file", {"path": "a.txt"})]


async def test_write_file_schlaegt_fehl_wenn_inhalt_nicht_uebereinstimmt():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "a.txt"): ToolResult(tool="read_file", ok=True, summary="gelesen",
                                          payload="etwas anderes"),
    })
    original = ToolResult(tool="write_file", ok=True, summary="geschrieben")
    check = await engine.verify(
        "write_file", {"path": "a.txt", "content": "hallo"}, original, run_tool)
    assert check.ok is False
    assert "stimmt nicht" in check.summary


async def test_write_file_schlaegt_fehl_wenn_datei_nicht_lesbar_ist():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "a.txt"): ToolResult(tool="read_file", ok=False, summary="existiert nicht"),
    })
    original = ToolResult(tool="write_file", ok=True, summary="geschrieben")
    check = await engine.verify("write_file", {"path": "a.txt"}, original, run_tool)
    assert check.ok is False


# ═══════════════════════════════════════════════════════════ delete_file
async def test_delete_file_bestaetigt_wenn_datei_wirklich_weg_ist():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "a.txt"): ToolResult(tool="read_file", ok=False, summary="existiert nicht"),
    })
    original = ToolResult(tool="delete_file", ok=True, summary="gelöscht")
    check = await engine.verify("delete_file", {"path": "a.txt"}, original, run_tool)
    assert check.ok is True


async def test_delete_file_schlaegt_fehl_wenn_datei_noch_lesbar_ist():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "a.txt"): ToolResult(tool="read_file", ok=True, summary="gelesen",
                                          payload="immer noch da"),
    })
    original = ToolResult(tool="delete_file", ok=True, summary="gelöscht")
    check = await engine.verify("delete_file", {"path": "a.txt"}, original, run_tool)
    assert check.ok is False
    assert "weiterhin lesbar" in check.summary


# ═══════════════════════════════════════════════════════════ move_file
async def test_move_file_bestaetigt_ueber_ziel_lesen():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "neu.txt"): ToolResult(tool="read_file", ok=True, summary="gelesen",
                                            payload="inhalt"),
    })
    original = ToolResult(tool="move_file", ok=True, summary="verschoben")
    check = await engine.verify(
        "move_file", {"source": "alt.txt", "destination": "neu.txt"}, original, run_tool)
    assert check.ok is True


async def test_move_file_faellt_bei_nicht_lesbarem_ziel_auf_list_dir_zurueck():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("read_file", "ordner/bild.png"): ToolResult(tool="read_file", ok=False,
                                                      summary="Verzeichnis oder Binärdatei"),
        ("list_dir", "ordner"): ToolResult(tool="list_dir", ok=True, summary="gelistet",
                                          payload="   bild.png\n   andere.txt"),
    })
    original = ToolResult(tool="move_file", ok=True, summary="verschoben")
    check = await engine.verify(
        "move_file", {"source": "x/bild.png", "destination": "ordner/bild.png"},
        original, run_tool)
    assert check.ok is True


# ═══════════════════════════════════════════════════════════ memory_add
async def test_memory_add_bestaetigt_ueber_suche():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("memory_search", "Wichtiger Fakt"): ToolResult(
            tool="memory_search", ok=True, summary="1 Treffer",
            payload="abc123  Wichtiger Fakt: ..."),
    })
    original = ToolResult(tool="memory_add", ok=True, summary="gemerkt")
    check = await engine.verify(
        "memory_add", {"label": "Wichtiger Fakt"}, original, run_tool)
    assert check.ok is True


async def test_memory_add_schlaegt_fehl_wenn_ueber_suche_nicht_auffindbar():
    engine = VerificationEngine()
    run_tool, _ = make_run_tool({
        ("memory_search", "Wichtiger Fakt"): ToolResult(
            tool="memory_search", ok=True, summary="Nichts gefunden",
            payload="(nichts gefunden)"),
    })
    original = ToolResult(tool="memory_add", ok=True, summary="gemerkt")
    check = await engine.verify(
        "memory_add", {"label": "Wichtiger Fakt"}, original, run_tool)
    assert check.ok is False
