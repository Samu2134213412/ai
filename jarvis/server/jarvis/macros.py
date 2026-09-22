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


#: Erlaubte Schrittarten -- dieselbe Liste, die ``MacroEngine._run_steps``
#: unten tatsächlich verarbeitet. Eine einzige Quelle statt einer zweiten,
#: unabhängig gepflegten Kopie beim Anlegen eines Makros.
STEP_KINDS = frozenset({"tool", "if", "loop", "parallel", "wait"})


def validate_steps(steps: object, path: str = "steps") -> None:
    """Prüft eine Schrittliste rekursiv, BEVOR sie gespeichert wird (Punkt 46)
    -- dieselbe Form, die die Engine zur Laufzeit erwartet, hier vorab, damit
    ein ungültiges Makro gar nicht erst abgelegt wird. Wird sowohl von
    ``automation.macro.create`` als auch (indirekt, über ``MacroStore.save``)
    von jeder anderen Stelle gebraucht, die Schritte entgegennimmt."""
    if not isinstance(steps, list):
        raise MacroError(f"{path} muss eine Liste von Schritten sein.")
    for i, step in enumerate(steps):
        ort = f"{path}[{i}]"
        if not isinstance(step, dict):
            raise MacroError(f"{ort} muss ein Objekt sein.")
        art = step.get("kind", "tool")
        if art not in STEP_KINDS:
            raise MacroError(f"{ort}: unbekannte Schrittart {art!r} (erlaubt: "
                             f"{', '.join(sorted(STEP_KINDS))}).")
        if art == "tool" and not str(step.get("tool") or "").strip():
            raise MacroError(f"{ort}: ein 'tool'-Schritt braucht ein 'tool'-Feld.")
        elif art == "if":
            validate_steps(step.get("then", []), f"{ort}.then")
            validate_steps(step.get("else", []), f"{ort}.else")
        elif art == "loop":
            if "times" not in step and "while" not in step:
                raise MacroError(f"{ort}: eine Schleife braucht 'times' oder 'while'.")
            validate_steps(step.get("body", []), f"{ort}.body")
        elif art == "parallel":
            for j, zweig in enumerate(step.get("branches", [])):
                validate_steps(zweig, f"{ort}.branches[{j}]")


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
class _StepCounter:
    """Die Gesamtschrittzahl über einen ganzen Lauf -- über alle
    Verschachtelungen UND alle parallelen Zweige hinweg gemeinsam gezählt
    (``MAX_STEPS_TOTAL`` gilt makroweit, nicht je Zweig), deshalb ein
    eigenes, geteiltes Objekt statt eines Felds auf ``_RunState``."""
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> int:
        self.value += 1
        return self.value


@dataclass
class _RunState:
    """Bündelt, was durch einen Lauf gereicht wird, statt vier einzelne
    Parameter durch jede ``_schritt_*``-Methode zu fädeln. ``results``/
    ``log``/``all_results`` sind je Zweig eigene Objekte (siehe ``branch()``);
    ``counter`` bleibt über alle Zweige hinweg dasselbe Objekt."""
    counter: _StepCounter
    results: dict[str, ToolResult] = field(default_factory=dict)
    log: list[MacroStepLog] = field(default_factory=list)
    all_results: list[ToolResult] = field(default_factory=list)

    def branch(self) -> "_RunState":
        """Ein neuer Zustand für einen parallelen Zweig: eigene Ergebnisse/
        Protokoll/Aufrufliste, damit sich parallele Zweige nicht gegenseitig
        sehen, bevor sie nach ``asyncio.gather`` zusammengeführt sind --
        derselbe Zähler, weil die Gesamtobergrenze für das ganze Makro gilt."""
        return _RunState(counter=self.counter)


class MacroEngine:
    #: Harte Obergrenzen, unabhängig davon, was ein einzelnes Makro angibt --
    #: dieselbe Vorsicht wie Watchdog/GoalBudget in Autonomy V1.
    MAX_LOOP_ITERATIONS = 200
    MAX_STEPS_TOTAL = 500
    MAX_WAIT_SECONDS = 300.0

    def __init__(self, run_tool: RunTool):
        self._run_tool = run_tool

    async def run(self, steps: list[dict[str, Any]]) -> MacroRun:
        state = _RunState(counter=_StepCounter())
        ok = await self._run_steps(steps, state)
        return MacroRun(ok=ok, log=state.log, results=state.results,
                        all_results=state.all_results)

    async def _run_steps(self, steps: list[dict[str, Any]], state: _RunState) -> bool:
        for step in steps or []:
            if state.counter.increment() > self.MAX_STEPS_TOTAL:
                raise MacroError(f"Makro abgebrochen: mehr als {self.MAX_STEPS_TOTAL} "
                                 "Einzelschritte insgesamt -- vermutlich eine Schleife "
                                 "ohne wirkliches Ende.")
            art = step.get("kind", "tool")
            if art == "tool":
                if not await self._schritt_werkzeug(step, state):
                    return False
            elif art == "if":
                bedingung = step.get("condition") or {}
                zweig = step.get("then", []) if auswerten(bedingung, state.results) \
                    else step.get("else", [])
                if not await self._run_steps(zweig, state):
                    return False
            elif art == "loop":
                if not await self._schritt_schleife(step, state):
                    return False
            elif art == "parallel":
                if not await self._schritt_parallel(step, state):
                    return False
            elif art == "wait":
                sekunden = max(0.0, min(float(step.get("seconds", 0) or 0),
                                        self.MAX_WAIT_SECONDS))
                await asyncio.sleep(sekunden)
                state.log.append(MacroStepLog(step.get("id", ""), "wait", True,
                                              f"{sekunden}s gewartet"))
            else:
                raise MacroError(f"Unbekannte Schrittart: {art!r} "
                                 f"(erlaubt: {', '.join(sorted(STEP_KINDS))})")
        return True

    async def _schritt_werkzeug(self, step: dict[str, Any], state: _RunState) -> bool:
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
        step_id = step.get("id") or f"schritt{state.counter.value}"
        state.results[step_id] = ergebnis
        state.all_results.append(ergebnis)
        state.log.append(MacroStepLog(step_id, "tool", ergebnis.ok, ergebnis.summary, versuch))
        return ergebnis.ok or bool(step.get("continue_on_error"))

    async def _schritt_schleife(self, step: dict[str, Any], state: _RunState) -> bool:
        koerper = step.get("body", [])
        obergrenze = min(int(step.get("max_iterations", 50) or 50), self.MAX_LOOP_ITERATIONS)
        if "times" in step:
            anzahl = max(0, min(int(step["times"]), obergrenze))
            for _ in range(anzahl):
                if not await self._run_steps(koerper, state):
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
            if not await self._run_steps(koerper, state):
                return False
            if not auswerten(bedingung, state.results):
                break
        else:
            raise MacroError(f"Schleife nach {obergrenze} Durchläufen abgebrochen -- "
                             "'while' wurde nie falsch. max_iterations erhöhen, wenn das "
                             "wirklich so lange dauern soll, oder die Bedingung prüfen.")
        return True

    async def _schritt_parallel(self, step: dict[str, Any], state: _RunState) -> bool:
        zweige = step.get("branches") or []
        if not zweige:
            return True
        teil_zustaende = [state.branch() for _ in zweige]
        aufgaben = [self._run_steps(zweig, ts) for zweig, ts in zip(zweige, teil_zustaende)]
        resultate = await asyncio.gather(*aufgaben)
        for ts in teil_zustaende:
            state.results.update(ts.results)
            state.log.extend(ts.log)
            state.all_results.extend(ts.all_results)
        return all(resultate)
