"""Der Wächter. Diese Datei ist die Zusage, die den Prompt ersetzt.

Die beiden ersten Tests bilden exakt nach, woran der Vorgänger scheiterte:
eine behauptete ``gaming.txt`` und ein behauptetes ``py_compile``.
"""

from __future__ import annotations

import pytest

from jarvis import guard
from jarvis.tools.base import ToolResult


def ok(tool="write_file", summary="Datei geschrieben: test.txt"):
    return ToolResult(tool=tool, ok=True, summary=summary,
                      evidence={"pfad": "/tmp/test.txt", "bytes": 5})


def bad(tool="write_file", summary="Schreiben fehlgeschlagen: Zugriff verweigert"):
    return ToolResult(tool=tool, ok=False, summary=summary)


# ----------------------------------------------------- die historischen Fälle
def test_behauptete_datei_ohne_werkzeug_wird_verworfen():
    """„Die Datei gaming.txt wurde auf dem Desktop erstellt." — ohne Tool."""
    reply = guard.verify("Die Datei gaming.txt wurde auf dem Desktop erstellt.", [])
    assert reply.blocked is True
    assert reply.text == guard.REFUSAL
    assert reply.provenance == guard.FAIL
    assert "gaming.txt" in reply.blocked_text


def test_behaupteter_befehl_ohne_werkzeug_wird_verworfen():
    """„Die Überprüfung des Moduls ist erfolgreich abgeschlossen." — ohne Tool."""
    reply = guard.verify("Die Überprüfung des Moduls ist erfolgreich abgeschlossen.", [])
    assert reply.blocked is True
    assert reply.text == guard.REFUSAL


# ------------------------------------------------------------ Herkunft
def test_herkunft_kommt_aus_belegen_nicht_aus_text():
    assert guard.verify("Plaudertext", []).provenance == guard.TALK
    assert guard.verify("egal", [ok()]).provenance == guard.TOOL
    assert guard.verify("egal", [ok(), bad()]).provenance == guard.FAIL


def test_mit_beleg_darf_erfolg_gemeldet_werden():
    reply = guard.verify("Die Datei test.txt liegt jetzt auf dem Desktop.", [ok()])
    assert reply.blocked is False
    assert reply.provenance == guard.TOOL
    assert "test.txt" in reply.text


def test_leerer_text_mit_beleg_faellt_auf_die_zusammenfassung_zurueck():
    reply = guard.verify("", [ok()])
    assert reply.text == "Datei geschrieben: test.txt"


# ------------------------------------------------------------ Fehlschlag
def test_beschoenigter_fehlschlag_wird_durch_den_echten_fehler_ersetzt():
    reply = guard.verify("Alles erledigt, die Datei ist gespeichert.", [bad()])
    assert reply.blocked is True
    assert reply.provenance == guard.FAIL
    assert "Zugriff verweigert" in reply.text
    assert "erledigt" not in reply.text


def test_ehrlicher_fehlertext_bleibt_stehen():
    text = "Das hat nicht geklappt, der Zugriff wurde verweigert."
    reply = guard.verify(text, [bad()])
    assert reply.blocked is False
    assert reply.text == text


# ------------------------------------------------- Erkennung von Behauptungen
@pytest.mark.parametrize("satz", [
    "Ich habe die Datei erstellt.",
    "Die Datei wurde erstellt.",
    "notizen.txt wurde gespeichert.",
    "Erledigt.",
    "Fertig!",
    "Das Programm ist gestartet.",
    "Ich habe den Ordner angelegt und die Datei hineingeschrieben.",
    "Die Änderungen sind gespeichert.",
    "Der Test wurde erfolgreich ausgeführt.",
    "Ich habe das für dich installiert.",
])
def test_vollzug_wird_erkannt(satz):
    assert guard.claims_completion(satz) is True


@pytest.mark.parametrize("satz", [
    "Soll ich die Datei erstellen?",
    "Möchtest du, dass ich das speichere?",
    "Ich werde die Datei gleich erstellen.",
    "Dafür bräuchte ich ein Werkzeug, das Dateien schreibt.",
    "Das kann ich aktuell noch nicht ausführen, weil mir dafür kein Tool zur Verfügung steht.",
    "Die Aktion ist fehlgeschlagen: Zugriff verweigert.",
    "Python ist eine Programmiersprache.",
    "Ich habe noch nicht gespeichert.",
    "Um die Datei zu erstellen, brauche ich einen Pfad.",
    "",
])
def test_kein_vollzug_kein_fehlalarm(satz):
    assert guard.claims_completion(satz) is False


def test_frage_im_selben_absatz_entschuldigt_die_behauptung_nicht():
    text = "Ich habe die Datei erstellt. Soll ich sie noch öffnen?"
    assert guard.claims_completion(text) is True
    assert guard.verify(text, []).blocked is True
