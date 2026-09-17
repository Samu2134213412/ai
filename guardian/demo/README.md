# Guardian Demo — Live Preview

Eine interaktive, rein clientseitige Vorschau der Guardian-Oberfläche
(Dashboard, Java Secure Mode, Event-Timeline) mit **simulierten**
Security-Events. Dient dazu, während der Entwicklung sofort sehen zu
können, wie sich geplante Funktionen anfühlen werden — nicht dazu, echte
Bedrohungen zu erkennen.

## Was das ist — und was nicht

- **Ist:** eine statische HTML/CSS/JS-Seite (`index.html`, kein Build-Schritt,
  keine Frameworks) mit einem kleinen State-Objekt in JavaScript, das durch
  Buttons verändert wird ("Simulate Safe File" usw.).
- **Ist nicht:** eine Vorwegnahme von Phase 2–4. Die echte Guardian-Engine
  (Rust, `cli/`) hat weiterhin keine Echtzeitüberwachung, keinen
  Prozessmonitor, keine Verhaltenserkennung und keinen Java Secure Mode —
  siehe `../ROADMAP.md`. Diese Demo zeigt nur, wie die Ergebnisse dieser
  künftigen Phasen später dargestellt werden könnten. Es findet keine
  Verbindung zur laufenden `guardian`-Binary statt, es wird keine echte
  Datei gescannt, kein echter Prozess beobachtet und keine Schadsoftware
  (auch keine simulierte ausführbare Datei) erzeugt oder ausgeführt — jeder
  Klick verändert nur In-Memory-JavaScript-State.
- Score-Aufschlüsselungen (`+20 Unbekannte ausführbare Datei`, ...) folgen
  bewusst demselben Format wie `Finding::explain()` in `core/src/finding.rs`,
  damit die Demo zeigt, wie die *echte* Score-Erklärung später aussehen wird
  — die Zahlen selbst sind aber Beispielwerte, keine echte Berechnung.

## Starten

```sh
cd guardian/demo
npm run dev
```

Keine Abhängigkeiten, kein `npm install` nötig — `dev.js` verwendet
ausschließlich Node-Bordmittel (`http`, `fs`, `path`, `net`). Das ist
bewusst so gewählt: ein Sicherheitsprojekt sollte für eine einzelne
statische Demo-Seite kein Drittanbieter-Paket mit großem, teils veraltetem
Abhängigkeitsbaum einbinden.

Startet einen lokalen Server (Standard-Port `3000`, sonst automatisch der
nächste freie Port) und gibt die URL aus, z. B. `http://localhost:3000`.
Änderungen an `index.html` werden per Live-Reload (Server-Sent Events)
automatisch im Browser nachgeladen — kein manueller Neustart nötig. Es
öffnet sich dabei **kein** Browserfenster von selbst; die URL wird nur in
der Konsole ausgegeben.

Alternativ funktioniert `index.html` auch ganz ohne Server — Datei direkt im
Browser öffnen. Live-Reload gibt es dann allerdings nicht.

## Bedienung

- **Dashboard**: Kennzahlen-Kacheln, Liste überwachter (simulierter)
  Dateien, Buttons zum Erzeugen neuer Ereignisse, sowie eine
  Score-Begründung für die zuletzt ausgewählte Datei.
- **Java Secure Mode**: Zeigt den letzten simulierten Java-Vorfall inkl.
  Event-Tree (`java.exe → jar → powershell.exe → downloaded.exe`),
  beobachtetem Verhalten und ausgeführten Maßnahmen.
- **Ereignisse**: Chronologische Timeline aller simulierten Ereignisse
  dieser Sitzung.

Alle Buttons erzeugen ausschließlich ungefährliche, rein simulierte
Einträge im Browser-Speicher der aktuellen Seite. Nichts wird auf die
Festplatte geschrieben, ausgeführt oder heruntergeladen.
