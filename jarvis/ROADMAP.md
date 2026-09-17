# Jarvis — Roadmap zum Agenten

Reihenfolge exakt wie beauftragt. Jede Phase beginnt erst, wenn die vorige
vollständig implementiert, getestet und dokumentiert ist — siehe
`../docs/JARVIS.md` Abschnitt 7 für die vollständige Ist-Zustand-Analyse, die
dieser Roadmap zugrunde liegt.

Diese Roadmap dupliziert keine bereits vorhandenen Systeme. Wo ein Punkt
schon existiert, steht das hier, statt ihn erneut einzuplanen.

## Phase 1 — Agent Mode, Permission System, Audit Log, Undo (abgeschlossen)

Baut auf dem bestehenden Agenten (`agent.py`, `router.py`, `guard.py`,
`tools/base.py`) auf, ersetzt ihn nicht.

**Ergebnis:** 237/237 Tests grün (`python -m pytest -q` in `jarvis/server`,
vorher 157). Zusätzlich live verifiziert — echter Server, echter Browser
(Playwright), ein kleiner echter HTTP-Server anstelle von Ollama (kein
Mock): Direktbefehl mit Bestätigungspflicht, Agent-Modus mit Plan/Schritten
und einer Bestätigung mitten im Ablauf, sowie „rückgängig machen" über die
Oberfläche — alle mit echter Wirkung auf der Festplatte geprüft, nicht nur
an der Chat-Antwort.

| Baustein | Neues Modul | Nutzt bereits vorhandenes |
|---|---|---|
| Permission System (SAFE/READ/WRITE/SYSTEM/CRITICAL) | `permissions.py` | `Tool` bekommt ein `level`-Feld statt des unbenutzten `mutating`-Booleans |
| Audit Log | `audit.py` | hängt sich an `Agent._run_tool` — dem einen Punkt, durch den heute schon jeder Werkzeugaufruf läuft (Router-Direkttreffer, Chat-Loop, Code-Modus) |
| Undo/Rollback | `undo.py` | Snapshot vor jedem mutierenden Aufruf, an derselben Stelle |
| Task Manager + Task History | `tasks.py` | neue SQLite-Tabelle, eigene Datei neben `gedaechtnis.sqlite3` |
| Planner + Executor + Error Recovery | `planner.py`, Erweiterung in `agent.py` | expliziter, dem Nutzer sichtbarer Plan für komplexe Aufträge; nutzt denselben `_run_tool`-Durchlauf wie der bestehende Chat-Loop |

Nicht Teil von Phase 1 (laut Vorgabe erst später, hier nicht vorgezogen):
Memory-Tiers mit Metadatenfeldern, Multi-Model-Router, Ollama-Umschalter,
Skills, Minecraft, Systemmonitoring-Erweiterung, Notifications, Computer
Control, Screen Understanding, Browser-Agent, Voice/TTS/Wake-Word,
Automation Engine, Model Council, Self-Check-Mehragentenschema, Dashboard,
Live-Agent-Visualisierung, Task-Queue-Oberfläche, Cost/Privacy-Dashboards,
Personality, Proactive Assistant, Smart Home, Vision.

## Phase 2 — Memory, Model Router, Ollama-Integration, Multi-Model

1. Memory-Tiers: Short-Term (laufender Chat-Verlauf, existiert bereits in
   `Agent.history`), Session, Long-Term (existiert, `memory.py`), Project.
   Erweiterung der bestehenden `Memory`-Zeile um `importance`, `source`,
   `confidence`, `timestamp` (heute nur `created`/`updated` intern, nicht
   nach außen gereicht) — Migration der bestehenden SQLite-Tabelle, kein
   Neubau des Speichers.
2. Model Router: `task_type`/`complexity`/`privacy`/`cost`/`latency`/
   `required_tools` → Modellwahl. Ollama bleibt Standard; die
   `OllamaClient`-Abstraktion in `ollama.py` wird die erste von mehreren
   Implementierungen hinter einem gemeinsamen Interface.
3. Local-First-Umschalter (Local Only/Prefer Local/Hybrid/Cloud Preferred)
   in `config.py`.

## Phase 3 — Skills, Minecraft, System-Monitoring, Notifications

1. Plugin/Skill-System: Skills bekommen ein eigenes Manifest
   (`name`/`description`/`permissions`/`tools`/`commands`/`requirements`)
   und werden über die bestehende `Registry` registriert — kein Parallelbau
   zur Werkzeugschicht.
2. Skill Discovery: Intent → Skill → Aktion, zusätzliche Erkennungsebene
   neben dem bestehenden Direct Action Router.
3. Minecraft-Server-Skill (Status, Start/Stopp/Neustart, Logs, Crash-Analyse,
   Backups, Performance).
4. System-Monitoring erweitert (`tools/system.py`): GPU/VRAM, Netzwerk,
   Warnschwellen.
5. Notification Center mit Prioritäten (info/warning/important/critical),
   aufbauend auf dem bestehenden `Hub`-Broadcast in `app.py`.

## Phase 4 — Computer Control, Screen Understanding, Browser-Agent

1. `open_program`, Fenstersteuerung, Lautstärke — offizielle APIs statt
   UI-Automation, wo möglich. Ergänzt die `PLANNED`-Liste in `tools/__init__.py`.
2. Context Awareness (aktives Fenster/Programm/Projekt).
3. Screen Understanding (Screenshots analysieren, vor jeder Aktion:
   was ist sichtbar → was soll sich ändern → welche Wirkung wird erwartet).
4. Browser-Agent — riskante Aktionen (Käufe, Nachrichten, Kontoänderungen)
   laufen zwingend über das Phase-1-Permission-System, keine Ausnahme.

## Phase 5 — Voice, Wake Word, Interruptions

STT existiert bereits (`whisper.py`). Ergänzt: Wake Word, TTS (modular,
ElevenLabs/lokal/andere APIs austauschbar), Streaming, Unterbrechung der
Sprachausgabe bei erneuter Nutzereingabe.

## Phase 6 — Automation Engine, Model Council, Self Check

1. Automation Engine: Event-basierte Regeln, aufbauend auf dem in Phase 1
   eingeführten Task-/Event-Modell und dem bestehenden `Hub`.
2. Model Council: mehrere Modelle parallel + Judge, nur für Aufgaben, bei
   denen es sich lohnt — baut auf dem Phase-2-Model-Router auf.
3. Self Check als Mehragentenschema (Coder/Reviewer/Tester/Judge) — der
   Wächter (`guard.py`) bleibt die harte Unterschicht, die auch diese
   Agenten nicht umgehen können.

## Phase 7 — Dashboard, Live Agent Visualization, Task Queue, Privacy

1. Dashboard-Bereiche (Home/Chat/Voice/Agents/Tasks/Memory/Skills/
   Automations/Models/System/Logs/Settings) — Erweiterung von
   `web/index.html`, das bereits Gauges/Werkzeugliste/Wissensnetz zeigt.
2. Live Agent Visualization auf Basis der Phase-1-Task-/Step-Events.
3. Task-Queue-Oberfläche auf Basis der Phase-1-`tasks.py`-Persistenz.
4. Privacy-Dashboard: einzeln abschaltbare Berechtigungen, aufbauend auf
   dem Phase-1-Permission-System.

## Phase 8 — Smart Home, Vision, weitere Skills

Home-Assistant-Skill, optionale Kameraanalyse (keine Daueraufnahme ohne
ausdrückliche Aktivierung), weitere Skills nach Bedarf.

## Nach jeder Phase (verbindlich)

1. Build/Tests ausführen (`python -m pytest -q` in `jarvis/server`).
2. Fehler beheben.
3. Regressionstest der vorigen Phasen.
4. Dokumentation aktualisieren (`docs/JARVIS.md`, dieses Dokument).
5. Server tatsächlich starten, Demo tatsächlich durchspielen (WebSocket/HTTP,
   nicht nur Unit-Tests).
6. Erst danach die nächste Phase beginnen.
