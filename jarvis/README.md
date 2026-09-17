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

Jarvis benutzt **zwei** Ollama-Modelle mit klar getrennten Aufgaben. Das zweite
spricht er nicht direkt an, sondern über CodePilot Remote — das Projekt, das in
diesem Repo bereits fertig unter `server/` liegt.

```
   Handy                         PC
     └──────────────┬─────────────┘
                    │  HTTP + WebSocket
         ┌──────────▼───────────┐
         │   Jarvis-Server      │   Router · Gedächtnis · Skills
         └──┬────────────────┬──┘
            │                │
  Gespräch, │                │ alles, was Code ist
  Planen,   │                │
  Erinnern  │                │
     ┌──────▼──────┐   ┌─────▼──────────────────┐
     │   Ollama    │   │  CodePilot Remote       │
     │ Chat-Modell │   │   → Claude Code (CLI)   │
     │   ~7–8 B    │   │   → Ollama qwen3-coder  │
     └─────────────┘   └─────┬──────────────────┘
                             │
                   Dateien · Terminal · Git · Tests
```

Der Gewinn liegt nicht in der Zahl der Modelle, sondern darin, **was
zurückkommt**. Ein Coding-Auftrag an CodePilot endet mit einem Diff und einer
Testausgabe. Das ist ein Beleg. Ein Chat-Modell, das behauptet, den Code
geschrieben zu haben, ist keiner.

Damit gilt die Grundregel des Projekts auch eine Ebene höher: **der Coding-Agent
ist selbst nur ein Werkzeug**, und `codepilot_task` meldet Erfolg genau dann,
wenn CodePilot einen gemeldet hat.

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

## Stand

Fertig und getestet (237 Tests, siehe `ROADMAP.md` für die Phasen):

* Werkzeugschicht mit erzwungenem Beleg — kein Erfolg ohne `ToolResult`
* Direct Action Router für eindeutige Befehle
* Langzeitgedächtnis in SQLite mit selbständigem Abruf vor jeder Modellanfrage
* Agent mit Ollama-Werkzeugaufruf
* `codepilot_task` als Brücke zum Coding-Agenten, per Werkzeugaufruf oder über den Code-Modus-Schalter, der ihn direkt anspricht
* WebSocket an alle Geräte gleichzeitig
* Speech-to-Text über Whisper (eigener API-Schlüssel), CodePilot-Statusmelder
* **Phase 1 (Agent Mode):** Planner/Executor mit Error Recovery, Task History,
  ein fünfstufiges Permission-System (SAFE…CRITICAL) mit echtem
  Bestätigungs-Round-Trip, ein Undo-System, ein filterbares Audit Log —
  siehe `server/README.md`

Offen (siehe `ROADMAP.md` für die volle Reihenfolge):

1. Chat-Modell auf der echten Maschine wählen und messen
2. Memory-Tiers (Short-/Session-/Long-Term/Project) mit Metadatenfeldern (Phase 2)
3. Multi-Model-Router, Ollama-Umschalter (Phase 2)
4. Skills, `screen_capture`, `web_search`, `mouse_keyboard`, `open_program` (Phase 3/4)
