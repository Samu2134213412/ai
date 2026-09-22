# Werkzeugreferenz

Automatisch erzeugt aus der Registry -- **398 Werkzeuge** in **24 Kategorien**. Nicht von Hand pflegen: `python -m jarvis --generate-docs` schreibt diese Datei neu, aus dem, was tatsächlich registriert ist.

## Kategorien

- [archive](#archive) (9)
- [audio](#audio) (12)
- [automation](#automation) (5)
- [clipboard](#clipboard) (4)
- [core](#core) (6)
- [db](#db) (10)
- [dev](#dev) (4)
- [dir](#dir) (10)
- [docker](#docker) (19)
- [files](#files) (45)
- [git](#git) (43)
- [image](#image) (23)
- [jarvis](#jarvis) (10)
- [minecraft](#minecraft) (19)
- [net](#net) (25)
- [nginx](#nginx) (8)
- [node](#node) (8)
- [npm](#npm) (1)
- [productivity](#productivity) (12)
- [python](#python) (10)
- [search](#search) (2)
- [system](#system) (44)
- [text](#text) (55)
- [video](#video) (14)

## archive

### `archive.gzip.compress`

Komprimiert eine einzelne Datei mit gzip.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, gzip
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |
| `level` | nein | 1–9, Vorgabe 6 |

### `archive.gzip.decompress`

Entpackt eine .gz-Datei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, gzip
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |

### `archive.inspect`

Erkennt das Archivformat und zeigt den Inhalt.

- **Stufe:** SAFE (LOW)
- **Tags:** archiv, pruefen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |

### `archive.tar.create`

Packt Dateien in ein tar-Archiv (gz, bz2, xz oder roh).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, tar, packen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |
| `sources` | ja |  |
| `compression` | nein | gz (Vorgabe), bz2, xz oder leer |

### `archive.tar.extract`

Entpackt ein tar-Archiv. Prüft auf Ausbruchspfade.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, tar, entpacken
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |
| `destination` | nein |  |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `archive.tar.list`

Listet den Inhalt eines tar-Archivs.

- **Stufe:** SAFE (LOW)
- **Tags:** archiv, tar
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |
| `limit` | nein |  |

### `archive.zip.create`

Packt Dateien oder Ordner in ein ZIP-Archiv.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, zip, packen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Das zu erzeugende Archiv |
| `sources` | ja | Pfade, durch Komma getrennt |
| `compress` | nein | Komprimieren (Vorgabe: ja) |

### `archive.zip.extract`

Entpackt ein ZIP-Archiv. Prüft auf Ausbruchspfade.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** archiv, zip, entpacken
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Das Archiv |
| `destination` | nein | Zielordner, leer = neben dem Archiv |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `archive.zip.list`

Listet den Inhalt eines ZIP-Archivs, ohne zu entpacken.

- **Stufe:** SAFE (LOW)
- **Tags:** archiv, zip
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |
| `limit` | nein |  |

## audio

### `audio.convert`

Wandelt eine Audiodatei in ein anderes Format um.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio, format
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.extract_from_video`

Extrahiert die Tonspur aus einer Videodatei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio, video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.fade`

Blendet eine Audiodatei ein und/oder aus.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `fade_in` | nein | Sekunden, 0 = kein Einblenden |
| `fade_out` | nein | Sekunden, 0 = kein Ausblenden |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.info`

Dauer, Codec, Samplerate und Kanäle einer Audiodatei.

- **Stufe:** READ (LOW)
- **Tags:** audio, info
- **Benötigt:** ffprobe
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFprobe (Teil von FFmpeg)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |

### `audio.merge`

Fügt mehrere Audiodateien nacheinander zusammen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `paths` | ja |  |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.normalize`

Gleicht die Lautheit auf einen Standardpegel an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.silence_detect`

Findet stille Abschnitte in einer Audiodatei.

- **Stufe:** READ (LOW)
- **Tags:** audio, analyse
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `noise_db` | nein | Schwelle in dB, Vorgabe -30 |
| `min_duration` | nein | Mindestdauer in Sekunden, Vorgabe 0.5 |

### `audio.speed`

Ändert die Wiedergabegeschwindigkeit ohne die Tonhöhe zu ändern (0.5-2.0).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `factor` | ja | 0.5-2.0 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.trim`

Schneidet einen Ausschnitt aus einer Audiodatei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `start` | ja | Start, z. B. 00:00:05 oder 5 |
| `duration` | nein | Dauer, leer = bis zum Ende |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.volume`

Ändert die Lautstärke (Faktor: 1.0 = unverändert, 2.0 = doppelt).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `factor` | ja | z. B. 1.5 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `audio.volume_detect`

Misst mittlere und maximale Lautstärke.

- **Stufe:** READ (LOW)
- **Tags:** audio, analyse
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |

### `audio.waveform.image`

Rendert die Wellenform als Bild.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** audio, bild
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `width` | nein | Breite in Pixeln, Vorgabe 800 |
| `height` | nein | Höhe in Pixeln, Vorgabe 200 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

## automation

### `automation.macro.create`

Speichert eine benannte Schrittfolge (Werkzeug-aufrufe mit optional IF/LOOP/PARALLEL/WAIT) unter einem Namen, zum späteren Ausführen ohne erneute Planung. Siehe macros.py für das Schrittformat.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** automation, makro
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Name des Makros |
| `steps` | ja | Liste von Makro-Schritten (kind: tool/if/loop/parallel/wait), siehe macros.py für das genaue Format. |
| `description` | nein | Kurzbeschreibung, optional |

### `automation.macro.delete`

Löscht ein gespeichertes Makro endgültig.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** automation, makro, loeschen
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Name des Makros |

### `automation.macro.get`

Zeigt die Schritte eines gespeicherten Makros.

- **Stufe:** READ (LOW)
- **Tags:** automation, makro
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Name des Makros |

### `automation.macro.list`

Listet gespeicherte Makros auf.

- **Stufe:** READ (LOW)
- **Tags:** automation, makro
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `automation.wait`

Wartet eine bestimmte Zeit, bevor der nächste Schritt läuft -- als Baustein in mehrstufigen Aufträgen.

- **Stufe:** SAFE (LOW)
- **Tags:** automation
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `seconds` | ja | Sekunden, max. 300 |

## clipboard

### `clipboard.clear`

Leert die Zwischenablage.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** zwischenablage
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `clipboard.has_content`

Prüft, ob die Zwischenablage Text enthält, ohne ihn im Verlauf anzuzeigen.

- **Stufe:** SAFE (LOW)
- **Tags:** zwischenablage
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `clipboard.read`

Liest den aktuellen Textinhalt der Zwischenablage.

- **Stufe:** READ (LOW)
- **Tags:** zwischenablage
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `clipboard.write`

Schreibt Text in die Zwischenablage.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** zwischenablage
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der zu kopierende Text |

## core

### `list_undoable`

Listet die letzten rückgängig machbaren Änderungen mit ihrer id.

- **Stufe:** SAFE (LOW)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `memory_add`

Legt eine neue Erinnerung an. Art: regel, projekt, hardware, vorliebe, skill, fakt, erfahrung.

- **Stufe:** WRITE (MEDIUM)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `label` | ja | Kurzer Titel |
| `text` | nein | Der Inhalt |
| `kind` | nein |  |

### `memory_forget`

Löscht eine Erinnerung endgültig.

- **Stufe:** CRITICAL (HIGH)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `id` | ja |  |

### `memory_link`

Verbindet zwei Erinnerungen miteinander.

- **Stufe:** WRITE (MEDIUM)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `a` | ja |  |
| `b` | ja |  |

### `memory_search`

Durchsucht das Langzeitgedächtnis nach Erinnerungen zu einem Thema.

- **Stufe:** SAFE (LOW)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `query` | ja |  |
| `limit` | nein |  |

### `undo_last_action`

Macht die letzte rückgängig machbare Änderung rückgängig, oder eine bestimmte über ihre id (siehe list_undoable).

- **Stufe:** WRITE (MEDIUM)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `record_id` | nein |  |

## db

### `db.sqlite.backup`

Kopiert die gesamte Datenbank in eine neue Datei (konsistent, auch während sie in Benutzung ist).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datenbank, sqlite, backup
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `output` | ja | Zielpfad |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `db.sqlite.create_table`

Legt eine neue Tabelle an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datenbank, sqlite
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |
| `columns` | ja | [{name, type, primary_key?, not_null?}, ...] |

### `db.sqlite.delete`

Löscht Zeilen aus einer Tabelle. Eine WHERE-Klausel ist Pflicht (Punkt 22) -- 'where="1=1"' für ausdrücklich alle Zeilen.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** datenbank, sqlite, loeschen
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |
| `where` | ja | WHERE-Bedingung ohne das Wort WHERE |
| `where_params` | nein | Werte für '?' in where |
| `dry_run` | nein | Nur zeigen, wie viele Zeilen betroffen wären |

### `db.sqlite.drop_table`

Löscht eine ganze Tabelle samt Inhalt, unwiderruflich.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** datenbank, sqlite, loeschen
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |
| `dry_run` | nein | Nur zeigen, wie viele Zeilen betroffen wären |

### `db.sqlite.info`

Größe, Tabellenzahl und Seiteninformationen der Datenbank.

- **Stufe:** READ (LOW)
- **Tags:** datenbank, sqlite
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |

### `db.sqlite.insert`

Fügt eine Zeile in eine Tabelle ein.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datenbank, sqlite
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |
| `values` | ja | {spalte: wert, ...} |

### `db.sqlite.query`

Führt eine einzelne SELECT-Abfrage aus (für Änderungen gibt es eigene Werkzeuge).

- **Stufe:** READ (LOW)
- **Tags:** datenbank, sqlite, sql
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `sql` | ja | SELECT-Anweisung, Platzhalter '?' |
| `params_list` | nein | Werte für die '?'-Platzhalter |
| `limit` | nein | Max. Zeilen, Vorgabe 200, Obergrenze 500 |

### `db.sqlite.schema`

Zeigt die CREATE-TABLE-Anweisung einer Tabelle.

- **Stufe:** READ (LOW)
- **Tags:** datenbank, sqlite
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |

### `db.sqlite.tables`

Listet Tabellen und Views einer SQLite-Datenbank.

- **Stufe:** READ (LOW)
- **Tags:** datenbank, sqlite
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |

### `db.sqlite.update`

Ändert Zeilen einer Tabelle. Eine WHERE-Klausel ist Pflicht (Punkt 22) -- 'where="1=1"' für ausdrücklich alle Zeilen.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** datenbank, sqlite
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich) |
| `table_name` | ja | Tabellenname |
| `set_values` | ja | {spalte: neuer_wert, ...} |
| `where` | ja | WHERE-Bedingung ohne das Wort WHERE, z. B. "id = ?" |
| `where_params` | nein | Werte für '?' in where |
| `dry_run` | nein | Nur zeigen, wie viele Zeilen betroffen wären |

## dev

### `dev.changelog.entry`

Ergänzt einen Eintrag in einer CHANGELOG-Datei (legt sie bei Bedarf an).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** entwicklung, dokumentation
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur CHANGELOG-Datei |
| `entry` | ja | Der neue Eintrag |
| `heading` | nein | Abschnittsüberschrift, Vorgabe: heutiges Datum |

### `dev.env.list`

Umgebungsvariablen des Jarvis-Prozesses -- Geheimnisse (Token, Passwörter, Schlüssel) werden geschwärzt.

- **Stufe:** READ (LOW)
- **Tags:** entwicklung, umgebung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `filter` | nein | Nur Namen, die diesen Text enthalten |

### `dev.project.detect`

Erkennt anhand bekannter Dateien, was für ein Projekt in einem Ordner liegt.

- **Stufe:** SAFE (LOW)
- **Tags:** entwicklung, projekt
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |

### `dev.stats`

Zählt Dateien und Zeilen je Dateityp in einem Ordner.

- **Stufe:** READ (LOW)
- **Tags:** entwicklung, statistik
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |
| `max_files` | nein |  |

## dir

### `dir.compare`

Vergleicht zwei Ordner: nur links, nur rechts, verschieden.

- **Stufe:** SAFE (LOW)
- **Tags:** ordner, vergleich
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path_a` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `path_b` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `dir.copy`

Kopiert einen Ordner samt Inhalt.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** ordner, kopieren
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `source` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `destination` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `dir.create`

Legt einen Ordner an, samt fehlender Elternordner.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** ordner, anlegen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `dir.delete`

Löscht einen Ordner. Nicht-leere nur mit recursive=true.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** ordner, loeschen
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `recursive` | nein | Auch mit Inhalt löschen |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `dir.empty.find`

Findet leere Ordner.

- **Stufe:** SAFE (LOW)
- **Tags:** ordner, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `limit` | nein |  |

### `dir.move`

Verschiebt oder benennt einen Ordner um.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** ordner, verschieben
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `source` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `destination` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `dir.size`

Gesamtgröße eines Ordners samt Unterordnern.

- **Stufe:** SAFE (LOW)
- **Tags:** ordner, groesse
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |

### `dir.sync`

Gleicht einen Ordner auf einen anderen ab. Standardmäßig nur als Probelauf.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** ordner, sync, sicherung
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `source` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `destination` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `delete` | nein | Im Ziel überzählige Dateien entfernen |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `dir.tree`

Zeigt den Ordnerbaum bis zu einer bestimmten Tiefe.

- **Stufe:** SAFE (LOW)
- **Tags:** ordner, uebersicht
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `depth` | nein | Tiefe, Vorgabe 2 |
| `limit` | nein |  |

### `dir.usage.breakdown`

Zeigt, welcher Unterordner wie viel Platz belegt.

- **Stufe:** SAFE (LOW)
- **Tags:** ordner, groesse, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `limit` | nein |  |

## docker

### `docker.build`

Baut ein Image aus einem Dockerfile.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker, image
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Ordner mit dem Dockerfile |
| `tag` | ja | Image-Name:Tag |
| `dockerfile` | nein | Dateiname, Vorgabe Dockerfile |

### `docker.compose.down`

Stoppt und entfernt alle Dienste eines Compose-Projekts.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker, compose
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Ordner mit docker-compose.yml |

### `docker.compose.ps`

Status der Dienste eines Compose-Projekts.

- **Stufe:** READ (LOW)
- **Tags:** docker, compose
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Ordner mit docker-compose.yml |

### `docker.compose.up`

Startet alle Dienste eines Compose-Projekts.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker, compose
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Ordner mit docker-compose.yml |
| `timeout` | nein | Sekunden, Vorgabe 120 |

### `docker.exec`

Führt einen Befehl in einem laufenden Container aus.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |
| `command` | ja | Programm mit Argumenten |

### `docker.images`

Lokal vorhandene Images.

- **Stufe:** READ (LOW)
- **Tags:** docker, image
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein | Vorgabe 50 |

### `docker.inspect`

Alle Details zu einem Container oder Image als JSON.

- **Stufe:** READ (LOW)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |

### `docker.logs`

Die letzten Log-Zeilen eines Containers.

- **Stufe:** READ (LOW)
- **Tags:** docker, log
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |
| `lines` | nein | Vorgabe 100 |

### `docker.networks.list`

Vorhandene Docker-Netzwerke.

- **Stufe:** READ (LOW)
- **Tags:** docker, netzwerk
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `docker.prune`

Entfernt gestoppte Container, ungenutzte Netzwerke/Images/Build-Cache.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** docker, loeschen
- **Benötigt:** docker
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `dry_run` | nein | Nur zeigen, was betroffen wäre |

### `docker.ps`

Laufende (oder alle) Container.

- **Stufe:** READ (LOW)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `all` | nein | Auch gestoppte Container zeigen |
| `limit` | nein | Vorgabe 50 |

### `docker.remove`

Entfernt einen Container endgültig.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** docker, loeschen
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |
| `force` | nein | Auch einen laufenden Container entfernen |

### `docker.restart`

Startet einen Container neu.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |

### `docker.run`

Startet einen neuen Container aus einem Image.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `image` | ja | Image-Name, z. B. nginx:latest |
| `name` | nein | Container-Name, optional |
| `ports` | nein |  |
| `volumes` | nein |  |
| `env` | nein | {VARIABLE: wert, ...} |
| `command` | nein | Befehl im Container, optional |
| `detach` | nein | Im Hintergrund laufen lassen, Vorgabe true |

### `docker.start`

Startet einen gestoppten Container.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |

### `docker.stats`

Aktuelle CPU-/Speicher-/Netzwerknutzung laufender Container.

- **Stufe:** READ (LOW)
- **Tags:** docker, performance
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein | Vorgabe 20 |

### `docker.stop`

Stoppt einen laufenden Container.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** docker
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Container-Name oder -ID |
| `timeout_sekunden` | nein | Vorgabe 10 |

### `docker.volume.remove`

Löscht ein Volume samt seiner Daten.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** docker, volume, loeschen
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Volume-Name |

### `docker.volumes.list`

Vorhandene Docker-Volumes.

- **Stufe:** READ (LOW)
- **Tags:** docker, volume
- **Benötigt:** docker
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

## files

### `delete_file`

Löscht eine einzelne Datei. Keine Verzeichnisse.

- **Stufe:** CRITICAL (HIGH)
- **Aliase:** `files.delete`
- **Tags:** datei, loeschen
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |

### `files.append_line`

Hängt eine Zeile an eine Textdatei an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, schreiben
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `line` | ja | Die anzuhängende Zeile |

### `files.backup`

Legt eine Sicherungskopie neben der Datei an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, sicherung
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `suffix` | nein | Endung, Vorgabe '.bak' |

### `files.compare`

Zeigt die Unterschiede zwischen zwei Textdateien.

- **Stufe:** SAFE (LOW)
- **Tags:** vergleich, diff
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path_a` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `path_b` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `context` | nein |  |

### `files.copy`

Kopiert eine Datei an einen anderen Ort.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, kopieren
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `source` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `destination` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `overwrite` | nein | Vorhandenes Ziel überschreiben |

Beispiel:
```json
{
  "source": "notizen.txt",
  "destination": "sicherung/"
}
```

### `files.count.by_extension`

Zählt Dateien und Platz je Dateiendung.

- **Stufe:** SAFE (LOW)
- **Tags:** statistik, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `limit` | nein |  |

### `files.csv.columns`

Listet die Spaltennamen einer CSV-Datei.

- **Stufe:** SAFE (LOW)
- **Tags:** csv, tabelle
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `delimiter` | nein |  |

### `files.csv.preview`

Zeigt die ersten Zeilen einer CSV-Datei als Tabelle.

- **Stufe:** SAFE (LOW)
- **Tags:** csv, tabelle
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `rows` | nein |  |
| `delimiter` | nein | Trennzeichen, sonst geraten |

### `files.duplicate.find`

Findet inhaltsgleiche Dateien über Größe und Prüfsumme.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, duplikate, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `limit` | nein |  |

### `files.empty.find`

Findet leere Dateien.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `limit` | nein |  |

### `files.encoding.detect`

Findet heraus, in welcher Zeichenkodierung eine Datei lesbar ist.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, kodierung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.exists`

Prüft, ob ein Pfad existiert, und was dort liegt.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, pruefen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.grep`

Sucht ein Textmuster in Dateien und zeigt die Fundstellen.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, text, grep
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pattern` | ja | Regulärer Ausdruck oder Text |
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `glob` | nein | Dateimuster, z. B. '*.py' |
| `ignore_case` | nein | Groß/Klein ignorieren (Vorgabe: ja) |
| `limit` | nein |  |

### `files.hash`

Prüfsumme einer Datei (md5, sha1, sha256, sha512).

- **Stufe:** SAFE (LOW)
- **Tags:** datei, hash, pruefsumme
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `algorithm` | nein | md5, sha1, sha256 (Vorgabe) oder sha512 |

### `files.hash.compare`

Vergleicht zwei Dateien über ihre Prüfsumme.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, hash, vergleich
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path_a` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `path_b` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `algorithm` | nein |  |

### `files.head`

Die ersten N Zeilen einer Datei.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, lesen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `lines` | nein | Anzahl Zeilen, Vorgabe 20 |

### `files.info`

Alle Eckdaten einer Datei: Größe, Typ, Zeiten, Rechte.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, metadaten
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.json.read`

Liest eine JSON-Datei, optional nur einen Teilpfad daraus.

- **Stufe:** SAFE (LOW)
- **Tags:** json, datei, lesen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `pointer` | nein | Pfad im Dokument, z. B. 'server.port' |

### `files.json.write`

Schreibt formatiertes JSON in eine Datei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** json, datei, schreiben
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `data` | ja | Das JSON als Text |
| `indent` | nein |  |

### `files.large.find`

Findet die größten Dateien unter einem Ordner.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, groesse, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `min_mb` | nein | Mindestgröße in MB, Vorgabe 100 |
| `limit` | nein |  |

### `files.line_count`

Zählt die Zeilen einer Datei.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, zaehlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.lines`

Einen Zeilenbereich einer Datei mit Zeilennummern.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, lesen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `start` | nein | Erste Zeile, Vorgabe 1 |
| `end` | nein | Letzte Zeile |

### `files.old.find`

Findet Dateien, die lange nicht angefasst wurden.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, alter, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `days` | nein | Alter in Tagen, Vorgabe 365 |
| `limit` | nein |  |

### `files.organize.by_extension`

Sortiert lose Dateien eines Ordners in Unterordner je Endung. Erst als Probelauf.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** ordner, aufraeumen
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `files.path.info`

Zerlegt einen Pfad in Ordner, Name, Stamm und Endung.

- **Stufe:** SAFE (LOW)
- **Tags:** pfad
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.path.relative`

Rechnet einen Pfad relativ zu einem anderen aus.

- **Stufe:** SAFE (LOW)
- **Tags:** pfad
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `base` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.permissions.change`

Ändert die Zugriffsrechte einer Datei (oktal, z. B. 644).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** datei, rechte
- **Plattformen:** linux, darwin
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `mode` | ja | Oktal, z. B. '644' oder '755' |

### `files.permissions.read`

Liest die Zugriffsrechte einer Datei.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, rechte
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.recent.find`

Findet zuletzt geänderte Dateien.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, zeit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad, relativ zum Arbeitsbereich oder absolut |
| `hours` | nein | Zeitraum in Stunden, Vorgabe 24 |
| `limit` | nein |  |

### `files.rename`

Benennt eine Datei oder einen Ordner um (gleicher Ordner).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, umbenennen
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `new_name` | ja | Neuer Dateiname ohne Pfad |

### `files.replace_text`

Ersetzt Text in einer Datei. Kann einen Probelauf.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, ersetzen
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `search` | ja | Gesuchter Text |
| `replace` | nein | Ersatztext |
| `regex` | nein | search als Regex lesen |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `files.size`

Größe einer einzelnen Datei in Bytes.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, groesse
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.symlink.create`

Legt einen symbolischen Link an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** symlink, pfad
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Der neue Link |
| `target` | ja | Das Ziel |

### `files.symlink.read`

Prüft, ob ein Pfad ein Symlink ist, und worauf er zeigt.

- **Stufe:** SAFE (LOW)
- **Tags:** symlink, pfad
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.tail`

Die letzten N Zeilen einer Datei — auch bei großen Logs.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, lesen, log
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `lines` | nein | Anzahl Zeilen, Vorgabe 20 |

### `files.temp.create`

Erzeugt eine temporäre Datei im Arbeitsbereich.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, temporaer
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `suffix` | nein | Endung, Vorgabe '.tmp' |
| `content` | nein | Inhalt |

### `files.timestamps.read`

Zeitstempel einer Datei: geändert, Zugriff, Status.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, zeit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.timestamps.set`

Setzt den Änderungszeitstempel einer Datei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, zeit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |
| `modified` | nein | 'JJJJ-MM-TT HH:MM:SS', leer = jetzt |

### `files.touch`

Legt eine leere Datei an oder frischt ihren Zeitstempel auf.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** datei, anlegen
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `files.type.detect`

Erkennt den Dateityp an den ersten Bytes, nicht nur an der Endung.

- **Stufe:** SAFE (LOW)
- **Tags:** datei, typ, mime
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad, relativ zum Arbeitsbereich oder absolut |

### `list_dir`

Listet den Inhalt eines Verzeichnisses auf.

- **Stufe:** SAFE (LOW)
- **Aliase:** `files.list`, `dir.list`
- **Tags:** ordner, lesen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein |  |

### `move_file`

Verschiebt oder benennt eine Datei um.

- **Stufe:** WRITE (MEDIUM)
- **Aliase:** `files.move`
- **Tags:** datei, verschieben
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `source` | ja |  |
| `destination` | ja |  |

### `read_file`

Liest eine Textdatei und gibt ihren Inhalt zurück.

- **Stufe:** SAFE (LOW)
- **Aliase:** `files.read`
- **Tags:** datei, lesen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja |  |

### `search_files`

Sucht Dateien nach Namensmuster, z. B. '*.py', rekursiv ab einem Ordner.

- **Stufe:** SAFE (LOW)
- **Aliase:** `files.search`
- **Tags:** suche, datei
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pattern` | ja |  |
| `path` | nein |  |
| `limit` | nein |  |

### `write_file`

Schreibt Text in eine Datei und gibt Pfad und Bytezahl zurück. Legt fehlende Ordner an. Für jede Art von Datei-Erstellung.

- **Stufe:** WRITE (MEDIUM)
- **Aliase:** `files.write`
- **Tags:** datei, schreiben
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad der Datei |
| `content` | nein | Der Inhalt |
| `append` | nein | Anhängen statt überschreiben |

## git

### `git.add`

Merkt Dateien für den nächsten Commit vor.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, commit
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `paths` | nein |  |
| `all` | nein | Alle Änderungen vormerken |

### `git.blame`

Wer hat welche Zeile einer Datei zuletzt geändert.

- **Stufe:** READ (LOW)
- **Tags:** git, blame
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `path` | ja | Pfad relativ zum Repository |
| `limit` | nein | Nur die ersten n Zeilen, 0 = alle |

### `git.branch.create`

Erstellt einen neuen Branch (ohne zu wechseln).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | Name des neuen Branches |
| `start_point` | nein | Ausgangspunkt, leer = aktueller HEAD |

### `git.branch.current`

Der aktuell ausgecheckte Branch.

- **Stufe:** READ (LOW)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.branch.delete`

Löscht einen Branch (nur wenn bereits gemergt -- git verweigert es sonst von selbst).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | Branch-Name |

### `git.branch.list`

Alle lokalen und entfernten Branches.

- **Stufe:** READ (LOW)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.checkout`

Wechselt zu einem Branch oder Commit.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | ja | Branch-Name oder Commit |

### `git.clean`

Löscht unversionierte Dateien endgültig von der Festplatte.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** git, loeschen
- **Benötigt:** git
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `include_ignored` | nein | Auch von .gitignore ausgeschlossene Dateien |
| `dry_run` | nein | Nur zeigen, was gelöscht würde |

### `git.clean.preview`

Zeigt, welche unversionierten Dateien 'git clean' entfernen würde -- löscht nichts.

- **Stufe:** READ (LOW)
- **Tags:** git, aufraeumen
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `include_ignored` | nein | Auch von .gitignore ausgeschlossene Dateien |

### `git.clone`

Klont ein Repository in den Arbeitsbereich.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo_url` | ja | Git-URL |
| `path` | ja | Zielordner im Arbeitsbereich |
| `timeout` | nein | Sekunden, Vorgabe 120 |

### `git.commit`

Erstellt einen Commit aus den vorgemerkten Änderungen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, commit
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `message` | ja | Commit-Nachricht |
| `add_all` | nein | Alle geänderten (bereits verfolgten) Dateien mit erfassen |

### `git.commit.amend`

Ändert den letzten Commit (Nachricht und/oder vorgemerkte Änderungen) -- schreibt Historie um.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, commit
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `message` | nein | Neue Nachricht, leer = behalten |

### `git.config.get`

Liest einen lokalen Git-Konfigurationswert dieses Repositories (nicht global).

- **Stufe:** READ (LOW)
- **Tags:** git, config
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `key` | ja | z. B. user.name |

### `git.config.set`

Setzt einen lokalen Git-Konfigurationswert dieses Repositories -- nie global oder systemweit.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, config
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `key` | ja | z. B. user.name |
| `value` | ja | Neuer Wert |

### `git.contributors`

Wer wie viel zu diesem Repository beigetragen hat.

- **Stufe:** READ (LOW)
- **Tags:** git, log
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `limit` | nein | Anzahl, Vorgabe 20 |

### `git.diff`

Unterschiede im Arbeitsverzeichnis (noch nicht vorgemerkt).

- **Stufe:** READ (LOW)
- **Tags:** git, diff
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `path` | nein | Nur diese Datei/diesen Ordner zeigen |

### `git.diff.commit`

Unterschied zwischen zwei Commits/Refs (oder einem Commit und dem Arbeitsverzeichnis).

- **Stufe:** READ (LOW)
- **Tags:** git, diff
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `a` | ja | Erster Ref/Commit |
| `b` | nein | Zweiter Ref/Commit, leer = Arbeitsverzeichnis |

### `git.diff.staged`

Unterschiede der vorgemerkten (staged) Änderungen.

- **Stufe:** READ (LOW)
- **Tags:** git, diff
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.fetch`

Holt neue Commits/Refs vom Remote, ohne den Arbeitsbereich zu verändern.

- **Stufe:** READ (LOW)
- **Tags:** git, remote
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `timeout` | nein | Sekunden, Vorgabe 120 |

### `git.ignore.add`

Fügt ein Muster zu .gitignore hinzu (legt die Datei an, falls nötig).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, gitignore
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `pattern` | ja | z. B. *.log oder node_modules/ |

### `git.init`

Legt ein neues, leeres Git-Repository an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Zielordner im Arbeitsbereich |

### `git.log`

Die letzten Commits.

- **Stufe:** READ (LOW)
- **Tags:** git, log
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `limit` | nein | Anzahl, Vorgabe 20 |

### `git.log.file`

Commit-Historie einer einzelnen Datei.

- **Stufe:** READ (LOW)
- **Tags:** git, log
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `path` | ja | Pfad relativ zum Repository |
| `limit` | nein | Anzahl, Vorgabe 20 |

### `git.pull`

Holt Commits vom Remote und führt sie in den aktuellen Branch zusammen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, remote
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `timeout` | nein | Sekunden, Vorgabe 120 |

### `git.push`

Sendet lokale Commits an ein Remote.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, remote
- **Benötigt:** git
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `remote` | nein | Remote-Name, leer = Vorgabe |
| `branch` | nein | Branch, leer = aktueller |
| `timeout` | nein | Sekunden, Vorgabe 120 |
| `dry_run` | nein | Nur zeigen, was gesendet würde |

### `git.rebase`

Setzt die Commits des aktuellen Branches auf einen anderen Stand um -- schreibt Historie um, kann Konflikte auslösen.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `upstream` | ja | Ziel-Branch/-Commit |

### `git.rebase.abort`

Bricht einen laufenden Rebase ab und stellt den vorherigen Zustand wieder her.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, branch
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.remote.add`

Trägt ein neues Remote ein.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, remote
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | z. B. origin |
| `url` | ja | Git-URL |

### `git.remote.list`

Eingetragene Remotes samt URL.

- **Stufe:** READ (LOW)
- **Tags:** git, remote
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.remote.remove`

Entfernt ein eingetragenes Remote.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, remote
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | Name des Remotes |

### `git.repo.info`

Branch, Remote, Sauberkeit und Vorsprung/Rückstand zum Upstream in einer Übersicht.

- **Stufe:** READ (LOW)
- **Tags:** git, status
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.reset.hard`

Verwirft alle Änderungen im Arbeitsverzeichnis und setzt den Branch auf einen Commit zurück -- unwiderruflich.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** git, loeschen
- **Benötigt:** git
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | nein | Ziel-Commit, Vorgabe HEAD |
| `dry_run` | nein | Nur zeigen, was verworfen würde |

### `git.revert`

Erstellt einen neuen Commit, der einen früheren Commit rückgängig macht -- ohne Historie umzuschreiben.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, commit
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | ja | Zu revertierender Commit |

### `git.show`

Details und Diff eines einzelnen Commits.

- **Stufe:** READ (LOW)
- **Tags:** git, log
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | nein | Commit/Ref, Vorgabe HEAD |

### `git.stash.drop`

Verwirft einen Stash endgültig.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** git, stash
- **Benötigt:** git
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | nein | z. B. stash@{0}, leer = neuester |
| `dry_run` | nein | Nur zeigen, was verworfen würde |

### `git.stash.list`

Zwischengelegte Änderungen (git stash).

- **Stufe:** READ (LOW)
- **Tags:** git, stash
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.stash.pop`

Holt den zuletzt (oder angegebenen) Stash zurück.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, stash
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `ref` | nein | z. B. stash@{0}, leer = neuester |

### `git.stash.save`

Legt unfertige Änderungen beiseite (git stash).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, stash
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `message` | nein | Beschreibung des Stashes |

### `git.status`

Status des Arbeitsverzeichnisses: Branch, vorgemerkte, geänderte und unversionierte Dateien.

- **Stufe:** READ (LOW)
- **Tags:** git, status
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.tag.create`

Setzt ein Tag auf einen Commit.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, tag
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | Tag-Name |
| `message` | nein | Nachricht -- setzt ein annotiertes Tag |
| `ref` | nein | Commit, leer = aktueller HEAD |

### `git.tag.delete`

Löscht ein Tag (nur lokal, nicht beim Remote).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, tag
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `name` | ja | Tag-Name |

### `git.tag.list`

Alle Tags mit ihrer Nachricht.

- **Stufe:** READ (LOW)
- **Tags:** git, tag
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |

### `git.unstage`

Nimmt Dateien aus der Vormerkung, ohne sie zu verändern.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** git, commit
- **Benötigt:** git
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `repo` | ja | Pfad des Git-Repositories (im Arbeitsbereich) |
| `paths` | nein |  |

## image

### `image.blur`

Weichzeichnen (Gauß-Filter).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `radius` | nein | Stärke, Vorgabe 2.0 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.border.add`

Fügt einen einfarbigen Rahmen hinzu.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `width` | nein | Rahmenbreite in Pixeln, Vorgabe 10 |
| `color` | nein | Farbe, Vorgabe black |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.brightness`

Ändert die Helligkeit (Faktor: 1.0 = unverändert).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `factor` | nein | z. B. 1.2 für heller, 0.8 für dunkler |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.compare`

Vergleicht zwei gleich große Bilder pixelweise.

- **Stufe:** SAFE (LOW)
- **Tags:** bild, vergleich
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path_a` | ja | Erstes Bild |
| `path_b` | ja | Zweites Bild |

### `image.compress`

Speichert ein Bild verlustbehaftet kleiner.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, komprimieren
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `quality` | nein | 1-95, Vorgabe 75 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.contrast`

Ändert den Kontrast (Faktor: 1.0 = unverändert).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `factor` | nein | z. B. 1.3 für mehr Kontrast |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.convert`

Wandelt ein Bild in ein anderes Format um (anhand der Zielendung).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, format
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.crop`

Schneidet einen rechteckigen Ausschnitt aus.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `left` | ja | Links |
| `top` | ja | Oben |
| `right` | ja | Rechts |
| `bottom` | ja | Unten |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.dominant_color`

Die auffälligste Farbe eines Bildes.

- **Stufe:** SAFE (LOW)
- **Tags:** bild, farbe
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |

### `image.exif.read`

Liest die EXIF-Metadaten eines Bildes (Kamera, Aufnahmedatum, ggf. GPS).

- **Stufe:** SAFE (LOW)
- **Tags:** bild, exif, metadaten
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |

### `image.exif.strip`

Entfernt alle Metadaten aus einem Bild (Datenschutz).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, exif, datenschutz
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.flip`

Spiegelt ein Bild horizontal oder vertikal.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `richtung` | nein | horizontal oder vertical |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.grayscale`

Wandelt ein Bild in Graustufen um.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.icon.create`

Erstellt eine .ico-Datei mit mehreren Auflösungen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, icon
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Quellbild (möglichst groß/quadratisch) |
| `output` | ja | Zielpfad, endet auf .ico |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.info`

Format, Größe und Farbmodus eines Bildes.

- **Stufe:** SAFE (LOW)
- **Tags:** bild, info
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |

### `image.merge`

Fügt mehrere Bilder nebeneinander oder übereinander zusammen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `paths` | ja |  |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `richtung` | nein | horizontal oder vertical |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.ocr`

Liest Text aus einem Bild (Tesseract OCR).

- **Stufe:** READ (LOW)
- **Tags:** bild, ocr, text
- **Benötigt:** tesseract
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: Tesseract OCR (https://github.com/tesseract-ocr/tesseract)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `lang` | nein | Sprachcode, Vorgabe eng |

### `image.pixelate`

Verpixelt ein Bild oder einen Ausschnitt daraus -- z. B. um ein Gesicht oder Kennzeichen unkenntlich zu machen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, datenschutz
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `block_size` | nein | Größe der Pixelblöcke, Vorgabe 12 |
| `box` | nein | [left, top, right, bottom], leer = ganzes Bild |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.resize`

Ändert die Bildgröße (eine Angabe genügt, das Seitenverhältnis bleibt erhalten).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `width` | nein | Zielbreite in Pixeln |
| `height` | nein | Zielhöhe in Pixeln |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.rotate`

Dreht ein Bild um einen beliebigen Winkel.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `degrees` | ja | Grad, im Uhrzeigersinn |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.sharpen`

Schärft ein Bild.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.thumbnail`

Erstellt eine verkleinerte Vorschau.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `max_size` | nein | Längste Seite in Pixeln, Vorgabe 256 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `image.watermark.text`

Fügt einen Textzusatz in eine Bildecke ein.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** bild, wasserzeichen
- **Benötigt:** pillow
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zum Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `text` | ja | Der Text |
| `position` | nein | unten-rechts/unten-links/oben-rechts/oben-links/mitte |
| `size` | nein | Schriftgröße, Vorgabe 24 |
| `color` | nein | Farbe, Vorgabe white |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

## jarvis

### `jarvis.tools.disable`

Schaltet ein Werkzeug ab (Punkt 26) -- keine Sicherheitsfunktion, sondern eine Vorliebe: das Werkzeug läuft danach nicht mehr, egal was das Permission-System dazu sagen würde.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Werkzeugname |
| `reason` | nein | Grund, optional |

### `jarvis.tools.enable`

Schaltet ein zuvor abgeschaltetes Werkzeug wieder an.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Werkzeugname |

### `jarvis.tools.favorite`

Markiert ein Werkzeug als Favorit -- taucht in der Suche danach bevorzugt auf.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Werkzeugname |

### `jarvis.tools.favorites`

Listet alle als Favorit markierten Werkzeuge.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `jarvis.tools.history`

Zeigt zuletzt aufgerufene Werkzeuge samt Ergebnis.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein | Maximal so viele Einträge, Vorgabe 30 |
| `tool` | nein | Nur dieses Werkzeug, optional |

### `jarvis.tools.info`

Zeigt alle Details zu einem Werkzeug: Parameter, Berechtigungsstufe, Verfügbarkeit, Beispiele.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Werkzeugname |

### `jarvis.tools.list`

Listet Werkzeuge, optional nach Kategorie/Tag gefiltert.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `category` | nein | Kategorie, optional |
| `tag` | nein | Tag, optional |

### `jarvis.tools.search`

Sucht im Werkzeugkasten nach passenden Werkzeugen (Name, Beschreibung, Tags, Beispielsätze). Nützlich, wenn kein passendes Werkzeug in der aktuellen Auswahl steht.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `query` | ja | Suchbegriff, z. B. 'gpu temperatur' |
| `limit` | nein | Maximal so viele Treffer, Vorgabe 10 |

### `jarvis.tools.stats`

Kennzahlen je Werkzeug: Aufrufe, Erfolgsquote, mittlere Dauer.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein | Maximal so viele Werkzeuge, Vorgabe 30 |

### `jarvis.tools.unfavorite`

Entfernt die Favoriten-Markierung.

- **Stufe:** SAFE (LOW)
- **Tags:** jarvis, werkzeuge
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Werkzeugname |

## minecraft

### `minecraft.backup.create`

Sichert den Weltordner als .tar.gz.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, backup
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `backup_dir` | nein | Zielordner, leer = <server>/backups |

### `minecraft.backup.list`

Vorhandene Weltsicherungen.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, backup
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `backup_dir` | nein | Backup-Ordner, leer = <server>/backups |

### `minecraft.broadcast`

Schickt eine Nachricht an alle Spieler.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, chat
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `message` | ja | Nachricht |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.command`

Sendet einen beliebigen Admin-Befehl über RCON -- verlangt deshalb immer eine ausdrückliche Bestätigung (Punkt 20: ein Text-Befehl lässt sich nicht sicher in harmlos/gefährlich einteilen).

- **Stufe:** CRITICAL (HIGH)
- **Tags:** minecraft, rcon
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `command` | ja | z. B. '/gamemode creative Name' |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.crash.analyze`

Sucht im letzten Crash-Report/Log nach bekannten Absturzursachen.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, log, diagnose
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |

### `minecraft.logs.tail`

Die letzten Zeilen des Server-Logs.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, log
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `lines` | nein | Anzahl, Vorgabe 40 |

### `minecraft.op.add`

Macht einen Spieler zum Operator (Admin-Rechte).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** minecraft, rechte
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.op.remove`

Entzieht einem Spieler die Operator-Rechte.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** minecraft, rechte
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.performance`

Server-Performance (TPS), sofern die Server-Software das unterstützt (Paper/Spigot; vanilla kennt den Befehl nicht).

- **Stufe:** READ (LOW)
- **Tags:** minecraft, performance
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.player.ban`

Bannt einen Spieler vom Server.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** minecraft, spieler
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `reason` | nein | Begründung |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.player.kick`

Wirft einen Spieler vom Server.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, spieler
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `reason` | nein | Begründung |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.players.list`

Wer gerade online ist.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, spieler
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.server.properties.read`

Alle Einstellungen aus server.properties.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, konfiguration
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |

### `minecraft.server.properties.set`

Ändert eine Einstellung in server.properties (wirkt erst nach einem Neustart).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, konfiguration
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `key` | ja | Schlüssel |
| `value` | ja | Neuer Wert |

### `minecraft.start`

Startet den Server-Prozess (java -jar ... nogui).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** minecraft
- **Benötigt:** java
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `jar` | nein | JAR-Datei, Vorgabe server.jar |
| `memory_mb` | nein | Arbeitsspeicher in MB, Vorgabe 2048 |

### `minecraft.status`

Ob der Server läuft (Prozess) und über RCON antwortet.

- **Stufe:** READ (LOW)
- **Tags:** minecraft, status
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |

### `minecraft.stop`

Beendet den Server geordnet über RCON (speichert die Welt).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** minecraft
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.whitelist.add`

Setzt einen Spieler auf die Whitelist.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, whitelist
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

### `minecraft.whitelist.remove`

Entfernt einen Spieler von der Whitelist.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** minecraft, whitelist
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `server_dir` | ja | Pfad zum Minecraft-Server-Ordner (im Arbeitsbereich) |
| `name` | ja | Minecraft-Name |
| `password` | nein | RCON-Passwort, leer = aus server.properties lesen |
| `port` | nein | RCON-Port, leer = aus server.properties lesen |

## net

### `net.arp.table`

Die Nachbarn im lokalen Netz (ARP).

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `net.connections`

Bestehende Netzwerkverbindungen.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |
| `state` | nein | z. B. ESTABLISHED |

### `net.dns.flush`

Leert den DNS-Zwischenspeicher des Systems.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** dns, reparatur
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.dns.lookup`

Löst einen Hostnamen zu IP-Adressen auf.

- **Stufe:** READ (LOW)
- **Tags:** dns, netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja | Der Hostname |
| `record` | nein | A (Vorgabe), AAAA, ANY, MX, TXT, NS … |

### `net.dns.reverse`

Findet den Hostnamen zu einer IP-Adresse.

- **Stufe:** READ (LOW)
- **Tags:** dns, netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `ip` | ja | Die IP-Adresse |

### `net.dns.servers`

Welche DNS-Server dieser Rechner benutzt.

- **Stufe:** READ (LOW)
- **Tags:** dns
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.gateway`

Das Standard-Gateway dieses Rechners.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.hostname`

Rechnername und vollständiger Domainname.

- **Stufe:** SAFE (LOW)
- **Tags:** netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.http.download`

Lädt eine Datei in den Arbeitsbereich.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** http, datei
- **Benötigt:** httpx
- **Rückgängig machbar:** ja (`undo_last_action`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ja |  |
| `path` | ja | Zielpfad im Arbeitsbereich |
| `timeout` | nein |  |

### `net.http.get`

Holt den Inhalt einer Adresse als Text.

- **Stufe:** READ (LOW)
- **Tags:** http
- **Benötigt:** httpx
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ja |  |
| `timeout` | nein |  |
| `max_chars` | nein |  |

### `net.http.headers`

Die HTTP-Kopfzeilen einer Adresse.

- **Stufe:** READ (LOW)
- **Tags:** http
- **Benötigt:** httpx
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ja |  |
| `timeout` | nein |  |

### `net.http.status`

Prüft, ob eine Adresse antwortet, und wie schnell.

- **Stufe:** READ (LOW)
- **Tags:** http, diagnose
- **Benötigt:** httpx
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ja | Die Adresse |
| `timeout` | nein |  |

### `net.interfaces`

Alle Netzwerkadapter mit Adresse und Zustand.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, hardware
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.latency.monitor`

Misst die Antwortzeit mehrfach und zeigt die Schwankung.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, diagnose
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja |  |
| `samples` | nein |  |
| `delay` | nein | Pause in Sekunden |

### `net.local.ip`

Die lokale IP-Adresse dieses Rechners.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.local.ports`

Welche Ports dieser Rechner geöffnet hat.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, port
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `net.ping`

Prüft mit ping, ob ein Host antwortet, und wie schnell.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, diagnose
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja |  |
| `count` | nein | Pakete, Vorgabe 4 |
| `timeout` | nein |  |

### `net.port.check`

Prüft, ob ein bestimmter Port erreichbar ist.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, port, diagnose
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja |  |
| `port` | ja | 1–65535 |
| `timeout` | nein | Sekunden, Vorgabe 3 |

### `net.public.ip`

Die öffentliche IP-Adresse (fragt einen Dienst).

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Benötigt:** httpx
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `timeout` | nein |  |

### `net.ssl.certificate`

Zeigt das TLS-Zertifikat eines Hosts samt Restlaufzeit.

- **Stufe:** READ (LOW)
- **Tags:** https, zertifikat
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja |  |
| `port` | nein |  |
| `timeout` | nein |  |

### `net.traceroute`

Zeigt den Weg der Pakete zu einem Host.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, diagnose
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `host` | ja |  |
| `max_hops` | nein |  |

### `net.traffic`

Gesendete und empfangene Bytes seit dem Systemstart.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `net.traffic.rate`

Misst die aktuelle Übertragungsrate.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `seconds` | nein | Messdauer, Vorgabe 2 |

### `net.url.parse`

Zerlegt eine URL in ihre Bestandteile.

- **Stufe:** SAFE (LOW)
- **Tags:** http, url
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ja |  |

### `net.wifi.networks`

Sichtbare WLAN-Netze mit Signalstärke.

- **Stufe:** READ (LOW)
- **Tags:** netzwerk, wlan
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

## nginx

### `nginx.access_log.tail`

Die letzten Zeilen des Zugriffs-Logs.

- **Stufe:** READ (LOW)
- **Tags:** nginx, log
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `lines` | nein | Vorgabe 50 |

### `nginx.config.test`

Prüft die nginx-Konfiguration auf Syntaxfehler, ohne etwas zu laden.

- **Stufe:** READ (LOW)
- **Tags:** nginx, konfiguration
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

### `nginx.error_log.tail`

Die letzten Zeilen des Fehler-Logs.

- **Stufe:** READ (LOW)
- **Tags:** nginx, log
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `lines` | nein | Vorgabe 50 |

### `nginx.reload`

Prüft die Konfiguration und lädt sie bei Erfolg neu -- ohne Verbindungsabbrüche.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** nginx, konfiguration
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

### `nginx.site.disable`

Deaktiviert eine Seite (entfernt den Symlink).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** nginx, seiten
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `site` | ja | Dateiname in sites-enabled |

### `nginx.site.enable`

Aktiviert eine Seite (Symlink nach sites-enabled).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** nginx, seiten
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `site` | ja | Dateiname in sites-available |

### `nginx.sites.list`

Verfügbare und aktive Seiten (sites-available/-enabled).

- **Stufe:** READ (LOW)
- **Tags:** nginx, seiten
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

### `nginx.version`

Installierte nginx-Version.

- **Stufe:** READ (LOW)
- **Tags:** nginx
- **Benötigt:** nginx
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: nginx (https://nginx.org)

## node

### `node.audit`

Bekannte Sicherheitslücken in den npm-Abhängigkeiten.

- **Stufe:** READ (LOW)
- **Tags:** node, sicherheit
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |

### `node.init`

Legt eine neue package.json an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** node
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |

### `node.install`

Installiert alle Abhängigkeiten aus package.json.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** node, pakete
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |
| `timeout` | nein | Sekunden, Vorgabe 300 |

### `node.package.add`

Fügt eine npm-Abhängigkeit hinzu.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** node, pakete
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |
| `package` | ja | Paketname, ggf. mit Version |
| `dev` | nein | Als devDependency eintragen |
| `timeout` | nein | Sekunden, Vorgabe 300 |

### `node.package.list`

Installierte npm-Pakete der obersten Ebene.

- **Stufe:** READ (LOW)
- **Tags:** node, pakete
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |

### `node.package.remove`

Entfernt eine npm-Abhängigkeit.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** node, pakete
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |
| `package` | ja | Paketname |

### `node.script.run`

Führt ein in package.json definiertes npm-Skript aus.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** node, skript
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Projektordner (im Arbeitsbereich) |
| `script` | ja | Skriptname aus package.json |
| `timeout` | nein | Sekunden, Vorgabe 300 |

### `node.version`

Installierte Node.js-Version.

- **Stufe:** READ (LOW)
- **Tags:** node
- **Benötigt:** node
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

## npm

### `npm.version`

Installierte npm-Version.

- **Stufe:** READ (LOW)
- **Tags:** node
- **Benötigt:** npm
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

## productivity

### `productivity.base.convert`

Wandelt eine Zahl zwischen Zahlensystemen um (Basis 2-36).

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, zahlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | Die Zahl als Text |
| `from_base` | ja | Ausgangsbasis, z. B. 10 |
| `to_base` | ja | Zielbasis, z. B. 16 |

### `productivity.calculate`

Wertet einen mathematischen Ausdruck aus (+ - * / // % **, Klammern, Konstanten pi/e) -- kein eval, kein Funktionsaufruf möglich.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, rechnen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `expression` | ja | z. B. '(3 + 4) * 2 / 7' |

### `productivity.color.convert`

Wandelt eine Farbe zwischen Hex/RGB/HSL um.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, farbe
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | z. B. #3366ff oder rgb(51,102,255) |

### `productivity.date.add`

Addiert Tage/Wochen zu einem Datum.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, datum
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `date` | ja | JJJJ-MM-TT |
| `days` | nein | Tage |
| `weeks` | nein | Wochen |

### `productivity.date.diff`

Anzahl Tage zwischen zwei Daten.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, datum
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `date_a` | ja | JJJJ-MM-TT |
| `date_b` | ja | JJJJ-MM-TT |

### `productivity.lorem.generate`

Erzeugt Platzhaltertext (Lorem Ipsum).

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, text
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `words` | nein | Anzahl Wörter, Vorgabe 50 |

### `productivity.number.to_words`

Schreibt eine Zahl auf Deutsch aus.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, zahlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | Die Zahl |

### `productivity.passphrase.generate`

Erzeugt eine leicht zu merkende Passphrase aus mehreren Wörtern (mit eingebauter Wortliste).

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, sicherheit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `words` | nein | Anzahl Wörter, Vorgabe 5 |
| `separator` | nein | Trennzeichen, Vorgabe '-' |
| `capitalize` | nein | Wörter großschreiben |

### `productivity.qrcode.generate`

Erstellt einen QR-Code als Bild.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** produktivitaet, qrcode
- **Benötigt:** qrcode
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Inhalt des QR-Codes |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `productivity.roman.convert`

Wandelt zwischen arabischen und römischen Zahlen um (in beide Richtungen erkannt).

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, zahlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | Zahl oder römische Zahl, z. B. 1994 oder MCMXCIV |

### `productivity.timezone.convert`

Rechnet eine Uhrzeit zwischen Zeitzonen um.

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, zeit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | ISO-Zeit ohne Zone, z. B. 2026-01-15T14:00:00 |
| `from_zone` | ja | z. B. Europe/Berlin |
| `to_zone` | ja | z. B. America/New_York |

### `productivity.unit.convert`

Rechnet zwischen Maßeinheiten um (Länge, Gewicht, Volumen, Temperatur).

- **Stufe:** SAFE (LOW)
- **Tags:** produktivitaet, einheiten
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | Ausgangswert |
| `from_unit` | ja | z. B. km, lb, c |
| `to_unit` | ja | z. B. mi, kg, f |

## python

### `python.format`

Formatiert Code mit ruff. Unterstützt einen echten Probelauf (zeigt das Diff, ändert nichts).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** python, format
- **Probelauf:** unterstützt (`dry_run: true`)
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Datei oder Ordner |
| `python` | nein | Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener |
| `dry_run` | nein | Nur zeigen, was passieren würde, ohne es zu tun |

### `python.lint`

Statische Codeprüfung mit ruff (falls installiert).

- **Stufe:** READ (LOW)
- **Tags:** python, lint, qualitaet
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Datei oder Ordner |
| `python` | nein | Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener |

### `python.package.install`

Installiert ein Paket mit pip.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** python, pakete
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `package` | ja | Paketname, ggf. mit Version |
| `python` | ja | Pfad zum Ziel-Interpreter (Pflicht, damit nicht aus Versehen Jarvis' eigene Umgebung verändert wird) |

### `python.package.uninstall`

Entfernt ein Paket mit pip.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** python, pakete
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `package` | ja | Paketname |
| `python` | ja | Pfad zum Ziel-Interpreter (Pflicht, damit nicht aus Versehen Jarvis' eigene Umgebung verändert wird) |

### `python.packages.list`

Installierte Pakete eines Interpreters (wie pip freeze).

- **Stufe:** READ (LOW)
- **Tags:** python, pakete
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `python` | nein | Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener |

### `python.requirements.freeze`

Schreibt die installierten Pakete eines Interpreters in eine requirements-Datei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** python, pakete
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Zieldatei, z. B. requirements.txt |
| `python` | ja | Pfad zum Ziel-Interpreter (Pflicht, damit nicht aus Versehen Jarvis' eigene Umgebung verändert wird) |

### `python.syntax_check`

Prüft eine Datei auf Syntaxfehler, ohne sie auszuführen.

- **Stufe:** SAFE (LOW)
- **Tags:** python, syntax
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Datei |

### `python.test`

Führt pytest aus.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** python, test
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Datei/Ordner/Modul, leer = Vorgabe von pytest |
| `python` | nein | Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener |
| `args` | nein | Zusätzliche pytest-Argumente ohne führendes '-' |

### `python.venv.create`

Legt eine virtuelle Umgebung an.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** python, venv
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Zielordner im Arbeitsbereich |
| `python` | nein | Basis-Interpreter, leer = Jarvis' eigener |

### `python.version`

Version des Python-Interpreters.

- **Stufe:** READ (LOW)
- **Tags:** python
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `python` | nein | Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener |

## search

### `search.apps`

Listet installierte Programme, optional gefiltert nach Name. Startet nichts -- nur zum Finden.

- **Stufe:** READ (LOW)
- **Tags:** suche, programme
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `query` | nein | Suchbegriff, leer = alle |
| `limit` | nein | Max. Treffer, Vorgabe 100 |

### `search.files`

Sucht Dateien anhand des Namens (nicht des Inhalts -- dafür gibt es files.grep). Unscharf: die Buchstaben des Suchbegriffs müssen nur in der richtigen Reihenfolge vorkommen.

- **Stufe:** SAFE (LOW)
- **Tags:** suche, dateien
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `query` | ja | Suchbegriff |
| `path` | nein | Ordner, leer = erste freigegebene Wurzel |
| `limit` | nein | Max. Treffer, Vorgabe 40 |

## system

### `system.battery`

Akkustand und ob das Gerät am Netz hängt.

- **Stufe:** READ (LOW)
- **Tags:** akku, hardware
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.boot_time`

Wann der Rechner gestartet wurde.

- **Stufe:** READ (LOW)
- **Tags:** system
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.cores`

Anzahl physischer und logischer CPU-Kerne.

- **Stufe:** READ (LOW)
- **Tags:** cpu
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.frequency`

Aktueller und maximaler CPU-Takt.

- **Stufe:** READ (LOW)
- **Tags:** cpu, takt
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.load`

Load Average der letzten 1, 5 und 15 Minuten.

- **Stufe:** READ (LOW)
- **Tags:** cpu, last
- **Plattformen:** linux, darwin
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.model`

Modellbezeichnung des Prozessors.

- **Stufe:** READ (LOW)
- **Tags:** cpu, hardware
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.times`

Wie sich die CPU-Zeit verteilt (user, system, idle).

- **Stufe:** READ (LOW)
- **Tags:** cpu
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.cpu.usage`

Aktuelle CPU-Auslastung in Prozent.

- **Stufe:** READ (LOW)
- **Aliase:** `get_cpu_info`
- **Tags:** cpu, auslastung
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `interval` | nein | Messdauer in Sekunden, Vorgabe 0.4 |
| `per_core` | nein | Je Kern statt gesamt |

### `system.disk.io`

Gelesene und geschriebene Bytes seit dem Systemstart.

- **Stufe:** READ (LOW)
- **Tags:** disk
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.disk.partitions`

Alle eingehängten Datenträger mit Belegung.

- **Stufe:** READ (LOW)
- **Tags:** disk, hardware
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.disk.smart`

SMART-Gesundheitswerte eines Datenträgers.

- **Stufe:** READ (LOW)
- **Tags:** disk, hardware, smart
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `device` | ja | z. B. /dev/sda oder \\.\PhysicalDrive0 |

### `system.disk.usage`

Freier und belegter Platz eines Laufwerks.

- **Stufe:** READ (LOW)
- **Aliase:** `get_disk_info`
- **Tags:** disk, speicherplatz
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | nein | Pfad oder Laufwerk, leer = Systemlaufwerk |

### `system.env.get`

Eine einzelne Umgebungsvariable.

- **Stufe:** READ (LOW)
- **Tags:** umgebung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |

### `system.env.list`

Die Umgebungsvariablen. Geheimnisverdächtige Werte werden verborgen.

- **Stufe:** READ (LOW)
- **Tags:** umgebung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `filter` | nein | Nur Namen, die das enthalten |
| `limit` | nein |  |

### `system.env.set`

Setzt eine Umgebungsvariable — nur für den laufenden Jarvis-Prozess.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** umgebung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |
| `value` | ja |  |

### `system.gpu.info`

GPU-Name, Temperatur, Auslastung und VRAM.

- **Stufe:** READ (LOW)
- **Tags:** gpu, hardware
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.gpu.temperature`

Temperatur der Grafikkarte.

- **Stufe:** READ (LOW)
- **Tags:** gpu, temperatur
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.info`

Betriebssystem, Rechnername, Architektur, Kernzahl.

- **Stufe:** READ (LOW)
- **Aliase:** `get_system_info`
- **Tags:** system, info
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.process.children`

Die Kindprozesse eines Prozesses.

- **Stufe:** READ (LOW)
- **Tags:** prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |

### `system.process.find`

Sucht laufende Prozesse nach Namen.

- **Stufe:** READ (LOW)
- **Tags:** prozess, suche
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Teil des Prozessnamens |

### `system.process.info`

Alle Eckdaten zu einem Prozess.

- **Stufe:** READ (LOW)
- **Tags:** prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja | Die Prozess-ID |

### `system.process.kill`

Beendet einen Prozess und prüft nach, ob er weg ist.

- **Stufe:** CRITICAL (HIGH)
- **Tags:** prozess, beenden
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** PERMISSION_REQUIRED -- Läuft, verlangt aber immer eine ausdrückliche Bestätigung.

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |
| `force` | nein | Hart beenden statt freundlich fragen |

### `system.process.list`

Laufende Prozesse, sortierbar nach CPU oder Speicher.

- **Stufe:** READ (LOW)
- **Aliase:** `list_processes`
- **Tags:** prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |
| `sort` | nein | cpu (Vorgabe), memory, name oder pid |
| `name_contains` | nein | Nur Prozesse, deren Name das enthält |

### `system.process.open_files`

Welche Dateien ein Prozess offen hat.

- **Stufe:** READ (LOW)
- **Tags:** prozess, datei
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |
| `limit` | nein |  |

### `system.process.priority`

Ändert die Priorität eines Prozesses.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** prozess, prioritaet
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |
| `level` | nein | niedrig, unter_normal, normal, ueber_normal, hoch |

### `system.process.resume`

Setzt einen angehaltenen Prozess fort.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |

### `system.process.suspend`

Hält einen Prozess an (er läuft nicht weiter).

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pid` | ja |  |

### `system.process.tree`

Der Prozessbaum des Systems.

- **Stufe:** READ (LOW)
- **Tags:** prozess, uebersicht
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `system.python.info`

Python-Version und Interpreterpfad.

- **Stufe:** READ (LOW)
- **Tags:** python, umgebung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.ram.top`

Welche Prozesse den meisten Speicher belegen.

- **Stufe:** READ (LOW)
- **Tags:** ram, prozess
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `system.ram.usage`

Belegter und freier Arbeitsspeicher.

- **Stufe:** READ (LOW)
- **Aliase:** `get_ram_info`
- **Tags:** ram, speicher
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.sensors.fans`

Lüfterdrehzahlen, soweit lesbar.

- **Stufe:** READ (LOW)
- **Tags:** luefter, hardware
- **Benötigt:** psutil
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.sensors.temperatures`

Alle lesbaren Temperatursensoren.

- **Stufe:** READ (LOW)
- **Tags:** temperatur, hardware
- **Benötigt:** psutil
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.service.list`

Die Systemdienste mit ihrem Zustand.

- **Stufe:** READ (LOW)
- **Tags:** dienst
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `limit` | nein |  |

### `system.service.logs`

Die letzten Logzeilen eines Dienstes.

- **Stufe:** READ (LOW)
- **Tags:** dienst, log
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |
| `lines` | nein |  |

### `system.service.restart`

Startet einen Dienst neu und prüft nach.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** dienst
- **Benötigt:** systemctl
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |

### `system.service.start`

Startet einen Dienst und prüft nach.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** dienst
- **Benötigt:** systemctl
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |

### `system.service.status`

Zustand eines einzelnen Dienstes.

- **Stufe:** READ (LOW)
- **Tags:** dienst
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Name des Dienstes |

### `system.service.stop`

Stoppt einen Dienst.

- **Stufe:** SYSTEM (MEDIUM)
- **Tags:** dienst
- **Benötigt:** systemctl
- **Plattformen:** linux
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja |  |

### `system.startup.list`

Programme, die beim Anmelden starten (Windows).

- **Stufe:** READ (LOW)
- **Tags:** windows, autostart
- **Benötigt:** powershell
- **Plattformen:** windows
- **Verfügbarkeit hier, jetzt geprüft:** UNSUPPORTED_PLATFORM -- Läuft nur auf: windows (hier: linux)

### `system.swap.usage`

Belegung des Auslagerungsspeichers.

- **Stufe:** READ (LOW)
- **Tags:** ram, swap
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.uptime`

Wie lange der Rechner schon läuft.

- **Stufe:** READ (LOW)
- **Tags:** system
- **Benötigt:** psutil
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.user.info`

Angemeldeter Benutzer, Heimverzeichnis, Rechte.

- **Stufe:** READ (LOW)
- **Tags:** benutzer
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

### `system.windows.powershell`

Führt einen PowerShell-Befehl aus (nur Windows).

- **Stufe:** CRITICAL (HIGH)
- **Tags:** windows, shell
- **Benötigt:** powershell
- **Plattformen:** windows
- **Verfügbarkeit hier, jetzt geprüft:** UNSUPPORTED_PLATFORM -- Läuft nur auf: windows (hier: linux)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `command` | ja | Der PowerShell-Befehl |
| `timeout` | nein |  |

## text

### `text.base64.decode`

Dekodiert Base64 zurück zu Text.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, base64
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Base64-Text |
| `urlsafe` | nein | URL-sicher |

### `text.base64.encode`

Kodiert Text als Base64.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, base64
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `urlsafe` | nein | URL-sicheres Alphabet |

### `text.case`

Ändert die Schreibweise: lower, upper, title, sentence, snake, kebab, camel, pascal, swap.

- **Stufe:** SAFE (LOW)
- **Tags:** text, schreibweise
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `style` | nein | Der Zielstil |

### `text.count`

Zählt Zeichen, Wörter, Zeilen, Sätze und Absätze.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zaehlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.csv.to_json`

Wandelt CSV-Text in JSON-Datensätze um.

- **Stufe:** SAFE (LOW)
- **Tags:** csv, json
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |
| `delimiter` | nein | Trennzeichen, sonst geraten |
| `header` | nein | Erste Zeile ist die Kopfzeile |

### `text.dedent`

Entfernt den gemeinsamen Einzug aller Zeilen.

- **Stufe:** SAFE (LOW)
- **Tags:** text, format
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.diff`

Zeigt die Unterschiede zwischen zwei Texten.

- **Stufe:** SAFE (LOW)
- **Tags:** vergleich, diff
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text_a` | ja |  |
| `text_b` | ja |  |
| `context` | nein |  |

### `text.extract.emails`

Holt alle E-Mail-Adressen aus einem Text.

- **Stufe:** SAFE (LOW)
- **Tags:** extrahieren, email
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.extract.ips`

Holt gültige IPv4-Adressen aus einem Text.

- **Stufe:** SAFE (LOW)
- **Tags:** extrahieren, netzwerk
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.extract.numbers`

Holt alle Zahlen heraus, mit Summe und Mittel.

- **Stufe:** SAFE (LOW)
- **Tags:** extrahieren, zahlen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.extract.urls`

Holt alle URLs aus einem Text.

- **Stufe:** SAFE (LOW)
- **Tags:** extrahieren, url
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.frequency`

Zählt, welche Wörter am häufigsten vorkommen.

- **Stufe:** SAFE (LOW)
- **Tags:** text, statistik
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `limit` | nein |  |
| `min_length` | nein | Kürzere Wörter überspringen |

### `text.hash`

Bildet eine Prüfsumme über einen Text.

- **Stufe:** SAFE (LOW)
- **Tags:** hash, pruefsumme
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `algorithm` | nein | md5, sha1, sha256, sha512 |

### `text.hex.decode`

Dekodiert Hexadezimal zurück zu Text.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, hex
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.hex.encode`

Kodiert Text als Hexadezimal.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, hex
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.html.escape`

Macht Text HTML-sicher (< > & " ').

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, html
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.html.to_text`

Macht aus HTML reinen Text.

- **Stufe:** SAFE (LOW)
- **Tags:** html, text
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Das HTML |

### `text.html.unescape`

Wandelt HTML-Entities zurück in Zeichen.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, html
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.indent`

Rückt alle Zeilen ein.

- **Stufe:** SAFE (LOW)
- **Tags:** text, format
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `spaces` | nein |  |
| `prefix` | nein | Eigenes Präfix |

### `text.join`

Verbindet Zeilen zu einer Zeile.

- **Stufe:** SAFE (LOW)
- **Tags:** text, verbinden
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `separator` | nein | Trenner, Vorgabe ', ' |

### `text.json.format`

Formatiert JSON lesbar und eingerückt.

- **Stufe:** SAFE (LOW)
- **Tags:** json, format
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Das JSON |
| `indent` | nein |  |
| `sort_keys` | nein | Schlüssel alphabetisch sortieren |

### `text.json.keys`

Listet die Schlüsselpfade eines JSON-Dokuments.

- **Stufe:** SAFE (LOW)
- **Tags:** json, struktur
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |
| `depth` | nein | Tiefe, Vorgabe 2 |

### `text.json.minify`

Entfernt alle Leerzeichen aus JSON.

- **Stufe:** SAFE (LOW)
- **Tags:** json
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.json.to_csv`

Wandelt eine JSON-Objektliste in CSV um.

- **Stufe:** SAFE (LOW)
- **Tags:** csv, json
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |
| `delimiter` | nein |  |

### `text.json.to_yaml`

Wandelt JSON in YAML um.

- **Stufe:** SAFE (LOW)
- **Tags:** json, yaml
- **Benötigt:** yaml
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.json.validate`

Prüft, ob ein Text gültiges JSON ist.

- **Stufe:** SAFE (LOW)
- **Tags:** json, pruefen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.language.detect`

Schätzt die Sprache anhand häufiger Funktionswörter.

- **Stufe:** SAFE (LOW)
- **Tags:** text, sprache
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.lines.filter`

Behält nur Zeilen, die ein Muster treffen.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zeilen, filter
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `pattern` | ja | Regulärer Ausdruck |
| `invert` | nein | Stattdessen die Treffer entfernen |
| `ignore_case` | nein | Groß/Klein ignorieren |

### `text.lines.number`

Stellt jeder Zeile ihre Nummer voran.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zeilen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `start` | nein |  |

### `text.lines.reverse`

Dreht die Reihenfolge der Zeilen um.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zeilen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.lines.sort`

Sortiert Zeilen alphabetisch oder numerisch.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zeilen, sortieren
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `reverse` | nein | Absteigend |
| `numeric` | nein | Nach der ersten Zahl je Zeile |
| `ignore_case` | nein | Groß/Klein ignorieren |

### `text.lines.unique`

Entfernt doppelte Zeilen.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zeilen, duplikate
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `keep_order` | nein | Reihenfolge beibehalten |
| `ignore_case` | nein | Groß/Klein ignorieren |

### `text.markdown.headings`

Listet die Überschriften eines Markdown-Texts.

- **Stufe:** SAFE (LOW)
- **Tags:** markdown, struktur
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.markdown.to_html`

Wandelt einfaches Markdown in HTML (ohne Tabellen und Fußnoten).

- **Stufe:** SAFE (LOW)
- **Tags:** markdown, html
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.password.generate`

Erzeugt ein Passwort aus kryptografischem Zufall.

- **Stufe:** SAFE (LOW)
- **Tags:** zufall, passwort
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `length` | nein | 8–128, Vorgabe 20 |
| `symbols` | nein | Sonderzeichen erlauben |

### `text.random.string`

Erzeugt eine zufällige Zeichenkette.

- **Stufe:** SAFE (LOW)
- **Tags:** zufall
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `length` | nein |  |
| `alphabet` | nein | Erlaubte Zeichen |

### `text.regex.extract`

Holt alle Treffer (oder eine Gruppe) heraus.

- **Stufe:** SAFE (LOW)
- **Tags:** regex, extrahieren
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pattern` | ja |  |
| `text` | ja | Der Eingabetext |
| `group` | nein | Gruppennummer, 0 = ganzer Treffer |
| `ignore_case` | nein | Groß/Klein ignorieren |

### `text.regex.replace`

Ersetzt über einen regulären Ausdruck.

- **Stufe:** SAFE (LOW)
- **Tags:** regex, ersetzen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pattern` | ja |  |
| `text` | ja | Der Eingabetext |
| `replace` | nein |  |
| `ignore_case` | nein | Groß/Klein ignorieren |
| `count` | nein |  |

### `text.regex.test`

Probiert einen regulären Ausdruck an einem Text aus.

- **Stufe:** SAFE (LOW)
- **Tags:** regex, pruefen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `pattern` | ja |  |
| `text` | ja | Der Eingabetext |
| `ignore_case` | nein | Groß/Klein ignorieren |

### `text.replace`

Ersetzt Text (wörtlich, nicht als Muster).

- **Stufe:** SAFE (LOW)
- **Tags:** text, ersetzen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `search` | ja |  |
| `replace` | nein |  |
| `count` | nein |  |

### `text.rot13`

Wendet ROT13 an (zweimal anwenden hebt es auf).

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.similarity`

Misst, wie ähnlich zwei Texte sind (0 bis 1).

- **Stufe:** SAFE (LOW)
- **Tags:** vergleich
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text_a` | ja |  |
| `text_b` | ja |  |

### `text.slug`

Macht aus einem Titel einen URL-tauglichen Slug.

- **Stufe:** SAFE (LOW)
- **Tags:** url, text
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `separator` | nein | Trennzeichen, Vorgabe '-' |

### `text.split`

Zerlegt Text an einem Trennzeichen.

- **Stufe:** SAFE (LOW)
- **Tags:** text, zerlegen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `separator` | nein |  |
| `limit` | nein |  |

### `text.timestamp.now`

Die aktuelle Zeit, lokal und als Unix-Zeit.

- **Stufe:** SAFE (LOW)
- **Tags:** zeit
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `format` | nein | strftime-Muster |

### `text.timestamp.parse`

Rechnet eine Unix-Zeit oder ein Datum in beide Richtungen um.

- **Stufe:** SAFE (LOW)
- **Tags:** zeit, umrechnen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `value` | ja | Unix-Zeit oder ISO-Datum |

### `text.trim`

Entfernt Leerraum: both, left, right, lines, blank.

- **Stufe:** SAFE (LOW)
- **Tags:** text, aufraeumen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `mode` | nein | both (Vorgabe), left, right, lines, blank |

### `text.url.decode`

Dekodiert prozentkodierten URL-Text.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, url
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |

### `text.url.encode`

Kodiert Text für die Verwendung in einer URL.

- **Stufe:** SAFE (LOW)
- **Tags:** kodierung, url
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `safe` | nein | Zeichen, die bleiben dürfen |

### `text.uuid`

Erzeugt eine oder mehrere UUIDs.

- **Stufe:** SAFE (LOW)
- **Tags:** id, uuid
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `version` | nein | 1 oder 4 (Vorgabe) |
| `count` | nein |  |

### `text.wrap`

Bricht Text auf eine feste Zeilenbreite um.

- **Stufe:** SAFE (LOW)
- **Tags:** text, format
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja | Der Eingabetext |
| `width` | nein | Vorgabe 80 |

### `text.xml.format`

Formatiert XML lesbar und eingerückt.

- **Stufe:** SAFE (LOW)
- **Tags:** xml, format
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |
| `indent` | nein |  |

### `text.xml.validate`

Prüft, ob ein Text wohlgeformtes XML ist.

- **Stufe:** SAFE (LOW)
- **Tags:** xml, pruefen
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

### `text.yaml.to_json`

Wandelt YAML in JSON um.

- **Stufe:** SAFE (LOW)
- **Tags:** json, yaml
- **Benötigt:** yaml
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |
| `indent` | nein |  |

### `text.yaml.validate`

Prüft, ob ein Text gültiges YAML ist.

- **Stufe:** SAFE (LOW)
- **Tags:** yaml, pruefen
- **Benötigt:** yaml
- **Verfügbarkeit hier, jetzt geprüft:** AVAILABLE

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `text` | ja |  |

## video

### `video.audio.remove`

Entfernt die Tonspur eines Videos.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.audio.replace`

Ersetzt die Tonspur eines Videos durch eine andere Datei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, audio
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `audio_path` | ja | Pfad zur neuen Audiodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.compress`

Verkleinert die Dateigröße durch stärkere Kompression (CRF: niedriger = größer/besser, höher = kleiner/schlechter).

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, komprimieren
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `crf` | nein | 0-51, Vorgabe 28 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.convert`

Wandelt eine Videodatei in ein anderes Format um.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, format
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.frames.extract`

Extrahiert Einzelbilder aus einem Video in einen Ordner.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, bild
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output_dir` | ja | Zielordner im Arbeitsbereich |
| `fps` | nein | Bilder pro Sekunde, Vorgabe 1.0 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.gif.create`

Erstellt ein animiertes GIF aus einem Videoausschnitt.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, gif
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `start` | nein | Start, Vorgabe 0 |
| `duration` | nein | Dauer in Sekunden, Vorgabe 3 |
| `fps` | nein | Bilder pro Sekunde, Vorgabe 10 |
| `width` | nein | Breite in Pixeln, Vorgabe 480 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.info`

Dauer, Auflösung, Bildrate und Codec einer Videodatei.

- **Stufe:** READ (LOW)
- **Tags:** video, info
- **Benötigt:** ffprobe
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFprobe (Teil von FFmpeg)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |

### `video.merge`

Fügt mehrere Videodateien nacheinander zusammen.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `paths` | ja |  |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.resize`

Skaliert die Auflösung eines Videos.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `width` | ja | Zielbreite in Pixeln |
| `height` | nein | Zielhöhe, -2 = proportional (Vorgabe) |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.rotate`

Dreht ein Video um 90/180/270 Grad.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `degrees` | ja | 90, 180, 270 oder -90 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.speed`

Ändert die Wiedergabegeschwindigkeit eines Videos.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `factor` | ja | z. B. 2.0 für doppelte Geschwindigkeit |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.thumbnail`

Extrahiert ein einzelnes Bild aus einem Video.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, bild
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `timestamp` | nein | Zeitpunkt, Vorgabe 00:00:01 |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.trim`

Schneidet einen Ausschnitt aus einer Videodatei.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `start` | ja | Start, z. B. 00:00:05 |
| `duration` | nein | Dauer, leer = bis Ende |
| `overwrite` | nein | Bestehendes Ziel überschreiben |

### `video.watermark.image`

Blendet ein Logo/Bild in ein Video ein.

- **Stufe:** WRITE (MEDIUM)
- **Tags:** video, logo
- **Benötigt:** ffmpeg
- **Verfügbarkeit hier, jetzt geprüft:** MISSING_DEPENDENCY -- Es fehlt: FFmpeg (https://ffmpeg.org/download.html)

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `path` | ja | Pfad zur Videodatei |
| `logo_path` | ja | Pfad zum Logo/Bild |
| `output` | ja | Zielpfad im Arbeitsbereich |
| `position` | nein | unten-rechts/unten-links/oben-rechts/oben-links/mitte |
| `overwrite` | nein | Bestehendes Ziel überschreiben |
