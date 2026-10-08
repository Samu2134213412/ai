# Tutor-Server

Die KI-Logik des Tutors als HTTP-Server (Node 20+, keine Abhängigkeiten). Er spricht mit Ollama, wählt selbst
zwischen schnellem und großem Modell, führt die Hinweisstufen, plant Aufgaben und liest Seiten – und speichert
alles **je Person**. Clients schicken Fragen hin und bekommen die Antwort zurück (Streaming).

```bash
node server/index.js                    # nur dieser PC:   http://127.0.0.1:8780
node server/index.js --host 0.0.0.0    # auch im WLAN (Handy, iPad)
# weitere Optionen: --port 8780 --ollama http://127.0.0.1:11434 --data ./tutor-data
```

Beim Start steht ein **Kopplungs-Link** im Terminal (10 Minuten, einmalig). Öffnen = dieses Gerät ist gekoppelt.
**Enter** erzeugt einen Link für ein weiteres Gerät derselben Person, **Name + Enter** legt eine neue Person
mit eigenem Verlauf an. (Die PC-App benutzt denselben Server und hat dafür den Knopf „Gerät koppeln“.)

## Sicherheit

- Anmeldung nur über Geräte-Token (Cookie oder Header `X-Tutor-Token` / `Authorization: Bearer`); gespeichert
  wird nur der SHA-256-Hash. Ohne Token antwortet der Server überall mit 401.
- Standard: nur `127.0.0.1`. WLAN-Zugang nur mit `--host 0.0.0.0` bzw. in der PC-App auf Knopfdruck.
- Die Ollama-Adresse bestimmt allein der Server; Clients können sie nicht umbiegen.
- Die lokale Erweiterung „Tutor Fokus“ darf ohne Token nur die drei Fokus-Routen nutzen, und nur vom selben
  Rechner mit `chrome-extension://`-Origin.
- **Ins Internet** gehört der Server nicht unverschlüsselt: davor einen HTTPS-Proxy (Caddy/nginx) oder ein VPN
  (z. B. Tailscale) setzen. Ein eigener Rechner im Netz funktioniert unverändert; nur Ollama muss dort laufen.

## API (JSON; Streaming per Server-Sent Events)

| Route | Zweck |
|---|---|
| `POST /api/pair {code}` → `{token}` | Kopplungs-Code gegen Geräte-Token tauschen (oder Link `/?pair=CODE`) |
| `POST /api/pairing {name?}` | neuen Kopplungs-Code erzeugen (nur Besitzer) → `{code, urls, qr}` |
| `GET /api/state`, `GET/POST /api/settings` | Stand (Stufe, Modelle, Problem), Modelle einstellen |
| `POST /api/chat {text}` | Frage → SSE: `{t}`-Textstücke, `{reset}`, `{done, state, route}` oder `{error}` |
| `POST /api/giveup`, `/api/new {text?}` | Aufgeben (mit Rückfrage), neue Aufgabe |
| `POST /api/page {images\|image, focus?}`, `/api/page_text` | Seite lesen (Vision), korrigierte Abschrift |
| `GET /api/planner`, `POST /api/tasks…`, `/api/reminders`, `/api/focus/start\|stop`, `GET /api/plan.ics` | Planer, Fokus, Kalender |
| `POST /api/shot` (Bild als Body), `GET /api/shot`, `/api/shot.img` | Screenshot hochladen (iPad-Kurzbefehl) |
| `GET /api/me` | wer bin ich (Besitzer?) |

Tests: `node --test server/test/server.test.js` (Kopplung, Streaming, getrennte Verläufe, Neustart, Fokus-API, CORS).


## Klassen-Pool (kein eigener Server nötig)

Jedes Gerät mit Tutor-App und Ollama kann seine Rechenleistung der Klasse zur Verfügung stellen und nutzt dafür die der anderen mit.

- **Einschalten:** PC-App → ⚙︎ → „Klassen-Pool“ → Klassencode eintragen (mind. 8 Zeichen, bei allen gleich) → App neu starten. Ohne App: `node server/index.js --pool <code>`.
- **Funktionsweise:** Alle paar Sekunden ruft jedes Gerät per UDP (Port 8767) seine Modelle aus, signiert mit dem Klassencode. Jede Anfrage läuft komplett auf *einem* Gerät: dem freien, das das Modell hat. Fällt eines aus oder ist besetzt, nimmt das nächste sie.
- **Auch ungenutzt:** Mit Pool startet die App beim Anmelden versteckt im Tray und bearbeitet Anfragen der anderen, auch wenn am Gerät gerade niemand den Tutor nutzt (nur solange der PC an ist).
- **Geben und Nehmen:** Der Pool nimmt nur Anfragen von Geräten an, die selbst beitragen (selbst Ollama mit Modell haben und mitrufen). Pro Gerät laufen höchstens 1–4 fremde Anfragen gleichzeitig.
- **Sicherheit:** Nur `/api/tags` und `/api/chat`, signiert (HMAC mit Klassencode, 60 s gültig), nur erlaubte Felder, kein Zugriff auf Verlauf oder Aufgaben der anderen. Die Fragetexte laufen im Klartext (HTTP) durchs Schulnetz und werden auf dem fremden Gerät verarbeitet. Nur im vertrauten Schul-WLAN nutzen, Code nicht weitergeben. Der Router/das WLAN muss Rundrufe zwischen Geräten erlauben (nicht bei „Client-Isolation“).
- **Grenzen:** Das teilt Arbeit auf, es macht kein großes Modell aus vielen schwachen Geräten (ein 32b-Modell braucht weiter ein starkes Gerät mit viel Speicher). Handy und iPad tragen nichts bei, sie nutzen den Pool über einen PC mit der App.
