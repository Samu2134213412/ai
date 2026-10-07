# ollama_max – das größte Modell, das dein PC ausführen kann

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

## Zwei Modi

### `ram`: alles in VRAM + RAM (schnell, Ollama)

| System-RAM | gewähltes Modell (ca.)       |
|-----------:|------------------------------|
| 32 GB      | `qwen3.6:27b`                |
| 64–96 GB   | `gpt-oss:120b`               |
| 192 GB+    | `qwen3:235b`                 |
| 512 GB+    | `deepseek-v3.1:671b`         |

### `stream`: größer als der RAM, direkt von der SSD (langsam, llama.cpp)

Ollama lädt kein Modell, das größer ist als VRAM + RAM. Für diesen Fall startet
das Programm **llama.cpp** mit derselben Modelldatei, die `ollama pull`
heruntergeladen hat. llama.cpp blendet die Datei per mmap in den Speicher ein:

- Was in die 24 GB passt (Attention, gemeinsame Gewichte, so viele Schichten bzw.
  Experten wie möglich), liegt auf der GPU.
- Der Rest bleibt auf der SSD. Das Betriebssystem liest pro Token nur die Teile,
  die gerade gebraucht werden, und hält die häufig genutzten im RAM.

Das funktioniert nur bei **Mixture-of-Experts-Modellen** gut. DeepSeek V3.1 nutzt pro
Token nur 37 der 671 Milliarden Parameter, also muss auch nur dieser Teil gelesen
werden. Ein „dichtes“ Modell braucht dagegen für jedes Token *alle* Gewichte.
Gestreamt hieße das, pro Token die ganze Datei zu lesen, also Minuten pro Token.

Grobe Schätzung bei 24 GB VRAM, 32 GB RAM und einer NVMe-SSD (2,5 GB/s):

| Modell                | Download | ca. s/Token | 1000 Tokens |
|-----------------------|---------:|------------:|------------:|
| `deepseek-v3.1:671b`  | 404 GB   | ~8          | ~2,3 h      |
| `qwen3:235b`          | 142 GB   | ~4          | ~1 h        |

Denkende Modelle schreiben pro Schritt oft 2000–8000 Tokens. Eine Antwort dauert
also Stunden bis Tage. Deshalb ist die Qualitätsstufe im Stream-Modus standardmäßig 2
(eine Antwort, Kritik, Überarbeitung) statt 3.

`--mode auto` (Standard) nimmt das beste Modell aus beiden Listen, das
schneller als `--max-spt` Sekunden pro Token läuft (Standard 10). Mit
`--max-spt 30` darf es noch langsamer werden.

**Voraussetzungen:** genug freier Platz auf einer **NVMe-SSD** (bei einer HDD ist es
hoffnungslos langsam) und `llama-server` aus llama.cpp. Fehlt er, bietet das Programm an,
das offizielle Release von GitHub herunterzuladen (Windows: CUDA-Build), und legt es in
`bigmodel/llama.cpp/` ab. Den Pfad kannst du auch mit `--llama-server` angeben. Statt einer
Ollama-Datei geht auch jede GGUF-Datei mit `--gguf PFAD`, zum Beispiel eine stärker
komprimierte Version von DeepSeek von Hugging Face.

**Ungetestet:** Mit echter Hardware ist der Stream-Modus noch nicht gelaufen.
Die Zeiten sind Schätzungen. In der Praxis werden häufig genutzte Experten im
RAM zwischengespeichert, dann geht es schneller. Unter Windows kann das
Einlagern der Seiten langsamer sein. Manche Ollama-Modelle (vor allem `gpt-oss`)
speichert Ollama in einem Format, das llama.cpp nicht lädt. Dann zeigt das
Programm den Fehler aus dem llama-server-Log; nimm dann `--gguf` mit einer
Datei von Hugging Face.

## Benutzung

```powershell
python ollama_max.py --check                        # nur anzeigen, was gewählt würde
python ollama_max.py --mode stream --check          # was mit SSD-Streaming ginge
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
- `--mode auto|ram|stream`, `--max-spt`, `--disk-speed`, `--gguf`, `--llama-server`: siehe oben
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
