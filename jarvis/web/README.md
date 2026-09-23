# Jarvis Core — Oberfläche

`index.html` ist eine eigenständige Datei ohne Abhängigkeiten. Doppelklick
genügt; später liefert der Jarvis-Server sie unter `/` aus. Sie läuft im
Browser und damit auf PC und Handy gleichermaßen.

## Warum die Kugel Zustand zeigt und nicht nur hübsch ist

Die Oberfläche unterscheidet sichtbar vier Zustände:

| Zustand | Bedeutung | Darstellung |
|---|---|---|
| `idle` | nichts läuft | gedämpfte Glut, träge Drehung, Iris geschlossen |
| `thinking` | **das Modell plant** | heller, schnellere Drehung |
| `executing` | **ein Werkzeug läuft tatsächlich** | Weißglut, Iris reißt auf, Druckwellen nach außen |
| `failed` | Aktion fehlgeschlagen | Rotstich, Drehung fällt ab |

Das ist der Punkt: `executing` sieht anders aus als alles andere. Behauptet das
Modell einen Erfolg, ohne dass ein Werkzeug lief, bleibt der Kern gedämpft, die
Iris geschlossen und es kommen keine Druckwellen — die Lüge ist am Bildschirm
sichtbar, bevor man die Festplatte prüft.

Ruhezustand und Denken teilen sich den Goldton. Das Erkennungsmerkmal ist
deshalb bewusst nicht die Farbe allein, sondern **Weißglut plus Iris plus
Druckwellen** — drei Signale, die nur gemeinsam auftreten und nur dann, wenn
ein Tool-Result vorliegt.

Jede Antwort im Verlauf trägt zusätzlich ihren Beleg:

* **Tool-Beleg** (grün) — ein Werkzeug lief und gab Erfolg zurück; Name, Pfad und Dauer stehen darunter
* **kein Tool** (grau) — reine Konversation, es wurde nichts getan
* **fehlgeschlagen** (rot) — mit dem echten Fehler

Seit dem Permission-System (Phase 1) kann eine Aktion außerdem eine
Bestätigung verlangen: der Verlauf zeigt dafür eine eigene Karte mit
„Erlauben“/„Ablehnen“ (`permission.requested`), die sich nach der Antwort
selbst zu „erlaubt“ oder „abgelehnt“ umfärbt, statt eine neue Zeile
anzuhängen. Im Agent-Modus erscheinen zusätzlich Verlaufszeilen für Plan,
laufenden Schritt, Wiederholungsversuch und Abschluss (`task.*`-Ereignisse).

Ohne Serververbindung führt die Oberfläche **nichts** aus und sagt das auch:
ein abgeschickter Befehl liefert „Der Befehl wurde nicht ausgeführt“ statt einer
erfundenen Bestätigung. Die Telemetriebalken bleiben leer, statt Zahlen zu
erfinden. Werkzeuge stehen auf „unbestätigt“, solange ihr Zustand nicht am Code
geprüft wurde.

## Zwei Spalten statt drei

Die Kommandozentrale zeigt links den Dialog (breit, der eigentliche Chat-
und Code-Verlauf) und rechts eine schmale Spalte mit Modellen, Auslastung
(dieselbe Werte-Kurve wie vorher, nur umgezogen), Werkzeugen, Verlauf
(Audit/Undo, siehe unten) und Spracheingabe. Die vorherige, separate
System-Spalte (CPU/GPU/OS als Rundinstrumente + fest eingetragene
Hardwarezeilen) ist weg -- die Werte waren größtenteils statischer Text,
keine echten Systeminformationen wert eines eigenen Bereichs, und der Dialog
brauchte den Platz mehr. Auf dem Handy bleiben die Bereiche als zwei Reiter
erreichbar (Dialog/Modelle).

## Als App auf dem Handy installieren

Die Seite ist eine installierbare PWA (Progressive Web App) — dieselbe
`index.html`, aber mit `manifest.webmanifest`, Icons und einem Service
Worker daneben, den der Jarvis-Server unter `/manifest.webmanifest`,
`/icons/*` und `/service-worker.js` mit ausliefert:

* **Android/Chrome:** die Server-Adresse öffnen (z. B.
  `http://192.168.1.40:8799/?token=…`), Menü → „App installieren" bzw.
  „Zum Startbildschirm hinzufügen".
* **iOS/Safari:** die Adresse öffnen, Teilen-Symbol → „Zum Home-Bildschirm".
  Safari liest kein volles Manifest, aber `apple-touch-icon` und die
  `apple-mobile-web-app-*`-Meta-Tags sorgen für Icon, Titel und einen
  Start ohne Safari-Chrome (`display: standalone`).

Danach startet Jarvis wie eine eigene App, ohne Adressleiste. Der Service
Worker cached ausschließlich die statische Hülle (HTML/Manifest/Icons) für
einen schnellen Kaltstart — **niemals** `/api/*` oder die WebSocket-Verbindung.
Ohne Server bleibt die Oberfläche also ehrlich bei „Kein Server" stehen,
statt veraltete Antworten aus dem Cache zu zeigen.

**Das Token übersteht die Installation.** `manifest.webmanifest`s
`start_url` zeigte früher auf `./index.html` — eine Adresse, die der
Jarvis-Server nie ausgeliefert hat (er kennt nur `/`), und jeder erneute
Start der installierten App landete auf einem 404. Behoben: `start_url`
zeigt jetzt auf `./`. Zusätzlich merkt sich der Browser das Token beim
ersten Öffnen (`localStorage`, nicht nur in der URL) und nimmt es aus der
sichtbaren Adresszeile — ein App-Icon, das ohne `?token=…` in der Adresse
öffnet (genau das, was jede installierte PWA beim Neustart tut), bleibt
trotzdem verbunden. Ändert sich das Token (siehe unten), reicht ein
erneutes Öffnen über den neuen Link, das alte wird überschrieben.

**Das Token übersteht auch einen Server-Neustart.** `python -m jarvis
--open-network` erzeugt beim allerersten Mal ein zufälliges Token und
schreibt es sofort in die Konfigurationsdatei zurück -- jeder weitere Start
verwendet danach dasselbe. Vorher wurde ein neues Token nur dann
gespeichert, wenn die Konfigurationsdatei gerade erst angelegt wurde; bei
jedem weiteren Start stand plötzlich ein anderes Token da, ohne dass sich
etwas geändert hätte, und jede zuvor aufs Handy eingetippte oder installierte
Adresse hörte auf zu funktionieren.

Es handelt sich nicht um eine native App und nicht um das separate
Expo-Projekt unter `../../mobile/` (das gehört zu CodePilot Remote) —
die Oberfläche war schon vorher für Handy-Breiten ausgelegt (eigene
`@media`-Regeln, Tab-Leiste statt Spalten); neu ist nur die
Installierbarkeit.

## Von unterwegs erreichbar (außerhalb des eigenen Netzwerks)

`python -m jarvis --open-network` reicht fürs selbe WLAN — die Adresse, die
es nennt, ist eine private Netzwerkadresse (192.168.x.x/10.x.x.x), die
außerhalb der eigenen Fritzbox/des eigenen Routers niemand erreicht. Für
unterwegs (mobile Daten, ein fremdes WLAN, ein anderes Land) braucht es eine
zweite Adresse, die von überall aus zu diesem Rechner findet.

**Empfohlener Weg: [Tailscale](https://tailscale.com/)** (kostenlos für den
persönlichen Gebrauch). Statt eine Pforte am eigenen Router zu öffnen (der
naheliegende, aber bei einem Werkzeug mit Datei-/Prozesszugriff riskante Weg
— jede Schwachstelle im Server wäre dann direkt aus dem ganzen Internet
erreichbar), baut Tailscale ein privates, Ende-zu-Ende-verschlüsseltes
Netz (WireGuard) zwischen den eigenen Geräten auf. Jarvis merkt davon
nichts: derselbe `--open-network`-Aufruf, dasselbe Token, nur eine
zusätzliche Netzwerkschnittstelle mit einer Adresse aus `100.64.0.0/10`.

1. Tailscale auf dem Rechner installieren, auf dem Jarvis läuft, und
   anmelden: <https://tailscale.com/download>.
2. Dieselbe Tailscale-App auf dem Handy installieren und mit **demselben
   Konto** anmelden.
3. `python -m jarvis --open-network` wie gewohnt starten. Im Terminal steht
   jetzt zusätzlich:
   ```
   Adresse (Handy, auch unterwegs -- über Tailscale):
     http://100.x.x.x:8770/?token=…
   ```
4. Diese Adresse auf dem Handy öffnen (Tailscale-App muss dafür laufen,
   braucht aber keine eigene Bedienung) — funktioniert im selben WLAN genauso
   wie unterwegs, eine einzige Adresse für beides. Als App installieren
   (siehe oben) funktioniert damit genauso.

Kommt keine solche Zeile, sondern nur der Hinweis auf diesen Abschnitt, läuft
entweder kein Tailscale auf diesem Rechner, oder `psutil` (siehe
`requirements.txt`) findet dessen Netzwerkschnittstelle nicht — ein
`tailscale status` im Terminal zeigt, ob der Dienst überhaupt aktiv ist.

## Kommando-Palette, Action Search, Tool Explorer

**F3** (oder **Strg/Cmd+K**, auch der „⌘ Palette"-Knopf neben dem
Befehlsfeld) öffnet eine Palette über der Oberfläche:

* **Ohne Suchtext** zeigt sie den ganzen Werkzeugkatalog — nach Kategorie
  filterbar über die Chips oben (Tool Explorer).
* **Mit Suchtext** dieselbe Rangfolge, die auch das Modell im Chat angeboten
  bekäme (`GET /api/tools?q=…`, derselbe Suchindex wie `discovery.py`) —
  plus lokale Aktionen (Ansicht wechseln, Modus wechseln, Sprechen, Demo,
  Tastenkürzel anzeigen/exportieren/importieren, Benachrichtigungen
  aktivieren), die rein im Browser laufen, und die gespeicherten **Makros**
  (`GET /api/macros`, Punkt 46) — ein Klick führt sie sofort aus
  (`mode: "macro"`, dieselbe Permission-Gate/Undo/Audit-Pipeline wie jeder
  andere Werkzeugaufruf je Schritt), ohne den Umweg über den Chat und ohne
  den Makronamen selbst tippen zu müssen.
* Jede Werkzeugzeile aufklappbar (Beschreibung, Verfügbarkeit, Tags) und mit
  zwei Schaltern: **★** Favorit setzen, **⊘** abschalten (Punkt 26) — beides
  direkt über `POST /api/tools/{name}/{aktion}`, ohne Umweg über das Modell.
  Ein abgeschaltetes Werkzeug läuft danach auch im Chat wirklich nicht mehr.
* Tastatur: ↑↓ zum Wählen, ⏎ zum Ausführen/Aufklappen, Esc zum Schließen.

Getragen von einem kleinen, eigenen **HotkeyManager** (Punkt 48, direkt im
Skript-Teil von `index.html`, kein separates Modul): Aktionen registrieren
sich mit einer oder mehreren Tastenkombinationen und optional einem Kontext
(„nur wenn die Palette offen ist"); `Mod` steht für Cmd auf dem Mac, sonst
Strg, eine Registrierung deckt also beide Plattformen ab. Eine Taste feuert
nie, während in einem Eingabefeld getippt wird, außer die Aktion sagt
ausdrücklich `allowInInput` (wie F3 selbst oder Esc). Remaps landen über
`HotkeyManager.exportJSON()`/`.importJSON()` in `localStorage` und
überleben einen Neustart der Seite — erreichbar über drei eigene
Palette-Aktionen ("Tastenkürzel anzeigen/exportieren/importieren"), Export
geht in die Zwischenablage, Import über einen Textprompt.

## Verlauf: Audit Log + Rückgängig, direkt in der Oberfläche

Im Bereich „Modelle" (rechte Spalte) zeigt die Karte **Verlauf** die letzten
Audit-Einträge (`GET /api/audit`) und die letzten rückgängig machbaren
Aktionen (`GET /api/undo`) — beide Wege gab es serverseitig schon lange,
bisher nur über den Chat oder von Hand über HTTP erreichbar. Ein Klick auf
**Rückgängig** ruft `POST /api/undo` auf und aktualisiert die Karte. Sie
lädt sich selbst neu bei jeder Verbindung und nach jedem `tool.finished`
(leicht entprellt), dazu über den kleinen **↻**-Knopf im Kopf der Karte von
Hand.

## Benachrichtigungen

Läuft ein Ziel im Hintergrund weiter (Autonomy V1) oder wartet eine
Bestätigung, während der Tab gerade nicht im Vordergrund ist, meldet sich
der Browser über die Web-Notification-API — nur dann, nie zusätzlich, wenn
ohnehin hingeschaut wird (das steht schon im Verlauf). Aktiviert wird das
ausdrücklich über die Palette-Aktion „Benachrichtigungen aktivieren", nie
automatisch beim Laden der Seite.

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

Die Kugel ist Canvas 2D, keine Bibliothek, kein WebGL.

* **Leiterbahnen** laufen als Geodäten über die Kugel und biegen gelegentlich um
  90° — daher der Platinen-Charakter.
* **Speichen** sind im Raum radiale Strecken. Eine solche Linie projiziert immer
  durch die Bildmitte, deshalb strahlen sie von selbst aus dem Zentrum.
* **Tiefenunschärfe**: jedes Segment bekommt nach seinem Abstand zur Fokusebene
  eine von drei Stufen. Scharfe Segmente gehen in den harten Durchgang, unscharfe
  nur in den weichgezeichneten — daraus entsteht das Bokeh.
* **Bokeh-Punkte** werden nach Unschärfestufe gebündelt: zwölf Füllungen pro Bild
  statt mehrerer hundert Einzelkreise.
* **Iris**: ein echtes Loch, mit `destination-out` in die Leinwand gestanzt, sodass
  der Raum dahinter durchscheint. Darum ein heißer Rand, ein mitlaufender
  Zahnkranz und konzentrische Bögen.
* Segmente sind nach Farbklasse und Unschärfestufe gebündelt — neun `stroke()`-
  Aufrufe pro Durchgang statt einiger tausend.

Auf dem Telefon wird die Geometrie ausgedünnt; `devicePixelRatio` ist auf 1,75
gedeckelt, weil die Kugel weiches Licht ist und keine Schrift.

Gemessen in diesem Container **ohne GPU** (reine Software-Rasterung, also ein
Boden, keine Vorhersage): 17 fps bei 1440×900, 34 fps bei 390×844. Die
Vorversion lag unter denselben Bedingungen bei 19 fps. Auf einer RX 7900 XTX ist
Canvas 2D hardwarebeschleunigt und liegt um ein Vielfaches darüber — nachmessen,
sobald es auf deiner Maschine läuft.

`prefers-reduced-motion` hält die Drehung an und unterdrückt die Druckwellen.
