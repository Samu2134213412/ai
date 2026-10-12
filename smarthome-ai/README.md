# smarthome-ai

Lokales, stromsparendes KI-Smart-Home für zwei Zimmer.

**Prinzip:** Ein Raspberry Pi 4 (≈ 4–5 W) läuft immer und erledigt alles Einfache
selbst – ohne Sprachmodell. Das „schwere Gehirn“ (Gaming-PC, später optional ein
GPU-Server) schläft und wird nur per Wake-on-LAN geweckt, wenn eine Aufgabe ein
großes Sprachmodell, Bildverarbeitung oder Slicing braucht. Danach schläft es
wieder. Keine Cloud nötig, kein Port ins Internet offen.

## Stand

| Meilenstein | Inhalt | Status |
|---|---|---|
| M0 | Planung, Repo-Struktur | ✅ fertig |
| M1 | Pi + Home Assistant + Fernzugriff per VPN | 🟡 Anleitung + Konfiguration fertig, Umsetzung bei dir |
| M2 | Zigbee, Licht an den Schrägen, Strommessung, Energie-Dashboard | 🟡 Licht geplant ([Arbeitszimmer](docs/11-arbeitszimmer.md)), wartet auf Maße + Hardware |
| M3 | Gehirn wecken/schlafen + Routing (Text) | ⏳ |
| M4 | Sprachsteuerung (2 Wake-Words) | ⏳ |
| M5 | Raumautomation komplett, Szenen | ⏳ |
| M6 | Bambu X2D Integration + Filament-Inventar | ⏳ ab Weihnachten |
| M7 | Druckplaner (Mehrteil-Projekte, Warteschlange) | ⏳ |
| M8 | Dashboard-Feinschliff + virtuelles Fenster (TV) | ⏳ |
| M9 | Neuer Schreibtisch mit Stift-Tablet und Gesten | 🟡 geplant, wartet auf Budget/Tablet-Wahl |
| M10 | Aufräum-System Stufe 1 (Kamera + LED) | ⏳ |
| M11 | Aufräum-System Stufe 2 (Roboterarm SO-101) | ⏳ |
| M12 | Optional: GPU-Server 2× Tesla P40 | ⏳ jederzeit nach M3 |

Details: [docs/03-meilensteine.md](docs/03-meilensteine.md)

**Aktueller Fokus:** Arbeitszimmer, hintere Raumhälfte – aufräumen, Licht an den
Schrägen, neuer Schreibtisch, virtuelles Fenster. Lüftung und Dachfenster folgen
nach Absprache mit den Eltern.

## Dokumente

| Dokument | Inhalt |
|---|---|
| [00 Offene Fragen](docs/00-offene-fragen.md) | Was ich von dir brauche, bevor ich weiterbaue |
| [01 Architektur](docs/01-architektur.md) | Geräte, Software, Datenflüsse, Stromverbrauch |
| [02 Hardware](docs/02-hardware.md) | Einkaufsliste Muss / Später / Nice-to-have mit Preisen |
| [03 Meilensteine](docs/03-meilensteine.md) | Reihenfolge, Abnahmekriterien, wer macht was |
| [04 Sicherheit](docs/04-sicherheit.md) | Netz, VPN, Secrets, Kamera-Privatsphäre |
| [05 Routing](docs/05-routing.md) | Lokal vs. Gehirn: Entscheidungslogik, Wake/Sleep |
| [06 Dashboard](docs/06-dashboard.md) | HA-Dashboard vs. eigenes Frontend – Entscheidung |
| [07 Schreibtisch](docs/07-schreibtisch.md) | Features, Teileliste, Kosten, Druckteile |
| [08 3D-Druck](docs/08-3d-druck.md) | X2D-Integration, Druckplaner, Filament-Inventar |
| [09 Aufräumen & Roboterarm](docs/09-aufraeumen-roboterarm.md) | Kamera, Bildverarbeitung, LED-Zonen, SO-101 |
| [10 GPU-Server](docs/10-gpu-server.md) | 2× Tesla P40, nur bei Bedarf an |
| [11 Arbeitszimmer](docs/11-arbeitszimmer.md) | Raumplan mit Skizze: Licht, virtuelles Fenster, Aufräumen; Lüftung als Phase 2 |
| [Setup M1](docs/setup/M1-pi-homeassistant.md) | Schritt-für-Schritt: Pi + Home Assistant |
| [Messwerte](docs/messwerte.md) | Echte Messungen statt Schätzungen |

## Repo-Struktur

```
homeassistant/   → wird nach /config auf dem Pi synchronisiert (tools/ha-sync.sh)
  configuration.yaml
  secrets.yaml.example   (Vorlage – die echte secrets.yaml liegt nur auf dem Pi)
  packages/              (ein Thema pro Datei: Automationen, Helfer, Sensoren)
tools/           → Hilfsskripte
docs/            → Planung und Anleitungen
```

## Grundregeln

1. **Keine Secrets im Repo.** Passwörter, Tokens, MAC-/IP-Adressen gehören in
   `secrets.yaml` auf dem Pi. Das Repo ist privat, trotzdem.
2. **Keine Portfreigaben ins Internet.** Fernzugriff nur über VPN (Tailscale oder
   FRITZ!Box-WireGuard), siehe [Sicherheit](docs/04-sicherheit.md).
3. **Jeder Meilenstein funktioniert für sich.** Fällt das Gehirn aus, laufen Licht,
   Heizung und einfache Sprachbefehle trotzdem.
4. **Erst messen, dann optimieren.** Alle Verbrauchswerte in den Docs sind
   Schätzungen, bis eine Messsteckdose sie bestätigt hat.
