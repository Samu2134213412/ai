# 02 – Fehlende Hardware

Preise: Richtwerte in Euro (Stand Okt. 2026, Neuware außer wo „gebraucht“ steht).
**Vor dem Kauf prüfen**, besonders Zigbee-Geräte auf
[zigbee2mq.tt/supported-devices](https://www.zigbee2mqtt.io/supported-devices/).
Konkrete Modelle für Licht, Rollos und Thermostate lege ich erst fest, wenn ich
deine Raumfotos und Antworten habe ([Offene Fragen](00-offene-fragen.md)).

🖨 = kann/soll auf dem X2D gedruckt werden.

## Muss (M1–M4)

| Teil | Wofür | Preis | Hinweis |
|---|---|---|---|
| USB-3-SSD 128–256 GB (oder SATA-SSD + USB-Gehäuse mit UASP) | System des Pi | 25–40 € | SD-Karten sterben an den Datenbank-Schreibzugriffen von HA. Entfällt, wenn vorhanden. Übergangsweise geht eine A2-microSD ≥ 32 GB. |
| Offizielles Pi-4-Netzteil 5,1 V / 3 A | Stabile Versorgung mit SSD | 10 € | Entfällt, wenn vorhanden |
| Passives Alu-Gehäuse für Pi 4 | Kühlung ohne Lüfter (Lüfter = Strom + Lärm) | 15–25 € | 🖨 Alternative: Gehäuse drucken + Kühlkörper (≈ 5 €) |
| Zigbee-Koordinator USB (z. B. SONOFF ZBDongle-E, SMLIGHT SLZB-07 oder HA Connect ZBT-2) | Funkzentrale | 25–50 € | Mit **USB-Verlängerung 0,5–1 m** betreiben – USB 3 der SSD stört 2,4 GHz |
| 4× Zigbee-Zwischenstecker **mit Messfunktion** | Strommessung: PC, Monitor+Lautsprecher, Pi/Router-Ecke, später Drucker | 50–90 € | PC-Stecker misst nur – niemals PC per Stecker abschalten! |
| Licht | Raumlicht + Ersatz der hässlichen LED-Leiste | 40–120 € | **Offen** – nach Raumfotos |
| Voice-Satellit: Home Assistant Voice Preview Edition (1 Stück) | Mikrofon, Lautsprecher, Wake-Word auf dem Gerät | 60–70 € | Alternative siehe Offene Fragen |
| **Summe Muss** | | **≈ 225–405 €** | je nach Vorhandenem |

## Später (M5–M8)

| Teil | Wofür | Preis | Hinweis |
|---|---|---|---|
| 2× Zigbee-Heizkörperthermostat (z. B. SONOFF TRVZB) | Heizung | 60–80 € | Ventilanschluss prüfen (Foto) |
| 2–3× Zigbee-Fensterkontakt | Heizung aus beim Lüften | 20–40 € | |
| 2× Zigbee-Temperatur/Feuchte (z. B. SONOFF SNZB-02D) | Raumklima | 25–35 € | |
| 2× CO₂-Sensor Selbstbau: ESP32-C3 + Sensirion SCD41 | Luftqualität, Lüft-Erinnerung | 50–80 € | 🖨 Gehäuse; ESPHome-Konfig baue ich |
| 2× Präsenz Selbstbau: ESP32 + HLK-LD2410C (mmWave) | „Jemand im Raum“ auch beim Stillsitzen | 20–40 € | 🖨 Gehäuse. Fertig-Alternative: Aqara FP1E ≈ 45 € |
| Rollo-Antriebe | Rollos | 60–80 € pro Fenster | **Offen** – hängt von deinen Rollos ab |
| Zigbee-Rauchmelder | **Sicherheit beim Drucken** | 25–50 € | Für den Druckerraum Pflicht, bevor unbeaufsichtigt gedruckt wird |
| Drucker-Abluft: Rohrlüfter 100 mm + Schlauch + Fensteradapter | ABS/ASA-Dämpfe | 40–80 € | 🖨 Fensteradapter. Nur nötig bei ABS/ASA/PC |
| Zigbee-Luftqualität (z. B. IKEA VINDSTYRKA: PM2.5 + VOC) | Druckerraum | 35–45 € | |
| 2. Voice-Satellit | zweites Zimmer | 60–70 € | |
| **Summe Später** | | **≈ 335–520 €** | ohne Rollos |

## Schreibtisch (M9) – Details in [07-schreibtisch.md](07-schreibtisch.md)

| Block | Preis |
|---|---|
| Gestell elektrisch (2 Motoren, RJ45-Steuerung) | 350–550 € |
| Tischplatte | 80–350 € |
| Steuerung + Präsenz + LED-Zonen (ESP32, LD2410C, LED-Streifen, Netzteil, Profil) | 65–120 € |
| Kabelwanne + schaltbare Zigbee-Steckdosen | 70–110 € |
| Kabellose Ladefläche (Unter-Tisch-Qi) | 30–60 € |
| Schiene für Kamera/Arm (Alu-Profil + Arm) | 40–80 € |
| Kamera (USB-Webcam, von oben) | 50–150 € |
| Touch-Panel (Android-Tablet 8–11") | 100–200 € (0 €, falls altes Tablet vorhanden) |
| Kleinteile | 20–30 € |
| **Summe** | **≈ 800–1.650 €** |

## Roboterarm (M11) – Details in [09-aufraeumen-roboterarm.md](09-aufraeumen-roboterarm.md)

| Teil | Preis |
|---|---|
| SO-101 Servo-Satz nur Follower (6× STS3215 + Bus-Adapter + Netzteil) | 120–160 € |
| Optional Leader-Arm (für Lernen per Vormachen) | +100–120 € |
| Druckteile | 🖨 ≈ 0,5–0,8 kg PLA/PETG ≈ 10–20 € |
| **Summe** | **≈ 130–300 €** |

## Nice-to-have

| Teil | Wofür | Preis |
|---|---|---|
| GPU-Server 2× Tesla P40 (gebraucht) | eigenes großes Gehirn, siehe [10-gpu-server.md](10-gpu-server.md) | 820–1.400 € |
| Pi 4 mit 8 GB | falls RAM-Warnung dauerhaft | ≈ 80 € |
| Kleine USV für Pi + FRITZ!Box | Haus läuft bei kurzem Stromausfall weiter | 50–80 € |
| NFC-Tags für Fremd-Filament | Spule per Handy dem Inventar zuordnen | 10 € |
| USB-Stick an der FRITZ!Box | Backup-Ziel für HA | 10–15 € (oft vorhanden) |

## Was du selbst drucken kannst (🖨 Gesamtüberblick)

Pi-Gehäuse, Sensor-Gehäuse (CO₂, Präsenz), Fensteradapter Abluft, Kabelkanal-
Clips, LED-Profil-Endkappen/Halter, Tablet-Halterung, Kamera-Halter +
Sichtschutz-Klappe, Halter für Qi-Lader, Ablage-Schalen für die Aufräum-Zonen,
SO-101-Arm komplett, Lüfterhutzen für die P40-Karten. Der X2D hat 256 × 256 ×
260 mm Bauraum – reicht für alle genannten Teile.
