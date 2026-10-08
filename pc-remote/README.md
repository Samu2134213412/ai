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
