"""Makros: gespeicherte, deterministische Werkzeugfolgen mit Kontrollfluss
(Punkt 46) -- IF/LOOP/PARALLEL/RETRY/WAIT.

Bewusst **keine** zweite Ausführungsmaschine neben dem, was schon da ist
(vgl. ``goals.py``s Docstring zum selben Prinzip): ein Makro-Schritt läuft
über genau dasselbe ``run_tool``-Callable, das ``verification.py`` und
``decision.py`` schon verwenden -- in der Praxis ``Agent._run_tool``, also
mit Permission-Gate, Audit-Log und Undo-Snapshot wie jeder andere
Werkzeugaufruf auch. Die Engine selbst kennt weder ``Agent`` noch die
Registry; sie bekommt nur das eine Callable hereingereicht.

Ein Makro ist als Liste einfacher Dictionaries gespeichert (kein eigener
Klassenbaum, keine eigene (De-)Serialisierung) -- dieselbe Form, in der ein
Modell es als Werkzeugargument ohnehin anliefert:

    {"id": "s1", "kind": "tool", "tool": "files.info",
     "arguments": {"path": "x.txt"}, "retry": 2, "retry_delay": 1.0}
    {"id": "c1", "kind": "if", "condition": {...}, "then": [...], "else": [...]}
    {"id": "l1", "kind": "loop", "times": 5, "body": [...]}
    {"id": "l2", "kind": "loop", "while": {...}, "max_iterations": 20, "body": [...]}
    # -- "while" wird NACH jedem Durchlauf geprüft, nicht davor: der
    #    Normalfall ist "wiederhole, solange Schritt X aus dem Rumpf noch
    #    nicht ok ist", und vor dem ersten Durchlauf gibt es für X schlicht
    #    noch kein Ergebnis, das sich prüfen ließe.
    {"id": "p1", "kind": "parallel", "branches": [[...], [...]]}
    {"id": "w1", "kind": "wait", "seconds": 2.5}

Zwei harte Obergrenzen schützen vor einem Makro, das sich selbst nie beendet
(dieselbe Sorge wie beim Watchdog aus Autonomy V1, Punkt 18/21): eine
Schleife ohne ``times`` läuft höchstens ``MAX_LOOP_ITERATIONS`` Mal, und ein
ganzer Lauf verarbeitet höchstens ``MAX_STEPS_TOTAL`` Einzelschritte
insgesamt (über alle Verschachtelungen hinweg) -- danach bricht die Engine
mit einer ehrlichen Fehlermeldung ab, statt endlos weiterzulaufen.

Eine Bedingung (``condition``/``while``) ist ein Vergleich gegen das
Ergebnis eines vorherigen Schritts, kein eval-fähiger Ausdruck (dieselbe
Vorsicht wie bei ``productivity.calculate``s eigenem AST-Auswerter):

    {"step": "s1", "field": "ok", "op": "==", "value": true}
    {"step": "s1", "field": "evidence.groesse", "op": ">", "value": 1000}
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from .tools.base import ToolResult

RunTool = Callable[[str, dict], Awaitable[ToolResult]]


class MacroError(Exception):
    """Ein Makro lässt sich nicht (weiter) ausführen -- ungültige Definition
    oder eine der beiden Notbremsen (Schleife/Gesamtschrittzahl) hat gegriffen."""


# ══════════════════════════════════════════════════════════════ Definition
@dataclass
class MacroDefinition:
    id: str
    name: str
    steps: list[dict[str, Any]]
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "beschreibung": self.description,
                "schritte": self.steps, "erstellt": self.created_at,
                "geaendert": self.updated_at, "anzahl_schritte": len(self.steps)}


# ══════════════════════════════════════════════════════════════ Ablage
_SCHEMA = """
CREATE TABLE IF NOT EXISTS macros (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    steps       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
"""


def _row_to_definition(row: sqlite3.Row) -> MacroDefinition:
    return MacroDefinition(id=row["id"], name=row["name"], description=row["description"],
                           steps=json.loads(row["steps"]), created_at=row["created_at"],
                           updated_at=row["updated_at"])


class MacroStore:
    """Gespeicherte Makros -- eine SQLite-Datei wie ``UndoStore``/``AuditLog``,
    überlebt also einen Serverneustart."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def save(self, name: str, steps: list[dict[str, Any]], description: str = "") -> MacroDefinition:
        n = (name or "").strip()
        if not n:
            raise MacroError("Kein Name angegeben.")
        if not steps:
            raise MacroError("Ein Makro ohne Schritte ist nicht erlaubt.")
        bestehend = self.get_by_name(n)
        jetzt = time.time()
        definition = MacroDefinition(
            id=bestehend.id if bestehend else str(uuid.uuid4()), name=n, steps=list(steps),
            description=description, created_at=bestehend.created_at if bestehend else jetzt,
            updated_at=jetzt)
        self._db.execute(
            "INSERT INTO macros (id, name, description, steps, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
            "steps=excluded.steps, updated_at=excluded.updated_at",
            (definition.id, definition.name, definition.description,
             json.dumps(definition.steps), definition.created_at, definition.updated_at))
        self._db.commit()
        return definition

    def get_by_name(self, name: str) -> MacroDefinition | None:
        row = self._db.execute("SELECT * FROM macros WHERE name = ?", (name,)).fetchone()
        return _row_to_definition(row) if row else None

    def list(self) -> list[MacroDefinition]:
        rows = self._db.execute("SELECT * FROM macros ORDER BY name").fetchall()
        return [_row_to_definition(r) for r in rows]

    def delete(self, name: str) -> bool:
        cur = self._db.execute("DELETE FROM macros WHERE name = ?", (name,))
        self._db.commit()
        return cur.rowcount > 0


# ══════════════════════════════════════════════════════════════ Bedingungen
_VERGLEICHE: dict[str, Callable[[Any, Any], bool]] = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b, "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
    "contains": lambda a, b: (b in a) if a is not None else False,
}


def _feldwert(result: ToolResult, feld: str) -> Any:
    if feld == "ok":
        return result.ok
    if feld == "summary":
        return result.summary
    if feld == "payload":
        return result.payload
    if feld.startswith("evidence."):
        return result.evidence.get(feld[len("evidence."):])
    raise MacroError(f"Unbekanntes Feld in einer Bedingung: {feld!r} "
                     "(erlaubt: ok, summary, payload, evidence.<schlüssel>)")


def auswerten(bedingung: dict[str, Any], ergebnisse: dict[str, ToolResult]) -> bool:
    schritt_id = bedingung.get("step")
    if schritt_id not in ergebnisse:
        raise MacroError(f"Bedingung verweist auf einen unbekannten oder noch nicht "
                         f"gelaufenen Schritt: {schritt_id!r}")
    op = bedingung.get("op", "==")
    vergleich = _VERGLEICHE.get(op)
    if vergleich is None:
        raise MacroError(f"Unbekannter Vergleichsoperator: {op!r} "
                         f"(erlaubt: {', '.join(_VERGLEICHE)})")
    wert = _feldwert(ergebnisse[schritt_id], bedingung.get("field", "ok"))
    return bool(vergleich(wert, bedingung.get("value")))


# ══════════════════════════════════════════════════════════════ Protokoll
@dataclass(frozen=True)
class MacroStepLog:
    step_id: str
    kind: str
    ok: bool
    summary: str
    versuche: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {"schritt": self.step_id, "art": self.kind, "erfolg": self.ok,
                "zusammenfassung": self.summary, "versuche": self.versuche}


@dataclass(frozen=True)
class MacroRun:
    ok: bool
    log: list[MacroStepLog]
    #: Nach Schritt-id, für Bedingungen (``if``/``while``) -- bei einer
    #: Schleife, deren Rumpf dieselbe id in jedem Durchlauf wiederverwendet
    #: (der im Docstring beschriebene Normalfall für ``while``), steht hier
    #: bewusst nur das jeweils LETZTE Ergebnis: eine Bedingung fragt "ist der
    #: Schritt gerade eben gelungen?", nicht "wie oft insgesamt?".
    results: dict[str, ToolResult]
    #: Jeder tatsächlich gelaufene Werkzeugaufruf, in Reihenfolge, OHNE das
    #: Wegfallen durch wiederverwendete ids -- die Grundlage für ``summary()``
    #: und für das, was ``Agent.run_macro`` als Beleg an guard.verify() gibt.
    #: Ohne dieses Feld würde ein "wiederhole Schritt X, bis ..."-Makro (die
    #: dokumentierte Standardform von ``while``) am Ende so berichtet, als
    #: wäre nur ein einziges Mal ein Werkzeug gelaufen, statt tatsächlich N Mal.
    all_results: list[ToolResult] = field(default_factory=list)

    def summary(self, name: str) -> str:
        """Bewusst ohne Vollzugsverb (kein "abgeschlossen"/"beendet") --
        das sind Wörter, die guard.claims_completion() als Behauptung liest;
        bei null gelaufenen Werkzeugaufrufen (z. B. ein reines wait-Makro)
        stünde dann eine Behauptung ganz ohne Beleg da."""
        gesamt = len(self.all_results)
        erfolgreich = sum(1 for r in self.all_results if r.ok)
        status = "alle erfolgreich" if self.ok else "mit Fehlschlag"
        return f"Makro '{name}': {erfolgreich}/{gesamt} Werkzeugaufrufe, {status}"


# ══════════════════════════════════════════════════════════════ Engine
class MacroEngine:
    #: Harte Obergrenzen, unabhängig davon, was ein einzelnes Makro angibt --
    #: dieselbe Vorsicht wie Watchdog/GoalBudget in Autonomy V1.
    MAX_LOOP_ITERATIONS = 200
    MAX_STEPS_TOTAL = 500
    MAX_WAIT_SECONDS = 300.0

    def __init__(self, run_tool: RunTool):
        self._run_tool = run_tool

    async def run(self, steps: list[dict[str, Any]]) -> MacroRun:
        ergebnisse: dict[str, ToolResult] = {}
        protokoll: list[MacroStepLog] = []
        alle: list[ToolResult] = []
        zaehler = [0]
        ok = await self._run_steps(steps, ergebnisse, protokoll, alle, zaehler)
        return MacroRun(ok=ok, log=protokoll, results=ergebnisse, all_results=alle)

    async def _run_steps(self, steps: list[dict[str, Any]], ergebnisse: dict[str, ToolResult],
                         protokoll: list[MacroStepLog], alle: list[ToolResult],
                         zaehler: list[int]) -> bool:
        for step in steps or []:
            zaehler[0] += 1
            if zaehler[0] > self.MAX_STEPS_TOTAL:
                raise MacroError(f"Makro abgebrochen: mehr als {self.MAX_STEPS_TOTAL} "
                                 "Einzelschritte insgesamt -- vermutlich eine Schleife "
                                 "ohne wirkliches Ende.")
            art = step.get("kind", "tool")
            if art == "tool":
                if not await self._schritt_werkzeug(step, ergebnisse, protokoll, alle, zaehler):
                    return False
            elif art == "if":
                bedingung = step.get("condition") or {}
                zweig = step.get("then", []) if auswerten(bedingung, ergebnisse) \
                    else step.get("else", [])
                if not await self._run_steps(zweig, ergebnisse, protokoll, alle, zaehler):
                    return False
            elif art == "loop":
                if not await self._schritt_schleife(step, ergebnisse, protokoll, alle, zaehler):
                    return False
            elif art == "parallel":
                if not await self._schritt_parallel(step, ergebnisse, protokoll, alle, zaehler):
                    return False
            elif art == "wait":
                sekunden = max(0.0, min(float(step.get("seconds", 0) or 0),
                                        self.MAX_WAIT_SECONDS))
                await asyncio.sleep(sekunden)
                protokoll.append(MacroStepLog(step.get("id", ""), "wait", True,
                                              f"{sekunden}s gewartet"))
            else:
                raise MacroError(f"Unbekannte Schrittart: {art!r} "
                                 "(erlaubt: tool, if, loop, parallel, wait)")
        return True

    async def _schritt_werkzeug(self, step: dict[str, Any], ergebnisse: dict[str, ToolResult],
                                protokoll: list[MacroStepLog], alle: list[ToolResult],
                                zaehler: list[int]) -> bool:
        tool = (step.get("tool") or "").strip()
        if not tool:
            raise MacroError("Ein Schritt vom Typ 'tool' braucht ein 'tool'-Feld.")
        arguments = step.get("arguments") or {}
        max_versuche = max(0, int(step.get("retry", 0) or 0)) + 1
        verzoegerung = max(0.0, float(step.get("retry_delay", 1.0) or 0))
        ergebnis: ToolResult | None = None
        versuch = 0
        for versuch in range(1, max_versuche + 1):
            ergebnis = await self._run_tool(tool, arguments)
            if ergebnis.ok or versuch == max_versuche:
                break
            await asyncio.sleep(verzoegerung)
        step_id = step.get("id") or f"schritt{zaehler[0]}"
        ergebnisse[step_id] = ergebnis
        alle.append(ergebnis)
        protokoll.append(MacroStepLog(step_id, "tool", ergebnis.ok, ergebnis.summary, versuch))
        return ergebnis.ok or bool(step.get("continue_on_error"))

    async def _schritt_schleife(self, step: dict[str, Any], ergebnisse: dict[str, ToolResult],
                                protokoll: list[MacroStepLog], alle: list[ToolResult],
                                zaehler: list[int]) -> bool:
        koerper = step.get("body", [])
        obergrenze = min(int(step.get("max_iterations", 50) or 50), self.MAX_LOOP_ITERATIONS)
        if "times" in step:
            anzahl = max(0, min(int(step["times"]), obergrenze))
            for _ in range(anzahl):
                if not await self._run_steps(koerper, ergebnisse, protokoll, alle, zaehler):
                    return False
            return True
        bedingung = step.get("while")
        if bedingung is None:
            raise MacroError("Ein Schritt vom Typ 'loop' braucht 'times' oder 'while'.")
        # Geprüft wird NACH jedem Durchlauf, nicht davor: 'while' bezieht sich
        # im typischen Fall ("wiederhole, solange Schritt X noch nicht ok
        # ist") auf einen Schritt aus dem eigenen Rumpf -- eine Prüfung vor
        # dem ersten Durchlauf hätte dafür schlicht noch kein Ergebnis, das
        # sie lesen könnte. Effektiv also ein repeat-until in umgekehrter
        # Bedingung, nicht das klassische, vorab prüfende while.
        for _ in range(obergrenze):
            if not await self._run_steps(koerper, ergebnisse, protokoll, alle, zaehler):
                return False
            if not auswerten(bedingung, ergebnisse):
                break
        else:
            raise MacroError(f"Schleife nach {obergrenze} Durchläufen abgebrochen -- "
                             "'while' wurde nie falsch. max_iterations erhöhen, wenn das "
                             "wirklich so lange dauern soll, oder die Bedingung prüfen.")
        return True

    async def _schritt_parallel(self, step: dict[str, Any], ergebnisse: dict[str, ToolResult],
                                protokoll: list[MacroStepLog], alle: list[ToolResult],
                                zaehler: list[int]) -> bool:
        zweige = step.get("branches") or []
        if not zweige:
            return True
        teil_ergebnisse: list[dict[str, ToolResult]] = [dict() for _ in zweige]
        teil_protokolle: list[list[MacroStepLog]] = [list() for _ in zweige]
        teil_alle: list[list[ToolResult]] = [list() for _ in zweige]
        aufgaben = [self._run_steps(zweig, te, tp, ta, zaehler)
                   for zweig, te, tp, ta in zip(zweige, teil_ergebnisse, teil_protokolle, teil_alle)]
        resultate = await asyncio.gather(*aufgaben)
        for te, tp, ta in zip(teil_ergebnisse, teil_protokolle, teil_alle):
            ergebnisse.update(te)
            protokoll.extend(tp)
            alle.extend(ta)
        return all(resultate)
