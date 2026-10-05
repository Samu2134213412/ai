# Tutor – PC-Version (Windows, macOS, Linux)

Desktop-App (Electron) mit derselben Oberfläche wie Web und iPad – **ohne Python-Server**:

- Die Logik läuft in der App, die KI über **Ollama auf demselben PC** (`http://localhost:11434`) –
  oder einem anderen Rechner im Netz (⚙︎ → Adresse).
- **Fenster teilen:** Chip „🖥 Fenster teilen“ zeigt eine Auswahl aller Fenster und Bildschirme
  (GoodNotes für Windows/Mac steht oben). Der Tutor sieht nur das gewählte Fenster.
- **Erinnerungen:** laufen im Hintergrund weiter; Schließen minimiert in den **Tray** (abschaltbar).
  Optional **Start beim Anmelden**.
- **Fokus:** Timer in der App; die **Browser-Erweiterung** (`../extension`) schließt YouTube/Instagram …
  und spricht dafür mit der App (`http://127.0.0.1:8765`) – Start/Stopp geht von beiden Seiten
  (App, Erweiterung, Tray-Menü).
- **Programme beenden:** In ⚙︎ → „PC“ trägst du Programmnamen ein (z. B. `discord`, `steam`).
  Nur diese werden beendet, nur während einer Fokus-Sitzung; System-Programme sind gesperrt.
  Auf Linux/macOS gilt der von `ps` gemeldete Name (Linux kürzt auf 15 Zeichen).

## Starten (Entwicklung)

```bash
cd tutor/desktop
npm install
npm start            # baut www/ aus ../web und startet die App
npm test             # Server, Fokus, Wächter, Einstellungen
```

Voraussetzungen: Node 20+, laufendes Ollama mit `qwen2.5:32b` (oder kleiner) und
`qwen2.5vl:7b` (Seiten lesen). Beim ersten Start öffnen sich die Einstellungen, falls Ollama
nicht erreichbar ist.

## Installer bauen

```bash
npm run dist         # Windows: .exe (Setup + portable), macOS: .dmg, Linux: AppImage + .deb → dist/
```

Gebaut wird nur für das System, auf dem der Befehl läuft. Für alle drei gleichzeitig:
GitHub → **Actions → „Tutor Desktop-App bauen“ → Run workflow**; die Installer hängen danach als
Artefakte am Lauf. Sie sind **nicht signiert**: Windows zeigt SmartScreen („Weitere Informationen →
Trotzdem ausführen“), macOS verlangt Rechtsklick → Öffnen. Für Signieren/Notarisieren braucht es
Zertifikate (`CSC_LINK`, Apple-Developer-ID).

## Sicherheit

- Fenster: `contextIsolation`, `sandbox`, kein Node in der Oberfläche; die Brücke (`preload.js`) bietet
  nur Fokus-Stand, Fensterliste, Einstellungen. Jeder Aufruf wird im Hauptprozess geprüft (nur Seiten
  der eigenen App).
- Der lokale Server hört nur auf `127.0.0.1`, prüft den Host-Header (DNS-Rebinding) und lässt für
  Start/Stopp nur die Erweiterung oder die App selbst zu, keine fremden Webseiten.
- Berechtigungen (Benachrichtigungen, Fensterfreigabe) gelten nur für die App-Seiten; eine Freigabe
  startet nie ohne deine Auswahl in der App.

## Stand

Geprüft in einer echten Electron-Instanz (Linux/Xvfb, auch als verpacktes `linux-unpacked`):
Oberfläche, Ollama-Anbindung, Fokus-Austausch mit der Erweiterungs-API in beide Richtungen,
Beenden eines echten Dummy-Prozesses, Fensterauswahl samt Freigabe. **Nicht geprüft:** Windows- und
macOS-Installer sowie `tasklist`/`taskkill` auf echtem Windows (nur mit simulierter Ausgabe getestet) –
der CI-Lauf baut beide, startet sie aber nicht.
