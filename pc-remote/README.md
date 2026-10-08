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
