"""Gedächtniswerkzeuge: nachschlagen und sich etwas merken.

Der automatische Abruf vor jeder Modellanfrage deckt den Normalfall ab. Diese
Werkzeuge sind für den Fall, dass das Modell gezielt nachfragen oder etwas
ablegen will — und dafür, dass ein „merk dir das" ein überprüfbares Ergebnis
bekommt statt eines Versprechens.
"""

from __future__ import annotations

from ..memory import KINDS, MemoryStore
from ..permissions import PermissionLevel
from .base import Tool, ToolError, ToolResult


def build(store: MemoryStore) -> list[Tool]:

    def memory_search(query: str, limit: int = 6) -> ToolResult:
        if not (query or "").strip():
            raise ToolError("Es wurde kein Suchbegriff angegeben.")
        limit = max(1, min(int(limit or 6), 25))
        hits = store.search(query, limit)
        lines = [f"{m.id}  {m.as_line()}" for m in hits]
        return ToolResult(
            tool="memory_search", ok=True,
            summary=(f"{len(hits)} Erinnerungen zu '{query}'" if hits
                     else f"Nichts gefunden zu '{query}'"),
            evidence={"suche": query, "treffer": len(hits)},
            payload="\n".join(lines) if lines else "(nichts gefunden)")

    def memory_add(label: str, text: str = "", kind: str = "fakt") -> ToolResult:
        if not (label or "").strip():
            raise ToolError("Eine Erinnerung braucht einen Titel.")
        if kind not in KINDS:
            raise ToolError(f"Unbekannte Art '{kind}'. Erlaubt: {', '.join(KINDS)}")
        node = store.add(label=label, text=text, kind=kind)
        # Der Beleg wird zurückgelesen, nicht angenommen.
        stored = store.get(node.id)
        if stored is None:
            raise ToolError("Die Erinnerung ist nach dem Schreiben nicht auffindbar.")
        return ToolResult(
            tool="memory_add", ok=True,
            summary=f"Gemerkt: {stored.label}",
            evidence={"id": stored.id, "art": stored.kind,
                      "zeichen": len(stored.text)},
            payload=stored.as_line())

    def memory_link(a: str, b: str) -> ToolResult:
        if not store.get(a):
            raise ToolError(f"Unbekannte Erinnerung: {a}")
        if not store.get(b):
            raise ToolError(f"Unbekannte Erinnerung: {b}")
        created = store.link(a, b)
        return ToolResult(
            tool="memory_link", ok=True,
            summary="Verbindung angelegt" if created else "Verbindung bestand bereits",
            evidence={"von": a, "nach": b, "neu": created})

    def memory_forget(id: str) -> ToolResult:  # noqa: A002 - Name im Schema
        node = store.get(id)
        if node is None:
            raise ToolError(f"Unbekannte Erinnerung: {id}")
        if not store.delete(id):
            raise ToolError(f"Löschen fehlgeschlagen: {id}")
        if store.get(id) is not None:
            raise ToolError(f"Erinnerung ist nach dem Löschen noch vorhanden: {id}")
        return ToolResult(
            tool="memory_forget", ok=True,
            summary=f"Vergessen: {node.label}",
            evidence={"id": id, "titel": node.label})

    _str = {"type": "string"}
    return [
        Tool("memory_search",
             "Durchsucht das Langzeitgedächtnis nach Erinnerungen zu einem Thema.",
             {"type": "object",
              "properties": {"query": _str, "limit": {"type": "integer"}},
              "required": ["query"]},
             memory_search, level=PermissionLevel.SAFE),
        Tool("memory_add",
             "Legt eine neue Erinnerung an. Art: " + ", ".join(KINDS) + ".",
             {"type": "object",
              "properties": {"label": {**_str, "description": "Kurzer Titel"},
                             "text": {**_str, "description": "Der Inhalt"},
                             "kind": {**_str, "enum": list(KINDS)}},
              "required": ["label"]},
             memory_add, level=PermissionLevel.WRITE),
        Tool("memory_link", "Verbindet zwei Erinnerungen miteinander.",
             {"type": "object", "properties": {"a": _str, "b": _str},
              "required": ["a", "b"]},
             memory_link, level=PermissionLevel.WRITE),
        Tool("memory_forget", "Löscht eine Erinnerung endgültig.",
             {"type": "object", "properties": {"id": _str}, "required": ["id"]},
             memory_forget, level=PermissionLevel.CRITICAL),
    ]
