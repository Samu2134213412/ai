# 00 – Offene Fragen

Bevor ich Hardware vorschlage, die du nicht genannt hast, brauche ich diese
Antworten. In Klammern: welcher Meilenstein davon abhängt.

## Bereits geklärt

| Frage | Antwort |
|---|---|
| PC | Windows, LAN-Kabel. Später optional eigener Server mit 2× Tesla P40, nicht dauerhaft an |
| Pi 4 | 2 GB RAM |
| Bestand | FRITZ!Box, eine LED-Leiste (soll neu geplant werden) |
| Repo | privat, `smarthome-ai` |

## Offen

### Räume (M2, M5, M8)
1. **Fotos beider Zimmer** + grobe Maße (Länge × Breite, Fenster, Türen, Heizkörper, Steckdosen). Daraus: Lichtplanung, Sensorplätze, Grundriss fürs Dashboard.
2. **Foto der LED-Leiste** inklusive Controller/Netzteil-Aufkleber. Je nach Typ kann sie mit einem Zigbee- oder WLED-Controller weiterleben.
3. **Mietwohnung?** Wenn ja: nur Lösungen ohne Eingriff in die Hausinstallation.
4. **Heizung:** Heizkörper mit Thermostatkopf? Foto vom Ventil (Anschlussgewinde).
5. **Rollos:** Was ist vorhanden – Innenrollo mit Kette, Rollladen mit Gurt, Plissee, nichts?
6. **Standorte:** In welchem Zimmer stehen FRITZ!Box/Pi, PC, Bett und später der Drucker?

### Sprache (M4)
7. **Satellit:** Home Assistant Voice PE (Wake-Word auf dem Gerät, ≈ 65 €, mein Vorschlag) – oder openWakeWord auf dem Pi mit USB-Konferenzlautsprecher (≈ 30–60 €, belastet den 2-GB-Pi, funktioniert nur gut, wenn der Pi im Raum steht, in dem du sprichst)?

### Netz und Strom (M1, M7)
8. **FRITZ!Box-Modell** und hat sie einen **USB-Anschluss** (Backup-Ziel)?
9. **Internetanschluss** mit eigener IPv4 oder DS-Lite (Kabel-Anschlüsse oft DS-Lite)? Relevant nur für FRITZ!Box-WireGuard.
10. **VPN:** Tailscale (keine offenen Ports, Koordinationsserver beim Anbieter) oder FRITZ!Box-WireGuard (kein Drittanbieter, ein UDP-Port offen)?
11. **Stromtarif:** fester Preis oder dynamisch (z. B. Tibber)? Nur dann ergibt „Drucken zu günstigen Zeiten“ Sinn.
12. **Pi-Zubehör:** Hast du eine SSD, ein offizielles Netzteil, ein Gehäuse?

### Drucker (M6)
13. **Materialien:** nur PLA/PETG oder auch ABS/ASA (→ Abluft nötig)?

### Schreibtisch (M9)
14. **Budget** und **Plattenmaß** (z. B. 160 × 80 oder 180 × 80)?
15. Steht der **PC am Schreibtisch**? (Kamera per USB am PC)
16. Hast du ein **altes Tablet** für das Tisch-Display?

### Pi-Hardware (M1)
17. Wie alt ist dein Pi 4 ungefähr? (Ab 2020 bootet er ohne Umweg von USB-SSD.)
