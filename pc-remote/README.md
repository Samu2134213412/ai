# PC Remote

PC vom Handy-Browser steuern: Touchpad, Tastatur, Medien/Lautstärke, Live-Bildschirm (antippen = Maus), Sperren/Standby/Herunterfahren. Optional Shell.

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
