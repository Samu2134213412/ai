# Jarvis-Server

```powershell
cd jarvis\server
pip install -r requirements.txt
python -m jarvis
```

Der erste Start legt `%USERPROFILE%\.jarvis\jarvis.json` an, sagt, wo der
Arbeitsbereich liegt, und meldet, was noch fehlt. Dann `http://127.0.0.1:8770/`
öffnen.

Fürs Handy:

```powershell
python -m jarvis --open-network
```

Das bindet auf alle Schnittstellen **und erzeugt ein Token**. Die vollständige
Adresse samt Token steht danach im Terminal. Ohne Token bindet der Server nicht
offen — er lehnt Anfragen mit 503 ab, statt sich ungeschützt zu öffnen.

## Wie ein Zug abläuft

```
Nachricht
   │
   ├─► Router ──── eindeutiger Befehl? ──► Werkzeug ──┐
   │                                                   │
   ├─► Gedächtnis ─── passende Erinnerungen ──┐        │
   │                                          ▼        │
   └─► Agent ──► Ollama plant ──► Werkzeuge ──┴────────┤
                                                       ▼
                                                  Wächter
                                                       │
                                                       ▼
                                             belegte Antwort
```

**Der Router zuerst.** „Erstelle test.txt auf dem Desktop mit dem Inhalt X" wird
deterministisch erkannt und sofort ausgeführt. Das Modell wird gar nicht erst
gefragt und kann folglich auch nichts erfinden. Was nicht sicher erkannt wird,
geht an den Agenten — im Zweifel greift der Router nicht.

**Der Wächter zuletzt.** Er ist der Grund, warum dieses Projekt neu gebaut wurde.

Zwischen „Werkzeug ausgewählt" und „Werkzeug ausgeführt" sitzt seit Phase 1
ein weiterer, für keinen Aufrufer umgehbarer Schritt — Router-Direkttreffer,
Chat-Loop, Code-Modus und Agent Mode laufen alle durch dieselbe Stelle
(`Agent._run_tool`):

```
Werkzeug ausgewählt
   │
   ▼
Permission-Gate ──── Bestätigung nötig? ──► warten auf Antwort ──┐
   │ (SAFE/erlaubt)                                              │
   ▼                                                             ▼
Undo-Snapshot                                              abgelehnt/Timeout
   │                                                             │
   ▼                                                             ▼
ausführen                                              ehrlicher Fehlschlag
   │
   ▼
Audit-Log-Eintrag
```

## Agent Mode

Für Aufträge, die mehrere Schritte brauchen ("Bring dieses Projekt zum
Laufen"), gibt es neben Chat- und Code-Modus einen dritten: **Agent-Modus**.

1. **Planner** (`planner.py`) fragt das Modell nach einer nummerierten
   Schrittliste. Antwortet es nicht brauchbar, wird der ganze Auftrag ehrlich
   als *ein* Schritt behandelt — nie ein vorgetäuschter Plan.
2. **Executor** (`Agent.handle_agent_task`) führt die Schritte nacheinander
   aus, über denselben Werkzeug-Loop wie der Chat-Modus.
3. **Error Recovery**: scheitert ein Schritt, wird nicht sofort aufgegeben —
   ein neuer Versuch mit dem Fehler als Kontext, bis zu `max_step_retries`
   (Vorgabe 2). Kein endloses Wiederholen.
4. **Task History / State Manager** (`tasks.py`): jeder Auftrag ist eine
   `Task` mit benannten `TaskStep`s, persistent in `aufgaben.sqlite3`,
   abrufbar über `GET /api/tasks` bzw. `GET /api/tasks/{id}`.

Jeder Schritt sendet Ereignisse (`task.created`, `task.step.started`,
`task.step.retry`, `task.step.finished`, `task.finished`) — in der Oberfläche
sichtbar als eigene Verlaufszeilen, nicht nur als Zustandsband.

## Permission-System

Jedes Werkzeug trägt eine Sicherheitsstufe (`permissions.py`):

| Stufe | Beispiele hier | Automatisch erlaubt? |
|---|---|---|
| `SAFE` | `read_file`, `list_dir`, `memory_search` | immer |
| `READ` | `get_system_info`, `get_cpu_info`, `get_ram_info` | per Vorgabe ja, konfigurierbar |
| `WRITE` | `write_file`, `move_file`, `memory_add`, `undo_last_action` | per Vorgabe **nein** |
| `SYSTEM` | `run_command`, `codepilot_task` | per Vorgabe **nein** |
| `CRITICAL` | `delete_file`, `memory_forget` | **nie automatisch, nicht konfigurierbar** |

Verlangt eine Aktion eine Bestätigung, sendet der Server ein
`permission.requested`-Ereignis (Werkzeug, Stufe, Argumente) an alle Geräte
und **wartet wirklich** — bis zu `permissions.confirmation_timeout` Sekunden
(Vorgabe 300), dann gilt sie als abgelehnt. Jedes Gerät kann antworten: über
die Oberfläche (Erlauben/Ablehnen-Karte im Verlauf), per WebSocket
(`{"type":"permission","request_id":…,"approved":true|false}`) oder über
`POST /api/permission/resolve`.

## Undo / Rückgängig

Vor jedem `write_file`, `delete_file`, `move_file`, `memory_add` und
`memory_forget` sichert `undo.py` den vorherigen Zustand — Dateiinhalt,
Existenz, oder die gelöschte Erinnerung. „Jarvis, mach die letzte Änderung
rückgängig" (oder `POST /api/undo`) macht die letzte solche Aktion rückgängig,
eine bestimmte über ihre `id` (`GET /api/undo` listet sie). Ein
Wiederherstellen, das eine inzwischen neu angelegte Datei überschreiben
würde, wird verweigert statt sie stillschweigend zu ersetzen.

## Audit Log

Jeder Werkzeugaufruf — erlaubt oder verweigert, erfolgreich oder
fehlgeschlagen — landet in `protokoll.sqlite3`: Zeit, ursprüngliche Anfrage,
Werkzeug, Sicherheitsstufe, Argumente, Ergebnis. Filterbar über
`GET /api/audit?tool=…&level=…&ok=…`.

## Code-Modus

Ein dritter Weg, neben Router und Agent: der Schalter „Code-Modus" in der
Oberfläche. Ist er an, geht **jede** Nachricht direkt an `codepilot_task` —
ohne Router, ohne Chat-Modell, ohne Interpretation.

Das ist kein Sonderfall des Agenten, sondern bewusst ein eigener, einfacherer
Pfad: der Nutzer hat den Modus selbst eingeschaltet, das ist die eindeutigste
Aussage, die es geben kann — eindeutiger als jedes erkannte Muster im Text.
Ist CodePilot nicht eingerichtet, kommt die ehrliche Absage statt eines
Rateversuchs (`agent.handle_code`, `tests/test_agent.py`).

### CodePilot startet sich selbst

Läuft CodePilot bei einer Codeaufgabe nicht, startet Jarvis es — **erst dann,
nicht beim Hochfahren**. Der Grund ist das VRAM: `qwen3-coder:30b` belegt rund
18 GB, die sonst dem Chat-Modell fehlen. Ein Dienst, der dauerhaft mitläuft,
nur damit er vielleicht gebraucht wird, kostet genau die Ressource, um die es
hier knapp ist.

Der Beleg sagt hinterher, was passiert ist: `codepilot: lief bereits` oder
`codepilot: von Jarvis gestartet (12 s)`. Klappt der Start nicht, endet die
Aufgabe mit der Begründung und den letzten Zeilen aus
`~/.jarvis/codepilot-start.log` — kein stiller Fehlschlag.

| Feld in `jarvis.json` | |
|---|---|
| `codepilot.autostart` | `true` (Vorgabe). `false` heißt: nur von Hand starten |
| `codepilot.start_dir` | leer = CodePilot im Repo neben `jarvis/` suchen |
| `codepilot.start_timeout` | Sekunden, die auf „antwortet" gewartet wird (90) |

Der gestartete Prozess ist losgelöst und überlebt einen Neustart von Jarvis.
Zwei gleichzeitige Codeaufgaben starten ihn nur einmal (`tests/test_codepilot_start.py`).

### Wenn ein Coding-Auftrag scheitert

Bevor die Aufgabe abgeschickt wird, liest Jarvis CodePilots eigenen
Umgebungsbericht (`/api/status`). Fehlt dort Claude Code, Ollama oder das
Code-Modell, bricht er **sofort** mit dieser Auskunft ab, statt eine Minute auf
einen Auftrag zu warten, der scheitern muss.

Scheitert er trotzdem, steht der Grund in der Antwort: `codepilot_task` liest
ihn aus dem `session.failed`-Ereignis und aus dem `error`-Feld der Sitzung.
Vorher meldete die Brücke nur „Status: failed" und verschwieg, was CodePilot
selbst längst wusste — ein Fehlschlag ohne Begründung ist fast so schlecht wie
ein erfundener Erfolg.

Den ganzen Strang prüft CodePilot selbst:

```powershell
cd %USERPROFILE%\jarvis-projekt
start.bat --doctor
```

## Statusmelder für CodePilot

Die Oberfläche zeigt unter „Modelle" live, ob CodePilot läuft und ob die Kette
dahinter (Claude Code, Ollama, das Coder-Modell) bereit ist — ohne dass jemand
in ein Konsolenfenster schauen muss:

* **grau** „Nicht eingerichtet" / „Nicht gestartet"
* **gelb** „Läuft · <Problem>" — z. B. Ollama oder das Modell fehlt
* **grün** „Läuft · bereit"

Der Server prüft das alle vier Sekunden (`registry.codepilot_link.status_snapshot()`,
niemals wirft diese Methode selbst — ein Fehler beim Prüfen zählt als „nicht
bereit", nicht als Absturz der Statusschleife) und schickt nur eine Meldung,
wenn sich der Zustand ändert (`codepilot_status` über WebSocket, dasselbe Feld
auch in `/api/health` und im `hello`-Frame).

## Speech-to-Text (Whisper)

Der Mikrofon-Knopf im Bedienfeld nimmt über den Browser auf und schickt die
Aufnahme an `/api/whisper/transcribe`, das sie an die Whisper-API von OpenAI
weiterreicht. Wie bei jedem Werkzeug gilt: **Text kommt nur zurück, wenn
Whisper tatsächlich geantwortet hat.** Ohne Schlüssel, bei einem Netzfehler,
einer Ablehnung oder einer leeren Antwort meldet Jarvis das als Fehlschlag —
und erfindet keinen Text.

Der eigene API-Schlüssel wird einmalig im Feld „Spracheingabe" eingetragen
(`PUT /api/whisper/key`) und liegt danach nur in `jarvis.json` auf dem
Jarvis-Server, nie im Browser. Leeres Feld speichern löscht ihn wieder.

| Feld in `jarvis.json` | |
|---|---|
| `whisper.api_key` | leer = Speech-to-Text aus |
| `whisper.model` | `whisper-1` (Vorgabe) |
| `whisper.timeout` | Sekunden, Vorgabe 30 |

## Die Grundregel als Mechanismus

> Eine reale Aktion darf nur dann als erfolgreich gemeldet werden, wenn ein
> Werkzeug tatsächlich lief und Erfolg zurückgab.

Zwei Ebenen setzen das durch, keine davon ist ein Prompt:

1. **Herkunft aus Daten.** `provenance` wird aus der Liste der `ToolResult`s
   berechnet, nie aus dem Text. Die Oberfläche zeigt „Tool-Beleg" genau dann,
   wenn einer vorliegt.
2. **Behauptungssperre.** Behauptet der Text eine erledigte Aktion, ohne dass ein
   erfolgreiches `ToolResult` dahintersteht, wird er **verworfen** und durch die
   ehrliche Absage ersetzt. Nicht markiert — ersetzt.

`tests/test_guard.py` und `tests/test_agent.py` bilden dafür genau die Fälle
nach, an denen der Vorgänger scheiterte: eine behauptete `gaming.txt` und ein
behauptetes `py_compile`. Geprüft wird beides — was der Nutzer zu sehen bekommt,
**und** was auf der Festplatte liegt.

Der Systemprompt sagt dem Modell dieselbe Regel. Das ist der Gürtel. Der Wächter
ist der Hosenträger.

## Werkzeuge

| Werkzeug | |
|---|---|
| `write_file` `read_file` `list_dir` `search_files` `move_file` | Dateien, nur innerhalb der freigegebenen Wurzeln |
| `delete_file` | **CRITICAL** — löscht eine Datei, immer mit Bestätigung |
| `get_system_info` `get_cpu_info` `get_ram_info` `get_disk_info` `list_processes` | Systemwerte, echt gemessen |
| `memory_search` `memory_add` `memory_link` | Langzeitgedächtnis |
| `memory_forget` | **CRITICAL** — löscht eine Erinnerung endgültig |
| `undo_last_action` `list_undoable` | letzte(n) Änderung(en) rückgängig machen bzw. ansehen |
| `run_command` | **aus per Voreinstellung**, Allowlist nötig |
| `codepilot_task` | nur wenn CodePilot eingerichtet ist |

Noch nicht gebaut und in der Oberfläche als „fehlt" sichtbar: `screen_capture`,
`web_search`, `mouse_keyboard`, `open_program`.

### Sicherheit

* **Pfadgrenze.** Jeder Pfad wird aufgelöst und gegen `roots` geprüft. `..` und
  Symlinks, die hinausführen, werden abgewiesen — nicht nur wörtliches `..`.
* **`run_command` ist aus.** Einschalten ist eine bewusste Entscheidung, und ohne
  Allowlist läuft trotzdem nichts. Es gibt **kein** `shell=True`, also keine
  Ketten mit `&&`, `|` oder `$()`: der Befehl wird mit `shlex` zerlegt und das
  Programm direkt gestartet.
* **Kein offener Bind ohne Token.** Sonst 503.

Empfohlene Allowlist für den Anfang: `python`, `pip`, `pytest`, `git`, `node`,
`npm`, `ollama`, `echo`, `where`, `dir`.

## Konfiguration

```json
{
  "host": "127.0.0.1",
  "port": 8770,
  "token": "",
  "model": "qwen3:14b",
  "ollama_url": "http://127.0.0.1:11434",
  "roots": ["C:\\Users\\DeinName\\Desktop"],
  "shell": {"enabled": false, "allowlist": [], "timeout": 60},
  "codepilot": {"url": "http://127.0.0.1:8765", "token": "", "project_id": ""},
  "whisper": {"api_key": "", "model": "whisper-1", "timeout": 30},
  "permissions": {"confirm_read": false, "confirm_write": true,
                  "confirm_system": true, "confirmation_timeout": 300.0}
}
```

`permissions.confirm_read`/`confirm_write`/`confirm_system` sind
einstellbar. SAFE ist immer automatisch erlaubt, CRITICAL immer
bestätigungspflichtig — beides absichtlich **kein** Feld hier.

`codepilot.token` ist ein Gerätetoken aus CodePilot Remote (`server/`), die
`project_id` das dortige Projekt. Erst wenn beides steht, erscheint
`codepilot_task` als verfügbares Werkzeug.

## Schnittstelle

| | |
|---|---|
| `GET /` | die Oberfläche aus `jarvis/web` |
| `GET /api/health` | Modelle, Werkzeuge, Ollama-Zustand, offene Probleme |
| `GET`/`PUT /api/memory` | das Wissensnetz |
| `GET /api/memory/search?q=` | gewichtete Begriffssuche |
| `POST /api/command` | ein Zug ohne WebSocket, für Skripte (`mode`: `chat`/`code`/`agent`) |
| `PUT /api/whisper/key` | eigenen Whisper-API-Schlüssel eintragen/löschen |
| `POST /api/whisper/transcribe` | Audio → Text über Whisper |
| `GET /api/audit` | Audit Log, filterbar nach `tool`/`level`/`ok` |
| `GET /api/undo`, `POST /api/undo` | rückgängig machbare Änderungen ansehen / eine rückgängig machen |
| `POST /api/permission/resolve` | eine offene Bestätigungsanfrage beantworten |
| `GET /api/tasks`, `GET /api/tasks/{id}` | Task History (Agent Mode) |
| `WS /ws` | Zustand, Nachrichten, Telemetrie, Gedächtnis, CodePilot-Status, Permission-Anfragen, Task-Ereignisse |

Ein Zug geht an **alle** offenen Verbindungen. Was am PC angefangen wird, läuft
auf dem Handy weiter — dieselbe Sitzung, derselbe Verlauf, dasselbe Gedächtnis.

## Tests

```bash
python -m pytest -q      # 237 Tests
```

Sie brauchen weder Ollama noch CodePilot noch einen echten Whisper-Schlüssel:
das Modell wird durch ein vorgegebenes ersetzt (damit sich auch prüfen lässt,
was passiert, wenn es lügt), und CodePilot sowie Whisper laufen gegen einen
echten Mini-HTTP-Server statt einen gefälschten Client.
