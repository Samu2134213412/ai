# Auftrag für Codex: Jarvis auf dem eigenen Rechner starten (inkl. Handy-Zugriff)

Codex läuft direkt auf deinem Computer und darf dort Befehle ausführen — genau
das, was hier gebraucht wird. Kopiere den Block unterhalb der Linie vollständig
in Codex hinein. Er ist bewusst so geschrieben, dass Codex **prüft** statt
behauptet: jede Zusage am Ende muss durch einen tatsächlich gelaufenen Befehl
gedeckt sein. Das ist dieselbe Regel, nach der Jarvis selbst arbeitet.

Eine Sache musst du vorher selbst eintragen: den Pfad, unter dem das
Repository auf deinem Rechner liegt (oder liegen soll).

---

Du arbeitest auf meinem Rechner und hast Zugriff auf Terminal und Dateisystem.
Ziel: Der Jarvis-Server läuft lokal, und ich kann die Oberfläche von meinem
Handy aus im selben WLAN öffnen.

REPO: https://github.com/Samu2134213412/ai
BRANCH: claude/bold-carson-ur1dni
ORDNER: <HIER DEN PFAD EINTRAGEN, z. B. C:\Users\Samuel\ai oder ~/ai>

Arbeite die Schritte der Reihe nach ab. Nach jedem Schritt: kurz sagen, was
herauskam. Wenn ein Schritt fehlschlägt, halte an und zeige mir die echte
Fehlermeldung, statt zum nächsten zu springen.

1) SYSTEM FESTSTELLEN
   Stelle fest: Betriebssystem und Version, Python-Version, ob git da ist,
   ob ollama da ist. Nenne mir die Werte. Installiere an dieser Stelle noch
   nichts.

2) CODE HOLEN
   Liegt ORDNER noch nicht vor: dorthin klonen.
   Liegt er vor: `git fetch origin` und auf den Branch oben wechseln
   (`git checkout claude/bold-carson-ur1dni && git pull origin claude/bold-carson-ur1dni`).
   Habe ich dort eigene, nicht committete Änderungen, dann überschreibe sie
   NICHT — zeig sie mir und frag, was damit passieren soll.
   Der Jarvis-Code liegt im Unterordner `jarvis/`, nicht im Wurzelverzeichnis.

3) PYTHON-UMGEBUNG
   Lege in `jarvis/server` eine virtuelle Umgebung an (`python -m venv .venv`),
   aktiviere sie und installiere `requirements.txt`.
   Python 3.11 oder neuer wird gebraucht. Ist es älter, sag mir das und
   installiere nichts von selbst nach.

4) TESTS
   Führe in `jarvis/server` `python -m pytest -q` aus.
   Erwartung: 586 Tests, alle grün oder übersprungen (bis zu 24 werden
   übersprungen, wenn ffmpeg/ffprobe/tesseract auf diesem Rechner fehlen --
   das ist kein Fehler, nur ein fehlendes optionales Programm). Kommt
   irgendetwas als FAILED heraus, zeig mir die Ausgabe — ich will die Zahl
   sehen, nicht die Zusammenfassung „läuft".

5) OLLAMA UND MODELLE
   Prüfe, ob Ollama läuft: `curl http://127.0.0.1:11434/api/tags`
   (unter Windows notfalls `Invoke-RestMethod`). Läuft es nicht, starte es.
   Jarvis erwartet standardmäßig zwei Modelle:
     - `qwen3:14b`        (Gespräch, Werkzeuge)
     - `qwen3-coder:30b`  (Code-Modus)
   Liste mir auf, welche davon vorhanden sind und welche fehlen, mit der
   jeweiligen Größe des Downloads. LADE NICHTS OHNE MEIN OK HERUNTER —
   das sind zweistellige Gigabyte-Mengen. Frag mich, dann zieh sie mit
   `ollama pull`.
   Ist auf diesem Rechner zu wenig Speicher oder VRAM für `qwen3-coder:30b`,
   sag mir das ehrlich und schlag ein kleineres Modell vor; eintragen lässt
   es sich in der Konfiguration unter `code.model`.

6) KONFIGURATION
   `python -m jarvis --init` legt die Konfiguration an (standardmäßig unter
   `~/.jarvis`). Zeig mir danach, welche Datei entstanden ist und was
   darin steht — allerdings mit geschwärzten Token, falls schon eines
   drinsteht.

7) START MIT HANDY-ZUGRIFF
   Starte: `python -m jarvis --open-network`
   Das bindet auf 0.0.0.0 und erzeugt ein Zugangstoken. Der Server gibt beim
   Start die Adressen aus, die vom Handy aus erreichbar sind — in der Form
   `http://192.168.x.y:8770/?token=...`.
   Gib mir diese Adresse vollständig zurück. Sie ist das eigentliche
   Ergebnis dieses Auftrags.

8) ERREICHBARKEIT WIRKLICH PRÜFEN
   Verlasse dich nicht darauf, dass der Start ohne Fehler durchlief:
   - Hole die LAN-Adresse des Rechners (`ipconfig` / `ip addr` / `ifconfig`).
   - Rufe die Oberfläche über genau diese Adresse ab, nicht über 127.0.0.1:
     `curl -s -o /dev/null -w "%{http_code}" "http://<LAN-IP>:8770/?token=<TOKEN>"`
     Erwartet wird 200. Kommt 000 oder ein Timeout, blockiert die Firewall.
   - Windows: eine eingehende Regel für TCP 8770 für das Profil „Privat"
     anlegen — und mir vorher sagen, dass du das tun willst.
     macOS: die Firewall fragt beim ersten Start; Linux: ggf. `ufw allow 8770`.
   - Prüfe, ob Rechner und Handy überhaupt im selben Netz sind (gleiches
     Subnetz). Bei WLAN-Gastnetzen oder aktivierter Client-Isolation im
     Router geht es grundsätzlich nicht — sag mir das dann klar.

9) DAUERBETRIEB (nur wenn ich zustimme)
   Frag mich, ob Jarvis beim Hochfahren automatisch starten soll. Wenn ja:
   Windows Aufgabenplanung / systemd-User-Service / launchd. Vorher den
   konkreten Vorschlag zeigen, dann erst einrichten.

ZUM SCHLUSS
Gib mir eine kurze Liste:
  - Adresse zum Eintippen auf dem Handy (vollständig, mit Token)
  - Testergebnis (die echte Zahl)
  - welche Modelle vorhanden sind, welche fehlen
  - was du an Firewall oder Autostart geändert hast
  - was NICHT funktioniert hat

Wichtig: Melde einen Punkt nur dann als erledigt, wenn ein Befehl
tatsächlich gelaufen ist und Erfolg zurückgegeben hat. Wenn du etwas nicht
prüfen konntest, schreib „nicht geprüft" — das ist mir lieber als eine
Zusage, die auf dem Handy dann nicht stimmt.
