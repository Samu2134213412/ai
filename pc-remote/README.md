# PC Remote

PC vom Handy-Browser steuern. Oben immer der Live-Bildschirm, **Wischen links/rechts wechselt den Monitor**. Button oben links schaltet den Modus:
- **Tasten:** Bild oben, unten Touchpad/Tastatur/Medien/Power. Tippen aufs Bild = Maus dorthin, Doppeltippen = Klick.
- **Touch:** Das Handy-Display *ist* der PC-Bildschirm, wie Android-Steuerung: Tippen = Linksklick, Doppeltippen = Doppelklick, lang drücken = Rechtsklick, hoch/runter wischen = scrollen, Tippen + sofort halten & ziehen = Ziehen. „⌨ Menü“ öffnet die Tasten-Leiste.
Optional Shell-Tab (`--allow-exec`).

```
pip install -r requirements.txt
python server.py            # --allow-exec aktiviert den Shell-Tab
```

Die ausgegebene URL (bzw. der QR-Code) auf dem Handy öffnen – selbes WLAN oder Tailscale. Der Token steht in `~/.pc-remote-token` (`--reset-token` erneuert ihn).

Sicherheit: Jede Aktion braucht den Token; Shell ist standardmäßig aus; **nie** per Portfreigabe ins Internet stellen (kein HTTPS). Windows-Firewall-Rückfrage für Python erlauben (privates Netz).
Linux/Wayland: pynput/mss funktionieren nur unter X11.

Tests: `pytest tests`

## Anschalten (Wake-on-LAN)
Ein ausgeschalteter PC kann keinen Server starten. Dafür `wake.py` auf einem immer laufenden Gerät im selben LAN (Raspberry Pi, NAS, Router mit Python):
```
python wake.py --mac AA:BB:CC:DD:EE:FF
```
URL aufs Handy → „PC anschalten“. (Fritz!Box: kann das auch direkt unter Heimnetz → Netzwerk → Gerät → „Computer starten“.)
Voraussetzungen am PC: LAN-Kabel (WLAN-WoL klappt meist nicht), im BIOS „Wake on LAN/PCIe“ an, Windows: Netzwerkadapter → Energieverwaltung → „Magic Packet“ erlauben, Schnellstart aus. Von unterwegs: Relay + Tailscale auf dem Always-on-Gerät.
Server nach dem Booten automatisch starten: Windows Aufgabenplanung („Bei Anmeldung“ → `python server.py`).

## Von überall (nicht nur im WLAN)
**Option A – Tunnel (am einfachsten):** `winget install Cloudflare.cloudflared`, neues Fenster, dann `py server.py --tunnel`. Es erscheint eine öffentliche `https://….trycloudflare.com/#TOKEN`-URL (ändert sich bei jedem Start). Kein Router-Setup nötig. `--allow-exec` dabei **nicht** verwenden.
**Option B – Tailscale (sicherer, feste Adresse):** Tailscale auf PC und Handy installieren, dann die Tailscale-IP des PCs: `http://100.x.y.z:8765/#TOKEN`. Nicht öffentlich erreichbar.
Der Token schützt den Zugang; nach 20 Fehlversuchen/Minute wird gesperrt.

## Ohne Computer-Gefummel: Anschalten + Autostart
1. **Autostart:** `install-autostart.bat` einmal doppelklicken. Danach startet PC Remote bei jeder Windows-Anmeldung von selbst (versteckt). Einmal vorher `py server.py` sichtbar starten und die URL am Handy öffnen – der Token wird im Handy gemerkt. Windows-Autologin (Win+R → `netplwiz`) einrichten, damit der PC nach dem Anschalten ohne PIN hochfährt. Entfernen: `uninstall-autostart.bat`. Für Zugriff von überall hier Tailscale nutzen (feste Adresse); die Tunnel-URL ändert sich bei jedem Start.
2. **Anschalten vom Handy** (PC muss per LAN-Kabel hängen, Wake-on-LAN in BIOS + Netzwerkadapter aktiv):
   - **Zuhause im WLAN:** Eine WoL-App aus dem Play Store (z. B. „Wake On Lan“) mit der MAC-Adresse des PCs.
   - **Von überall mit Fritz!Box:** MyFRITZ einrichten, Fritz!Box-Oberfläche am Handy öffnen → Heimnetz → Netzwerk → PC → „Computer starten“.
   - **Von überall mit eigenem Gerät:** `wake.py` auf einem Raspberry Pi/NAS (+ Tailscale): `python wake.py --mac AA:BB:CC:DD:EE:FF --pc-url http://100.x.y.z:8765/`. Seite am Handy öffnen → „PC anschalten“ → danach „PC-Steuerung öffnen“.

## Autologin nur beim Wecken vom Handy (Boot-Guard)
Idee: Windows-Autologin bleibt an, aber `boot_guard.py` sperrt den PC direkt nach dem Hochfahren wieder – **außer** das Wake-Relay (`wake.py` auf dem Raspberry Pi) hat kurz vorher (10 min) ein Weck-Signal vom Handy gesendet. Powertaste = Passwort, Handy = direkt Desktop. Relay nicht erreichbar = gesperrt.
Einrichten (erst wenn `wake.py` auf dem Pi läuft): `install-guard.bat` → Pi-Adresse + Token eingeben. Entfernen: `uninstall-guard.bat`.
Grenzen: Beim Powertasten-Start ist der Desktop ~1–2 s sichtbar, bevor er sperrt; das Autologin-Passwort liegt in Windows gespeichert. Nur bei einem PC zu Hause sinnvoll. Der Guard greift nur in den ersten 10 min nach dem Booten.
