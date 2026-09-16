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
4. **Jarvis-Server fehlt vollständig.** Ohne ihn führt die Oberfläche nichts aus
   und sagt das auch so.
