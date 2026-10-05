# tutor – Lern-Tutor im Terminal (lokal mit Ollama)

Ein Chat-Tutor, der **keine fertigen Lösungen** verrät, sondern zum Selbermachen
führt: erst nachfragen, dann Hilfe in Stufen (Leitfrage → Denkanstoß →
Teilschritt). Läuft komplett lokal über [Ollama](https://ollama.com).

```
tutor/
├── main.py            # CLI, Hinweisstufen-Logik, Streaming, Befehle
├── config.yaml        # Modell, temperature, Fach, Sprache, Stufen, Sessions
├── prompts/tutor.md   # System-Prompt mit Regeln + 2 Beispieldialogen
├── requirements.txt
├── sessions/          # gespeicherte Verläufe (*.json)
└── tests/             # Offline-Tests + Live-Check gegen das echte Modell
```

## Installation

Voraussetzungen: Python 3.10+, Ollama installiert und gestartet.

```bash
# 1. Modell laden (~20 GB, braucht ca. 20–24 GB VRAM/RAM)
ollama pull qwen2.5:32b

# 2. Abhängigkeiten
cd tutor
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Kleinere Alternativen bei wenig Speicher: `qwen2.5:14b` oder `qwen2.5:7b`
(in `config.yaml` unter `model` eintragen oder `--modell` beim Start).

## Start

```bash
python main.py                          # Werte aus config.yaml
python main.py --fach "Mathe Klasse 9"  # Fach für diese Sitzung
python main.py --modell qwen2.5:14b --speichern
```

| Befehl           | Wirkung                                                     |
|------------------|-------------------------------------------------------------|
| `/hilfe`         | Befehle anzeigen                                            |
| `/neu [Aufgabe]` | neue Aufgabe, Hinweisstufe und Verlauf zurücksetzen         |
| `/aufgeben`      | vollständige Lösung mit Erklärung (bei < 2 Versuchen mit Rückfrage) |
| `/modell <name>` | Modell wechseln (wird vorher geprüft)                       |
| `/status`        | Aufgabe, Versuche, aktuelle Hinweisstufe                    |
| `/speichern`     | Verlauf nach `sessions/<Datum>.json` schreiben              |
| `/exit`          | beenden (auch Strg+D)                                       |

Strg+C bricht eine laufende Antwort ab, ohne das Programm zu beenden.

## Wie die Hinweisstufen funktionieren

Pro Aufgabe zählt das Programm die Nachrichten des Lernenden. Daraus ergibt
sich die erlaubte Stufe (bei `turns_per_stage: 2`):

| Nachricht | Stufe            |
|-----------|------------------|
| 1–2       | 1 – Leitfrage    |
| 3–4       | 2 – Denkanstoß   |
| ab 5      | 3 – Teilschritt  |
| `/aufgeben` | Lösung freigegeben |

Die Stufe wird bei jeder Anfrage als Status-Block an den System-Prompt
angehängt, sodass das Modell nicht zu früh zu viel verrät. `/neu` setzt den
Zähler zurück. Den Prompt selbst passt man in `prompts/tutor.md` an
(`{{fach}}` und `{{sprache}}` werden aus der Konfiguration ersetzt).

## Fehlermeldungen

- *„Ollama ist unter … nicht erreichbar“* → Ollama-App starten bzw. `ollama serve`.
- *„Das Modell '…' ist nicht installiert“* → `ollama pull <modell>`.

## Läuft das Modell auf der AMD-GPU?

Während (oder kurz nach) einer Antwort in einem zweiten Terminal:

```bash
ollama ps
```

```
NAME           ID            SIZE     PROCESSOR    UNTIL
qwen2.5:32b    9f13ba1299af  23 GB    100% GPU     4 minutes from now
```

- **`100% GPU`** → alles gut, das Modell liegt komplett im VRAM.
- **`48%/52% CPU/GPU`** o. ä. → zu wenig VRAM, ein Teil läuft auf der CPU
  (deutlich langsamer). Kleineres Modell wählen, z. B. `qwen2.5:14b`.
- **`100% CPU`** → GPU wird nicht genutzt. Prüfen:
  - Linux: ROCm-Treiber installiert? Ollama-Log ansehen:
    `journalctl -u ollama | grep -i -E "rocm|amdgpu|gpu"`.
    Bei nicht offiziell unterstützten Karten hilft oft
    `HSA_OVERRIDE_GFX_VERSION` (z. B. `10.3.0` für RDNA2, `11.0.0` für RDNA3)
    als Umgebungsvariable für den Ollama-Dienst.
  - Windows: aktuellen AMD-Adrenalin-Treiber installieren; Ollama erkennt
    unterstützte Radeon-Karten automatisch. Log: `%LOCALAPPDATA%\Ollama\server.log`.
  - Auslastung live: `rocm-smi` (Linux) bzw. Task-Manager → GPU (Windows).

## Tests

```bash
# Offline (ohne Ollama): Stufenlogik, Befehle, Fehlerbehandlung, Speichern
python -m unittest discover -s tests -v

# Live gegen das echte Modell: Lernender drängelt 5× nach der Lösung
# von 3x + 7 = 22 – vor /aufgeben darf "x = 5" nicht fallen, danach schon.
python tests/live_check.py --modell qwen2.5:32b
```
