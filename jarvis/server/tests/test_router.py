"""Der Router. Zwei Pflichten: treffen, wenn es eindeutig ist — und sonst
die Finger weglassen, damit der Agent übernehmen kann."""

from __future__ import annotations

import pytest

from jarvis.router import route


def test_dateierstellung_mit_inhalt_und_ort():
    action = route("Erstelle eine Datei in /tmp/arbeit namens liste.txt "
                   "mit dem Inhalt Milch und Brot")
    assert action.tool == "write_file"
    assert action.arguments["path"] == "/tmp/arbeit/liste.txt"
    assert action.arguments["content"] == "Milch und Brot"


def test_dateiname_verschluckt_das_verb_nicht():
    """Regression: aus 'lies bericht.txt' wurde der Name 'lies bericht.txt'."""
    action = route("lies bericht.txt")
    assert action.tool == "read_file"
    assert action.arguments["path"] == "bericht.txt"


def test_desktop_wird_zum_pfad():
    action = route("Erstell mir notizen.txt auf dem Desktop")
    assert action.tool == "write_file"
    assert action.arguments["path"].lower().endswith("notizen.txt")
    assert "desktop" in action.arguments["path"].lower() or \
           "schreibtisch" in action.arguments["path"].lower()


def test_inhalt_in_anfuehrungszeichen():
    action = route('Schreibe "Hallo Welt" in gruss.txt')
    assert action.tool == "write_file"
    assert action.arguments["content"] == "Hallo Welt"


def test_loeschen_geht_dem_erstellen_vor():
    """'Lösche die erstellte test.txt' darf nicht zum Schreiben führen."""
    action = route("Lösche die erstellte test.txt")
    assert action.tool == "delete_file"


@pytest.mark.parametrize("satz,tool", [
    ("Wie viel RAM ist belegt?", "get_ram_info"),
    ("Zeig mir die CPU-Auslastung", "get_cpu_info"),
    ("Wie viel Speicherplatz ist noch auf der Festplatte?", "get_disk_info"),
    ("Gib mir mal die Systeminfos", "get_system_info"),
    ("Was läuft gerade?", "list_processes"),
])
def test_systemfragen(satz, tool):
    assert route(satz).tool == tool


def test_merken_erzeugt_eine_erinnerung():
    action = route("Merk dir: ich arbeite am liebsten mit VS Code")
    assert action.tool == "memory_add"
    assert "VS Code" in action.arguments["text"]


def test_abrufen_durchsucht_das_gedaechtnis():
    action = route("Was weißt du über meinen Rechner?")
    assert action.tool == "memory_search"
    assert "Rechner" in action.arguments["query"]


@pytest.mark.parametrize("satz", [
    "Wie geht es dir?",
    "Erklär mir, wie ein Dateisystem funktioniert",
    "Was hältst du von Python 3.12?",
    "Schreib mir ein Gedicht über den Herbst",
    "Bau mir einen Test für die Pfadprüfung und lass ihn laufen",
    "Ich habe gestern Version 3.2 installiert",
    "",
    "   ",
])
def test_uneindeutiges_geht_an_den_agenten(satz):
    """Im Zweifel nicht greifen: None heißt 'der Agent übernimmt'."""
    assert route(satz) is None


def test_versionsnummer_ist_kein_dateiname():
    """'Version 3.2' darf keinen Dateinamen ergeben — daher die Endungsliste."""
    assert route("Erstelle mir eine Notiz zu Version 3.2") is None
