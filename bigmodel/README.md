# ollama_max – das größte Ollama-Modell, das auf deinen PC passt

Ein eigenständiges Programm (nur Python-Standardbibliothek), getrennt von CodePilot.
Ziel ist die bestmögliche Antwort, die Geschwindigkeit spielt keine Rolle.

## Was es macht

1. **Hardware messen:** VRAM (`nvidia-smi`), RAM und freien Plattenplatz.
2. **Modell wählen:** Es geht eine nach Qualität sortierte Liste durch
   (`deepseek-v3.1:671b` → `qwen3:235b` → `gpt-oss:120b` → `qwen3.6:27b` → …)
   und nimmt das erste Modell, das in **VRAM + RAM** passt. Die echte Größe
   liest es aus der Ollama-Registry, ohne etwas herunterzuladen. Ollama legt
   so viele Schichten wie möglich auf die GPU und den Rest in den RAM.
3. **Herunterladen:** Nur wenn du zustimmst (oder `--yes` angibst).
4. **Qualitäts-Pipeline** (Standard `--quality 3`):
   3 unabhängige Entwürfe mit maximalem „Thinking“ → Synthese der besten Teile
   → harte Selbstkritik → überarbeitete Endantwort.

## Mit 24 GB VRAM entscheidet der RAM

| System-RAM | gewähltes Modell (ca.)       |
|-----------:|------------------------------|
| 32 GB      | `qwen3.6:27b` (komplett auf der GPU, schnell) |
| 64–96 GB   | `gpt-oss:120b`               |
| 192 GB+    | `qwen3:235b`                 |
| 512 GB+    | `deepseek-v3.1:671b`         |

Ein Modell, das größer als VRAM + RAM ist, lädt Ollama gar nicht. Deshalb ist der
RAM die Grenze und nicht die Geduld.

## Benutzung

```powershell
python ollama_max.py --check                        # nur anzeigen, was gewählt würde
python ollama_max.py "Deine Frage"                  # eine Frage
python ollama_max.py                                # interaktiv
python ollama_max.py --file frage.txt --out antwort.md   # inkl. aller Zwischenschritte
```

Unter Windows geht auch `run_max.bat "Deine Frage"`.

Wichtige Optionen:

- `--quality 1|2|3`: 1 = eine Antwort, 2 = Antwort + Kritik + Revision, 3 = Standard (siehe oben)
- `--drafts N`: Anzahl der Entwürfe bei Stufe 3
- `--ctx 32768`: Kontextfenster. Mehr Kontext kostet Speicher und kann zu einem kleineren Modell führen.
- `--model TAG`: ein bestimmtes Modell erzwingen
- `--verbose`: das Denken des Modells live mitlesen
- `--vram`, `--ram`, `--reserve`: die erkannte Hardware überschreiben

## Tipps

- Startet das Programm Ollama selbst, setzt es `OLLAMA_FLASH_ATTENTION=1` und
  `OLLAMA_KV_CACHE_TYPE=q8_0`. Das spart Speicher für den Kontext. Läuft bereits
  die Ollama-App, setze beide Variablen dauerhaft (`setx …`) und starte sie neu.
- Die Modellliste steht oben in `ollama_max.py` (`CATALOG`). Tags, die es in der
  Registry nicht gibt, werden übersprungen. Neue Modelle trägst du einfach oben ein.
- Speicherbedarf und KV-Cache sind Schätzungen. Lädt ein Modell nicht, gib `--reserve`
  höher oder `--ctx` kleiner an.

Tests: `python -m pytest bigmodel`
