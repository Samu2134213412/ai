"""Grobe Einteilung: braucht diese Nachricht das große Modell, oder reicht
das kleine, schnelle für eine Antwort?

Nur relevant, wenn ein schnelles Modell konfiguriert ist (``config.fast_model``)
und der Router (``router.py``) schon durchgelassen hat -- ein eindeutiger
Befehl geht sowieso direkt ans Werkzeug, ganz ohne Modell. Was hier ankommt,
ist freier Text: eine Frage, ein Gespräch, oder eine Aufgabe, die der Router
nicht sicher erkannt hat.

Die Regel ist bewusst konservativ, spiegelbildlich zu router.py: **im Zweifel
das große Modell.** Der Grund ist kein Geschmacksurteil, sondern dieselbe
Lehre wie beim Router: eine als "einfach" eingestufte Aufgabe bekommt vom
kleinen Modell überhaupt kein Werkzeugschema (siehe agent.py, ``_try_fast``)
-- es kann sie also gar nicht ausführen, sondern höchstens fälschlich
behaupten, es getan zu haben. Genau das fängt ``guard.verify()`` ab, egal
welches Modell geantwortet hat. Für Tatsachenfragen zu etwas, das sich
laufend ändert (Uhrzeit, Wetter, Akkustand, Auslastung), greift dieses Netz
aber nicht -- eine falsche Antwort ist dort keine unbelegte Aktionsbehauptung,
sondern schlicht erfunden. Deshalb der eigene Ausschluss unten.
"""

from __future__ import annotations

import re

#: Wörter, die nahelegen, dass etwas in der realen Welt geschehen soll --
#: eine Datei, ein Prozess, eine Konfiguration, ein System, Code. Trifft
#: eines davon zu, ist es keine "einfache Frage" mehr, egal wie sie klingt.
_BRAUCHT_WERKZEUG = re.compile(
    r"\b(?:erstell\w*|erzeug\w*|anleg\w*|schreib\w*|speicher\w*|lösch\w*|"
    r"loesch\w*|entfern\w*|verschieb\w*|umbenenn\w*|kopier\w*|öffne\w*|"
    r"oeffne\w*|starte\w*|beende\w*|install\w*|deinstall\w*|ausführ\w*|"
    r"ausfuehr\w*|download\w*|herunterlad\w*|hochlad\w*|upload\w*|"
    r"such\w*\s+(?:im\s+)?(?:internet|web|netz)|google\w*|recherchier\w*|"
    r"code\w*|programmier\w*|skript\w*|script\w*|funktion\w*|python\w*|"
    r"javascript\w*|refactor\w*|debugg?\w*|reparier\w*|konfigurier\w*|"
    r"einricht\w*|einstell\w*|backup\w*|git\w*|commit\w*|push\w*|deploy\w*|"
    r"docker\w*|server\w*|datenbank\w*|sql\w*|minecraft\w*|ordner|"
    r"verzeichnis|prozess\w*|termin\w*|kalender\w*|erinnere\s+mich|"
    r"nachricht\w*|e-?mail\w*|mail\w*|whatsapp\w*|lautstärke|lautstaerke|"
    r"helligkeit|drucker|scann\w*)\b", re.I)

#: Fragen nach etwas, das sich jederzeit ändert. Ein Sprachmodell -- klein
#: wie groß -- kennt dafür keine echte Antwort, nur eine erfundene, wenn kein
#: Werkzeug läuft. Häufige Fälle davon fängt der Router schon ab
#: (RAM/CPU/Disk/Sysinfo/Prozesse); der Rest landet hier als Sicherheitsnetz.
_BRAUCHT_AKTUELLE_DATEN = re.compile(
    r"\b(?:wie\s+spät|wieviel\s+uhr|wie\s+viel\s+uhr|uhrzeit|welches\s+datum|"
    r"heutiges?\s+datum|wetter|akku\w*|batterie\w*|ip-?adresse|"
    r"öffentliche\s+ip|oeffentliche\s+ip)\b", re.I)

#: Grenze in Wörtern. Länger ist meist ein mehrteiliger Auftrag, kein kurzer
#: Austausch -- selbst wenn kein Schlüsselwort oben zutrifft.
_MAX_WOERTER = 25


def is_simple(text: str) -> bool:
    """Kann das kleine, schnelle Modell das übernehmen -- ganz ohne Werkzeuge?

    ``False`` ist die sichere Antwort und der Normalfall bei Zweifel.
    """
    text = (text or "").strip()
    if not text:
        return False
    if _BRAUCHT_WERKZEUG.search(text) or _BRAUCHT_AKTUELLE_DATEN.search(text):
        return False
    if len(text.split()) > _MAX_WOERTER:
        return False
    return True
