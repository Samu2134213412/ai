"""Das Langzeitgedächtnis: ein Netz aus Erinnerungen in SQLite.

Dieselbe Form wie im Wissensnetz der Oberfläche — Knoten mit Art und Text,
Kanten dazwischen. Der Abruf ist bewusst einfach gehalten und ohne zusätzliche
Abhängigkeit: Begriffe werden gewichtet gezählt, Titel zählen mehr als Fließtext.
Für ein persönliches Gedächtnis in der Größenordnung von hunderten Einträgen
trägt das, und es hat keine Einbettungen, die stillschweigend veralten.
"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

KINDS = ("regel", "projekt", "hardware", "vorliebe", "skill", "fakt")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id      TEXT PRIMARY KEY,
    label   TEXT NOT NULL,
    kind    TEXT NOT NULL DEFAULT 'fakt',
    text    TEXT NOT NULL DEFAULT '',
    x       REAL,
    y       REAL,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    a TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    b TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (a, b)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
"""

_WORD = re.compile(r"[\wäöüßÄÖÜ]{3,}", re.UNICODE)

#: Häufige deutsche Füllwörter tragen keine Bedeutung für den Abruf.
_STOP = {
    "der", "die", "das", "und", "oder", "aber", "auch", "eine", "einen", "einem",
    "eines", "einer", "für", "mit", "von", "vom", "zum", "zur", "auf", "aus",
    "bei", "nach", "über", "unter", "ist", "sind", "war", "waren", "hat", "habe",
    "haben", "wird", "werden", "kann", "könnte", "soll", "sollte", "muss", "mir",
    "mich", "dich", "dir", "sich", "wie", "was", "wer", "wann", "wo", "warum",
    "nicht", "kein", "keine", "noch", "schon", "sehr", "mal", "bitte", "dann", "du",
    "wenn", "dass", "als", "ich", "wir", "ihr", "sie", "man", "des", "dem",
}


def _terms(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP]


@dataclass(frozen=True)
class Memory:
    id: str
    label: str
    kind: str
    text: str
    score: float = 0.0

    def as_line(self) -> str:
        return f"[{self.kind}] {self.label}: {self.text}" if self.text else f"[{self.kind}] {self.label}"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "cat": self.kind, "text": self.text}


class MemoryStore:
    """Das Gedächtnis. Eine Datei, kein Server, kein Dienst."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # -- schreiben ---------------------------------------------------------
    def add(self, label: str, text: str = "", kind: str = "fakt",
            node_id: str | None = None, x: float | None = None,
            y: float | None = None) -> Memory:
        label = (label or "").strip() or "Ohne Titel"
        kind = kind if kind in KINDS else "fakt"
        node_id = node_id or f"n{uuid.uuid4().hex[:10]}"
        now = time.time()
        self._db.execute(
            "INSERT INTO nodes (id,label,kind,text,x,y,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET label=excluded.label, kind=excluded.kind, "
            "text=excluded.text, x=excluded.x, y=excluded.y, updated=excluded.updated",
            (node_id, label, kind, (text or "").strip(), x, y, now, now),
        )
        self._db.commit()
        return Memory(node_id, label, kind, (text or "").strip())

    def link(self, a: str, b: str) -> bool:
        if a == b:
            return False
        lo, hi = sorted((a, b))
        try:
            self._db.execute("INSERT OR IGNORE INTO links (a,b) VALUES (?,?)", (lo, hi))
        except sqlite3.IntegrityError:
            return False
        self._db.commit()
        return True

    def unlink(self, a: str, b: str) -> None:
        lo, hi = sorted((a, b))
        self._db.execute("DELETE FROM links WHERE a=? AND b=?", (lo, hi))
        self._db.commit()

    def delete(self, node_id: str) -> bool:
        cur = self._db.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        self._db.execute("DELETE FROM links WHERE a=? OR b=?", (node_id, node_id))
        self._db.commit()
        return cur.rowcount > 0

    # -- lesen -------------------------------------------------------------
    def get(self, node_id: str) -> Memory | None:
        row = self._db.execute(
            "SELECT id,label,kind,text FROM nodes WHERE id=?", (node_id,)).fetchone()
        return Memory(row["id"], row["label"], row["kind"], row["text"]) if row else None

    def all(self) -> list[Memory]:
        rows = self._db.execute(
            "SELECT id,label,kind,text FROM nodes ORDER BY updated DESC").fetchall()
        return [Memory(r["id"], r["label"], r["kind"], r["text"]) for r in rows]

    def graph(self) -> dict[str, Any]:
        """Die Form, die das Wissensnetz der Oberfläche erwartet."""
        rows = self._db.execute(
            "SELECT id,label,kind,text,x,y FROM nodes ORDER BY created").fetchall()
        nodes = [{"id": r["id"], "label": r["label"], "cat": r["kind"],
                  "text": r["text"], **({"x": r["x"], "y": r["y"]}
                                        if r["x"] is not None else {})} for r in rows]
        links = [[r["a"], r["b"]] for r in
                 self._db.execute("SELECT a,b FROM links").fetchall()]
        return {"nodes": nodes, "links": links}

    def replace_graph(self, graph: dict[str, Any]) -> int:
        """Übernimmt den Stand aus der Oberfläche. Ersetzt, nicht mischt."""
        nodes = graph.get("nodes") or []
        links = graph.get("links") or []
        now = time.time()
        with self._db:
            self._db.execute("DELETE FROM links")
            self._db.execute("DELETE FROM nodes")
            for n in nodes:
                if not isinstance(n, dict) or not n.get("id"):
                    continue
                kind = n.get("cat") or n.get("kind") or "fakt"
                self._db.execute(
                    "INSERT OR REPLACE INTO nodes (id,label,kind,text,x,y,created,updated)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (str(n["id"]), str(n.get("label") or "Ohne Titel"),
                     kind if kind in KINDS else "fakt", str(n.get("text") or ""),
                     n.get("x"), n.get("y"), now, now))
            known = {str(n["id"]) for n in nodes if isinstance(n, dict) and n.get("id")}
            for pair in links:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                a, b = str(pair[0]), str(pair[1])
                if a in known and b in known and a != b:
                    lo, hi = sorted((a, b))
                    self._db.execute("INSERT OR IGNORE INTO links (a,b) VALUES (?,?)", (lo, hi))
        return len(known)

    def neighbours(self, node_id: str) -> list[Memory]:
        rows = self._db.execute(
            "SELECT n.id,n.label,n.kind,n.text FROM nodes n JOIN links l "
            "ON (l.a=n.id AND l.b=?) OR (l.b=n.id AND l.a=?)",
            (node_id, node_id)).fetchall()
        return [Memory(r["id"], r["label"], r["kind"], r["text"]) for r in rows]

    # -- abrufen -----------------------------------------------------------
    def search(self, query: str, limit: int = 6) -> list[Memory]:
        """Gewichtete Begriffssuche. Titeltreffer zählen dreifach.

        Regeln werden angehoben: was Jarvis nie tun darf, soll nicht deshalb
        aus dem Kontext fallen, weil die Frage andere Wörter benutzt.
        """
        terms = set(_terms(query))
        rows = self._db.execute("SELECT id,label,kind,text FROM nodes").fetchall()
        scored: list[Memory] = []
        for r in rows:
            label_terms = set(_terms(r["label"]))
            text_terms = set(_terms(r["text"]))
            score = 3.0 * len(terms & label_terms) + 1.0 * len(terms & text_terms)
            if r["kind"] == "regel":
                score += 2.0
            if score > 0:
                scored.append(Memory(r["id"], r["label"], r["kind"], r["text"], score))
        scored.sort(key=lambda m: (-m.score, m.label))
        return scored[:limit]

    def context_for(self, query: str, limit: int = 6) -> str:
        """Der Gedächtnisblock, der vor jeder Modellanfrage eingesetzt wird."""
        hits = self.search(query, limit)
        if not hits:
            return ""
        return "\n".join(f"- {m.as_line()}" for m in hits)

    def seed(self, entries: Iterable[tuple[str, str, str]]) -> None:
        """Erstbefüllung. Überschreibt nichts, was schon da ist."""
        if self._db.execute("SELECT 1 FROM nodes LIMIT 1").fetchone():
            return
        for label, kind, text in entries:
            self.add(label=label, kind=kind, text=text)


DEFAULT_SEED = [
    ("Grundregel", "regel",
     "Eine reale Aktion darf nur dann als erfolgreich gemeldet werden, wenn ein "
     "Werkzeug tatsächlich lief und Erfolg zurückgab. Fehlt das Werkzeug: sagen, "
     "dass es fehlt. Schlägt es fehl: den echten Fehler nennen."),
    ("Deutsch", "vorliebe", "Jarvis antwortet auf Deutsch."),
    ("Lokal statt Cloud", "vorliebe",
     "Läuft lokal über Ollama. Keine laufenden API-Kosten, private Daten bleiben "
     "auf dem Rechner."),
]
