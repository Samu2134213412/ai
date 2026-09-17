"""Autonomy Levels: wie viel Eigeninitiative Jarvis nehmen darf.

Bewusst getrennt vom Permission-System (``permissions.py``): die Autonomiestufe
entscheidet, **ob** Jarvis überhaupt von sich aus handeln oder ein Ziel
eigenständig verfolgen darf. Das Permission-System entscheidet **für jeden
einzelnen Werkzeugaufruf**, ob er ohne Rückfrage laufen darf. Beide zusammen,
nie eine anstelle der anderen — eine hohe Autonomiestufe hebt keine
Bestätigungspflicht auf, sie erlaubt nur, dass Jarvis mehrere Schritte
selbstständig hintereinander plant, statt bei jedem Schritt zu fragen, ob er
weitermachen soll.

    LEVEL 0  Nur reden. Keine Aktionen.
    LEVEL 1  Nur ungefährliche Read-Only-Aktionen automatisch.
    LEVEL 2  Ungefährliche lokale Aktionen selbstständig, riskante fragen nach.
    LEVEL 3  Jarvis darf ein ganzes, vom Nutzer gegebenes Ziel eigenständig verfolgen.
    LEVEL 4  Jarvis darf auf erkannte Ereignisse von sich aus reagieren.

Stufe 2 ist die Voreinstellung — "ein sinnvoller mittlerer Level", wie
gefordert: Werkzeuge laufen nach den ganz normalen Regeln aus
``permissions.py``, aber Jarvis darf noch kein Ziel ohne expliziten Auftrag
verfolgen (das braucht Stufe 3) und nicht von sich aus auf Ereignisse
reagieren (das braucht Stufe 4).
"""

from __future__ import annotations

from enum import IntEnum


class AutonomyLevel(IntEnum):
    NONE = 0
    READ_ONLY = 1
    LOCAL_ACTIONS = 2
    GOAL_PURSUIT = 3
    PROACTIVE = 4

    @property
    def label(self) -> str:
        return {
            AutonomyLevel.NONE: "Nur Gespräch",
            AutonomyLevel.READ_ONLY: "Nur lesende Aktionen",
            AutonomyLevel.LOCAL_ACTIONS: "Lokale Aktionen",
            AutonomyLevel.GOAL_PURSUIT: "Eigenständige Zielverfolgung",
            AutonomyLevel.PROACTIVE: "Proaktiv",
        }[self]

    @classmethod
    def from_value(cls, value: "int | AutonomyLevel") -> "AutonomyLevel":
        try:
            return cls(int(value))
        except ValueError:
            raise ValueError(f"Unbekannte Autonomiestufe: {value}") from None
