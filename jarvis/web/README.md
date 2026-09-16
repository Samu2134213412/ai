# Jarvis Core — Oberfläche

`index.html` ist eine eigenständige Datei ohne Abhängigkeiten. Doppelklick
genügt; später liefert der Jarvis-Server sie unter `/` aus. Sie läuft im
Browser und damit auf PC und Handy gleichermaßen.

## Warum die Kugel Zustand zeigt und nicht nur hübsch ist

Die Oberfläche unterscheidet sichtbar vier Zustände:

| Zustand | Bedeutung | Darstellung |
|---|---|---|
| `idle` | nichts läuft | langsame Drehung, gedämpft |
| `thinking` | **das Modell plant** | schnelle Drehung, heller Kern |
| `executing` | **ein Werkzeug läuft tatsächlich** | Druckwellen laufen nach außen |
| `failed` | Aktion fehlgeschlagen | Rotstich, Drehung fällt ab |

Das ist der Punkt: `thinking` und `executing` sehen verschieden aus. Behauptet
das Modell einen Erfolg, ohne dass ein Werkzeug lief, fehlen die Druckwellen —
die Lüge ist am Bildschirm sichtbar, bevor man die Festplatte prüft.

Jede Antwort im Verlauf trägt zusätzlich ihren Beleg:

* **Tool-Beleg** (grün) — ein Werkzeug lief und gab Erfolg zurück; Name, Pfad und Dauer stehen darunter
* **kein Tool** (grau) — reine Konversation, es wurde nichts getan
* **fehlgeschlagen** (rot) — mit dem echten Fehler

Ohne Serververbindung führt die Oberfläche **nichts** aus und sagt das auch:
ein abgeschickter Befehl liefert „Der Befehl wurde nicht ausgeführt“ statt einer
erfundenen Bestätigung. Die Telemetriebalken bleiben leer, statt Zahlen zu
erfinden. Werkzeuge stehen auf „unbestätigt“, solange ihr Zustand nicht am Code
geprüft wurde.

## Anbindung an den Server

Die Seite stellt genau fünf Funktionen bereit. Mehr braucht der Adapter nicht:

```js
JARVIS.connect({host: "192.168.1.40", model: "qwen2.5:14b"});
JARVIS.state("executing", "<b>write_file</b> · schreibe notizen.txt");
JARVIS.message({who: "jarvis", prov: "tool", text: "…", evidence: "write_file → <b>success=true</b> · 41 ms"});
JARVIS.telemetry({cpu: 23, ram: {used: 11.4, total: 32}, gpu: {used: 18.1, total: 24}});
JARVIS.tools([{name: "write_file", status: "ok"}]);
JARVIS.disconnect();
```

`prov` ist `"tool"`, `"talk"` oder `"fail"`. `status` ist `"ok"`, `"unknown"`
oder `"none"`.

**Regel für den Adapter:** `prov: "tool"` wird ausschließlich aus einem echten
Tool-Result gesetzt, niemals aus dem Text des Modells. Wer diese Regel im
Adapter bricht, hebelt die ganze Oberfläche aus.

## Technik

Die Kugel ist Canvas 2D, keine Bibliothek, kein WebGL. Leiterbahnen laufen als
Geodäten über die Kugel und biegen gelegentlich um 90° — daher der
Platinen-Charakter der Vorlage. Gezeichnet wird in zwei Durchgängen: ein Halo in
Drittelauflösung, weichgezeichnet und additiv darübergelegt, dann die scharfen
Linien. Segmente werden nach Farbklasse und Tiefe gebündelt, sodass pro Bild
neun `stroke()`-Aufrufe genügen statt einiger tausend. Auf dem Telefon wird die
Geometrie ausgedünnt und `devicePixelRatio` auf 2 gedeckelt.

`prefers-reduced-motion` hält die Drehung an und unterdrückt die Druckwellen.
