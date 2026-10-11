# 04 – Sicherheit

Grundsatz: **Von außen ist nichts erreichbar.** Fernzugriff nur über ein VPN, das
dich als bekanntes Gerät ausweist.

## Fernzugriff: zwei Wege, du entscheidest

| | Tailscale (Vorschlag) | FRITZ!Box-WireGuard |
|---|---|---|
| Offene Ports | **keine** (Verbindung wird von innen aufgebaut) | 1 UDP-Port an der FRITZ!Box (WireGuard antwortet unbekannten Absendern nicht – für Scanner unsichtbar) |
| Drittanbieter | Tailscale-Koordinationsserver (sieht Metadaten, nicht deinen Datenverkehr – der ist Ende-zu-Ende verschlüsselt) | keiner |
| Funktioniert mit DS-Lite (keine öffentliche IPv4) | ja | nur über IPv6 – oft hakelig |
| Einrichtung | Add-on auf dem Pi + App aufs Handy, 10 min | FRITZ!Box-Menü + App, 15 min |

Beides lässt sich auch kombinieren (WireGuard als Notfallzugang).

### Tailscale-Regeln

- Add-on auf dem Pi, **Funnel bleibt aus** (Funnel würde HA öffentlich ins Internet stellen).
- Kein Subnet-Router: Über das VPN erreichst du nur den Pi, nicht PC/Drucker. Alles läuft über HA.
- In der Tailscale-Verwaltung: Schlüsselablauf für den Pi deaktivieren, für Handys aktiv lassen; 2FA für dein Tailscale-Konto.

## FRITZ!Box

- **Internet → Freigaben:** keine Einträge; „Selbstständige Portfreigaben“ (UPnP) für alle Geräte aus.
- **MyFRITZ!-Internetzugriff** auf die Box aus (außer du nutzt WireGuard).
- **Zugangsprofile:** Drucker, ESP-Geräte, Tablet und Satellit bekommen ein Profil ohne Internet. Die Geräte können dann nicht „nach Hause telefonieren“. Firmware-Updates machst du bewusst, indem du das Profil kurz wechselst.
- Feste IP-Adressen (DHCP-Reservierung) für Pi, PC, Server, Drucker.

## Home Assistant

- Starkes Passwort + **Zwei-Faktor (TOTP)** für deinen Benutzer.
- `ip_ban_enabled` + `login_attempts_threshold: 5` (in `configuration.yaml`).
- Eigene HA-Benutzer für Dienste (MQTT), Option „nur aus lokalem Netz anmelden“.
- Nabu Casa Cloud: nicht nötig, bleibt aus.
- Backups verschlüsselt (Standard seit HA 2025.1); den Notfallschlüssel im Passwortmanager speichern.

## Dienste im LAN

| Dienst | Absicherung |
|---|---|
| MQTT (Mosquitto) | Kein anonymer Zugriff, eigener Benutzer pro Client (HA, Zigbee2MQTT, pc-agent, Drucker-Brücke) |
| Ollama (PC/Server) | **Hat keine Anmeldung.** Windows-Firewall: Port 11434 nur für die IP des Pi. Unter Linux: `ufw` entsprechend |
| Whisper (Wyoming) | Port 10300 nur für die IP des Pi |
| ESPHome-Geräte | API-Verschlüsselungsschlüssel + OTA-Passwort pro Gerät |
| Bambu X2D | LAN-only-Modus, Zugangscode nur in `secrets.yaml` |

## Secrets und Repo

- Repo **privat**. Trotzdem: keine Passwörter, Tokens, Zugangscodes, MAC-Adressen im Repo.
- Alles Geheime in `/config/secrets.yaml` auf dem Pi; im Repo liegt nur `secrets.yaml.example` mit Platzhaltern.
- Der Pi holt das Repo mit einem **Deploy-Key (nur Lesen)** – kompromittierter Pi kann nichts ins Repo schreiben.

## Kameras und Privatsphäre

- Schreibtisch-Kamera hängt am PC (USB) und ist nur aktiv, wenn du eine Prüfung auslöst. Bilder werden standardmäßig nicht gespeichert.
- 🖨 Mechanische Sichtschutzklappe für die Kamera.
- Drucker-Kamera nur im LAN; von unterwegs über HA (VPN), nie über einen öffentlichen Link.
- Mikrofon: Der Satellit überträgt Audio erst nach dem Wake-Word; Stummschalter am Gerät.

## Updates

HA: Backup vor jedem Update (Option im Update-Dialog). FRITZ!OS: automatische
Updates an. PC/Server: normale Updates, Treiber für P40 bewusst festhalten
(siehe [10-gpu-server.md](10-gpu-server.md)).
