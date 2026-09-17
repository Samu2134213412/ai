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
   Gedächtnis; `qwen3-coder:30b` für Code, angesprochen über CodePilot Remote
   statt direkt. Begründung und VRAM-Rechnung in `../jarvis/README.md`.
2. **Der Coding-Agent ist ein Werkzeug.** `codepilot_task` meldet Erfolg genau
   dann, wenn CodePilot einen Diff und eine Testausgabe geliefert hat. Damit
   gilt die Grundregel auch eine Ebene höher.
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
