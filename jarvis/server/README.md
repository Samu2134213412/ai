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

## Code-Modus

Ein dritter Weg, neben Router und Agent: der Schalter „Code-Modus" in der
Oberfläche. Ist er an, geht **jede** Nachricht direkt an `codepilot_task` —
ohne Router, ohne Chat-Modell, ohne Interpretation.

Das ist kein Sonderfall des Agenten, sondern bewusst ein eigener, einfacherer
Pfad: der Nutzer hat den Modus selbst eingeschaltet, das ist die eindeutigste
Aussage, die es geben kann — eindeutiger als jedes erkannte Muster im Text.
Ist CodePilot nicht eingerichtet, kommt die ehrliche Absage statt eines
Rateversuchs (`agent.handle_code`, `tests/test_agent.py`).

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
| `write_file` `read_file` `list_dir` `search_files` `delete_file` `move_file` | Dateien, nur innerhalb der freigegebenen Wurzeln |
| `get_system_info` `get_cpu_info` `get_ram_info` `get_disk_info` `list_processes` | Systemwerte, echt gemessen |
| `memory_search` `memory_add` `memory_link` `memory_forget` | Langzeitgedächtnis |
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
  "codepilot": {"url": "http://127.0.0.1:8765", "token": "", "project_id": ""}
}
```

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
| `POST /api/command` | ein Zug ohne WebSocket, für Skripte |
| `WS /ws` | Zustand, Nachrichten, Telemetrie, Gedächtnis |

Ein Zug geht an **alle** offenen Verbindungen. Was am PC angefangen wird, läuft
auf dem Handy weiter — dieselbe Sitzung, derselbe Verlauf, dasselbe Gedächtnis.

## Tests

```bash
python -m pytest -q      # 109 Tests
```

Sie brauchen weder Ollama noch CodePilot: das Modell wird durch ein
vorgegebenes ersetzt, damit sich auch prüfen lässt, was passiert, wenn es lügt.
