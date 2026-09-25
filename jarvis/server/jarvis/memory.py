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

# "erfahrung" ist die Art, unter der die Zielverfolgung ihre Lehren ablegt
# (Punkt 15, Experience Learning). "sitzung" ist die Session-Ebene zwischen
# Kurz- und Langzeitgedächtnis (ROADMAP Phase 2): läuft, anders als jede
# andere Art, von selbst über ``expires`` ab. Ohne einen eigenen Eintrag
# würde ``add()`` unbekannte Arten stillschweigend zu "fakt" herabstufen und
# der Abruf fände sie nie wieder.
KINDS = ("regel", "projekt", "hardware", "vorliebe", "skill", "fakt", "erfahrung", "sitzung")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'fakt',
    text       TEXT NOT NULL DEFAULT '',
    x          REAL,
    y          REAL,
    importance REAL NOT NULL DEFAULT 0.5,
    source     TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0,
    created    REAL NOT NULL,
    updated    REAL NOT NULL,
    expires    REAL
);
CREATE TABLE IF NOT EXISTS links (
    a TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    b TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (a, b)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
"""

#: Spalten, die es vor dieser Version noch nicht gab -- an einer bestehenden,
#: schon befüllten Datenbank auf der Maschine des Nutzers reicht "CREATE TABLE
#: IF NOT EXISTS" allein nicht, die Tabelle existiert dort ja schon ohne sie.
_NEUE_SPALTEN = (
    ("importance", "REAL NOT NULL DEFAULT 0.5"),
    ("source", "TEXT NOT NULL DEFAULT ''"),
    ("confidence", "REAL NOT NULL DEFAULT 1.0"),
    ("expires", "REAL"),
)

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


_COLS = "id,label,kind,text,importance,source,confidence,created,updated,expires"


def _aus_zeile(row: sqlite3.Row, score: float = 0.0) -> "Memory":
    return Memory(row["id"], row["label"], row["kind"], row["text"],
                  row["importance"], row["source"], row["confidence"],
                  row["created"], row["updated"], row["expires"], score)


@dataclass(frozen=True)
class Memory:
    id: str
    label: str
    kind: str
    text: str
    importance: float = 0.5
    source: str = ""
    confidence: float = 1.0
    created: float = 0.0
    updated: float = 0.0
    #: Nur bei der Session-Ebene gesetzt (``kind="sitzung"``) -- ab diesem
    #: Zeitpunkt taucht der Knoten in keinem Abruf mehr auf. ``None`` heißt
    #: dauerhaft, wie jede andere Erinnerungsart.
    expires: float | None = None
    score: float = 0.0

    def as_line(self) -> str:
        return f"[{self.kind}] {self.label}: {self.text}" if self.text else f"[{self.kind}] {self.label}"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "cat": self.kind, "text": self.text,
                "importance": self.importance, "source": self.source,
                "confidence": self.confidence, "created": self.created, "updated": self.updated,
                "expires": self.expires}


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
        self._migrate()
        self._db.commit()
        # Bei jedem Start, nicht per eigenem Hintergrundtimer: eine
        # abgelaufene Sitzungs-Erinnerung ist ab ``expires`` ohnehin in jedem
        # Abruf schon unsichtbar (siehe search()/context_for()/graph()) --
        # das hier räumt nur noch die Platte auf.
        self.purge_expired()

    def _migrate(self) -> None:
        """Fügt Spalten nach, die eine bereits bestehende, schon befüllte
        Datenbank auf der Maschine des Nutzers noch nicht hat -- CREATE TABLE
        IF NOT EXISTS allein greift dort nicht, die Tabelle gibt es ja
        schon."""
        vorhanden = {row["name"] for row in self._db.execute("PRAGMA table_info(nodes)")}
        for spalte, definition in _NEUE_SPALTEN:
            if spalte not in vorhanden:
                self._db.execute(f"ALTER TABLE nodes ADD COLUMN {spalte} {definition}")

    def close(self) -> None:
        self._db.close()

    def _row(self, node_id: str) -> Memory | None:
        row = self._db.execute(
            f"SELECT {_COLS} FROM nodes WHERE id=?", (node_id,)).fetchone()
        return _aus_zeile(row) if row else None

    # -- schreiben ---------------------------------------------------------
    def add(self, label: str, text: str = "", kind: str = "fakt",
            node_id: str | None = None, x: float | None = None,
            y: float | None = None, importance: float = 0.5,
            source: str = "", confidence: float = 1.0,
            expires: float | None = None) -> Memory:
        label = (label or "").strip() or "Ohne Titel"
        kind = kind if kind in KINDS else "fakt"
        node_id = node_id or f"n{uuid.uuid4().hex[:10]}"
        importance = max(0.0, min(float(importance), 1.0))
        confidence = max(0.0, min(float(confidence), 1.0))
        source = (source or "").strip()
        now = time.time()
        self._db.execute(
            "INSERT INTO nodes (id,label,kind,text,x,y,importance,source,confidence,"
            "created,updated,expires) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET label=excluded.label, kind=excluded.kind, "
            "text=excluded.text, x=excluded.x, y=excluded.y, "
            "importance=excluded.importance, source=excluded.source, "
            "confidence=excluded.confidence, updated=excluded.updated, "
            "expires=excluded.expires",
            (node_id, label, kind, (text or "").strip(), x, y, importance, source,
             confidence, now, now, expires),
        )
        self._db.commit()
        # Zurückgelesen statt angenommen -- bei einem Konflikt (node_id gab es
        # schon) bleibt "created" das ursprüngliche, nicht "now".
        return self._row(node_id)

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
        return self._row(node_id)

    def all(self) -> list[Memory]:
        rows = self._db.execute(
            f"SELECT {_COLS} FROM nodes WHERE expires IS NULL OR expires > ? "
            "ORDER BY updated DESC", (time.time(),)).fetchall()
        return [_aus_zeile(r) for r in rows]

    def graph(self) -> dict[str, Any]:
        """Die Form, die das Wissensnetz der Oberfläche erwartet.

        Eine abgelaufene Sitzungs-Erinnerung taucht hier nicht mehr auf --
        physisch gelöscht ist sie deshalb noch nicht (siehe ``purge_expired``),
        aber sichtbar ist sie nirgends mehr.
        """
        rows = self._db.execute(
            f"SELECT {_COLS},x,y FROM nodes WHERE expires IS NULL OR expires > ? "
            "ORDER BY created", (time.time(),)).fetchall()
        nodes = [{**_aus_zeile(r).as_dict(),
                  **({"x": r["x"], "y": r["y"]} if r["x"] is not None else {})} for r in rows]
        sichtbar = {r["id"] for r in rows}
        links = [[r["a"], r["b"]] for r in
                 self._db.execute("SELECT a,b FROM links").fetchall()
                 if r["a"] in sichtbar and r["b"] in sichtbar]
        return {"nodes": nodes, "links": links}

    def replace_graph(self, graph: dict[str, Any]) -> int:
        """Übernimmt den Stand aus der Oberfläche. Ersetzt, nicht mischt.

        "created" bleibt dabei erhalten, wenn die Kennung schon existierte --
        die Oberfläche schickt bei jeder Änderung (auch nur einen Knoten
        verschieben) den ganzen Graphen neu; ohne das würde "created" bei
        jedem Ziehen stillschweigend auf "jetzt" zurückspringen und wäre als
        Zeitstempel wertlos.
        """
        nodes = graph.get("nodes") or []
        links = graph.get("links") or []
        now = time.time()
        bestehend = {r["id"]: r["created"] for r in
                     self._db.execute("SELECT id, created FROM nodes")}
        with self._db:
            self._db.execute("DELETE FROM links")
            self._db.execute("DELETE FROM nodes")
            for n in nodes:
                if not isinstance(n, dict) or not n.get("id"):
                    continue
                node_id = str(n["id"])
                kind = n.get("cat") or n.get("kind") or "fakt"
                importance = n.get("importance")
                importance = (max(0.0, min(float(importance), 1.0))
                              if importance is not None else 0.5)
                confidence = n.get("confidence")
                confidence = (max(0.0, min(float(confidence), 1.0))
                              if confidence is not None else 1.0)
                expires = n.get("expires")
                self._db.execute(
                    "INSERT OR REPLACE INTO nodes (id,label,kind,text,x,y,importance,"
                    "source,confidence,created,updated,expires) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (node_id, str(n.get("label") or "Ohne Titel"),
                     kind if kind in KINDS else "fakt", str(n.get("text") or ""),
                     n.get("x"), n.get("y"), importance, str(n.get("source") or ""),
                     confidence, bestehend.get(node_id, now), now,
                     float(expires) if expires is not None else None))
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
        cols = ",".join(f"n.{c}" for c in _COLS.split(","))
        rows = self._db.execute(
            f"SELECT {cols} FROM nodes n JOIN links l "
            "ON (l.a=n.id AND l.b=?) OR (l.b=n.id AND l.a=?) "
            "WHERE n.expires IS NULL OR n.expires > ?",
            (node_id, node_id, time.time())).fetchall()
        return [_aus_zeile(r) for r in rows]

    # -- abrufen -----------------------------------------------------------
    def search(self, query: str, limit: int = 6) -> list[Memory]:
        """Gewichtete Begriffssuche. Titeltreffer zählen dreifach.

        Regeln werden angehoben: was Jarvis nie tun darf, soll nicht deshalb
        aus dem Kontext fallen, weil die Frage andere Wörter benutzt. Eine
        abgelaufene Sitzungs-Erinnerung (``expires`` in der Vergangenheit)
        wird gar nicht erst bewertet -- die Session-Ebene soll von selbst
        verblassen, nicht nur schlechter ranken.
        """
        terms = set(_terms(query))
        rows = self._db.execute(
            f"SELECT {_COLS} FROM nodes WHERE expires IS NULL OR expires > ?",
            (time.time(),)).fetchall()
        scored: list[Memory] = []
        for r in rows:
            label_terms = set(_terms(r["label"]))
            text_terms = set(_terms(r["text"]))
            score = 3.0 * len(terms & label_terms) + 1.0 * len(terms & text_terms)
            if r["kind"] == "regel":
                score += 2.0
            if score > 0:
                # Wichtigkeit verschiebt nur die Rangfolge unter echten
                # Treffern (0.5 = Vorgabe = keine Verschiebung), entscheidet
                # aber nie allein: ohne Begriffstreffer bleibt score 0, und
                # der Knoten fällt weiterhin ganz aus dem Ergebnis heraus.
                scored.append(_aus_zeile(r, score * (0.5 + r["importance"])))
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
            self.add(label=label, kind=kind, text=text, source="seed")

    def purge_expired(self) -> int:
        """Löscht abgelaufene Erinnerungen endgültig von der Platte.

        Sichtbar sind sie schon vorher nirgends mehr -- jeder Abruf
        (``search``/``context_for``/``graph``/``all``/``neighbours``)
        filtert selbst nach ``expires``. Das hier ist nur das Aufräumen, das
        sonst über Monate hinweg tote Sitzungs-Erinnerungen anhäufen würde.
        Läuft automatisch bei jedem Start (siehe ``__init__``); kein eigener
        Hintergrundtimer nötig, weil ein Server-Neustart auf einem
        Heimrechner die Regel ist, kein Sonderfall.
        """
        now = time.time()
        with self._db:
            faellig = [r["id"] for r in self._db.execute(
                "SELECT id FROM nodes WHERE expires IS NOT NULL AND expires <= ?", (now,))]
            for node_id in faellig:
                self._db.execute("DELETE FROM links WHERE a=? OR b=?", (node_id, node_id))
            self._db.execute(
                "DELETE FROM nodes WHERE expires IS NOT NULL AND expires <= ?", (now,))
        return len(faellig)


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
