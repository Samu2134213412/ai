# PC Remote – PC vom Handy steuern, dauerhaft

## So richtest du es einmal ein (alles im Kontrollfenster)
1. ZIP entpacken, im Ordner `pc-remote` **`PC-Remote.bat`** doppelklicken.
2. Im Fenster die Liste „Einrichtung“ von oben nach unten abarbeiten (rote ✗ → Knopf klicken):
   Programmteile · Autostart · Fester Link (Tailscale) · Automatisch anmelden · PC fürs Anschalten vorbereiten.
3. Oben auf **Starten**. Unter „Verbindung vom Handy“ den **festen Link** kopieren, am Handy öffnen, als Lesezeichen speichern.
4. Fertig: PC aus → wieder an → Windows meldet sich selbst an → Server startet unsichtbar → derselbe Link geht wieder.
5. **Anschalten vom Handy aus** (wenn der PC ganz aus ist): braucht ein Gerät, das immer läuft (Raspberry Pi) oder eine Fritz!Box:
   `sudo bash pi-wake-setup.sh <MAC-des-PCs>` auf dem Pi (MAC steht im Fenster). Ergibt einen festen Link „PC anschalten“.
   Am PC: LAN-Kabel, im BIOS „Wake on LAN“ an, Knopf „PC vorbereiten (Admin)“.

Wenn sich Fenster immer wieder öffnen oder etwas nicht klappt: Protokoll (Knopf im Fenster) ansehen oder Foto schicken.

---

# PC Remote

PC vom Handy-Browser steuern. Oben immer der Live-Bildschirm, **Wischen links/rechts wechselt den Monitor**. Button oben links schaltet den Modus:
- **Tasten:** Bild oben, unten Touchpad/Tastatur/Medien/Power. Tippen aufs Bild = Maus dorthin, Doppeltippen = Klick.
- **Touch:** Das Handy-Display *ist* der PC-Bildschirm, wie Android-Steuerung: Tippen = Linksklick, Doppeltippen = Doppelklick, lang drücken = Rechtsklick, hoch/runter wischen = scrollen, Tippen + sofort halten & ziehen = Ziehen. „⌨ Menü“ öffnet die Tasten-Leiste.
- **Spiel-Modus** (3. Modus im Menü ☰): Live-Videostrom (Motion-JPEG, bis ~30 FPS) mit Bildschirm-Controller: links Stick = WASD, rechts ziehen = Maus-Blick, Buttons für Feuer (halten + ziehen = zielen), Zielen, Sprung, Sprint, Ducken, E/Q/R/Tab/Esc. Einstellungen (FPS, Breite, Qualität, Maus-Tempo) im Menü. Handy quer halten.
Optional Shell-Tab (`--allow-exec`).
- **Zoom:** Mit zwei Fingern zoomen (Pinch) und verschieben; zoomt scharf (der PC liefert den Ausschnitt in voller Auflösung). Menü ☰ (links oben): Zoom +/−/1×, Modus, Tastatur-Menü, **Vollbild** (⛶; iPhone: Teilen → Zum Home-Bildschirm).
- **Tastenkombis:** Tab „Tastatur“: Strg/Alt/Shift/Win antippen (bleiben aktiv), dann eine Taste; fertige Kombis (Strg+C/V/X/A/Z, Alt+Tab, Alt+F4, Win+D, Task-Manager …), F1–F12, freies Tastenfeld.
- **Leuchten am PC:** Solange das Handy steuert (und 2,5 s danach), liegt ein blau leuchtender Ring um den Mauszeiger auf dem PC (klickdurchlässig, nicht im Handy-Bild). Abschalten: `--no-overlay`. Braucht tkinter (bei python.org-Python für Windows dabei).
- **Cursor am Handy:** Der echte PC-Mauszeiger wird als blau leuchtender Zeiger mit Klick-Welle angezeigt.

**Ohne Befehle:** `PC-Remote.bat` (oder `panel.pyw`) doppelklicken → Kontrollfenster mit Starten/Stoppen, Links + QR-Code, Autostart-Haken, Einstellungen, Programmteile installieren, Desktop-Verknüpfung. Das Fenster zu schließen stoppt den Server nicht.

Mit Befehlen:
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

## Spiel-Modus: Grenzen (ehrlich)
- Es ist Tastatur+Maus-Steuerung, **kein Gamepad**. Gut für Strategie, Aufbau, Koop, langsame Shooter; für schnelle Online-Shooter ist die Latenz zu hoch.
- FPS: Das Bild wird in 3 Threads parallel umgerechnet und in Reihenfolge gesendet (Motion-JPEG). Im Test (Linux, leerer Bildschirm) waren es 57–60 FPS; auf einem echten Windows-Desktop hängt es an der Bildschirmaufnahme: `pip install -r requirements-game.txt` (dxcam) macht sie deutlich schneller. Danach zählt das Netz (WLAN 5 GHz) und die Breite (480–854 ist schneller als 1280+). Zusätzlich ~50–100 ms Latenz.
- Das Spiel im **Fenster- oder randlosen Vollbild** starten, nicht „exklusiver Vollbildmodus“ (sonst schwarzes Bild). Spiele mit Anti-Cheat (EAC/BattlEye/Vanguard) können simulierte Eingaben blockieren oder deswegen bannen: nur Einzelspieler-/Koop-Spiele ohne Anti-Cheat verwenden.
- Am besten im WLAN (5 GHz) oder über Tailscale. Über den öffentlichen Tunnel ist der Videostrom zu langsam. Der Stream-Link enthält den Token (nur für `/api/stream`), nicht weitergeben.
- Sicherheitsnetz: Lässt das Handy die Verbindung fallen, lässt der PC nach 3 s alle gehaltenen Tasten los.

## Fester Link, läuft unsichtbar im Hintergrund
1. `install-autostart.bat` (Server startet bei jeder Windows-Anmeldung unsichtbar).
2. `install-fixed-link.bat` einmalig: installiert Tailscale (kostenlos), Anmeldung im Browser, schaltet `tailscale funnel --bg 8765` ein. Danach gibt es einen **festen** Link `https://<pc>.<tailnet>.ts.net/#TOKEN` (ändert sich nie, auch nicht nach Neustart). Falls Tailscale eine Freischaltung („Enable HTTPS/Funnel“) im Browser verlangt: einmal bestätigen und das Skript nochmal starten.
3. `LINK-ANZEIGEN.bat` zeigt alle Links an und kopiert den öffentlichen. Auf dem Handy als Lesezeichen / „Zum Startbildschirm“ speichern: der Token wird gemerkt.
Sicherheit: Der Link ist öffentlich erreichbar; Schutz ist der lange Zugangscode. Falsche Codes werden gebremst, der richtige nie gesperrt. Nicht weitergeben. Neuer Code: `py server.py --reset-token` (dann Link neu holen). Für den Mama-Hilfe-Fall bleibt `HILFE-STARTEN.bat` (Wegwerf-Link, nur solange das Fenster offen ist).
