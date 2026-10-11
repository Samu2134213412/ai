# 03 – Meilensteine

Jeder Meilenstein ist für sich nutzbar. Fällt ein späterer Teil aus, funktionieren
die früheren weiter. Pro Meilenstein: was ich baue (🤖), was du machst (🧑), und
woran wir erkennen, dass er fertig ist (✅).

## M1 – Pi + Home Assistant + Fernzugriff

Ziel: HA läuft stabil auf dem Pi, du erreichst es von unterwegs nur per VPN.

- 🤖 Grundkonfiguration (`homeassistant/`), Sync-Skript, Pi-Gesundheitswarnungen, [Anleitung](setup/M1-pi-homeassistant.md)
- 🧑 HA OS flashen, FRITZ!Box-Einstellungen, Einrichtung, Tailscale-Login, Messwerte notieren
- ✅ HA erreichbar im LAN und per Tailscale vom Handy (mobile Daten); keine Portfreigabe in der FRITZ!Box; Backup läuft; RAM-Auslastung notiert
- Hardware: nur SSD (empfohlen), sonst nichts Neues

## M2 – Zigbee, erstes Licht, Strommessung

Ziel: „Licht an/aus“ per App und Dashboard; Verbrauch aller gemessenen Geräte sichtbar, Tages-/Monatsstatistik.

- 🤖 Zigbee2MQTT-Konfiguration, Energie-Paket (Tages-/Monatszähler mit `utility_meter`), erstes Dashboard (dunkles Theme, Raum-Kacheln, Energie-Kachel)
- 🧑 Geräte koppeln, Raumfotos liefern, Licht-Hardware nach meinem Vorschlag kaufen
- ✅ Licht schaltbar; Energie-Dashboard zeigt PC, Pi, Monitor/Lautsprecher; Pi ≤ 6 W gemessen
- Hardware: Zigbee-Stick, Messstecker, Licht

## M3 – Gehirn: Wecken, Schlafen, Routing (Text)

Ziel: Im Dashboard-Chat beantwortet der Pi einfache Befehle selbst; komplexe Fragen wecken den PC, Ollama antwortet, der PC schläft danach wieder.

- 🤖 `pc-agent` (Windows), `brain_router` (HA-Integration) mit Tests, Windows-Firewall-Regeln als Skript, Anleitung Wake-on-LAN (BIOS + Treiber + Schnellstart aus)
- 🧑 BIOS/Treiber-Einstellungen, Agent installieren, Modell auswählen
- ✅ „Licht aus“ im Chat → PC bleibt im Schlaf; „Erkläre mir …“ → PC wacht auf, Antwort < 30 s, PC schläft nach eingestellter Zeit wieder; beim Spielen wird nicht gestört
- Hardware: keine

## M4 – Sprache

Ziel: Zwei Wake-Words: lokal (≈ 1 s, ohne PC) und Gehirn (weckt PC).

- 🤖 Pipelines, eigene deutsche Sätze für Szenen/Geräte, `brain-stt-proxy` (Add-on), Whisper-Server-Setup für den PC
- 🧑 Satellit einrichten, Wake-Words wählen, Testsätze sprechen
- ✅ 20 Testbefehle lokal mit ≥ 90 % Trefferquote; Gehirn-Anfrage per Sprache funktioniert aus dem Schlaf
- Hardware: Voice-Satellit

## M5 – Raumautomation komplett

Ziel: Heizung, Rollos, Sensoren, Präsenz; Szenen „Fokus“, „Gaming“, „Schlafen“, „Drucken“.

| Szene | Vorschlag (passen wir an) |
|---|---|
| Fokus | Schreibtischlicht hell/neutralweiß, Raumlicht gedimmt, Benachrichtigungen stumm, Sitz/Steh-Erinnerung an |
| Gaming | Ambientlicht gedimmt/farbig, Rollo gegen Blendung, PC wecken, Gehirn-Router meidet den PC |
| Schlafen | Alles aus außer Nachtlicht, Heizung abgesenkt, Rollos zu, Monitor-/Lautsprecher-Steckdosen aus, PC schlafen (wenn kein Spiel, keine Lease), keine neuen Druckstarts |
| Drucken | Kamera-Licht, Abluft (materialabhängig), Temperaturüberwachung, Fertig-/Fehler-Meldungen |

- 🤖 ESPHome-Konfigurationen (CO₂, Präsenz), Heizungslogik mit Fensterkontakten, Präsenz-Logik (Strom sparen), Szenen
- 🧑 Sensoren bauen (löten optional – es gibt steckbare Varianten), Gehäuse drucken, montieren
- ✅ Szenen per Sprache, Dashboard und Zeitplan; Monitor/Lautsprecher gehen bei Abwesenheit aus
- Hardware: Thermostate, Sensoren, Rollo-Antriebe, Rauchmelder

## M6 – Bambu X2D (ab Weihnachten)

Ziel: Status, Kamera, Fortschritt, Filament, Fehler-Push; Raumautomation beim Drucken; Filament-Inventar.

- 🤖 Integration ha-bambulab (LAN-only + Developer Mode), Automationen, Spoolman + Kopplung mit AMS
- 🧑 Drucker in LAN-only-Modus versetzen, Zugangscode eintragen, Spulen erfassen
- ✅ Druckstatus + Kamera im Dashboard; Push bei Fehler; Drucker geht nach Abkühlen aus; Restmengen stimmen
- Hardware: Messstecker Drucker, Rauchmelder, ggf. Abluft

## M7 – Druckplaner

Ziel: „Plane mir einen Druck für ein Kabelhalter-Set“ → Teileliste, Reihenfolge, Filament- und Zeitbedarf, Startzeiten zu ruhigen/günstigen Zeiten.

- 🤖 Planer-Dienst (auf dem PC beim Slicen, Ergebnis in HA), Slicer-CLI-Anbindung, Warteschlange, Planungs-Panel
- ✅ Projekt mit ≥ 3 Teilen geplant; Filament-Prüfung gegen Inventar; Vorschlag für Startzeiten

## M8 – Dashboard-Feinschliff

Ziel: Grundriss mit klickbaren Geräten, Glas-Optik, Tisch-Display-Ansicht, Druckplaner-Panel. Siehe [06-dashboard.md](06-dashboard.md).

## M9 – Neuer Schreibtisch

Siehe [07-schreibtisch.md](07-schreibtisch.md). Kann zeitlich auch vor M6 kommen.

## M10 – Aufräum-System Stufe 1

Kamera über dem Tisch, Erkennung auf dem PC, „was gehört wohin“, LED markiert Ablageplätze. Siehe [09-aufraeumen-roboterarm.md](09-aufraeumen-roboterarm.md).

## M11 – Aufräum-System Stufe 2: Roboterarm SO-101

Zuletzt. Drucken, aufbauen, kalibrieren, Kleinteile in Zonen sortieren.

## M12 – Optional: GPU-Server 2× P40

Jederzeit nach M3 möglich, weil der Router Backends austauschbar behandelt. Siehe [10-gpu-server.md](10-gpu-server.md).
