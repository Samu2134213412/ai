# 08 – 3D-Druck mit dem Bambu Lab X2D

Eckdaten X2D (laut Händlerangaben, beim Auspacken prüfen): geschlossener
Bauraum 256 × 256 × 260 mm, zwei Düsen, Düse bis 300 °C, Bett bis 120 °C,
aktive Bauraumheizung.

## 1. Integration (M6)

| Baustein | Umsetzung |
|---|---|
| Verbindung | Drucker im **LAN-only-Modus** + **Developer Mode** → HA-Integration [ha-bambulab](https://github.com/greghesp/ha-bambulab) (HACS) spricht direkt MQTT/TLS mit dem Drucker |
| Status, Fortschritt, Restzeit, Fehler, Temperaturen | Sensoren der Integration |
| Kamera | Kamera-Entität der Integration → Dashboard |
| Filamentstand | AMS-Daten (Bambu-Spulen mit RFID automatisch) + Spoolman (siehe 3.) |
| Benachrichtigung | Push aufs Handy + Ansage bei Fehler, Fertig, Filament leer |

**Abwägung LAN-only/Developer Mode:** Ohne Cloud funktioniert die Bambu-Handy-App
von unterwegs nicht mehr (du schaust stattdessen über HA per VPN). Bambu stuft den
Developer Mode als „nicht unterstützt“ ein – bei Problemen gibt es dafür keinen
Support. Ob ha-bambulab den X2D vollständig unterstützt, prüfe ich beim
Einrichten (neues Modell).

## 2. Raumautomation beim Drucken

| Auslöser | Aktion |
|---|---|
| Druck startet | Szene „Drucken“: Kamera-Licht an (Druckerlicht + Raumlicht, wenn dunkel) |
| Material ABS/ASA/PC/PA | Abluft an; läuft nach Druckende 10 min nach |
| Raumtemperatur > 30 °C oder < 15 °C während des Drucks, oder +3 °C in 10 min | Warnung Push + Ansage |
| Rauchmelder | Alarm + Push; **Drucker-Steckdose aus** (einziger Fall, in dem während eines Drucks abgeschaltet wird) |
| Druck fertig | Push „fertig, Platte abnehmen“; nach Abkühlen (Düse/Bett < 50 °C) und 30 min ohne neuen Auftrag: Drucker-Steckdose aus |
| Szene „Schlafen“ aktiv | keine neuen Druckstarts aus der Warteschlange |

## 3. Filament-Inventar

[Spoolman](https://github.com/Donkie/Spoolman) als Add-on auf dem Pi
(≈ 100 MB RAM): Spulen mit Hersteller, Material, Farbe, Leergewicht, Restmenge.
Verbrauch kommt pro Druck vom Drucker. Bambu-Spulen werden per RFID erkannt,
Fremdspulen ordnest du einmal per Dashboard (oder NFC-Tag) einem AMS-Platz zu.
Warnung, wenn ein geplanter Druck mehr braucht, als auf der Spule ist.

## 4. Druckplaner für Mehrteil-Projekte (M7)

Beispiel: „Plane mir einen Druck für ein Kabelhalter-Set“

```
1. Verstehen        LLM (PC) zerlegt das Projekt in Teile + Stückzahlen
2. Modelle          a) eigene STL/3MF aus deinem Ordner
                    b) einfache Teile parametrisch erzeugen: LLM schreibt
                       OpenSCAD-Code → STL (gut für Halter, Clips, Kappen)
                    c) optional Modell-Datenbanken (Internet = optional)
3. Slicen           Bambu Studio / OrcaSlicer per Kommandozeile auf dem PC
                    → exakte Zeit + Filament pro Platte
4. Prüfen           Filament gegen Inventar, Teile auf Platten verteilen
5. Planen           Reihenfolge + Startzeiten (siehe unten)
6. Warteschlange    in HA; Start per Knopfdruck (du bestätigst, dass die
                    Platte leer ist)
```

Was „günstig/ruhig“ bedeutet, legen wir fest – Vorschlag:

- **Ruhig:** nicht während Szene „Schlafen“, falls der Drucker im Schlafzimmer steht; bevorzugt während deiner Abwesenheit.
- **Günstig:** nur relevant bei dynamischem Stromtarif (Frage offen); sonst egal.
- **Machbar:** Zwischen zwei Platten muss jemand die Platte abnehmen → Druckenden sollen in Zeiten fallen, in denen du da und wach bist.

Ein automatischer Start ohne Bestätigung ist bewusst **nicht** vorgesehen: Liegt
noch ein Teil auf der Platte, druckt der Drucker darauf.
