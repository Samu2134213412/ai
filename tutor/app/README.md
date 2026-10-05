# Tutor – iPad-App

Die Web-Oberfläche des Tutors als iPad-App (Capacitor 8 + Swift), mit nativen Teilen:

| Funktion | Umsetzung |
|---|---|
| Tutor-Chat, Hinweisstufen, Planer, Seiten lesen | `web/` (gleicher Code wie im Browser), Logik lokal in `web/core.js` + `web/backend-local.js` |
| KI | **Ollama auf deinem Mac/PC im WLAN** – kein Python-Server nötig |
| Aufgaben, Einstellungen, Verlauf | auf dem Gerät (UserDefaults über `@capacitor/preferences`) |
| Erinnerungen / Einheiten / Fokus-Ende | echte lokale Benachrichtigungen (`@capacitor/local-notifications`), auch bei geschlossener App |
| Fokus-Sperre für Apps (Instagram, YouTube …) | Screen-Time-API, `FocusShieldPlugin.swift` |
| GoodNotes live ansehen, ohne Export | ReplayKit-Übertragung, `ScreenSharePlugin.swift` + Broadcast-Extension |
| Split View neben GoodNotes | iPad-only, kein `UIRequiresFullScreen` |

## Ehrlicher Stand

Dieses Projekt wurde **ohne Mac/Xcode** erstellt (Linux-Container). Geprüft ist alles, was
ohne Xcode prüfbar ist: der JS-Kern (Parität zu Python, Node-Tests), die komplette Oberfläche im
Browser im App-Modus gegen ein Fake-Ollama, das Erzeugen des Xcode-Projekts und die Plugin-
Erkennung durch `cap sync`, dazu statische Prüfungen der Swift-Dateien (Methoden ↔ JS-Brücke,
Klammern, IDs). **Nicht geprüft:** Kompilieren der Swift-Dateien, Lauf auf einem echten iPad,
Screen-Time-Sperre, ReplayKit. Rechne beim ersten Build mit kleinen Korrekturen in
`app/plugins/tutor-native/ios/Sources/`.

## Voraussetzungen

- Mac mit **Xcode 16+**, Node 20+
- iPad mit iPadOS 15+ (Fokus-Sperre: 16+, **nur echtes Gerät**, nicht der Simulator)
- Apple-ID (kostenlos reicht zum Testen auf dem eigenen iPad, Apps laufen dann 7 Tage).
  Für **Family Controls** (Fokus-Sperre) muss Apple die Capability für deine App-ID freischalten
  (Antrag im Developer-Portal, bezahltes Developer-Programm). Ohne sie läuft alles andere.

## Bauen

```bash
cd tutor/app
npm install
npm run sync        # baut www/ aus ../web und ../prompts, dann `cap sync ios`
npm run open        # öffnet ios/App/App.xcodeproj in Xcode
```

Nach jeder Änderung an `web/` oder `prompts/`: `npm run sync`.

### Einmalig in Xcode

1. Target **App** → *Signing & Capabilities* → Team wählen (Bundle-ID `de.tutor.app` ggf. anpassen –
   dann auch `appId` in `capacitor.config.json` und die IDs in `ScreenSharePlugin.swift`).
2. **Capability „App Groups“** hinzufügen: `group.de.tutor.app`.
3. **Capability „Family Controls“** hinzufügen (siehe oben; sonst Schritt auslassen).
4. **Broadcast-Extension anlegen** (für die Bildschirm-Freigabe):
   - *File → New → Target → Broadcast Upload Extension*, Product Name **Broadcast**,
     „Include UI Extension“ **abwählen**. Die Bundle-ID muss `de.tutor.app.Broadcast` werden.
   - Die erzeugte `SampleHandler.swift` durch `native/BroadcastExtension/SampleHandler.swift` ersetzen
     (Target-Mitgliedschaft nur „Broadcast“). Die `Info.plist` der Extension braucht dieselben
     `NSExtension`-Schlüssel wie `native/BroadcastExtension/Info.plist`.
   - Im Target **Broadcast** ebenfalls die Capability *App Groups* mit `group.de.tutor.app` setzen.
5. Gerät wählen → ▶︎.

## Ollama auf dem Mac/PC

```bash
ollama pull qwen2.5:32b        # oder ein kleineres Modell, siehe unten
ollama pull qwen2.5vl:7b       # liest deine Seiten
OLLAMA_HOST=0.0.0.0 OLLAMA_ORIGINS="*" ollama serve
```

(macOS-App von Ollama: `launchctl setenv OLLAMA_HOST 0.0.0.0` und `OLLAMA_ORIGINS "*"`, Ollama neu starten.)
Beide Geräte im selben WLAN. In der App **⚙︎** → Adresse `http://<IP des Rechners>:11434` → *Verbindung
testen*. `OLLAMA_ORIGINS` ist nötig, weil die App ihre Seiten unter `capacitor://localhost` lädt.
Wer das Netz absichern will, nutzt statt `*` den Wert `capacitor://localhost`.

Das iPad selbst kann ein 32B-Modell nicht ausführen; das Modell läuft immer auf dem Rechner.

## Native Funktionen

- **Benachrichtigungen:** Beim ersten Start fragt der Willkommens-Dialog; ⚙︎ → *Benachrichtigungen*.
  Plan, Erinnerungszeit und Fokus werden bei jeder Änderung neu eingeplant (Einheit −10 min,
  tägliche Erinnerung, Fokus-Ende).
- **Fokus-Sperre:** ⚙︎ → *Fokus-Sperre: Apps wählen* → Freigabe erteilen → Apps/Kategorien/Webseiten
  wählen. Startet eine Fokus-Sitzung (🎯), werden sie abgeschirmt; am Ende wird die Sperre aufgehoben.
  Beendet iPadOS die App vor dem Ende der Sitzung, bleibt die Sperre bis zum nächsten Öffnen der App
  bestehen (die App hebt sie beim Start auf, wenn kein Fokus läuft). Eine Sperre ohne App im Hintergrund
  bräuchte eine DeviceActivity-Monitor-Extension – das ist noch nicht gebaut.
- **GoodNotes live:** Split View: GoodNotes links, Tutor rechts. In der App **📱 Bildschirm teilen** →
  „Broadcast“ wählen → Übertragung starten. Der Tutor holt etwa alle 2 s das aktuelle Bild und liest es
  (bei eingeschaltetem 👀). Der Screenshot enthält beide Fenster; GoodNotes sollte also den größeren
  Teil einnehmen.

## Prüfliste auf dem iPad

1. ⚙︎ → Verbindung testen → ✅.
2. Frage stellen → Antwort streamt, Hinweisstufe wechselt.
3. Foto einer Notizseite wählen (📄) → Abschrift erscheint, `[?]` korrigierbar.
4. Planer → Aufgabe mit Frist → Plan; Benachrichtigungen erlauben → App schließen → Erinnerung kommt.
5. Fokus-Sperre: Apps wählen → 🎯 Fokus → Instagram/YouTube sind abgeschirmt, nach Ablauf wieder frei.
6. 📱 Bildschirm teilen → in GoodNotes schreiben → nach ~2 s liest der Tutor die neue Seite.

## Tests ohne Xcode

```bash
cd tutor
python -m unittest discover -s tests       # inkl. Parität Python↔JS, Node-Tests, Swift-Konsistenz
```
