"""Das Datei-Pack: jedes Werkzeug einmal wirklich ausgeführt.

Kein Mock, kein Stub -- ein echter Ordner im ``tmp_path`` der Testsitzung,
echte Dateien, echte Archive. Die Aufgabenstellung verlangt ausdrücklich
keine Attrappen (Punkt 40); der einzige Weg, das zu belegen, ist, jedes
Werkzeug laufen zu lassen und sein Ergebnis zu prüfen.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


@pytest.fixture
def baum(workspace):
    """Ein kleiner, vorhersagbarer Dateibaum für alle Tests hier."""
    (workspace / "notizen.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (workspace / "kopie.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (workspace / "anders.txt").write_text("alpha\nDELTA\ngamma\n", encoding="utf-8")
    (workspace / "leer.txt").write_text("", encoding="utf-8")
    (workspace / "daten.json").write_text(
        json.dumps({"server": {"port": 8770, "host": "127.0.0.1"}}), encoding="utf-8")
    (workspace / "tabelle.csv").write_text(
        "name;menge\nSchraube;12\nMutter;30\n", encoding="utf-8")
    unter = workspace / "unter"
    unter.mkdir()
    (unter / "tief.py").write_text("def f():\n    return 42  # TODO\n", encoding="utf-8")
    (unter / "gross.bin").write_bytes(b"\x00" * 50_000)
    (workspace / "leerer_ordner").mkdir()
    return workspace


@pytest.fixture
def tools(config, store, baum):
    registry = build_registry(config, store)

    # Positional-only (das '/'), damit ein Tool-Argument namens
    # 'name' nicht mit dem Parameter des Helfers kollidiert.
    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


# ═══════════════════════════════════════════════════════════════ Grundlagen
def test_copy_rename_exists_info(tools, baum):
    erfolg(tools("files.copy", source="notizen.txt", destination="zweit.txt"))
    assert (baum / "zweit.txt").read_text(encoding="utf-8").startswith("alpha")

    erfolg(tools("files.rename", path="zweit.txt", new_name="dritt.txt"))
    assert (baum / "dritt.txt").exists() and not (baum / "zweit.txt").exists()

    assert erfolg(tools("files.exists", path="dritt.txt")).evidence["existiert"] is True
    assert tools("files.exists", path="niewas.txt").evidence["existiert"] is False

    info = erfolg(tools("files.info", path="notizen.txt"))
    assert info.evidence["bytes"] == 17  # "alpha\nbeta\ngamma\n"
    assert info.evidence["art"] == "Datei"


def test_copy_ueberschreibt_nicht_ungefragt(tools):
    fehl = tools("files.copy", source="notizen.txt", destination="kopie.txt")
    assert fehl.ok is False and "overwrite" in fehl.summary
    erfolg(tools("files.copy", source="notizen.txt", destination="kopie.txt",
                 overwrite=True))


def test_rename_verweigert_einen_pfad_als_namen(tools):
    fehl = tools("files.rename", path="notizen.txt", new_name="unter/x.txt")
    assert fehl.ok is False and "files.move" in fehl.summary


def test_hash_und_vergleich(tools):
    a = erfolg(tools("files.hash", path="notizen.txt", algorithm="sha256"))
    assert len(a.payload) == 64

    gleich = erfolg(tools("files.hash.compare", path_a="notizen.txt", path_b="kopie.txt"))
    assert gleich.evidence["identisch"] is True
    verschieden = erfolg(tools("files.hash.compare", path_a="notizen.txt",
                               path_b="anders.txt"))
    assert verschieden.evidence["identisch"] is False

    assert tools("files.hash", path="notizen.txt", algorithm="rot13").ok is False


def test_touch_und_append(tools, baum):
    neu = erfolg(tools("files.touch", path="frisch.txt"))
    assert neu.evidence["neu"] is True and (baum / "frisch.txt").exists()
    assert erfolg(tools("files.touch", path="frisch.txt")).evidence["neu"] is False

    erfolg(tools("files.append_line", path="frisch.txt", line="erste"))
    erfolg(tools("files.append_line", path="frisch.txt", line="zweite"))
    assert (baum / "frisch.txt").read_text(encoding="utf-8") == "erste\nzweite\n"


def test_backup_und_temp(tools, baum):
    sicherung = erfolg(tools("files.backup", path="notizen.txt"))
    assert (baum / "notizen.txt.bak").exists()
    # Ein zweites Backup überschreibt das erste nicht.
    zweites = erfolg(tools("files.backup", path="notizen.txt"))
    assert zweites.evidence["nach"] != sicherung.evidence["nach"]

    temp = erfolg(tools("files.temp.create", suffix=".tmp", content="flüchtig"))
    assert temp.evidence["bytes"] == len("flüchtig".encode("utf-8"))


# ══════════════════════════════════════════════════════════════════ Inhalt
def test_head_tail_lines_count(tools):
    assert erfolg(tools("files.head", path="notizen.txt", lines=2)).payload == "alpha\nbeta"
    assert erfolg(tools("files.tail", path="notizen.txt", lines=2)).payload == "beta\ngamma"
    assert "2  beta" in erfolg(tools("files.lines", path="notizen.txt", start=2, end=2)).payload
    assert erfolg(tools("files.line_count", path="notizen.txt")).evidence["zeilen"] == 3


def test_lines_mit_vertauschten_grenzen_ist_ein_ehrlicher_fehler(tools):
    fehl = tools("files.lines", path="notizen.txt", start=5, end=2)
    assert fehl.ok is False and "liegt vor" in fehl.summary


def test_grep_findet_und_nennt_die_zeile(tools):
    treffer = erfolg(tools("files.grep", pattern="TODO", path="."))
    assert treffer.evidence["treffer"] == 1
    assert "tief.py" in treffer.payload and "2" in treffer.payload

    leer = erfolg(tools("files.grep", pattern="gibtesnicht", path="."))
    assert leer.evidence["treffer"] == 0

    assert tools("files.grep", pattern="[unfertig", path=".").ok is False


def test_replace_text_mit_und_ohne_probelauf(tools, baum):
    probe = erfolg(tools("files.replace_text", path="notizen.txt", search="beta",
                         replace="BETA", dry_run=True))
    assert probe.evidence == {"probelauf": True, "pfad": str(baum / "notizen.txt"),
                              "treffer": 1}
    assert "beta" in (baum / "notizen.txt").read_text(encoding="utf-8")

    echt = erfolg(tools("files.replace_text", path="notizen.txt", search="beta",
                        replace="BETA"))
    assert echt.evidence["treffer"] == 1
    assert "BETA" in (baum / "notizen.txt").read_text(encoding="utf-8")


def test_compare_zeigt_den_unterschied(tools):
    identisch = erfolg(tools("files.compare", path_a="notizen.txt", path_b="kopie.txt"))
    assert identisch.evidence["identisch"] is True

    diff = erfolg(tools("files.compare", path_a="notizen.txt", path_b="anders.txt"))
    assert diff.evidence["identisch"] is False
    assert "-beta" in diff.payload and "+DELTA" in diff.payload


def test_typ_und_kodierung(tools, baum):
    (baum / "bild.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    png = erfolg(tools("files.type.detect", path="bild.png"))
    assert png.evidence["magic"] == "image/png"

    text = erfolg(tools("files.type.detect", path="notizen.txt"))
    assert text.evidence["binaer"] is False

    kodierung = erfolg(tools("files.encoding.detect", path="notizen.txt"))
    assert kodierung.evidence["kodierung"] == "utf-8"


def test_zeitstempel_lesen_und_setzen(tools, baum):
    erfolg(tools("files.timestamps.read", path="notizen.txt"))
    erfolg(tools("files.timestamps.set", path="notizen.txt",
                 modified="2020-01-02 03:04:05"))
    gelesen = erfolg(tools("files.timestamps.read", path="notizen.txt"))
    assert gelesen.evidence["geaendert"].startswith("2020-01-02")

    assert tools("files.timestamps.set", path="notizen.txt", modified="gestern").ok is False


def test_rechte_lesen_und_setzen(tools, baum):
    vorher = erfolg(tools("files.permissions.read", path="notizen.txt"))
    assert vorher.evidence["lesbar"] is True

    geaendert = erfolg(tools("files.permissions.change", path="notizen.txt", mode="600"))
    assert geaendert.evidence["nachher"] == "0o600"
    assert tools("files.permissions.change", path="notizen.txt", mode="xyz").ok is False


def test_json_lesen_schreiben(tools, baum):
    ganz = erfolg(tools("files.json.read", path="daten.json"))
    assert "8770" in ganz.payload

    teil = erfolg(tools("files.json.read", path="daten.json", pointer="server.port"))
    assert teil.payload == "8770"

    assert tools("files.json.read", path="daten.json", pointer="server.gibtsnicht").ok is False
    assert tools("files.json.read", path="notizen.txt").ok is False

    erfolg(tools("files.json.write", path="neu.json", data='{"a":[1,2]}'))
    assert json.loads((baum / "neu.json").read_text(encoding="utf-8")) == {"a": [1, 2]}
    assert tools("files.json.write", path="kaputt.json", data="{nicht json").ok is False


def test_csv_vorschau_und_spalten(tools):
    vorschau = erfolg(tools("files.csv.preview", path="tabelle.csv"))
    assert vorschau.evidence["trenner"] == ";"
    assert "Schraube" in vorschau.payload

    spalten = erfolg(tools("files.csv.columns", path="tabelle.csv"))
    assert spalten.evidence["spalten"] == 2 and "menge" in spalten.payload


# ═══════════════════════════════════════════════════════════════════ Suche
def test_grosse_alte_neue_leere_dateien(tools, baum):
    gross = erfolg(tools("files.large.find", path=".", min_mb=0.01))
    assert "gross.bin" in gross.payload

    alt = erfolg(tools("files.old.find", path=".", days=1))
    assert alt.evidence["treffer"] == 0  # alles gerade erst angelegt

    neu = erfolg(tools("files.recent.find", path=".", hours=1))
    assert neu.evidence["treffer"] >= 5

    leer = erfolg(tools("files.empty.find", path="."))
    assert "leer.txt" in leer.payload


def test_duplikate_werden_ueber_den_inhalt_gefunden(tools):
    result = erfolg(tools("files.duplicate.find", path="."))
    assert result.evidence["gruppen"] == 1
    assert "notizen.txt" in result.payload and "kopie.txt" in result.payload
    assert result.evidence["verschwendet_bytes"] == 17


def test_zaehlung_nach_endung(tools):
    result = erfolg(tools("files.count.by_extension", path="."))
    assert ".txt" in result.payload and ".py" in result.payload


# ═══════════════════════════════════════════════════════════════════ Pfade
def test_pfadwerkzeuge(tools, baum):
    info = erfolg(tools("files.path.info", path="unter/tief.py"))
    assert info.evidence["endung"] == ".py" and info.evidence["stamm"] == "tief"

    relativ = erfolg(tools("files.path.relative", path="unter/tief.py", base="."))
    assert relativ.payload.replace("\\", "/") == "unter/tief.py"


def test_symlink_anlegen_und_lesen(tools, baum):
    erfolg(tools("files.symlink.create", path="verweis.txt", target="notizen.txt"))
    gelesen = erfolg(tools("files.symlink.read", path="verweis.txt"))
    assert gelesen.evidence["symlink"] is True
    assert gelesen.evidence["ziel_existiert"] is True

    assert erfolg(tools("files.symlink.read",
                        path="notizen.txt")).evidence["symlink"] is False
    assert tools("files.symlink.create", path="verweis.txt", target="kopie.txt").ok is False


# ══════════════════════════════════════════════════════════════════ Ordner
def test_ordner_anlegen_kopieren_verschieben_loeschen(tools, baum):
    erfolg(tools("dir.create", path="neu/tiefer"))
    assert (baum / "neu" / "tiefer").is_dir()

    erfolg(tools("dir.copy", source="unter", destination="unter_kopie"))
    assert (baum / "unter_kopie" / "tief.py").exists()

    erfolg(tools("dir.move", source="unter_kopie", destination="verschoben"))
    assert (baum / "verschoben").is_dir() and not (baum / "unter_kopie").exists()

    nicht_leer = tools("dir.delete", path="verschoben")
    assert nicht_leer.ok is False and "nicht leer" in nicht_leer.summary
    erfolg(tools("dir.delete", path="verschoben", recursive=True))
    assert not (baum / "verschoben").exists()


def test_dir_copy_probelauf_kopiert_nichts(tools, baum):
    probe = erfolg(tools("dir.copy", source="unter", destination="probe_ziel",
                         dry_run=True))
    assert probe.evidence["probelauf"] is True
    assert probe.evidence["dateien"] == 2
    assert not (baum / "probe_ziel").exists()


def test_baum_groesse_und_aufschluesselung(tools):
    baum_result = erfolg(tools("dir.tree", path=".", depth=2))
    assert "unter" in baum_result.payload and "tief.py" in baum_result.payload

    groesse = erfolg(tools("dir.size", path="."))
    assert groesse.evidence["bytes"] > 50_000

    aufteilung = erfolg(tools("dir.usage.breakdown", path="."))
    assert "unter" in aufteilung.payload


def test_leere_ordner_und_ordnervergleich(tools, baum):
    leer = erfolg(tools("dir.empty.find", path="."))
    assert "leerer_ordner" in leer.payload

    (baum / "zwilling").mkdir()
    (baum / "zwilling" / "tief.py").write_text("anders\n", encoding="utf-8")
    vergleich = erfolg(tools("dir.compare", path_a="unter", path_b="zwilling"))
    assert vergleich.evidence["nur_a"] == 1        # gross.bin
    assert vergleich.evidence["verschieden"] == 1  # tief.py


def test_sync_ist_standardmaessig_nur_ein_probelauf(tools, baum):
    ziel = baum / "spiegel"
    probe = erfolg(tools("dir.sync", source="unter", destination="spiegel"))
    assert probe.evidence["probelauf"] is True
    assert probe.evidence["neu"] == 2
    assert not (ziel / "tief.py").exists(), "Der Probelauf hat trotzdem kopiert"

    echt = erfolg(tools("dir.sync", source="unter", destination="spiegel", dry_run=False))
    assert echt.evidence["neu"] == 2
    assert (ziel / "tief.py").exists()

    nochmal = erfolg(tools("dir.sync", source="unter", destination="spiegel",
                           dry_run=False))
    assert nochmal.evidence["neu"] == 0 and nochmal.evidence["geaendert"] == 0


def test_aufraeumen_zeigt_erst_was_passieren_wuerde(tools, baum):
    ordner = baum / "downloads"
    ordner.mkdir()
    for name in ("a.pdf", "b.pdf", "c.zip"):
        (ordner / name).write_text("x", encoding="utf-8")

    probe = erfolg(tools("files.organize.by_extension", path="downloads"))
    assert probe.evidence["probelauf"] is True and probe.evidence["dateien"] == 3
    assert (ordner / "a.pdf").exists(), "Der Probelauf hat trotzdem verschoben"

    echt = erfolg(tools("files.organize.by_extension", path="downloads", dry_run=False))
    assert echt.evidence["verschoben"] == 3
    assert (ordner / "pdf" / "a.pdf").exists() and (ordner / "zip" / "c.zip").exists()


# ═════════════════════════════════════════════════════════════════ Archive
def test_zip_packen_listen_entpacken(tools, baum):
    erfolg(tools("archive.zip.create", path="paket.zip", sources="notizen.txt,unter"))
    assert zipfile.is_zipfile(baum / "paket.zip")

    liste = erfolg(tools("archive.zip.list", path="paket.zip"))
    assert liste.evidence["eintraege"] == 3
    assert "notizen.txt" in liste.payload

    probe = erfolg(tools("archive.zip.extract", path="paket.zip", destination="raus",
                         dry_run=True))
    assert probe.evidence["probelauf"] is True
    assert not (baum / "raus").exists()

    erfolg(tools("archive.zip.extract", path="paket.zip", destination="raus"))
    assert (baum / "raus" / "notizen.txt").exists()


def test_zip_mit_ausbruchspfad_wird_verweigert(tools, baum):
    """Zip-Slip: ein Eintrag wie '../ausbruch.txt' darf nicht ausserhalb des
    Zielordners landen -- geprüft wird vor dem ersten Schreiben."""
    boese = baum / "boese.zip"
    with zipfile.ZipFile(boese, "w") as archiv:
        archiv.writestr("../ausbruch.txt", "sollte nie entstehen")

    result = tools("archive.zip.extract", path="boese.zip", destination="ziel")
    assert result.ok is False and "Ausbruchspfad" in result.summary
    assert not (baum.parent / "ausbruch.txt").exists()


def test_tar_packen_listen_entpacken(tools, baum):
    erfolg(tools("archive.tar.create", path="paket.tar.gz", sources="notizen.txt"))
    liste = erfolg(tools("archive.tar.list", path="paket.tar.gz"))
    assert liste.evidence["eintraege"] == 1

    erfolg(tools("archive.tar.extract", path="paket.tar.gz", destination="tarraus"))
    assert (baum / "tarraus" / "notizen.txt").exists()

    assert tools("archive.tar.create", path="x.tar", sources="notizen.txt",
                 compression="rar").ok is False


def test_archive_inspect_erkennt_das_format(tools, baum):
    erfolg(tools("archive.zip.create", path="a.zip", sources="notizen.txt"))
    erfolg(tools("archive.tar.create", path="b.tar.gz", sources="notizen.txt"))
    assert erfolg(tools("archive.inspect", path="a.zip")).tool == "archive.zip.list"
    assert erfolg(tools("archive.inspect", path="b.tar.gz")).tool == "archive.tar.list"
    assert tools("archive.inspect", path="notizen.txt").ok is False


def test_gzip_hin_und_zurueck(tools, baum):
    gepackt = erfolg(tools("archive.gzip.compress", path="unter/gross.bin"))
    assert gepackt.evidence["bytes_nachher"] < gepackt.evidence["bytes_vorher"]

    (baum / "unter" / "gross.bin").unlink()
    erfolg(tools("archive.gzip.decompress", path="unter/gross.bin.gz"))
    assert (baum / "unter" / "gross.bin").stat().st_size == 50_000

    assert tools("archive.gzip.decompress", path="notizen.txt").ok is False


# ═════════════════════════════════════════════ Die Arbeitsbereich-Grenze
def test_kein_werkzeug_kommt_aus_dem_arbeitsbereich_heraus(tools, baum):
    """Die Grenze aus ``tools/files.py`` gilt für alle neuen Werkzeuge, ohne
    dass eines davon sie selbst durchsetzen müsste."""
    draussen = str(baum.parent / "verboten.txt")
    for name, args in (("files.copy", {"source": "notizen.txt", "destination": draussen}),
                       ("files.info", {"path": draussen}),
                       ("files.hash", {"path": draussen}),
                       ("dir.create", {"path": draussen}),
                       ("files.json.write", {"path": draussen, "data": "{}"}),
                       ("archive.zip.create", {"path": draussen, "sources": "notizen.txt"})):
        result = tools(name, **args)
        assert result.ok is False, f"{name} hat den Arbeitsbereich verlassen"
        assert "außerhalb" in result.summary
    assert not (baum.parent / "verboten.txt").exists()
