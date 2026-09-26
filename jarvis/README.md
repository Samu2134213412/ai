# Jarvis

Persönlicher Assistent auf dem eigenen Rechner, bedienbar von PC und Handy.

Stand: die Oberfläche steht (`web/`). Der Server steht noch aus — und der alte
Jarvis-Code vom Windows-PC ist noch nicht eingelesen (siehe `../docs/JARVIS.md`).

## Die Aufteilung

```
        LLM  =  Denken und Planen
      Tools  =  tatsächliches Handeln
     Memory  =  langfristiges Wissen
     Skills  =  bekannte wiederverwendbare Abläufe
```

Das Modell simuliert nichts selbst. Es plant, und gehandelt wird über Werkzeuge,
die ein überprüfbares Ergebnis zurückgeben.

## Zwei Modelle, ein Manager

Jarvis benutzt **zwei** Ollama-Modelle mit klar getrennten Aufgaben — beide
direkt, ohne Dienst dazwischen.

```
   Handy                         PC
     └──────────────┬─────────────┘
                    │  HTTP + WebSocket
         ┌──────────▼───────────┐
         │   Jarvis-Server      │   Router · Gedächtnis · Werkzeuge
         └──┬────────────────┬──┘
            │                │
  Gespräch, │                │ alles, was Code ist
  Planen,   │                │
  Erinnern  │                │
     ┌──────▼──────┐   ┌─────▼───────────┐
     │   Ollama    │   │     Ollama      │
     │ Chat-Modell │   │ qwen3-coder:30b │
     │   ~7–14 B   │   │                 │
     └─────────────┘   └─────┬───────────┘
                             │
              dieselben Werkzeuge wie überall:
           Dateien · Suche · Terminal · Permission
                 · Undo · Audit Log
```

Der Gewinn liegt nicht in der Zahl der Modelle, sondern darin, **was
zurückkommt**. Ein Code-Auftrag endet damit, dass Jarvis die geänderte Datei
zurückliest und ihre Syntax prüft. Das ist ein Beleg. Ein Modell, das
behauptet, den Code geschrieben zu haben, ist keiner.

Bis vor Kurzem lief der Code-Modus über CodePilot Remote (das Projekt unter
`server/` in diesem Repo). Das war eine Kette aus drei Diensten, von denen
jeder laufen musste — und weil in einer frischen Installation keine
Projekt-ID eingetragen ist, konnte der Code-Modus in der Praxis meistens gar
nichts. Seit dem Ausbau spricht Jarvis das Code-Modell selbst an. Der
wichtigere Gewinn: **jede Dateiänderung läuft jetzt durch Jarvis' eigenen
Werkzeugpfad** und ist damit bestätigungspflichtig, protokolliert und
rückgängig zu machen. Vorher hat ein fremder Prozess geschrieben, und Jarvis
hat nur dessen Bericht weitergereicht.

CodePilot Remote bleibt als eigenständiges Projekt im Repo erhalten — Jarvis
hängt nur nicht mehr davon ab.

### Drittes Modell: schnell für einfache Fragen

Optional, in `jarvis.json` unter `fast_model` einzutragen (leer = aus, der
Standard). Trifft `complexity.is_simple()` auf eine Nachricht zu -- kurz,
keine Datei-/System-/Code-Aktion, keine Live-Daten wie Uhrzeit oder Wetter --,
beantwortet dieses kleinere Modell sie **ohne Werkzeugschema**. Im Zweifel
bleibt es beim Hauptmodell; ein zu Unrecht als "einfach" eingestuftes Anliegen
bekommt so gar keine Chance, ein Werkzeug unzuverlässig aufzurufen, und eine
trotzdem behauptete Aktion fängt derselbe Wächter (`guard.py`) ab wie jede
andere Antwort auch. Ein Beispiel: `qwen3:1.7b` neben `qwen3:14b` und
`qwen3-coder:30b` -- für "Wie viel ist 12 mal 15?" muss dann kein 14B-Modell
laden.

### Warum nicht ein Modell für beides

`llama3.2:3b` hat Aktionen als erledigt gemeldet, die nie stattfanden. Ein 3B-Modell
ruft Werkzeuge unzuverlässig auf — das ist die Ursache, nicht die
Prompt-Formulierung. Ein 30B-Coder wiederum ist für jedes „wie spät ist es“
verschwendet und lädt die GPU unnötig voll.

### Die VRAM-Rechnung (bitte auf deiner Maschine nachprüfen)

| | |
|---|---|
| RX 7900 XTX | 24 GB |
| `qwen3-coder:30b` Q4 | ~18 GB |
| Rest für das Chat-Modell | ~5 GB |

Ein Modell bis etwa 8B in Q4 passt damit daneben und **beide bleiben geladen**:

```powershell
setx OLLAMA_MAX_LOADED_MODELS 2
```

Wird das Chat-Modell größer, lädt Ollama abwechselnd um — jeder Wechsel kostet
dann spürbar Zeit. Die Zahlen oben sind Richtwerte aus der Doku und aus
`../PROJECT_STATUS.md`; der KV-Cache großer Kontexte kommt obendrauf. Was
wirklich passt, sagt `ollama ps` auf deinem Rechner.

**Empfehlung, noch zu verifizieren:** als Chat-Modell etwas aus der 7–8B-Klasse
mit gutem Werkzeugaufruf und brauchbarem Deutsch. Entschieden wird das, sobald
der alte Jarvis-Code vorliegt und klar ist, welche Werkzeugschnittstelle er
erwartet.

## Ordner

| Pfad | Inhalt |
|---|---|
| `web/` | Oberfläche: Kommandozentrale und Wissensnetz, eine Datei, keine Abhängigkeiten |
| `server/` | Router, Werkzeuge, Gedächtnis, Agent, Wächter, WebSocket — siehe `server/README.md` |
| `CODEX-AUFTRAG.md` | Fertiger Auftragstext für Codex, um Jarvis auf dem eigenen Rechner samt Handy-Zugriff einzurichten |

## Stand

Fertig und getestet (930 Tests, siehe `ROADMAP.md` für die Phasen):

* Werkzeugschicht mit erzwungenem Beleg — kein Erfolg ohne `ToolResult`
* 416 Werkzeuge in Tool-Packs, u. a. Dateien/Archive, Text/Daten, System/
  Prozesse, Netzwerk sowie **Git (43 Operatoren), Python und Node.js**
  (venv, pip, ruff, pytest, npm), **Medien** (Bild über Pillow, Audio/
  Video über ffmpeg/ffprobe, 49 Operatoren), **Docker (19), nginx (8),
  Minecraft (19, über eine eigene RCON-Implementierung) und SQLite (10)**
  sowie **Zwischenablage, Produktivität (Taschenrechner ohne eval, Einheiten/
  Farben/Datum, QR-Codes, gespeicherte Makros), Suche (21, inkl. Web-Suche
  über SearXNG/Brave und Programme starten) und Desktop (6: Bildschirmfoto,
  Maus/Tastatur-Automatisierung über PyAutoGUI)** — kleine, benannte Befehle
  statt eines `git_do_everything`; destruktive (reset --hard, clean, DROP
  TABLE, docker.prune) mit echtem Probelauf, siehe `server/jarvis/tools/packs/`
* **Makros:** gespeicherte Schrittfolgen mit IF/LOOP/PARALLEL/RETRY/WAIT
  (`server/jarvis/macros.py`) — jeder Schritt läuft über dieselbe
  `Agent._run_tool`-Pipeline wie ein einzelner Werkzeugaufruf (Permission-
  Gate, Undo, Audit), angelegt/verwaltet über `automation.macro.*`,
  ausgeführt über den eigenen Modus `mode: "macro"`
* **Tool Discovery:** bei 416 Werkzeugen passen die vollständigen Schemata
  nicht mehr ins Kontextfenster — vor jeder Modellanfrage sucht
  `discovery.py` lokal und deterministisch (Begriffstreffer, Tippfehler-
  toleranz, Favoriten-/Verlaufs-/Kontextbonus) die passende Handvoll
  Werkzeuge heraus, statt den ganzen Katalog zu schicken. `jarvis.tools.*`
  (14 Meta-Werkzeuge: `search`/`info`/`list`/`favorite`/`disable`/`history`/
  `stats`/`dependencies`/`install_dependency`/…) macht denselben Suchindex
  und die Werkzeug-Historie auch dem Modell selbst zugänglich, samt einer
  Möglichkeit, einzelne Werkzeuge gezielt abzuschalten (Punkt 26) — siehe
  `server/README.md`
* **Ehrliche Werkzeug-Statusliste:** die Liste in der Oberfläche zeigt den
  echten Zustand auf DIESEM Rechner statt "registriert = bereit" — `bereit`,
  `nachrüsten` (Abhängigkeit fehlt), `anderes OS`, `abgeschaltet` oder
  `fehlt`, jeweils mit Grund als Tooltip, das Behebbare zuerst. Nach
  `jarvis.shell.enable`, `jarvis.tools.install_dependency` oder dem
  Ab-/Anschalten im Explorer aktualisiert sie sich sofort
* **`jarvis.shell.enable`/`.disable`:** `run_command` steht per Voreinstellung
  aus (siehe Sicherheit oben) und blieb deshalb in der Werkzeug-Statuszeile
  der Oberfläche dauerhaft grau, obwohl es längst gebaut ist — diese beiden
  Werkzeuge schalten es mit einer vorsichtigen Vorgabe-Allowlist um, ohne von
  Hand in der `jarvis.json` zu editieren und ohne das Permission-System zu
  umgehen (jeder `run_command`-Aufruf verlangt weiterhin seine eigene
  Bestätigung) — siehe `server/README.md`
* **`jarvis.tools.dependencies`/`.install_dependency`:** dieselbe Idee wie
  beim Shell-Umschalter, für fehlende Python-Pakete (PyAutoGUI, qrcode, …)
  statt für `run_command` -- installiert mit `pip` in Jarvis' eigener
  Laufzeitumgebung, mit `dry_run` (Punkt 30) und echter Nachprüfung, ob das
  Paket danach wirklich importierbar ist, statt pip's Exit-Code zu glauben.
  Externe Programme (ffmpeg, Tesseract, nginx, …) bleiben bewusst außen vor —
  die verlangen weiterhin einen Installer oder den Paketmanager des
  Betriebssystems, von Hand
* **Guardian-Anbindung (`guardian.*`):** der Virenschutz aus `../guardian`
  ist per Chat bedienbar — Status, Datei/Ordner prüfen (`guardian.check`,
  mit echtem Probelauf), Quarantäne ansehen, Ereignisse, Regeln. Jarvis ruft
  Guardians Programm mit `--json` auf, prüft jede gemeldete Quarantäne bzw.
  Wiederherstellung auf der Platte nach, und das Zurückholen einer als
  Bedrohung eingestuften Datei ist CRITICAL: immer mit Bestätigung.
  Installiert wird Guardian per Doppelklick auf `guardian\install.bat` —
  siehe `server/README.md` und `../guardian/README.md`
* **Session-Gedächtnis (`kind="sitzung"`):** die in `ROADMAP.md` offen
  gelassene Ebene zwischen Kurz- und Langzeitgedächtnis. Zug-Paare, die aus
  dem kurzlebigen Chat-Fenster (`Agent.history`) fallen, landen jetzt mit
  eigener Ablaufzeit im Wissensnetz (`memory.py`, Vorgabe 48 Stunden), statt
  spurlos zu verschwinden -- aber auch, ohne das Gedächtnis auf Dauer mit
  flüchtigem Chat-Kleinkram vollzustopfen: abgelaufene Erinnerungen tauchen
  in keinem Abruf mehr auf und werden beim nächsten Start endgültig
  gelöscht. `memory_add` kann jetzt ebenfalls ein `ttl_hours` setzen ("merk
  dir das nur für heute")
* Direct Action Router für eindeutige Befehle
* Langzeitgedächtnis in SQLite mit selbständigem Abruf vor jeder Modellanfrage
* Agent mit Ollama-Werkzeugaufruf
* Code-Modus: das Code-Modell direkt über Ollama, mit denselben Werkzeugen, demselben Permission-System und derselben Undo-Historie wie alles andere — und einer Syntaxprüfung nach jeder Änderung
* **Fokus-Modus:** im Code-Modus schreiben/ausführen, ohne bei jeder
  einzelnen Änderung nachzufragen (`POST /api/focus-mode`) — eine vom
  Nutzer selbst eingeschaltete, andere Bestätigungs-Policy statt eines
  Umgehens des Permission-Systems; CRITICAL bleibt immer bestätigungspflichtig
* **Erweiterungsmodus:** sucht sich selbst Programmieraufgaben (über das
  Chat-Modell, ausgehend vom Gedächtnis) und arbeitet sie ab — für
  unbeaufsichtigten Betrieb z. B. über Nacht, mit Pause/Fortsetzen/Stopp und
  einer Selbstabschaltung nach wiederholten Fehlschlägen in Folge
  (`POST /api/extension-mode/{start|pause|resume|stop}`, Autonomiestufe 3)
  — siehe `server/README.md`
* WebSocket an alle Geräte gleichzeitig
* Speech-to-Text über Whisper (eigener API-Schlüssel)
* **Phase 1 (Agent Mode):** Planner/Executor mit Error Recovery, Task History,
  ein fünfstufiges Permission-System (SAFE…CRITICAL) mit echtem
  Bestätigungs-Round-Trip, ein Undo-System, ein filterbares Audit Log —
  siehe `server/README.md`
* **Autonomy V1:** Jarvis verfolgt Ziele selbstständig im Hintergrund —
  planen, entscheiden, ausführen, **unabhängig nachprüfen**, aus Fehlern
  einen anderen Weg wählen. Mit Autonomiestufen 0–4, Budgets und Watchdog
  gegen Endlosschleifen, Pause/Weiter/Stopp jederzeit, und einem Event-
  Mechanismus, der bei unklarer Ursache fragt statt zu handeln — siehe
  `server/README.md` und `../docs/JARVIS.md` §8
* Installierbar auf dem Handy als App (Manifest, Icons, Service Worker) —
  siehe `web/README.md`
* **Kommando-Palette (F3/Strg+K):** Action Search + Tool Explorer direkt in
  der Oberfläche — Werkzeuge suchen (dieselbe Rangfolge wie im Chat),
  favorisieren, abschalten, alles ohne Modell-Umweg (`GET`/`POST
  /api/tools/*`), dazu gespeicherte **Makros per Klick ausführen**
  (`GET /api/macros`). Ein kleiner, eigener HotkeyManager: registrierbare,
  kontextabhängige Tastenkürzel mit Export/Import — siehe `web/README.md`
* **Verlauf + Benachrichtigungen:** Audit Log und Rückgängig-Historie direkt
  in der Oberfläche sichtbar und bedienbar (`GET`/`POST /api/undo`,
  `GET /api/audit`), dazu Browser-Benachrichtigungen für Bestätigungsanfragen
  und abgeschlossene Ziele, wenn der Tab gerade nicht im Vordergrund ist —
  siehe `web/README.md`
* **Health-Check + Doku-Generator:** `GET /api/health` meldet jede bekannte
  Abhängigkeit (git, ffmpeg, docker, psutil, …) mit Installationshinweis,
  wenn sie fehlt; `python -m jarvis --generate-docs` schreibt die
  vollständige Werkzeugreferenz (`docs/WERKZEUGE.md`) direkt aus der
  laufenden Registry, nie von Hand gepflegt — siehe `server/README.md`
* **Handybedienung:** alle Bedienelemente auf Fingergröße (44 px), Eingabe
  mit 16 px, damit iOS beim Tippen nicht zoomt; geprüft auf iPhone SE/13,
  Pixel 7 und Galaxy Fold (280 px) — ohne horizontalen Überlauf.
  `python -m jarvis --open-network` nennt beim Start die Adresse, die sich
  auf dem Handy eintippen lässt, samt einer zweiten, über Tailscale
  erreichbaren Adresse, wenn eingerichtet — funktioniert dann auch
  außerhalb des eigenen Netzwerks (mobile Daten, fremdes WLAN), siehe
  `web/README.md`

Offen (siehe `ROADMAP.md` für die volle Reihenfolge):

1. Chat-Modell auf der echten Maschine wählen und messen
2. Memory-Tiers (Phase 2) — Metadatenfelder erledigt: jeder Knoten trägt
   jetzt `importance` (fließt in die Rangfolge beim Abruf ein), `source`
   und echte `created`/`updated`-Zeitstempel, im Wissensnetz sichtbar und
   die Wichtigkeit dort auch bearbeitbar. Project-Ebene existiert bereits
   (`kind="projekt"`, siehe „Erinnert sich an frühere Arbeit"). Offen bleibt
   eine eigene Session-Ebene zwischen Short- und Long-Term.
3. Multi-Model-Router (Phase 2) — erster Schritt fertig: `fast_model` +
   `complexity.is_simple()` unterscheiden einfach/komplex für zwei Modelle.
   Offen bleiben mehr als zwei Modelle sowie die Dimensionen
   privacy/cost/latency und ein Ollama-Umschalter für Nicht-Ollama-Backends.
4. Skills (Phase 3/4) — `screen_capture`, `web_search`, `mouse_keyboard` und
   `open_program` sind inzwischen gebaut (`desktop.screen.capture`,
   `search.web`, `desktop.mouse.*`/`desktop.keyboard.*`, `search.apps.open`)
