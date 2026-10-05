"""Automatische Modellwahl: einfache Nachrichten beantwortet ein kleines, schnelles Modell,
alles was nach Aufgabe aussieht das große. Der Lernende schaltet nie von Hand um.

Zwei Sicherungen: (1) Regeln entscheiden vorab, (2) das kleine Modell darf selbst an das große
übergeben (ESCAPE als erste Ausgabe). Dazu der Sprach-Wächter gegen abgerutschte Antworten
(chinesische Zeichen). Spiegel in web/core.js – Parität wird in tests/test_parity.py geprüft.
"""

from __future__ import annotations

import re

ESCAPE = "[[WEITER]]"

LIGHT_BLOCK = (
    "\n\n# Schnell-Modus\n"
    "Du bist die schnelle Variante des Tutors. Beantworte nur Begrüßungen, Smalltalk, Organisatorisches "
    "und kurze Wissensfragen – kurz (1–3 Sätze), freundlich, auf Deutsch. Verlangt die Nachricht, eine "
    "Aufgabe zu lösen, zu rechnen, zu programmieren, einen Text zu schreiben, eine mehrschrittige "
    "Erklärung oder Hilfe bei einer Aufgabe, antworte AUSSCHLIESSLICH mit " + ESCAPE + " und sonst nichts.\n"
)

STRICT_LANG = (
    "\n\n# Sprache (wichtig)\n"
    "Antworte ausschließlich auf Deutsch mit lateinischen Buchstaben. Verwende niemals chinesische "
    "oder andere asiatische Zeichen und erkläre nie, dass du etwas nicht beantworten kannst.\n"
)

# Chinesisch/Japanisch/Koreanisch inkl. Satzzeichen und Vollbreiten-Formen
CJK = re.compile("[　-ヿ㐀-䶿一-鿿가-힯＀-￯]")

MATH = re.compile(r"\d\s*[-+*/=^×÷]|[=^]|\b\d+[a-zA-Z]\b|[²³√∫∑]|\b[a-z]\s*\(\s*[a-z0-9]\s*\)", re.I)
CODE = re.compile(r"```|\bdef \w|\bfunction\b|\bclass \w|#include|\bprint\(|=>|[{};]\s*$|\bimport \w", re.I | re.M)
TASK_WORDS = re.compile(
    r"\b(löse\w*|löst|berechne\w*|rechne\w*|beweis\w*|beweise|herleit\w*|ableit\w*|integrier\w*|vereinfach\w*|"
    r"umform\w*|übersetz\w*|programmier\w*|debug\w*|bug|fehler|aufgabe\w*|übung\w*|hausaufgabe\w*|lösung\w*|"
    r"ergebnis\w*|schritt\w*|analysier\w*|interpretier\w*|erörter\w*|gleichung\w*|formel\w*|funktion\w*|"
    r"aufsatz|essay|zusammenfassung|schreib\w*\s+(mir\s+)?(einen|ein|eine)|warum|wieso|weshalb|erklär\w*|"
    r"verstehe?\s+nicht|hilf\w*|hilfe)\b", re.I)
GREETING = re.compile(
    r"^\s*(hi+|hallo+|hey+|moin|servus|huhu|yo|guten\s+(morgen|tag|abend)|danke\w*|thx|thanks|ok(ay)?|okey|"
    r"ja|nein|jo|nö|cool|super|nice|top|alles\s+klar|passt|tschüss|tschau|bye|bis\s+(bald|später)|"
    r"wie\s+geht'?s)\b[\s!.?,:)]*", re.I)
ORGANIZE = re.compile(
    r"\b(plan\w*|termin\w*|frist\w*|erinner\w*|zeitplan|stundenplan|pause\w*|pomodoro|fokus\w*|lernplan|"
    r"wecker|motivier\w*|motivation|prüfungsphase)\b", re.I)
SOCIAL = re.compile(r"^\s*(hi+|hallo+|hey+|moin|servus|huhu|guten\s+(morgen|tag|abend)|danke\w*|thx|thanks|tschüss|tschau|bye|bis\s+(bald|später))\b", re.I)
SHORT_FACT = re.compile(r"^\s*(was|wer|wo|wann|wofür|wozu|welche[rsnm]?|wie\s+heißt)\b", re.I)


def classify(text: str, ctx: dict | None = None) -> tuple[str, str]:
    """Liefert ("light" | "main", Grund). ctx: attempts, given_up, has_page, has_image, last_tier."""
    ctx = ctx or {}
    t = text.strip()
    n = len(t)
    greeting = bool(GREETING.match(t)) and n <= 50 and not TASK_WORDS.search(t) and not MATH.search(t)

    if ctx.get("given_up"):
        return "main", "Lösung erklären"
    if ctx.get("has_image"):
        return "main", "Bild"
    if MATH.search(t) or CODE.search(t) or TASK_WORDS.search(t):
        return "main", "Aufgabe"
    if n > 160:
        return "main", "lange Nachricht"
    social = greeting and bool(SOCIAL.match(t))       # „ok“/„ja“ sind mitten in einer Aufgabe Antworten
    if ctx.get("attempts", 0) >= 1 and ctx.get("last_tier") == "main" and not social:
        return "main", "laufende Aufgabe"
    if ctx.get("has_page") and not social:
        return "main", "Seite geladen"
    if greeting:
        return "light", "Smalltalk"
    if ORGANIZE.search(t):
        return "light", "Organisation"
    if SHORT_FACT.match(t) and n <= 90:
        return "light", "kurze Frage"
    if n <= 25 and ctx.get("attempts", 0) == 0:
        return "light", "kurz"
    return "main", "Standard"


def has_cjk(text: str) -> bool:
    return bool(CJK.search(text))


def strip_cjk(text: str) -> str:
    return CJK.sub("", text)
