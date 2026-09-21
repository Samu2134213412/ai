# Jarvis — Übernahme und Ist-Zustand

Stand: 2026-09-16. Dieses Dokument hält fest, was beim Übernehmen des
Jarvis-Projekts **tatsächlich vorgefunden** wurde, und was nur behauptet,
geplant oder unbekannt ist. Es wird bei jedem Entwicklungsschritt
fortgeschrieben, damit der Kontext nicht — wie bei den bisherigen Anläufen —
zwischen den Sitzungen verloren geht.

Sprache: Deutsch, weil dies das Übergabedokument des Projektinhabers ist. Der
Code und die übrigen `docs/` bleiben englisch.

---

## 1. Zielbild

Jarvis soll ein persönlicher KI-Assistent auf dem eigenen PC werden:
deutschsprachig, mit Langzeitgedächtnis, der Programme und Dateien bedient,
den Bildschirm sieht, mehrstufige Aufgaben erledigt und Abläufe als
wiederverwendbare Skills lernt.

Die Grundaufteilung:

| Schicht | Aufgabe |
|---|---|
| LLM | Denken und Planen |
| Tools | Tatsächliches Handeln |
| Memory | Langfristiges Wissen |
| Skills | Bekannte wiederverwendbare Abläufe |

Das LLM simuliert nichts selbst. Es plant, und gehandelt wird über echte Tools.

---

## 2. Die nicht verhandelbare Regel

Der bisherige Jarvis lief auf `llama3.2:3b` über Ollama und hat **Aktionen als
erfolgreich gemeldet, die nie stattgefunden haben** — eine `gaming.txt`, die es
nicht gab; ein `py_compile`, das nie lief.

> **Jarvis darf eine reale Aktion nur dann als erfolgreich melden, wenn ein Tool
> tatsächlich ausgeführt wurde und ein erfolgreiches Ergebnis zurückgegeben hat.**

Daraus folgt, verbindlich für jede weitere Implementierung:

* Die Erfolgsmeldung an den Nutzer wird **aus dem Tool-Result erzeugt**, nicht
  aus dem Fließtext des Modells. Eine Behauptung des LLM ist niemals ein Beleg.
* Fehlt das Tool: *„Das kann ich aktuell noch nicht ausführen, weil mir dafür
  kein Tool zur Verfügung steht."*
* Schlägt das Tool fehl: *„Die Aktion ist fehlgeschlagen: …"* mit dem echten
  Fehler.
* Erfolg wird nie erfunden.

Diese Regel ist testbar und muss durch Tests abgesichert sein, nicht durch
Prompt-Formulierungen. Ein Prompt ist eine Bitte; ein Test ist eine Zusage.

---

## 3. Ist-Zustand (gemessen, nicht angenommen)

Die Analyse lief in einem Linux-Cloud-Container, **nicht** auf dem Windows-PC.

| Prüfung | Ergebnis |
|---|---|
| Jarvis-Code in `Samu2134213412/ai` | **nicht vorhanden** — 0 Treffer für `jarvis` (case-insensitive, alle Dateien, alle Branches) |
| Git-Historie des Repos | 3 Commits, alle **CodePilot Remote** |
| Weitere Repos des Kontos | nur `Samu2134213412/tiefenrausch` — kein Jarvis |
| `C:\Users\SohndesDrachen\Desktop\jarvis` | vom Container aus **nicht erreichbar** |

**Der bisherige Jarvis-Code wurde damit noch nicht analysiert.** Alles, was in
der Projektübergabe über `jarvis.py`, `memory.py`, den Direct Action Router und
die Tool-Definitionen steht, ist bisher Beschreibung aus zweiter Hand und keine
Feststellung am Code. Sobald der Code vorliegt, wird dieser Abschnitt durch eine
echte Code-Analyse ersetzt.

### Bekannt aus der Übergabe (unverifiziert)

* Ollama `0.32.15`, Modell `llama3.2:3b`, im Code als `MODEL = "llama3.2:3b"`.
* Ein echtes `write_file`-Tool wurde eingebaut (schreibt Datei, gibt Pfad und
  Erfolg/Fehler zurück) — das kleine Modell rief es trotzdem oft nicht auf.
* Deshalb zusätzlich ein **Direct Action Router**: eindeutige Befehle werden
  deterministisch (teils per Regex) erkannt und direkt an das Tool geleitet,
  statt sie dem LLM zu überlassen. Danach funktionierte die Dateierstellung.
* Tool-Definitionen bestanden u.a. für `get_system_info`, `get_cpu_info`,
  `get_ram_info` und weitere — **die Liste der Übergabe bricht hier ab.**

### Hardware

| | |
|---|---|
| Haupt-PC | Ryzen 7 7800X3D, Radeon RX 7900 XTX, Windows 11 |
| Nebengerät | Raspberry Pi 4 Model B, 2 GB RAM, SD-Karte |

Der Pi soll langfristig einzelne Dienste dauerhaft tragen. Das schwere LLM muss
dort nicht laufen.

---

## 4. Wiederverwendbare Bausteine im Repo

`Samu2134213412/ai` enthält **CodePilot Remote** (5.008 Zeilen Python,
77 Tests grün). Das ist zwar ein anderes Produkt, löst aber mehrere
Jarvis-Kernprobleme bereits produktionsreif:

| Modul | Zeilen | Wert für Jarvis |
|---|---|---|
| `server/codepilot/bridge/claude_session.py` | 475 | Agent als echter Subprozess, typisierte Result-Events — **das Modell kann den Erfolg gar nicht behaupten** |
| `server/codepilot/bridge/permission_mcp.py` | 167 | Tool-Freigabe über MCP, jeder Tool-Call geht durch eine echte Entscheidung |
| `server/codepilot/bridge/approvals.py` | 128 | Freigabe-Round-Trip, verifiziert gegen einen echten MCP-Kindprozess |
| `server/codepilot/security.py` | 166 | Pfad-Containment, Projekt-Allowlist, Traversal- und Symlink-Schutz |
| `server/codepilot/providers/ollama.py` | 66 | Ollama-Anbindung inkl. Modell-Health und „Modell fehlt"-Erkennung |
| `server/codepilot/detect.py` / `doctor.py` | 245 / 352 | Systeminfo auslesen, Diagnose der gesamten Kette |
| `server/codepilot/events.py` / `db.py` | 94 / 253 | Event-Log mit lückenloser `seq`, Replay nach Verbindungsabbruch |
| `server/codepilot/compat_proxy.py` | 172 | Umgeht den `count_tokens`-404-Sturm gegen Ollama (ollama/ollama#13949) |

Die Architekturentscheidung für Jarvis lautet daher: **nicht neben CodePilot
bauen, sondern dessen bewährte Schichten mitbenutzen.** Jarvis zieht nach
`jarvis/` in diesem Repo, neben `server/` und `mobile/`.

---

## 5. Getroffene Entscheidungen

1. **Zwei Modelle statt einem.** Ein Chat-Modell für Gespräch, Planung und
   Gedächtnis; `qwen3-coder:30b` für Code. Begründung und VRAM-Rechnung in
   `../jarvis/README.md`. ~~Angesprochen über CodePilot Remote statt direkt.~~
   **Überholt, siehe Abschnitt 10:** Jarvis spricht das Code-Modell direkt an.
2. ~~**Der Coding-Agent ist ein Werkzeug.** `codepilot_task` meldet Erfolg
   genau dann, wenn CodePilot einen Diff und eine Testausgabe geliefert hat.~~
   **Überholt, siehe Abschnitt 10:** Der Beleg kommt jetzt aus Jarvis' eigenen
   Werkzeugergebnissen plus einer Syntaxprüfung der geänderten Dateien. Die
   Grundregel gilt damit nicht mehr eine Ebene höher, sondern auf derselben
   Ebene wie überall sonst — und ist dadurch nachprüfbar statt geglaubt.
3. **Die Oberfläche ist eine Webseite**, keine zwei Apps — damit läuft dieselbe
   Bedienung auf PC und Handy. Liegt in `../jarvis/web/`.
4. **Farbe trägt Bedeutung.** Cyan = Ruhezustand, Gold = das Modell denkt,
   Weißglut = ein Werkzeug läuft tatsächlich, Rot = fehlgeschlagen. Ein
   erfundener Erfolg hat kein Weißglut und keine Druckwellen.

## 6. Offene Punkte

1. ~~**Jarvis-Code fehlt.**~~ **Geklärt, negativ:** Auf dem Windows-PC wurde
   `C:\Users\SohndesDrachen\jarvis` geprüft (`dir jarvis`) — der Ordner enthält
   **0 Dateien**, nur einen alten `.venv`. Kein `jarvis.py`, kein `memory.py`.
   Der alte Quellcode existiert auf dieser Maschine nicht mehr; ob er woanders
   liegt oder gelöscht wurde, ist unbekannt. Es gibt also nichts mehr
   anzubinden oder gegen die neue Fassung abzugleichen — der Server in
   `../jarvis/server/` ist ab jetzt die einzige Implementierung.
2. **Die Übergabe bricht in Abschnitt 6 ab** (mitten in `search_file_`). Die
   vollständige Tool-Liste und alle folgenden Abschnitte fehlen noch.
3. **Welches Chat-Modell** konkret — zu entscheiden, sobald klar ist, welche
   Werkzeugschnittstelle der alte Code erwartet.
4. ~~**Jarvis-Server fehlt vollständig.**~~ **Überholt, siehe Abschnitt 7:**
   der Server existiert, ist ausgebaut und hat 157 grüne Tests.

---

## 7. Ist-Zustand vor dem Agent-Ausbau (2026-09-17, gemessen am Code)

Anlass: Auftrag, Jarvis von einem Sprach-/Chat-Assistenten zu einem modularen
Agenten auszubauen (Agent Mode, Permission System, Undo, Memory-Tiers,
Skills, Voice, Multi-Model-Router, ...). Dieser Abschnitt hält fest, was
**tatsächlich im Code steht** (`jarvis/server/jarvis/`, 4.409 Zeilen,
157 Tests grün — `python -m pytest -q` in `jarvis/server`), bevor irgendetwas
Neues gebaut wird, damit nichts doppelt entsteht.

### 7.1 Was schon da ist

| Bereich | Datei(en) | Zustand |
|---|---|---|
| HTTP + WebSocket, ein Hub für alle Geräte | `app.py` | Fertig. `/api/*`, `/ws`, Telemetrie- und CodePilot-Statusschleifen im Lifespan. |
| Direct Action Router | `router.py` | Fertig. Regex-Erkenner für eindeutige Befehle (Datei lesen/schreiben/löschen, Systemwerte, Gedächtnis merken/abrufen) — läuft am Modell vorbei, bewusst konservativ ("im Zweifel nicht greifen"). |
| Agent-Loop | `agent.py` | Fertig, aber **impliziter** ReAct-Loop: `handle()` ruft `OllamaClient.chat` mit Werkzeugschema, bis zu `max_tool_rounds` (Default 6) Runden. Kein expliziter, dem Nutzer sichtbarer Plan mit benannten Schritten, kein Task-Objekt, keine Historie über den laufenden Chat-Verlauf hinaus. |
| Wächter / Self-Check | `guard.py` | Fertig, und bereits genau das Prinzip, das Punkt 12 ("Self Check") verlangt — nur auf Satzebene statt über eigene Agenten: `provenance_of()` berechnet die Herkunft einer Antwort ausschließlich aus `ToolResult`-Listen; `claims_completion()` erkennt Vollzugsbehauptungen im Modelltext per Regex und `verify()` **verwirft** unbelegte Behauptungen statt sie zu markieren. |
| Werkzeugschicht | `tools/base.py` | Fertig. `Registry`/`Tool`/`ToolResult`, erzwingt `ToolResult` als einzige Quelle für Erfolgsmeldungen. Trägt bereits ein `mutating: bool`-Feld — **Metadatum, nirgends ausgewertet** — die Vorstufe eines Permission-Systems. |
| Dateiwerkzeuge | `tools/files.py` | Fertig. `write_file/read_file/list_dir/search_files/delete_file/move_file`, alle über `Workspace` auf eine Root-Allowlist beschränkt (`..`- und Symlink-sicher aufgelöst). |
| Systemwerkzeuge | `tools/system.py` | Fertig. CPU/RAM/Disk/Prozesse über `psutil`, verweigert ehrlich statt zu raten, wenn `psutil` fehlt. `telemetry()` speist die Live-Gauges der Oberfläche. |
| Gedächtniswerkzeuge | `tools/knowledge.py` | Fertig. `memory_search/add/link/forget`, liest nach dem Schreiben zurück, statt dem Erfolg zu vertrauen. |
| Shell | `tools/shell.py` | Fertig, standardmäßig **aus**. Keine echte Shell (`shell=False`, `shlex`-Zerlegung), Allowlist. |
| CodePilot-Brücke | `tools/codepilot.py` | Fertig. `codepilot_task` reicht Codeaufgaben an das bereits produktionsreife CodePilot-Remote-Projekt (`server/`, separates Produkt in diesem Repo) weiter — echtes Claude Code gegen `qwen3-coder:30b`, mit Autostart, Ketten-Gesundheitsprüfung, Poll-Loop, ehrlichem Fehlgrund. **Der Coding-Agent aus Punkt 20 der Aufgabenstellung existiert damit bereits** und wird nicht neu gebaut. |
| Gedächtnis | `memory.py` | Fertig als **ein** Tier: SQLite-Knotengraph, gewichtete Begriffssuche (Titel ×3, `regel`-Art angehoben), automatischer Kontextabruf vor jeder Modellanfrage. Entspricht am ehesten "Long-Term/Project Memory" aus Punkt 4 — aber ohne die geforderten Felder (`importance`, `source`, `confidence`, `timestamp`) und ohne Short-Term/Session-Trennung. |
| Konfiguration | `config.py` | Fertig. Eine JSON-Datei, `roots`-Allowlist, Shell-Policy, CodePilot-Link, Whisper-Key, Token-Zwang sobald nicht-loopback. |
| Speech-to-Text | `whisper.py` | Fertig (voriger Auftrag). Nutzereigener API-Key, ehrlicher Fehlschlag bei jedem Problem. |
| Oberfläche | `web/index.html` (1.381 Zeilen, eine Datei) | Fertig als Kommandozentrale: Chat/Code-Modus-Umschalter, Mikrofon, Wissensnetz (Knoten ziehen/verknüpfen/löschen), Werkzeugliste, CPU/RAM/Disk-Gauges aus der Telemetrie, CodePilot-Statusanzeige, WebSocket mit Reconnect. |

### 7.2 Abgleich gegen die 36 geforderten Punkte

Legende: **Vorhanden** = nichts weiter tun · **Teilweise** = ausbauen, nicht neu bauen · **Fehlt** = neu.

| # | Punkt | Zustand | Einordnung |
|---|---|---|---|
| 1 | Agent Mode | Teilweise (impliziter Loop in `agent.py`) | Phase 1 |
| 2 | Permission System | Fehlt (`mutating` ist unbenutztes Metadatum) | Phase 1 |
| 3 | Undo/Rollback | Fehlt | Phase 1 |
| 4 | Memory System (4 Stufen, Metadatenfelder) | Teilweise (ein Tier, andere Felder) | Phase 2 |
| 5 | Context Awareness | Fehlt | Phase 4 |
| 6 | Screen Understanding | Fehlt (in `PLANNED` vermerkt) | Phase 4 |
| 7 | Computer Control | Teilweise (`run_command` startet Programme aus der Allowlist) | Phase 4 |
| 8 | Voice System | Teilweise (STT fertig, kein TTS/Wake-Word) | Phase 5 |
| 9 | Multi-Model Router | Fehlt (ein Chat-Modell, ein fixer Code-Pfad) | Phase 2 |
| 10 | Local-First AI | Teilweise (läuft bereits nur lokal, kein Umschalter) | Phase 2 |
| 11 | Model Council | Fehlt | Phase 6 |
| 12 | Self Check | Teilweise/im Kern vorhanden (`guard.py`, Satzebene statt Agentenrunde) | Phase 6 baut darauf auf |
| 13 | Plugin/Skill System | Fehlt (Tools sind fest einkompiliert) | Phase 3 |
| 14 | Skill Discovery | Fehlt | Phase 3 |
| 15 | Minecraft-Server-Skill | Fehlt | Phase 3 |
| 16 | PC Monitoring | Teilweise (CPU/RAM/Disk/Prozesse, keine GPU/Netzwerk/Warnschwellen) | Phase 3 |
| 17 | Notification System | Fehlt | Phase 3 |
| 18 | Automation Engine | Fehlt | Phase 6 |
| 19 | Browser Agent | Fehlt | Phase 4 |
| 20 | Coding Agent | **Vorhanden** (CodePilot Remote) | nichts tun |
| 21 | Live Preview | Fehlt für Jarvis/CodePilot-Webprojekte | bei Bedarf, kein eigener Phasen-Slot |
| 22 | Smart Home | Fehlt | Phase 8 |
| 23 | Vision | Fehlt | Phase 8 |
| 24 | Audit Log | Fehlt (nur Live-Events, nicht persistent) | Phase 1 |
| 25 | Dashboard | Teilweise (`web/index.html` ist bereits ein Dashboard, andere Bereiche fehlen) | Phase 7 |
| 26 | Live Agent Visualization | Fehlt | Phase 7 (Grundlage: Phase-1-Task-Events) |
| 27 | Task Queue | Fehlt | Persistenz in Phase 1, Oberfläche in Phase 7 |
| 28 | Error Recovery | Teilweise (Tools scheitern ehrlich, kein Retry/Alternativstrategie) | Phase 1 |
| 29 | Cost Control | Fehlt, aktuell irrelevant (kein Cloud-Modell im Einsatz) | Phase 2/6 |
| 30 | Privacy Control | Teilweise (lokal per Voreinstellung, kein Dashboard) | Phase 7 |
| 31 | Personality | Fehlt | Backlog, keiner Phase explizit zugeordnet |
| 32 | Proactive Assistant | Fehlt | nach Phase 6 (braucht Automation Engine) |
| 33 | Offline Mode | **Weitgehend vorhanden** (alles außer Whisper läuft ohne Internet) | dokumentieren |
| 34 | Event Bus | Teilweise (`Hub` in `app.py` ist ein einfacher Broadcast-Bus) | wird mit Skills (Phase 3) erweitert |
| 35 | Architektur-Baum | Bestehende Struktur ist flacher | siehe 7.3 |
| 36 | Sicherheitsgrundsatz (Understand→Plan→Permission→Execute→Verify→Log) | Understand/Execute/Verify vorhanden, Plan+Permission fehlen, Log nicht persistent | Phase 1 schließt die Lücke |

### 7.3 Architektur-Entscheidung: kein Umbau auf den vorgeschlagenen Ordnerbaum

Die Aufgabenstellung schlägt `core/agents/models/memory/skills/automation/voice/...`
vor. Entschieden wird dagegen, aus demselben Grund wie beim Rust/Python-Split
bei Guardian: **bestehende, getestete Module nicht anfassen, wenn kein
funktionaler Grund dafür besteht.** `agent.py`, `router.py`, `guard.py`,
`memory.py`, `ollama.py`, `config.py` liegen alle flach in `jarvis/` und sind
zusammen mit ihren Tests eingespielt. Sie in einen `core/`- oder `agents/`-Baum
zu verschieben wäre reine Umbenennung mit Regressionsrisiko und keinem
Funktionsgewinn.

Stattdessen: neue Phase-1-Module (`permissions.py`, `audit.py`, `undo.py`,
`tasks.py`, `planner.py`) kommen **auf derselben Ebene** dazu, im Stil der
bestehenden Dateien. Erst wenn ein Bereich in einer späteren Phase groß genug
wird, um ein eigenes Unterpaket zu rechtfertigen (`skills/` in Phase 3,
`voice/` in Phase 5), entsteht ein Unterordner — für neuen Code, nicht als
nachträgliche Verschiebung des bereits funktionierenden.

### 7.4 Nachtrag: Phase 1 abgeschlossen (2026-09-17)

Alle fünf Bausteine aus 7.2 (Agent Mode, Permission System, Audit Log,
Undo/Rollback, Task History) sind gebaut, getestet (237/237, vorher 157) und
live verifiziert — Details, Endpunkte und Konfiguration stehen in
`../jarvis/server/README.md`, der Phasenabschluss in `../jarvis/ROADMAP.md`.
Kurz zusammengefasst, ohne die Analyse oben zu wiederholen:

* Jeder Werkzeugaufruf (Router, Chat-Loop, Code-Modus, Agent Mode) läuft
  durch denselben, einen Durchlauf in `Agent._run_tool` — Permission-Check,
  Undo-Snapshot und Audit-Eintrag sind dort verankert, nicht wiederholt an
  mehreren Stellen.
* `Tool.mutating: bool` wurde durch `Tool.level: PermissionLevel` ersetzt
  (mit `mutating` als abgeleiteter Rückwärtskompatibilitäts-Eigenschaft) —
  keine Verdopplung, sondern dieselbe Stelle, jetzt aussagekräftiger.
* Agent Mode ist ein dritter Modus neben Chat und Code (`mode: "agent"`),
  kein Ersatz für den bestehenden ReAct-Loop: dessen Schleife blieb
  unangetastet, der Executor hat eine eigene, bewusst leicht redundante
  Schleife, um das bestehende, gut getestete `handle()` nicht anzufassen.

Punkt 4 (Memory-Tiers) bleibt wie geplant für Phase 2 offen.

### 7.5 Nachtrag: Installierbar als App auf dem Handy (2026-09-17)

Außerhalb der Phasenreihenfolge, auf expliziten Wunsch: `jarvis/web/`
bekam ein `manifest.webmanifest`, einen Service Worker und generierte
Icons (im Stil der Oberfläche: Void/Cyan/Gold, „Weißglut plus Iris"),
sodass sich die bestehende, bereits handy-taugliche `index.html` jetzt
über „Zum Startbildschirm hinzufügen" wie eine eigene App installieren
lässt (`display: standalone`). Kein neues UI-Framework, keine native App —
`jarvis/app.py` liefert die drei neuen Dateien nur zusätzlich zu `index.html`
aus, genau wie vorher schon `favicon.ico`. Der Service Worker cached
ausschließlich die statische Hülle, nie `/api/*` oder den WebSocket, damit
die Grundregel (kein Erfolg ohne echtes Tool-Result) nicht durch einen
veralteten Cache unterlaufen werden kann. 3 neue Tests (240/240 grün),
live mit Playwright unter einem iPhone-13-Profil gegen den echten Server
geprüft: Manifest, Apple-Touch-Icon und Service-Worker-Registrierung laden
korrekt, keine neuen Konsolenfehler.

## 8. Autonome Agenten-Schicht — Ist-Zustand vor "Autonomy V1" (2026-09-17)

Neue Aufgabenstellung (24 Punkte): Jarvis soll Ziele selbstständig verfolgen
statt nur auf einzelne Befehle zu reagieren. Wie in Abschnitt 7: erst
Bestandsaufnahme, dann Entscheidung, dann Code — nichts doppelt bauen.

### 8.1 Deckung mit Phase 1 (bereits vorhanden, wird ausgebaut, nicht ersetzt)

| Punkt der Aufgabenstellung | Ist-Zustand | Entscheidung |
|---|---|---|
| 4. Execution Engine (strukturierte Tool-Ergebnisse) | `tools/base.py::ToolResult(ok, summary, evidence, payload)` — entspricht exakt `{success, result, error}` | übernehmen, nicht umbenennen |
| 6. Self-Correction, Retry-Limit | `agent.py::handle_agent_task` wiederholt einen gescheiterten Schritt bis `max_step_retries` mit dem Fehler als Kontext | Grundmechanik vorhanden; **fehlt**: bewusste Auswahl einer *anderen* Strategie statt desselben Prompts erneut — kommt über die DecisionEngine |
| 7. Background Tasks (Task-Objekt, Fortschritt, Task History) | `tasks.py::Task/TaskStep/TaskManager`, persistent, mit Status/Retries/Zeiten | **Lücke gefunden**: `app.py::run_turn` hält ein globales `busy`-Lock über die *gesamte* Laufzeit von `mode="agent"` — der Server ist blockiert, bis das Goal fertig ist. Widerspricht Punkt 7 direkt. Wird umgebaut (8.3) |
| 11. Risk/Permission Engine | `permissions.py`: SAFE/READ/WRITE/SYSTEM/CRITICAL, CRITICAL immer Bestätigung, echter Round-Trip | inhaltlich deckungsgleich mit LOW/MEDIUM/HIGH der Aufgabenstellung; **keine zweite Engine** — stattdessen ein `.risk`-Label auf `PermissionLevel` |
| 12. Undo System | `undo.py::UndoStore`, Snapshot vor jeder mutierenden Aktion, "rückgängig" im Router | vollständig vorhanden, unverändert nutzen |
| 20. Full Audit Log (teilweise) | `audit.py::AuditLog`, filterbar nach tool/level/ok/since; Spalte `task_id` existiert im Schema, wird aber nirgends befüllt | Lücke schließen: `task_id`/`goal_id` beim Aufruf durchreichen, statt neues Log zu bauen |
| 21. Natural Status Updates | `handle_agent_task` schickt `task.step.*` nur als WS-Ereignis (Task-Panel), nicht als Chat-Text pro Mini-Schritt; Chat-Antwort ist bereits eine Zusammenfassung | Verhalten bereits richtig, nur dokumentieren |
| 23. Core Rule (Autonomie ersetzt nicht Determinismus) | `guard.py` + `Agent._run_tool` als einziger Durchlaufpunkt | bleibt die tragende Schicht; jede neue Komponente läuft **durch** `_run_tool`, nie daran vorbei |

### 8.2 Echt fehlend (Punkte 1, 2, 3, 5, 8, 9, 10, 13, 14, 15, 18, 19, 22 — Kern)

Diese Bausteine existieren in keiner Form und werden neu gebaut, als flache
Module neben den bestehenden (gleiche Begründung wie 7.3 — Umbau in einen
`core/agents/...`-Baum hätte nur Regressionsrisiko, keinen Funktionsgewinn):

`autonomy.py`, `goals.py`, `decision.py`, `verification.py`, `watchdog.py`,
`events.py`, `world_state.py`. Erweiterung in `agent.py` (die Loop-Phasen
ANALYZE/SELECT ACTION/VERIFY/REFLECT um die bestehenden PLAN/EXECUTE herum)
und `app.py` (Hintergrund-Ausführung, neue Endpunkte).

**Goal vs. Task — bewusst keine Dopplung:** Die Aufgabenstellung beschreibt
unter Punkt 2 ein „Goal" mit Unterzielen, Prioritäten, Deadlines,
Erfolgs-/Fehlerbedingungen. Das bestehende `Task`/`TaskStep` (Phase 1) deckt
bereits „Auftrag → benannte Schritte → Status → Retry" ab und ist getestet.
Ein zweites, konkurrierendes Ausführungsmodell wäre genau die verbotene
Dopplung. Deshalb: **`Goal` ist die äußere Hülle** (Priorität, Deadline,
Bedingungen, Autonomiestufe, Budget), **`Task` bleibt die innere
Ausführung** (Schritte, Retries, Werkzeugaufrufe) — ein Goal referenziert
genau eine Task für seinen aktuellen Plan. Die Dekomposition eines Goals in
Schritte ist exakt `planner.plan()`, wiederverwendet statt neu geschrieben.

### 8.3 Der eine notwendige Umbau: Hintergrund-Ausführung

`run_turn()` in `app.py` nimmt für **jeden** Modus (`chat`/`code`/`agent`)
dasselbe `busy`-Lock und hält es, bis die komplette Antwort steht. Für
`chat`/`code` ist das richtig (ein Zug nach dem anderen, keine
Race Conditions auf `self.history`). Für ein autonomes Goal ist es falsch:
Punkt 7 verlangt ausdrücklich, dass der Nutzer währenddessen etwas anderes
fragen kann. Der Umbau: `mode="agent"` nimmt das Lock **nicht**, legt das
Goal an, startet die Ausführung über `asyncio.create_task` und antwortet
sofort mit einer Zwischenmeldung ("Ich beginne: …, Ziel-ID …"). Das
Endergebnis kommt asynchron als eigene Chat-Nachricht — genau wie eine
Bestätigungsanfrage heute schon asynchron über den Hub läuft. Der
bestehende Test `test_agent_modus_zerlegt_und_fuehrt_aus` prüft heute das
synchrone Warten auf das Endergebnis; er wird an das neue, bewusst
geänderte Verhalten angepasst — keine übersehene Regression, sondern die
Funktion, die Punkt 7 verlangt.

### 8.4 Was ehrlich zurückgestellt wird

* **Punkt 16 (Spezialisierte Agenten):** eine echte Aufteilung auf mehrere
  Modelle braucht den Multi-Model-Router aus Phase 2, der noch nicht
  existiert. Statt separater "Agenten", die nur dieselbe LLM mit anderem
  Prompt wären, bekommen Schritte eine interne Rollen-Markierung
  (Coding/Research/System/Memory) fürs Protokoll — echte Spezialisierung
  folgt mit Phase 2.
* **Punkt 17 (Parallelität):** unabhängige Goals parallel laufen zu lassen,
  ohne Race Conditions auf gemeinsamen Dateien/Ressourcen einzuführen,
  braucht ein Sperren-Konzept, das sich in diesem Umfang nicht seriös
  mitverifizieren lässt. Goals/Tasks sind als eigenständige Datensätze
  bereits parallelitätsfähig angelegt — die tatsächliche gleichzeitige
  Ausführung kommt erst, wenn sie einzeln getestet werden kann.
* **Minecraft-Absturz-Erkennung, GPU-Temperatur (Beispiele in Punkt 9):**
  Es gibt weder eine Minecraft-Anbindung (Phase 3) noch einen
  GPU-Sensor (`tools/system.py` liest nur CPU/RAM/Disk über `psutil`, keine
  Temperatur). Diese konkreten Beispiele werden nicht vorgetäuscht. Gebaut
  wird der generische Mechanismus (EventBus → Regel → Entscheidung →
  optionale Aktion) plus **ein echtes, heute schon verfügbares** Beispiel:
  wiederholter Fehlschlag desselben Werkzeugs löst bei Autonomiestufe 4
  ein Diagnose-Goal aus einem rein lesenden Werkzeug aus. Domänen-Reaktionen
  wie Minecraft-Neustart docken an denselben Mechanismus an, sobald die
  jeweilige Anbindung existiert.
* **Punkt 13 (World State) — nur wahre Felder:** `active_app`/
  `current_project` aus dem Beispiel der Aufgabenstellung setzen Screen/
  Context Awareness voraus (Phase 4, nicht gebaut). `world_state.py`
  liefert deshalb nur, was heute wirklich messbar ist: Systemwerte,
  Ollama-Erreichbarkeit, Anzahl aktiver Goals/Tasks.

### 8.5 Nachtrag: "Autonomy V1" abgeschlossen (2026-09-21)

Gebaut wie in 8.1–8.3 festgelegt. Die Schleife aus Punkt 1 liegt in
`agent.py` und benutzt an jeder Phase etwas Echtes:

| Phase | Wo | Was wirklich passiert |
|---|---|---|
| ANALYZE | `world_state.snapshot()` | `psutil`-Telemetrie + Ollama-Health. Keine erfundenen Felder (siehe 8.4) |
| PLAN | `planner.plan()` (Phase 1) | unverändert wiederverwendet |
| SELECT ACTION | Modell, nach einem Fehlschlag `DecisionEngine` | Kandidaten kommen vom Modell, die **Auswahl** ist deterministischer Code mit benannten Gewichten; „bisherige Erfahrung" ist die echte Erfolgsquote des Werkzeugs aus dem Audit Log |
| EXECUTE | `Agent._run_tool` (Phase 1) | Autonomiestufe → Berechtigung → Undo-Snapshot → Ausführung → Audit |
| VERIFY | `VerificationEngine` | ein **zweiter, unabhängiger** Werkzeugaufruf (`write_file` wird per `read_file` gegengelesen). Widerspricht er, gilt der Schritt als gescheitert — auch wenn das erste Werkzeug Erfolg meldete |
| REFLECT | Retry + `Watchdog` + Experience Learning | neuer Ansatz statt gleicher Versuch; Lehre als Erinnerung der Art `erfahrung` |

**Neue Module:** `autonomy.py`, `goals.py`, `decision.py`, `verification.py`,
`watchdog.py`, `world_state.py`, `events.py`.
**Neue Endpunkte:** `/api/goals`, `/api/goals/{id}`,
`/api/goals/{id}/{pause|resume|cancel}`, `/api/decisions`, `/api/events`,
`/api/proactive/{id}`.

**Hintergrund-Ausführung (8.3) umgesetzt:** `mode="agent"` nimmt das
`busy`-Lock nicht mehr, `start_goal()` antwortet sofort mit einer
Zwischenmeldung — die bewusst *nichts* über ein Ergebnis behauptet — und
stellt das belegte Ergebnis später als eigene Nachricht zu.
`handle_agent_task()` bleibt als synchroner Einstieg erhalten.

**Abbruch/Pause sind kooperativ, nicht `task.cancel()`.** Es gibt feste
Haltepunkte *zwischen* den Aktionen. Mitten in einem laufenden
Werkzeugaufruf abzubrechen würde die Welt in einem halben Zustand
hinterlassen, den niemand protokolliert hat — genau das, was Punkt 23
ausschließt. Der Preis: ein „Stopp" wirkt erst, wenn die gerade laufende
Aktion fertig ist. Das ist die richtige Richtung, in die man irrt.

#### Korrektur zu 8.4: Punkt 17 ist doch umgesetzt

In 8.4 war Parallelität zurückgestellt worden, weil ein Sperren-Konzept
sich nicht seriös mitverifizieren ließe. Durch die Hintergrund-Ausführung
wurde sie unvermeidlich — also wurde sie gebaut statt ignoriert:

* Verändernde Werkzeuge (WRITE und höher) laufen unter `_mutation_lock`
  streng nacheinander. Damit gehört ein Undo-Snapshot immer zu genau dem
  Zustand, der gleich verändert wird. Lesen bleibt parallel.
* `GoalManager` und `TaskManager` bekommen ein Lock um ihre
  SQLite-Verbindung, die sich jetzt Event-Loop und Worker-Threads teilen.

#### Bewusst geänderte Testverträge

* `test_agent_modus_zerlegt_und_fuehrt_aus` wartet jetzt auf den echten
  Endzustand des Ziels, statt ihn aus der Sofortantwort zu schließen —
  angekündigt in 8.3.
* Die beiden Retry-Tests bekommen je eine Modellantwort mehr, weil die
  DecisionEngine vor jedem Neuversuch genau einmal abwägt.
* `memory.py::KINDS` kennt jetzt `erfahrung`. Ohne das hätte `add()` jede
  Lehre stillschweigend zu `fakt` herabgestuft und der Abruf hätte sie nie
  wiedergefunden.

#### Was geprüft ist

321 Tests grün. `tests/test_autonomy_v1.py` deckt die dreizehn in Punkt 24
genannten Verhaltensweisen über den echten Weg ab. Gegengeprüft durch
gezieltes Sabotieren: ohne die Haltepunkte fallen die Abbruch- und
Pause-Tests; ohne Nachprüfung, Schritt-Budget bzw. Experience Learning
fallen genau die drei zugehörigen Tests. Die Tests hängen also an den
Mechanismen, nicht am Zufall.

Live gegen einen echten HTTP-Server (kein Test-Stub) und echtes Chromium
auf der echten Oberfläche:

* Zielauftrag im Agent-Modus antwortet in 43 ms; das Ziel läuft danach im
  Hintergrund fertig und legt die Datei wirklich an.
* Das Audit Log zeigt `write_file`, gefolgt von einem eigenen `read_file` —
  die unabhängige Nachprüfung hat also wirklich stattgefunden.
* Undo nimmt die vom Ziel geschriebene Datei zurück.
* Pause über den Knopf: Karte wird „pausiert", der Server meldet Status
  `waiting`, die Arbeit steht wirklich still; „Weiter" führt zu Ende.
* `process.crashed` mit `{"name": "Minecraft-Server"}` erzeugt den Vorschlag
  „Finde heraus, warum Minecraft-Server abgestürzt ist" **mit** Rückfrage,
  weil die Ursache nicht als sicher hinterlegt ist.

#### Was weiterhin ehrlich fehlt

* **Punkt 16 (spezialisierte Agenten)** bleibt zurückgestellt — unverändert
  die Begründung aus 8.4: ohne Multi-Model-Router wären das dieselbe LLM mit
  anderem Prompt. Auch die dort angekündigte Rollen-Markierung ist **nicht**
  gebaut; sie hätte ohne echte Spezialisierung nur Etiketten erzeugt.
* **Domänen-Reaktionen** (Minecraft-Neustart, GPU-Temperatur) brauchen
  weiterhin die jeweilige Anbindung. Der generische Mechanismus steht und
  hat ein echtes Beispiel: `Agent._note_reliability` meldet drei
  Fehlschläge desselben Werkzeugs in Folge als `tool.failing` — eine
  beobachtbare Tatsache, kein Sensor, den es nicht gibt.
* **Proaktives Handeln ohne Rückfrage** ist gebaut, aber greift
  absichtlich nirgends von allein: alle mitgelieferten Regeln stehen auf
  „Ursache nicht als sicher hinterlegt", also fragt Jarvis. Wer das ändern
  will, setzt `Rule.known_cause` und Autonomiestufe 4 bewusst selbst.
* **Deadlines und Erfolgs-/Fehlerbedingungen** eines Goals werden
  gespeichert und ausgeliefert, aber noch nicht ausgewertet. Sie stehen im
  Datenmodell, weil Punkt 2 sie verlangt — dass sie heute nichts auslösen,
  steht hier, statt es offen zu lassen.

---

## 9. Das große Tool-System — Ist-Zustand vor "Operator Library" (2026-09-21)

Neue Aufgabenstellung (60 Punkte): aus „Jarvis kann Dateien verwalten" sollen
30–60 konkrete Datei-Operatoren werden, aus „Jarvis kann den PC steuern" 80+
System-Actions. Ziel sind mindestens 400 tatsächlich nutzbare Tools, mit einer
Architektur, die auch 5.000 trägt. Denkmodell: **Blender-Operatoren**, nicht
Features.

Wie in Abschnitt 7 und 8: erst Bestandsaufnahme, dann Entscheidung, dann Code.

### 9.1 Was schon da ist und bleibt

| Punkt der Aufgabenstellung | Ist-Zustand | Entscheidung |
|---|---|---|
| 1. `ToolResult` | `tools/base.py::ToolResult(ok, summary, evidence, payload, duration_ms)` | unverändert übernehmen — das ist die tragende Struktur des ganzen Projekts |
| 1. `ToolRegistry` | `tools/base.py::Registry` mit `add`/`get`/`names`/`schemas`/`call`; `call()` fängt jeden Fehler ab und macht daraus ein ehrliches `ToolResult` | erweitern, nicht ersetzen |
| 1. `ToolExecutor` | `agent.py::Agent._run_tool` — der **eine** Durchlaufpunkt: Autonomiestufe → Permission → Mutations-Lock → Undo-Snapshot → Ausführung → Audit | bleibt der einzige Weg. Jedes neue Tool läuft **durch** ihn, keins daran vorbei |
| 31. Permission Levels | `permissions.py`: SAFE/READ/WRITE/SYSTEM/CRITICAL, dazu `.risk` (LOW/MEDIUM/HIGH) | deckungsgleich mit den fünf geforderten Stufen. **Keine sechste Skala** |
| 29. Undo-System | `undo.py::UndoStore` mit Snapshot vor jeder verändernden Aktion | vorhanden; neue Tools melden über `undoable`, ob sie davon erfasst sind |
| 36. Tool History (teilweise) | `audit.py::AuditLog` protokolliert Tool, Argumente, Erfolg, Dauer, Ziel-ID | Grundlage vorhanden. Ergänzt wird eine tool-zentrierte Sicht (Favoriten, Aufrufzahlen) statt eines zweiten Logs |
| 52. Error Recovery | `agent.py` Retry + `decision.py` für einen *anderen* Ansatz + `watchdog.py` gegen Schleifen | vollständig vorhanden (Autonomy V1), gilt automatisch für alle neuen Tools |
| 34. Parallele Ausführung | `_mutation_lock` serialisiert nur verändernde Tools; Lesen ist bereits parallel | Grundlage vorhanden; Tool-Ketten bauen darauf auf |

### 9.2 Die eine echte Sperre: der Voll-Schema-Dump

`agent.py` ruft an zwei Stellen `self.registry.schemas()` und legt damit **jede**
Werkzeugbeschreibung in **jede** Modellanfrage. Bei heute 16 Tools ist das
unauffällig. Bei 400 Tools sind das grob 60.000 Token pro Anfrage — mehr als
das konfigurierte `context_length` von 8192. Das System würde nicht langsam,
es würde **gar nicht mehr funktionieren**.

Das ist exakt Punkt 2 und 50 der Aufgabenstellung, und es ist die Änderung,
die vor allen Tool-Packs kommen muss: nicht „alle Schemas", sondern eine
Vorauswahl über `ToolDiscovery` — Kernwerkzeuge plus die Top-N zur Anfrage
passenden. Ohne diesen Umbau wäre jedes weitere Tool ein Rückschritt.

### 9.3 Erweitern statt ersetzen

`Tool` ist ein `frozen dataclass` mit fünf Feldern und wird an rund 30 Stellen
positionsbasiert konstruiert. Die geforderten Metadaten (Kategorie, Tags,
Synonyme, Plattformen, Dependencies, Timeout, Undo, Dry-Run, Version,
Beispiele) kommen deshalb als **zusätzliche Felder mit Vorgabewerten** dazu.
Jeder bestehende Aufruf bleibt gültig, kein Test muss angefasst werden.

**IDs:** Die Aufgabenstellung will `system.file.rename` statt
`file_manager_do_everything`. Neue Tools bekommen genau solche gepunkteten
Namen, und Kategorie/Unterkategorie werden daraus abgeleitet. Die sechzehn
bestehenden Namen (`write_file`, `get_cpu_info`, …) **bleiben wie sie sind** —
sie stehen im Router, im Systemprompt und in über hundert Tests. Sie bekommen
ihren gepunkteten Namen als Alias, damit beide Schreibweisen funktionieren.

**Plattform-Ehrlichkeit:** Ein großer Teil der gewünschten System-Tools ist
Windows-spezifisch (Dienste, Clipboard, Fenster, Bluetooth). Der Entwicklungs-
und Testrechner ist Linux, der Zielrechner Windows 11. Es wäre gelogen, 200
Windows-Tools zu registrieren und zu behaupten, sie funktionierten. Stattdessen
deklariert jedes Tool seine `platforms` und seine `requires`, und die
Selbstdiagnose (Punkt 53) meldet ehrlich `UNSUPPORTED_PLATFORM` oder
`MISSING_DEPENDENCY`, bevor jemand es aufruft.

Dependencies auf diesem Rechner geprüft: `psutil`, `PIL`, `httpx`, `yaml`,
`git`, `docker`, `node`, `npm`, `unzip` sind da; `playwright`, `ffmpeg`, `7z`,
`tesseract`, `python-magic` fehlen. Tools, die darauf angewiesen sind, werden
trotzdem gebaut — sie melden dann `MISSING_DEPENDENCY` statt zu scheitern, und
der Installations-Assistent (Punkt 55) fragt, statt blind zu installieren.

### 9.4 Aufbau

```
tools/
  base.py        Tool (erweitert), Registry (erweitert), ToolResult
  catalog.py     ToolContext, Dependency-Probes, Selbstdiagnose
  discovery.py   Keyword/Fuzzy/Tag/Kategorie-Suche, Ranking
  history.py     Tool-Historie und Favoriten
  packs/         die Tool-Packs, je ein Modul pro Sachgebiet
```

Die Reihenfolge der Umsetzung folgt Punkt 57: erst die Infrastruktur
vollständig, dann Pack für Pack. Jedes Pack wird einzeln getestet und
committet, damit der Stand jederzeit lauffähig ist.

---

## 10. Code-Modus: CodePilot ausgebaut, Code-Modell direkt in Jarvis (2026-09-21)

Anlass: Meldung des Projektinhabers, der Code-Modus funktioniere nicht — mit
der Anweisung, CodePilot zu streichen und die Code-KI direkt in Jarvis zu
integrieren.

### 10.1 Warum er nicht funktioniert hat

`Agent.handle_code` prüfte `if "codepilot_task" not in self.registry` und gab
sonst eine Absage zurück. Registriert wurde `codepilot_task` aber nur, wenn
`config.codepilot.project_id` **und** `token` gesetzt waren *und* CodePilot
Remote lief. In einer frischen Installation ist die Projekt-ID leer — der
Code-Modus war also im Normalfall eine Absage, kein Fehler.

Die Kette dahinter war:

```
Jarvis → HTTP → CodePilot Remote → Claude Code (CLI) → Ollama
```

Drei Dienste zwischen der Frage und dem Modell, jeder einzeln zu starten und
einzurichten.

### 10.2 Was jetzt passiert

```
Jarvis → Ollama (qwen3-coder:30b)
```

* **`coder.py`** (neu): Systemprompt für Code, eine eingegrenzte
  Werkzeugauswahl (`CODE_TOOLS`, 23 Namen statt des ganzen Katalogs), die
  Auswertung dessen, was wirklich geändert wurde, und die Syntaxprüfung.
* **`Agent.handle_code`**: läuft über `_run_tool_loop`, das jetzt einen
  eigenen Client, eine eigene Werkzeugliste, einen eigenen Systemprompt und
  ein eigenes Rundenlimit annimmt. **Kein zweiter Ausführungspfad** — dieselbe
  Schleife wie der Agent-Modus, nur anders parametriert.
* **`CodeConfig`** ersetzt `CodePilotConfig`: Modell, Runden, Temperatur,
  Timeout, automatische Nachprüfung.
* Ein zweiter `OllamaClient` in `app.py` mit dem Code-Modell, niedrigerer
  Temperatur und längerem Timeout.

### 10.3 Der eigentliche Gewinn: der Werkzeugpfad

Beim Umweg über CodePilot hat ein **fremder Prozess** die Dateien geschrieben.
Jarvis hat dessen Bericht weitergereicht und konnte ihn weder prüfen noch
zurücknehmen. Jetzt läuft jede Codeänderung durch `Agent._run_tool` und damit
durch dieselben drei Schichten wie jede andere Aktion:

| | vorher (CodePilot) | jetzt |
|---|---|---|
| Permission-System | umgangen — CodePilot hatte eigene MCP-Freigaben | `write_file` ist WRITE, fragt nach Richtlinie |
| Undo | nicht möglich | `POST /api/undo` stellt den alten Inhalt wieder her |
| Audit Log | ein Eintrag „codepilot_task ok" | jeder einzelne Werkzeugaufruf mit Stufe und Argumenten |
| Nachprüfung | Diff + Testausgabe von CodePilot | Jarvis liest die Datei selbst zurück und prüft die Syntax |

Die Nachprüfung folgt der Verification Engine aus Autonomy V1: die Rückmeldung
des schreibenden Werkzeugs allein ist zu wenig. Ist die Datei nach dem
Schreiben syntaktisch kaputt, ist das Ergebnis ein **Fehlschlag**, auch wenn
das Modell „fertig" gesagt hat.

### 10.4 Eine Lücke im Wächter, die dabei aufgefallen ist

`guard._DONE` kannte „geändert" und „aktualisiert", aber **nicht** „angepasst",
„behoben", „implementiert", „ergänzt" — genau die Wörter, mit denen ein
Code-Modell eine Änderung behauptet. Die Behauptungssperre war also
ausgerechnet dort blind, wo sie am nötigsten ist: bei einem Modell, das Code
beschreibt, statt ihn zu schreiben. Das ist der Ausgangsfehler dieses ganzen
Projekts.

Aufgefallen ist das, weil ein neuer Test genau diesen Fall prüft: das Modell
sagt „Ich habe die Datei angepasst" und ruft kein Werkzeug auf. Vorher ging
der Satz durch.

Zwanzig Partizipien ergänzt, satzweise gegen „soll ich", „könnte", „noch
nicht" geprüft wie bisher. Gegenprobe: Angebote und Fragen laufen weiterhin
durch.

### 10.5 Was entfernt wurde

`jarvis/tools/codepilot.py` (380 Zeilen), `tests/test_codepilot_task.py`,
`tests/test_codepilot_start.py`, der Statusmelder in `app.py`, das
CodePilot-Feld in `/api/health`, die Statusanzeige im Frontend.

**CodePilot Remote selbst (`server/`, `mobile/`) bleibt unangetastet** — es ist
ein eigenständiges Produkt in diesem Repo. Entfernt wurde nur Jarvis'
Abhängigkeit davon. `permissions.py` nennt CodePilots `ApprovalBroker`
weiterhin als Herkunft des Freigabe-Musters; das ist eine Quellenangabe, keine
Abhängigkeit.

Eine bestehende `jarvis.json` mit `codepilot`-Block stört nicht: `from_dict`
verwirft unbekannte Abschnitte. Live geprüft — der Server startet damit ohne
Beanstandung.

### 10.6 Live geprüft

Gegen einen echten HTTP-Server mit einem Ollama-Doppel, das das Modell und die
mitgeschickte Werkzeugzahl mitschreibt:

* Der Auftrag ging an **`qwen3-coder:30b`**, nicht an das Chat-Modell, mit
  **22 Werkzeugen** statt aller 75.
* Die Datei wurde wirklich geändert (`multipliziere()` ergänzt).
* Der Beleg zeigt `read_file` → `write_file` → **ein zweites, unabhängiges
  `read_file`**: die Nachprüfung hat stattgefunden.
* Das Audit Log führt jeden Aufruf mit seiner Stufe (`write_file` WRITE).
* `POST /api/undo` hat die Codeänderung zurückgenommen — mit CodePilot war das
  nicht möglich.

355 Tests grün.
