"""Der Wächter. Hier wird die Grundregel des Projekts durchgesetzt.

    Eine reale Aktion darf nur dann als erfolgreich gemeldet werden, wenn ein
    Werkzeug tatsächlich lief und Erfolg zurückgab.

Ein Prompt, der das verlangt, ist eine Bitte. Dieser Modul ist eine Zusage. Er
arbeitet auf zwei Ebenen:

1. **Herkunft aus Daten.** ``provenance`` einer Antwort wird aus der Liste der
   ``ToolResult``s berechnet, nie aus dem Text. Die Oberfläche zeigt deshalb
   „Tool-Beleg" genau dann, wenn einer vorliegt.

2. **Behauptungssperre.** Behauptet der Text eine erledigte Aktion, ohne dass
   ein erfolgreiches ``ToolResult`` dahintersteht, wird der Text **verworfen**
   und durch eine wahrheitsgemäße Antwort ersetzt. Nicht markiert, nicht
   abgeschwächt — ersetzt.

Das ist bewusst streng. Ein zu Unrecht kassierter Satz kostet Bequemlichkeit,
eine durchgelassene Lüge kostet das Vertrauen in das ganze System.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tools.base import ToolResult

TALK = "talk"
TOOL = "tool"
FAIL = "fail"

#: Partizipien, die eine vollzogene Veränderung an der Welt behaupten.
_DONE = (
    r"erstellt|angelegt|geschrieben|gespeichert|abgelegt|gelöscht|entfernt|"
    r"verschoben|umbenannt|kopiert|geöffnet|gestartet|ausgeführt|installiert|"
    r"eingerichtet|geändert|aktualisiert|hinzugefügt|heruntergeladen|gesendet|"
    r"verschickt|beendet|geschlossen|erledigt|abgeschlossen|durchgeführt|"
    r"gelesen|geprüft|überprüft|abgerufen|ausgelesen|aufgerufen|angezeigt"
)

#: Ein Satz behauptet Vollzug, wenn er eines dieser Muster trägt.
_CLAIM_PATTERNS = [
    # "habe die Datei erstellt", "ich habe ... geschrieben"
    re.compile(rf"\bhabe\b.*\b(?:{_DONE})\b", re.I | re.S),
    # "wurde erstellt", "ist gespeichert", "wurde auf dem Desktop erstellt".
    # Bis zu sechs Wörter dazwischen: die Ortsangabe steht im Deutschen fast
    # immer zwischen Hilfsverb und Partizip.
    re.compile(rf"\b(?:wurde|wurden|ist|sind|war|waren)\b(?:\s+[\wäöüßÄÖÜ.]+){{0,6}}\s+\b(?:{_DONE})\b", re.I),
    # "Datei erstellt." / "Test ausgeführt." — knappe Vollzugsmeldung
    re.compile(rf"^\s*\W*\b(?:{_DONE})\b\W*$", re.I),
    # "Erledigt.", "Fertig!", "Alles erledigt, ich habe ..."
    re.compile(r"\b(?:erledigt|fertig)\b", re.I),
    # "erfolgreich erstellt", "erfolgreich abgeschlossen"
    re.compile(rf"\berfolgreich\b.*\b(?:{_DONE})\b", re.I),
    # "Die Überprüfung ist erfolgreich abgeschlossen."
    re.compile(r"\berfolgreich\b\s+\babgeschlossen\b", re.I),
]

#: Formulierungen, die keinen Vollzug behaupten, sondern ihn anbieten oder planen.
_HYPOTHETICAL = re.compile(
    r"\b(?:soll ich|möchtest du|willst du|kann ich|könnte ich|würde ich|"
    r"ich werde|ich würde|damit ich|um zu|wenn du|falls du|sobald|"
    r"noch nicht|nicht ausgeführt|kein tool|kein werkzeug|fehlgeschlagen)\b",
    re.I,
)

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?", re.S)

REFUSAL = (
    "Das kann ich aktuell noch nicht ausführen, weil mir dafür kein Tool zur "
    "Verfügung steht."
)


@dataclass(frozen=True)
class Reply:
    """Was aus einem Zug herausgeht. Die Oberfläche rendert genau das."""

    text: str
    provenance: str
    results: list[ToolResult] = field(default_factory=list)
    #: Gesetzt, wenn der Wächter den Text des Modells verworfen hat.
    blocked: bool = False
    blocked_text: str = ""

    def as_event(self) -> dict:
        return {
            "text": self.text,
            "provenance": self.provenance,
            "evidence": [r.as_event() for r in self.results],
            "blocked": self.blocked,
        }


def claims_completion(text: str) -> bool:
    """Behauptet dieser Text, eine Aktion sei vollzogen?

    Satzweise, damit ein „soll ich …?“ im selben Absatz nicht die ganze Antwort
    entschuldigt und umgekehrt ein Vollzugssatz nicht durch einen Nebensatz
    getarnt wird.
    """
    for match in _SENTENCE.finditer(text or ""):
        sentence = match.group().strip()
        if not sentence or sentence.endswith("?"):
            continue
        if _HYPOTHETICAL.search(sentence):
            continue
        if any(p.search(sentence) for p in _CLAIM_PATTERNS):
            return True
    return False


def provenance_of(results: list[ToolResult]) -> str:
    """Die Herkunft folgt aus den Belegen, nie aus dem Text."""
    if not results:
        return TALK
    if all(r.ok for r in results):
        return TOOL
    return FAIL


def verify(text: str, results: list[ToolResult] | None = None) -> Reply:
    """Die einzige Stelle, an der eine Antwort an den Nutzer entsteht."""
    results = list(results or [])
    provenance = provenance_of(results)
    text = (text or "").strip()

    if provenance == TOOL:
        # Ein Beleg liegt vor. Der Text darf melden, was geschehen ist.
        return Reply(text=text or results[-1].summary, provenance=TOOL, results=results)

    if provenance == FAIL:
        # Mindestens ein Werkzeug ist gescheitert. Der echte Fehler gewinnt
        # gegen jede beschönigende Formulierung des Modells.
        failed = [r for r in results if not r.ok]
        detail = "; ".join(f"{r.tool}: {r.summary}" for r in failed)
        honest = f"Die Aktion ist fehlgeschlagen: {detail}"
        if claims_completion(text):
            return Reply(text=honest, provenance=FAIL, results=results,
                         blocked=True, blocked_text=text)
        return Reply(text=text or honest, provenance=FAIL, results=results)

    # Kein Werkzeug lief. Jetzt darf nichts behauptet werden.
    if claims_completion(text):
        return Reply(text=REFUSAL, provenance=FAIL, results=results,
                     blocked=True, blocked_text=text)
    return Reply(text=text, provenance=TALK, results=results)
