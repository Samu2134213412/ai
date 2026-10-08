# SchulKI – geteilte KI im Schulnetz, ohne Server

Jedes Gerät, auf dem `schulki.py` läuft, wird Teil des Pools:

- **Mitrechnen:** Ein PC oder Mac, der stark genug ist, betreibt über Ollama ein
  *komplettes* Modell und beantwortet Fragen aus dem ganzen Pool.
- **Nutzen:** Jedes Gerät stellt die Chat-Seite bereit. Handys, Tablets und
  Chromebooks öffnen sie einfach im Browser.
- **Verteilung:** Eine Frage geht an das Gerät, das gerade frei ist. Bei
  „gründlich“ geht sie an das Gerät mit dem besten Modell. Fällt ein Gerät aus,
  etwa weil ein Laptop zugeklappt wurde, übernimmt automatisch ein anderes.
- **Fairness:** Wer mitrechnet, wird zuerst bedient. Fragen von Geräten, die nur
  nutzen, warten, solange Mitrechner in der Schlange stehen.
- **Kein Server:** Die Geräte finden sich per Broadcast im WLAN und tauschen ihre
  Gerätelisten aus. Ein einziger bekannter Teilnehmer reicht.

## Warum nicht ein großes Modell auf alle Geräte verteilt?

Technisch geht das (llama.cpp RPC), aber jedes Token müsste nacheinander durch alle
Geräte über das WLAN laufen. Das ist sehr langsam, und sobald *ein* Laptop zugeklappt
wird, steht die KI für alle. Darum rechnet bei SchulKI jedes Gerät ein ganzes Modell,
und mehr Geräte bedeuten mehr gleichzeitige Antworten.

## Start

```powershell
python schulki.py --key KLASSENPASSWORT
```

oder unter Windows `start_schulki.bat`. Alle Geräte brauchen dasselbe Passwort (mindestens
6 Zeichen). Es wird in `~/.schulki.json` gespeichert, beim nächsten Mal genügt also
`python schulki.py`. Die Konsole zeigt die Adresse, z. B. `http://10.0.4.17:47801`.
Diese Adresse öffnen Handys im selben WLAN.

| Gerät                  | Rolle                                                                    |
|------------------------|--------------------------------------------------------------------------|
| PC/Laptop mit Grafikkarte | rechnet mit, bestes Modell, das in den VRAM passt (bis `qwen3.6:27b`) |
| PC/Laptop/Mac ohne Grafikkarte | rechnet ab ca. 16 GB RAM mit einem kleinen Modell (`qwen3:4b`/`8b`) mit, nutzt höchstens 40 % des RAM |
| Handy/Tablet           | nutzt den Pool im Browser (siehe unten)                                  |
| Chromebook             | Browser; Mitrechnen nur mit aktiviertem Linux, siehe unten               |

Mitrechnen braucht [Ollama](https://ollama.com/download). Ohne Ollama oder mit
`--no-contribute` nutzt das Gerät den Pool nur. Das Modell wird erst nach Rückfrage
heruntergeladen.

## Wenn sich die Geräte nicht finden

Viele Schul-WLANs haben **Client-Isolation**: Geräte dürfen nicht direkt miteinander
sprechen, nur mit dem Internet. Dann funktioniert SchulKI dort gar nicht, auch nicht mit
`--peer`, und nur die IT kann das für ein eigenes WLAN oder VLAN abschalten. Prüfen kannst du es so:
Öffne auf einem Handy die Adresse, die ein PC anzeigt. Lädt die Seite nicht, ist das
Netz isoliert (oder die Windows-Firewall blockiert, siehe unten).

Ist nur Broadcast blockiert, starte ein Gerät normal und die anderen mit
`--peer <IP des ersten>`. Die Liste wird weitergegeben.

**Windows-Firewall:** Beim ersten Start fragt Windows, ob Python im Netzwerk erreichbar
sein darf. Für „Private Netzwerke“ erlauben. Ist das Schul-WLAN als „Öffentlich“
eingestuft, muss es auf „Privat“ gestellt werden.

## Handys, Tablets, Chromebooks

- **Browser** (alle): Adresse eines laufenden Geräts öffnen, Passwort eingeben, fertig.
- **Android zum Mitrechnen** (experimentell): In [Termux](https://termux.dev)
  `pkg install python ollama`, dann `ollama serve &` und `python schulki.py`. Ein Handy schafft
  höchstens `qwen3:1.7b`/`4b` und wird dabei warm, der Akku leert sich schnell.
- **iPhone/iPad:** nur Browser. iOS erlaubt keinen solchen Hintergrunddienst.
- **Chromebook zum Mitrechnen:** Linux-Entwicklungsumgebung aktivieren, Ollama und
  Python darin installieren und in den ChromeOS-Einstellungen unter *Linux → Port-Weiterleitung*
  die Ports 47801 (TCP) freigeben. Broadcast kommt aus der Linux-Umgebung nicht heraus,
  daher `--peer` nutzen.

## Sicherheit und Grenzen

- Das Passwort hält Fremde aus dem Pool. Die Verbindung ist aber unverschlüsselt (HTTP).
  Wer im selben WLAN mitschneidet, kann Fragen und Antworten mitlesen. Also nichts
  Persönliches eingeben.
- Jede Frage wird auf dem Gerät eines anderen Schülers berechnet. Der Besitzer
  sieht zwar nichts davon in der Konsole, technisch könnte er die Inhalte aber mitlesen.
- Die Gesprächshistorie liegt nur im Browser des Fragenden. Kein Gerät speichert sie.
- Kleine Modelle machen mehr Fehler. „Gründlich“ lässt das Modell seine Antwort selbst
  prüfen und verbessern, ersetzt aber kein Nachdenken.

Tests: `python -m pytest bigmodel`
