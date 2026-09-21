"""complexity.is_simple: konservative Einteilung einfach/komplex.

Die Regel ist absichtlich streng zugunsten "komplex" -- ein falsch als
"einfach" eingestuftes Anliegen bekommt vom kleinen Modell kein
Werkzeugschema und kann daher nichts kaputt machen, aber eine falsche
Tatsachenbehauptung (Uhrzeit, Wetter, ...) würde niemand auffangen. Beide
Richtungen werden hier geprüft.
"""

from __future__ import annotations

import pytest

from jarvis.complexity import is_simple


@pytest.mark.parametrize("text", [
    "Wer war Albert Einstein?",
    "Was ist die Hauptstadt von Frankreich?",
    "Wie viel ist 12 mal 15?",
    "Erzähl mir einen Witz.",
    "Danke dir!",
    "Was bedeutet das Wort Serendipität?",
])
def test_einfache_fragen_gelten_als_einfach(text):
    assert is_simple(text) is True


@pytest.mark.parametrize("text", [
    "Erstelle eine Datei namens test.txt auf dem Desktop",
    "Lösche die Datei bericht.txt",
    "Schreib mir ein Python-Skript, das Primzahlen findet",
    "Starte den Server neu",
    "Committe die Änderungen und pushe sie",
    "Wie spät ist es gerade?",
    "Wie ist das Wetter heute?",
    "Wie viel Akku hat der Laptop noch?",
])
def test_aktionen_und_live_daten_gelten_als_komplex(text):
    assert is_simple(text) is False


def test_ram_cpu_disk_ueberlaesst_complexity_py_dem_router():
    """RAM/CPU/Disk/Sysinfo fängt schon router.route() ab (siehe dort) --
    solche Nachrichten erreichen is_simple() im echten Betrieb nie. Dieser
    Test hält das bewusst fest, statt die Schlüsselwörter hier zu duplizieren."""
    from jarvis.router import route
    action = route("Wie hoch ist die CPU-Auslastung?")
    assert action is not None and action.tool == "get_cpu_info"


def test_leerer_text_gilt_als_komplex():
    """Kein Text heißt: es gibt nichts einzustufen -- die sichere Antwort."""
    assert is_simple("") is False
    assert is_simple("   ") is False


def test_langer_text_gilt_als_komplex_auch_ohne_schluesselwort():
    """Ein langer Text ist meist ein mehrteiliger Auftrag, kein Austausch."""
    lang = " ".join(["irgendein"] * 30)
    assert is_simple(lang) is False
