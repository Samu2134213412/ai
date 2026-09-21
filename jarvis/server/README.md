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

## Autonome Zielverfolgung

Über dem Agent Mode liegt seit „Autonomy V1" eine Zielschicht. Ein `Goal`
(`goals.py`) trägt Priorität, Frist, Erfolgs-/Fehlerbedingungen, Fortschritt
und ein Budget; die Ausführung bleibt die schon getestete `Task`-Maschine —
keine zweite Ausführungsmaschine daneben.

Die Schleife in `agent.py`:

```
GOAL → ANALYZE → PLAN → SELECT ACTION → EXECUTE → VERIFY → REFLECT → …
```

* **ANALYZE** (`world_state.py`): echte Telemetrie und Ollama-Erreichbarkeit.
  Keine Felder, die nur so klingen, als wären sie gemessen.
* **SELECT ACTION** nach einem Fehlschlag (`decision.py`): Kandidaten schlägt
  das Modell vor, die **Auswahl** ist deterministischer Code. „Bisherige
  Erfahrung" ist die echte Erfolgsquote des Werkzeugs aus dem Audit Log.
  Jede Abwägung steht in `entscheidungen.sqlite3` (`GET /api/decisions`).
* **VERIFY** (`verification.py`): ein **zweiter, unabhängiger** Aufruf.
  `write_file` wird per `read_file` gegengelesen, `delete_file` durch einen
  fehlschlagenden Lesezugriff bestätigt. Widerspricht die Nachprüfung, gilt
  der Schritt als gescheitert — auch wenn das erste Werkzeug Erfolg meldete.
* **REFLECT**: Retry mit dem echten Fehler als Kontext, `watchdog.py` für
  Budgets und Wiederholungsmuster, und die Lehre als Erinnerung der Art
  `erfahrung`. Eine Erinnerung liefert nur Kontext für die Planung — sie
  ersetzt nie einen Werkzeugaufruf, der aktuelle Zustand wird jedes Mal neu
  geprüft.

**Autonomiestufen** (`autonomy.py`, `autonomy_level` in `jarvis.json`):

| Stufe | Bedeutung |
|---|---|
| 0 | nur Gespräch, keine Aktionen |
| 1 | nur lesend; alles Verändernde braucht Bestätigung |
| 2 | **Vorgabe** — normale Werkzeugregeln, keine eigenständige Zielverfolgung |
| 3 | Zielverfolgung im Hintergrund |
| 4 | zusätzlich: eigenständige Reaktion auf Ereignisse |

Die Stufe kann das Permission-System nur **verschärfen**, nie lockern.

**Im Hintergrund, nicht blockierend:** `mode="agent"` antwortet sofort mit
einer Zwischenmeldung — die nichts über ein Ergebnis behauptet — und arbeitet
daneben weiter. Steuerbar über `POST /api/goals/{id}/{pause|resume|cancel}`
oder im Gespräch („Stopp.", „Pause.", „Mach weiter.", „Versuch Methode B.").
Pause und Abbruch greifen an festen Haltepunkten *zwischen* den Aktionen,
nie mitten in einem laufenden Werkzeugaufruf.

**Ereignisse und Vorschläge** (`events.py`): `POST /api/events` meldet etwas
Beobachtetes; was daraus folgt, entscheidet `ProactiveEngine` — nicht der
Absender und nicht das Modell. Ohne ausdrücklich als sicher hinterlegte
Ursache wird gefragt, nicht gehandelt.

## Permission-System

Jedes Werkzeug trägt eine Sicherheitsstufe (`permissions.py`):

| Stufe | Beispiele hier | Automatisch erlaubt? |
|---|---|---|
| `SAFE` | `read_file`, `list_dir`, `memory_search` | immer |
| `READ` | `get_system_info`, `get_cpu_info`, `get_ram_info` | per Vorgabe ja, konfigurierbar |
| `WRITE` | `write_file`, `move_file`, `memory_add`, `undo_last_action` | per Vorgabe **nein** |
| `SYSTEM` | `run_command`, `files.permissions.change` | per Vorgabe **nein** |
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

Ein dritter Weg, neben Router und Agent: der Schalter Code-Modus in der
Oberfläche. Ist er an, geht **jede** Nachricht an das Code-Modell — ohne
Router, ohne Chat-Modell, ohne Interpretation.

Das ist kein Sonderfall des Agenten, sondern bewusst ein eigener Pfad: der
Nutzer hat den Modus selbst eingeschaltet, das ist die eindeutigste Aussage,
die es geben kann — eindeutiger als jedes erkannte Muster im Text.

### Jarvis programmiert selbst (seit dem Ausbau von CodePilot)

Früher lief der Code-Modus über CodePilot Remote:

```
Jarvis → HTTP → CodePilot → Claude Code → Ollama
```

Drei Dienste zwischen der Frage und dem Modell, von denen jeder einzeln
laufen und eingerichtet sein musste. War einer davon nicht da, konnte der
Code-Modus **gar nichts** — und weil `codepilot.project_id` in einer frischen
Installation leer ist, war genau das der Normalzustand.

Jetzt:

```
Jarvis → Ollama (qwen3-coder:30b)
```

Das Code-Modell ist ein zweiter Draht zu demselben Ollama, mit niedrigerer
Temperatur (bei Code ist Erfindungsreichtum keine Tugend) und längerem
Timeout (ein 30B-Modell braucht beim ersten Aufruf Zeit zum Laden).

Der Gewinn ist nicht nur eine kürzere Kette. Jede Dateiänderung läuft jetzt
durch `Agent._run_tool` und damit durch **Permission-System, Undo-Snapshot und
Audit Log** — dieselben drei Schichten wie bei jeder anderen Aktion. Beim
Umweg über CodePilot hat ein fremder Prozess die Dateien geschrieben; Jarvis
hat nur dessen Bericht weitergereicht und konnte ihn weder prüfen noch
zurücknehmen. Eine Codeänderung lässt sich heute mit `POST /api/undo`
zurücknehmen.

### Was der Code-Modus bekommt

Eine **eingegrenzte** Werkzeugauswahl (`coder.CODE_TOOLS`, rund zwanzig)
statt des ganzen Katalogs: lesen, suchen, schreiben, ausführen. Ein
Code-Auftrag braucht keine Audiogeräte und keine Firewall. Weniger Werkzeuge
heißt außerdem weniger Kontext pro Anfrage und damit mehr Platz für den
eigentlichen Code.

### Nachprüfung statt Vertrauen

Nach den Änderungen liest Jarvis jede geänderte Datei über ein echtes
`read_file` **zurück** und prüft, was prüfbar ist — Python-Syntax über
`ast.parse`, JSON über `json.loads`. Ist die Datei danach kaputt, ist das
Ergebnis ein **Fehlschlag**, kein Erfolg mit Fußnote, auch wenn das Modell
fertig gemeldet hat.

Derselbe Gedanke wie die Verification Engine aus Autonomy V1: die Rückmeldung
des schreibenden Werkzeugs allein ist zu wenig; erst ein zweiter,
unabhängiger Lesevorgang zeigt, was wirklich in der Datei steht.

Die Antwort an den Nutzer entsteht aus den geänderten Dateien plus dem
Prüfergebnis, nie aus dem Satz des Modells. Behauptet das Modell eine
Änderung, die kein Werkzeug belegt, verwirft der Wächter den Text.

| Feld in `jarvis.json` | |
|---|---|
| `code.model` | Das Code-Modell (Vorgabe `qwen3-coder:30b`). Leer = dasselbe wie im Chat |
| `code.max_rounds` | Werkzeugrunden je Auftrag (14) |
| `code.temperature` | Vorgabe 0.1 |
| `code.timeout` | Sekunden je Modellanfrage (600) |
| `code.auto_check` | Nach Änderungen automatisch nachprüfen (an) |

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
  "code": {"model": "qwen3-coder:30b", "max_rounds": 14, "auto_check": true},
  "whisper": {"api_key": "", "model": "whisper-1", "timeout": 30},
  "permissions": {"confirm_read": false, "confirm_write": true,
                  "confirm_system": true, "confirmation_timeout": 300.0}
}
```

`permissions.confirm_read`/`confirm_write`/`confirm_system` sind
einstellbar. SAFE ist immer automatisch erlaubt, CRITICAL immer
bestätigungspflichtig — beides absichtlich **kein** Feld hier.

`code.model` muss in Ollama vorhanden sein (`ollama pull qwen3-coder:30b`).
Fehlt es, meldet `/api/health` es als nicht geladen, und der Code-Modus sagt
beim ersten Auftrag ehrlich, dass das Modell nicht erreichbar ist.

Ein alter `codepilot`-Block in der Datei stört nicht: unbekannte Abschnitte
werden beim Laden ignoriert.

## Schnittstelle

| | |
|---|---|
| `GET /` | die Oberfläche aus `jarvis/web` |
| `GET /manifest.webmanifest`, `GET /service-worker.js`, `GET /icons/*` | Installierbarkeit als App auf dem Handy (siehe `web/README.md`) |
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
| `GET /api/goals`, `GET /api/goals/{id}` | verfolgte Ziele mit Fortschritt, Budget und Entscheidungen |
| `POST /api/goals/{id}/{pause\|resume\|cancel}` | ein laufendes Ziel steuern |
| `GET /api/decisions` | protokollierte Abwägungen der Decision Engine |
| `POST`/`GET /api/events` | ein Ereignis melden / letzte Ereignisse und offene Vorschläge |
| `POST /api/proactive/{id}` | einem proaktiven Vorschlag zustimmen oder ihn ablehnen |
| `WS /ws` | Zustand, Nachrichten, Telemetrie, Gedächtnis, Permission-Anfragen, Task- und Ziel-Ereignisse |

Ein Zug geht an **alle** offenen Verbindungen. Was am PC angefangen wird, läuft
auf dem Handy weiter — dieselbe Sitzung, derselbe Verlauf, dasselbe Gedächtnis.

## Tests

```bash
python -m pytest -q      # 478 Tests
```

Sie brauchen weder Ollama noch einen echten Whisper-Schlüssel:
das Modell wird durch ein vorgegebenes ersetzt (damit sich auch prüfen lässt,
was passiert, wenn es lügt), und Whisper läuft gegen einen
echten Mini-HTTP-Server statt einen gefälschten Client.
