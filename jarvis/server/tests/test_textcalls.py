"""Werkzeugaufrufe, die das Modell als Text schreibt.

Anlass: Qwen3-Coder schrieb auf einen großen Auftrag hin

    Ich werde nun mit der Analyse des Arbeitsbereichs beginnen ...
    <function=list_dir> <parameter=path> C:\\...\\Desktop </parameter> </function> </tool_call>

-- ohne öffnendes ``<tool_call>``. Ollama erkannte das nicht als Aufruf,
Jarvis hielt es für die fertige Antwort und machte nichts mehr.
"""

from __future__ import annotations

import json

import httpx
import pytest

from jarvis import guard
from jarvis import ollama as ollama_mod
from jarvis.agent import Agent
from jarvis.ollama import OllamaClient
from jarvis.permissions import PermissionGate, PermissionPolicy
from jarvis.textcalls import extract

WERKZEUGE = [
    {"type": "function", "function": {"name": "list_dir", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "write_file", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"},
                                         "content": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "files.large.find", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"},
                                         "limit": {"type": "integer"},
                                         "recursive": {"type": "boolean"},
                                         "extensions": {"type": "array"}}}}},
]

SCREENSHOT = ("Ich werde nun mit der Analyse des Arbeitsbereichs beginnen, um die vorhandenen "
              "Dateien zu erkennen und den aktuellen Stand des Projekts zu verstehen.\n\n"
              "<function=list_dir>\n<parameter=path>\nC:\\Users\\SohndesDrachen\\Desktop\n"
              "</parameter>\n</function>\n</tool_call>")


# ══════════════════════════════════════════════════════ Formate
def test_der_fall_aus_dem_screenshot():
    text, calls = extract(SCREENSHOT, WERKZEUGE)
    assert calls == [("list_dir", {"path": "C:\\Users\\SohndesDrachen\\Desktop"})]
    assert text.startswith("Ich werde nun mit der Analyse")
    assert "<" not in text, "vom Aufruf darf nichts in der Antwort stehen bleiben"


def test_qwen_xml_mit_rahmen_typen_und_zwei_aufrufen():
    antwort = ("<tool_call>\n<function=files.large.find>\n<parameter=path>\nDownloads\n"
               "</parameter>\n<parameter=limit>\n5\n</parameter>\n<parameter=recursive>\n"
               "True\n</parameter>\n<parameter=extensions>\n[\"zip\", \"iso\"]\n</parameter>\n"
               "</function>\n</tool_call>\n<tool_call>\n<function=write_file>\n"
               "<parameter=path>\nnotiz.txt\n</parameter>\n<parameter=content>\n"
               "Zeile 1\n\nZeile 3\n\n</parameter>\n</function>\n</tool_call>")
    text, calls = extract(antwort, WERKZEUGE)
    assert text == ""
    assert calls == [
        ("files.large.find", {"path": "Downloads", "limit": 5, "recursive": True,
                              "extensions": ["zip", "iso"]}),
        # Genau ein Umbruch vorn/hinten gehört zum Format -- der Rest zum Inhalt.
        ("write_file", {"path": "notiz.txt", "content": "Zeile 1\n\nZeile 3\n"}),
    ]


def test_abgeschnittener_aufruf_wird_trotzdem_gelesen():
    _, calls = extract("<function=read_file><parameter=path>a.txt", WERKZEUGE)
    assert calls == [("read_file", {"path": "a.txt"})]


def test_hermes_json_im_rahmen():
    antwort = ('Ich lese nach.\n<tool_call>\n{"name": "read_file", "arguments": '
               '{"path": "a.txt"}}\n</tool_call>')
    text, calls = extract(antwort, WERKZEUGE)
    assert calls == [("read_file", {"path": "a.txt"})]
    assert text == "Ich lese nach."
    # Argumente als JSON-Text (manche Vorlagen) gehen auch.
    _, calls = extract('<tool_call>{"name": "read_file", "arguments": "{\\"path\\": '
                       '\\"b.txt\\"}"}</tool_call>', WERKZEUGE)
    assert calls == [("read_file", {"path": "b.txt"})]


def test_reines_json_nur_mit_angebotenem_werkzeug():
    _, calls = extract('```json\n{"name": "list_dir", "parameters": {"path": "."}}\n```',
                       WERKZEUGE)
    assert calls == [("list_dir", {"path": "."})]
    # Gewöhnliches JSON als Antwort ist kein Aufruf.
    for antwort in ('{"name": "Sam", "arguments": {}}', '{"temperatur": 21}', "[1, 2]"):
        assert extract(antwort, WERKZEUGE) == (antwort, [])


def test_erfundener_name_im_eindeutigen_format_kommt_durch():
    """Der Agent sagt dem Modell dann "existiert nicht" -- besser als stumm
    aufzuhören."""
    _, calls = extract("<function=desktop.aufraeumen>\n</function>", WERKZEUGE)
    assert calls == [("desktop.aufraeumen", {})]


# ══════════════════════════════════════════════════════ Grenzen
def test_aufruf_im_codezaun_bleibt_text():
    antwort = ("So sähe ein Aufruf aus:\n```\n<function=write_file>\n<parameter=path>\nx\n"
               "</parameter>\n</function>\n```")
    assert extract(antwort, WERKZEUGE) == (antwort, [])


def test_ohne_angebotene_werkzeuge_wird_nichts_gelesen():
    assert extract(SCREENSHOT, None) == (SCREENSHOT, [])
    assert extract(SCREENSHOT, []) == (SCREENSHOT, [])


def test_normale_antwort_bleibt_unberuehrt():
    antwort = "Auf dem Desktop liegen 3 Dateien. Soll ich sie sortieren?"
    assert extract(antwort, WERKZEUGE) == (antwort, [])


# ══════════════════════════════════════════════════════ der ganze Zug
@pytest.fixture
def ollama_antwortet(monkeypatch):
    """Ein echter ``OllamaClient``, dessen HTTP-Gegenüber der Test spielt --
    so läuft auch das Auslesen der Antwort mit, nicht nur der Agent."""
    anfragen: list[dict] = []
    antworten: list[dict] = []
    echt = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        anfragen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": antworten.pop(0)})

    monkeypatch.setattr(ollama_mod.httpx, "AsyncClient",
                        lambda **kw: echt(transport=httpx.MockTransport(handler), **kw))

    def setze(*nachrichten: dict) -> list[dict]:
        antworten.extend(nachrichten)
        return anfragen
    return setze


async def test_agent_macht_nach_einem_textaufruf_weiter(
        config, store, registry, workspace, ollama_antwortet):
    (workspace / "notiz.txt").write_text("hallo", encoding="utf-8")
    anfragen = ollama_antwortet(
        {"role": "assistant", "content": SCREENSHOT.replace(
            "C:\\Users\\SohndesDrachen\\Desktop", str(workspace))},
        {"role": "assistant", "content": "Im Arbeitsbereich liegt notiz.txt."})
    gate = PermissionGate(policy=PermissionPolicy(confirm_read=False))
    agent = Agent(config, store, registry, OllamaClient(), permission_gate=gate)

    reply = await agent.handle("Schau dir meinen Arbeitsbereich an")

    # Das Werkzeug lief wirklich, und das Modell bekam sein Ergebnis zurück.
    assert [r.tool for r in reply.results] == ["list_dir"]
    assert reply.results[0].ok is True
    assert len(anfragen) == 2
    assistent, werkzeug = anfragen[1]["messages"][-2:]
    assert assistent["tool_calls"][0]["function"] == {
        "name": "list_dir", "arguments": {"path": str(workspace)}}
    assert "<function=" not in assistent["content"]
    assert werkzeug["role"] == "tool" and "notiz.txt" in werkzeug["content"]
    assert reply.provenance == guard.TOOL
    assert reply.text == "Im Arbeitsbereich liegt notiz.txt."
