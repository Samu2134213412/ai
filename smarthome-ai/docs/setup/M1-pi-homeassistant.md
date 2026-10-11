# Setup M1 – Pi + Home Assistant + Fernzugriff

Dauer: ≈ 1–2 Stunden. Du machst die Schritte selbst; zu jedem steht, **warum**.
Ergebnis: Home Assistant läuft auf dem Pi, ist im LAN und per VPN erreichbar,
sichert sich täglich und übernimmt Konfiguration aus diesem Repo.

Du brauchst: Pi 4, Netzteil, LAN-Kabel zur FRITZ!Box, USB-SSD (oder übergangsweise
microSD ≥ 32 GB, Klasse A2), einen PC mit Raspberry Pi Imager.

---

## 1. Bootloader prüfen (nur bei SSD)

**Warum:** Der Pi 4 muss von USB starten können. Geräte ab etwa Herbst 2020 können
das ab Werk.

Falls unklar: Im Raspberry Pi Imager „Misc utility images → Bootloader (Pi 4
family) → USB Boot“ auf eine microSD schreiben, Pi damit einmal starten, bis die
grüne LED gleichmäßig blinkt, ausschalten, Karte entfernen.

## 2. Home Assistant OS auf die SSD schreiben

Raspberry Pi Imager → Gerät „Raspberry Pi 4“ → Betriebssystem „Other
specific-purpose OS → Home assistants and home automation → Home Assistant →
Home Assistant OS (RPi 4/400)“ → Ziel: die SSD.

**Warum HA OS:** Betriebssystem, Home Assistant und Add-ons kommen als eine
Einheit mit Ein-Klick-Updates und Backups. Für dich: weniger Linux-Pflege.

## 3. Optional: Funk des Pi abschalten (Strom)

Die SSD am PC lassen, Partition **hassos-boot** öffnen, in `config.txt` am Ende
ergänzen:

```
dtoverlay=disable-wifi
dtoverlay=disable-bt
```

**Warum:** Der Pi hängt am Kabel; WLAN und Bluetooth bräuchten nur Strom
(Ersparnis gering, ≈ 0,1–0,3 W) und erzeugen Funkverkehr neben dem Zigbee-Stick.
Brauchst du später Bluetooth-Geräte, Zeile wieder entfernen.

## 4. Starten und feste IP vergeben

SSD an einen **blauen** USB-3-Port, LAN-Kabel, Strom. Erster Start dauert einige
Minuten.

FRITZ!Box: Heimnetz → Netzwerk → Gerät **homeassistant** → Bearbeiten →
„Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen“.

**Warum:** PC, Handy-App und später der Drucker sprechen den Pi über diese Adresse
an. Wechselt sie, bricht alles.

Dann im Browser: `http://homeassistant.local:8123` (oder `http://<IP>:8123`).

## 5. Einrichtung und Absicherung

1. Benutzer anlegen (**starkes Passwort**), Standort, Einheiten, Zeitzone.
2. Profil (unten links) → **Erweiterter Modus** an.
   *Warum:* Zeigt Add-ons und Optionen, die wir brauchen.
3. Profil → Sicherheit → **Zwei-Faktor-Authentifizierung (TOTP)** aktivieren.
   *Warum:* Selbst wenn jemand dein Passwort kennt, kommt er ohne Handy nicht rein.

## 6. FRITZ!Box anbinden (Anwesenheit)

1. FRITZ!Box: Heimnetz → Netzwerk → Netzwerkeinstellungen → „Zugriff für
   Anwendungen zulassen“ an. *Warum:* Darüber (TR-064, nur im LAN) liest HA, welche
   Geräte im WLAN sind.
2. FRITZ!Box: System → FRITZ!Box-Benutzer → neuen Benutzer `homeassistant` mit
   Recht „FRITZ!Box Einstellungen“. *Warum:* Eigener Benutzer = eigene Rechte,
   jederzeit entziehbar.
3. HA: Einstellungen → Geräte & Dienste → Integration hinzufügen →
   **AVM FRITZ!Box Tools** → Host `fritz.box`, Benutzer von eben.
4. Einstellungen → Personen → dich anlegen und dein Handy als Tracker zuordnen.

## 7. Fernzugriff per Tailscale

1. Einstellungen → Add-ons → Add-on-Store → **Tailscale** → Installieren →
   Starten → „Web-UI öffnen“ → anmelden.
2. In den Add-on-Optionen bleibt **Funnel aus**.
   *Warum:* Funnel würde HA öffentlich ins Internet stellen – genau das wollen wir nicht.
3. [Tailscale-Verwaltung](https://login.tailscale.com/admin/machines): beim Pi
   „Disable key expiry“. Dein Tailscale-Konto mit 2FA absichern.
4. Tailscale-App aufs Handy, gleiches Konto.
5. HA Companion App: interne URL `http://<Pi-IP>:8123` (mit deinem WLAN-Namen),
   externe URL `http://homeassistant.<dein-tailnet>.ts.net:8123`.

**Test:** WLAN am Handy aus, nur mobile Daten → App öffnet HA. Dann in der
FRITZ!Box unter Internet → Freigaben prüfen: **keine Einträge**.

Lieber FRITZ!Box-WireGuard? Siehe [Sicherheit](../04-sicherheit.md) – sag Bescheid,
dann schreibe ich den Abschnitt dafür.

## 8. Backups

1. Einstellungen → System → Backups → automatische Backups: täglich, 7 behalten.
2. **Notfall-Schlüssel herunterladen** und im Passwortmanager speichern.
   *Warum:* Backups sind verschlüsselt; ohne Schlüssel sind sie wertlos.
3. Falls die FRITZ!Box einen USB-Speicher hat: Einstellungen → System → Speicher →
   Netzwerkspeicher hinzufügen → Verwendung „Backup“, SMB, Server `fritz.box`,
   Freigabe des USB-Speichers, FRITZ!Box-Benutzer mit NAS-Recht. Dann im
   Backup-Dialog als zusätzlichen Speicherort wählen.
   *Warum:* Stirbt die SSD, liegen die Backups noch woanders.

## 9. Konfiguration aus dem Repo übernehmen

**Warum dieser Weg:** Das Repo ist die Quelle der Wahrheit für alles, was als YAML
gepflegt wird. Der Pi holt es mit einem **Deploy-Key, der nur lesen darf** – selbst
ein kompromittierter Pi könnte nichts ins Repo schreiben.

1. Add-on-Store → **Advanced SSH & Web Terminal** installieren. Konfiguration:
   `packages:` → `rsync` eintragen; SSH-Netzwerkport leer lassen (wir nutzen nur das
   Web-Terminal in der Seitenleiste). Starten.
2. Im Terminal einen Schlüssel erzeugen und anzeigen:
   ```bash
   mkdir -p /share/.ssh && chmod 700 /share/.ssh
   ssh-keygen -t ed25519 -N "" -C "ha-pi deploy" -f /share/.ssh/smarthome_deploy
   cat /share/.ssh/smarthome_deploy.pub
   ```
3. GitHub → Repo `smarthome-ai` → Settings → Deploy keys → Add deploy key →
   den angezeigten Text einfügen, **„Allow write access“ aus lassen**.
4. Skript holen und ausführen (beim ersten Mal per Kopie aus dem Repo, danach liegt
   es unter `/share/smarthome-ai/tools/`):
   ```bash
   GIT_SSH_COMMAND="ssh -i /share/.ssh/smarthome_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
     git clone --depth 1 git@github.com:samu2134213412/smarthome-ai.git /share/smarthome-ai
   bash /share/smarthome-ai/tools/ha-sync.sh
   ```
5. Meldet das Skript „Konfiguration gültig“: `ha core restart`.

Später reicht nach jeder Änderung im Repo: `bash /share/smarthome-ai/tools/ha-sync.sh`.

## 10. Pi-Gesundheit aktivieren

Einstellungen → Geräte & Dienste → Integration hinzufügen → **System Monitor**.
Danach beim Gerät „System Monitor“ die (standardmäßig deaktivierten) Sensoren
**Arbeitsspeicher-Auslastung**, **Datenträger-Auslastung** und
**Prozessortemperatur** aktivieren. Entwicklerwerkzeuge → Zustände → nach
`system_monitor` filtern und prüfen, ob die IDs zu
`homeassistant/packages/pi_health.yaml` passen.

## 11. Messen und notieren (deine Aufgabe)

Trag nach 24 h Laufzeit in [../messwerte.md](../messwerte.md) ein: RAM-Auslastung,
CPU-Last, Temperatur. Stromverbrauch des Pi messen wir in M2 mit der ersten
Messsteckdose.

## Abnahme M1

- [ ] HA im LAN erreichbar, feste IP
- [ ] 2FA aktiv
- [ ] HA per Tailscale über mobile Daten erreichbar
- [ ] FRITZ!Box: keine Portfreigaben, Funnel aus
- [ ] Automatisches Backup + Notfall-Schlüssel gesichert
- [ ] `ha-sync.sh` läuft durch, Pi-Gesundheitswarnungen aktiv
- [ ] Messwerte eingetragen
