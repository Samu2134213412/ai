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

## Autonomy V1 — Zielverfolgung, Entscheidungen, Selbstkorrektur (fertig, 2026-09-21)

Außerhalb der ursprünglichen Phasennummerierung, auf expliziten Wunsch: eine
Vertiefung von Phase 1s Agent Mode, keine neue Phase mit eigener Nummer, um
die bestehende Reihenfolge 2-8 nicht zu verschieben. Vollständige Analyse
und Architekturentscheidung in `../docs/JARVIS.md` Abschnitt 8.

Baut auf Permission System, Audit Log, Undo und Task Manager (Phase 1) auf,
ersetzt keins davon. `Goal` ist die neue äußere Hülle (Priorität, Deadline,
Erfolgs-/Fehlerbedingungen, Autonomiestufe, Budget); `Task` bleibt die
innere Ausführung der Schritte — keine zweite, konkurrierende
Ausführungsmaschine.

| Baustein | Neues Modul | Nutzt bereits vorhandenes |
|---|---|---|
| Autonomy Levels (0-4) | `autonomy.py` | Config-Feld, Enforcement in `Agent._run_tool` |
| Risk-Label LOW/MEDIUM/HIGH | — | `.risk`-Property auf `PermissionLevel`, keine zweite Engine |
| Goal Manager, Dekomposition in Unterziele | `goals.py` | Dekomposition ist `planner.plan()`, Ausführung ist die bestehende `Task`-Maschine |
| Decision Engine | `decision.py` | Erfolgshistorie kommt aus dem bestehenden `AuditLog` |
| Verification Engine | `verification.py` | echte Folge-Aufrufe über bestehende, bereits registrierte Tools |
| Watchdog + Task-Budgets | `watchdog.py` | wird zwischen den Schritten der bestehenden Ausführung befragt |
| Event Bus + ein echtes proaktives Beispiel | `events.py` | Telemetrie-Loop und `_run_tool`-Fehlschläge als reale Quellen |
| World State, Working Memory, Experience Learning | `world_state.py`, Erweiterung in `agent.py` | Erfahrung liegt im bestehenden `MemoryStore` (`kind="erfahrung"`), ersetzt nie die echte Prüfung |
| Hintergrund-Ausführung, Pause/Resume/Cancel, Interrupt | Erweiterung `app.py`/`agent.py`/`router.py` | löst die in §8.3 gefundene Lücke (globales `busy`-Lock blockierte den Server während eines Goals) |

Alle Bausteine der Tabelle sind gebaut. Ergebnis, Live-Verifikation und die
bewusst geänderten Testverträge stehen in `../docs/JARVIS.md` §8.5.
321 Tests grün; `server/tests/test_autonomy_v1.py` deckt die dreizehn in
Punkt 24 der Aufgabenstellung geforderten Verhaltensweisen ab.

Zurückgestellt, mit Begründung in §8.4/§8.5: echte spezialisierte Modelle
(braucht Phase 2s Model Router), domänenspezifische proaktive Beispiele
(Minecraft, GPU-Temperatur — beide Integrationen existieren nicht),
Screen/Context-Awareness-Felder im World State (Phase 4), und die
Auswertung von Deadlines/Erfolgsbedingungen eines Goals (gespeichert, aber
noch ohne Wirkung). **Nicht** mehr zurückgestellt: Parallelität (Punkt 17)
wurde durch die Hintergrund-Ausführung unvermeidlich und ist mit
`_mutation_lock` und Locks auf den SQLite-Ablagen umgesetzt — siehe §8.5.

**Seither ergänzt, auf derselben Grundlage (Permission-System +
Hintergrund-Ausführung):** Fokus-Modus (Code-Modus ohne Bestätigung für
WRITE/SYSTEM, per Schalter, CRITICAL bleibt unberührt) und Erweiterungsmodus
(eine unbeaufsichtigte, budgetlose Schleife aus selbst gestellten
Programmieraufgaben, für Betrieb z. B. über Nacht, mit Selbstabschaltung
nach wiederholten Fehlschlägen) — siehe `server/README.md`.

## Phase 2 — Memory, Model Router, Ollama-Integration, Multi-Model

1. Memory-Tiers: Short-Term (laufender Chat-Verlauf, existiert bereits in
   `Agent.history`), Session, Long-Term (existiert, `memory.py`), Project
   (existiert seit der Wissensnetz-Überarbeitung: `kind="projekt"`, vom
   Code-Modus selbständig befüllt). **Metadatenfelder erledigt:**
   `importance`, `source`, `confidence` sowie echte, nach außen gereichte
   `created`/`updated`-Zeitstempel liegen jetzt auf jedem Knoten — per
   Migration an einer bestehenden SQLite-Tabelle nachgerüstet, kein Neubau.
   `importance` fließt in die Rangfolge beim Abruf ein (0.5 = Vorgabe = keine
   Verschiebung), `replace_graph()` behält `created` jetzt über jeden
   Oberflächen-Speichervorgang hinweg bei, statt es bei jedem Ziehen eines
   Knotens stillschweigend zurückzusetzen. Offen bleibt eine echte
   **Session**-Ebene zwischen Short-Term und Long-Term — noch ohne
   festgelegten Mechanismus.
2. Model Router: `task_type`/`complexity`/`privacy`/`cost`/`latency`/
   `required_tools` → Modellwahl. Ollama bleibt Standard; die
   `OllamaClient`-Abstraktion in `ollama.py` wird die erste von mehreren
   Implementierungen hinter einem gemeinsamen Interface.
   **Erster Schritt erledigt:** `complexity.py` entscheidet nach `complexity`
   (kurz, keine Datei-/System-/Code-Aktion, keine Live-Daten) zwischen genau
   zwei Ollama-Modellen -- `config.fast_model` für einfache Fragen ohne
   Werkzeugschema, sonst das Hauptmodell. `task_type`/`privacy`/`cost`/
   `latency`/`required_tools` sowie mehr als zwei Modelle bleiben offen.
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

1. Fenstersteuerung, Lautstärke — offizielle APIs statt UI-Automation, wo
   möglich. `open_program` (`search.apps.open`) sowie einfache Maus-/
   Tastatursteuerung (`desktop.mouse.*`/`desktop.keyboard.*`) und ein
   Bildschirmfoto (`desktop.screen.capture`) sind bereits gebaut -- die
   `PLANNED`-Liste in `tools/__init__.py` ist damit leer.
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
