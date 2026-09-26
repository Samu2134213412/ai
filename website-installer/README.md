# Website-Installer

Eine Datei, doppelklicken, fertig: **`Website-Installer.bat`** richtet auf einem
Windows-PC (10 oder 11) eine eigene Website ein. Keine Admin-Rechte, keine
zusätzlichen Programme – es nutzt nur das PowerShell, das in Windows schon drin ist.

Der Installer fragt zuerst, **was für eine Website** es sein soll:

- **[1] Einfache Website** – dein HTML-Design (z. B. aus Claude Design) hochladen und im
  eingebauten Editor bearbeiten.
- **[2] WordPress** – das bekannte WordPress, auf Deutsch. Seiten, Beiträge, Bilder, Menüs,
  Plugins und Themes bearbeitest du im WordPress-Dashboard.
  Details unten unter [WordPress](#wordpress).

Danach fragt er, **wo** sie laufen soll:

- **[1] Nur auf diesem PC** – zum Ausprobieren, nur du siehst die Seite.
- **[2] Im Internet unter deiner eigenen Domain** – dieser PC wird zum Server.
  Die Website startet automatisch mit Windows, und du bearbeitest sie von
  überall unter `https://deine-domain.de/_admin/` (mit Passwort).
  Details unten unter [Online mit eigener Domain](#online-mit-eigener-domain).

## So geht's

1. `Website-Installer.bat` herunterladen (auf GitHub: Datei öffnen → „Download raw file“).
2. Doppelklicken. Falls Windows warnt („Der Computer wurde durch Windows geschützt“):
   **Weitere Informationen → Trotzdem ausführen**.
3. Namen für die Website eingeben (oder einfach Enter).
4. Der Browser öffnet die **Bearbeiten-Seite**. Dort den Export aus
   **Claude Design** hineinziehen – als ZIP, HTML-Datei oder ganzer Ordner.

Danach liegen auf dem Desktop zwei Verknüpfungen:

| Verknüpfung | Was sie tut |
|---|---|
| **Meine Website** | startet die Website und zeigt sie im Browser (`http://localhost:8080/`) |
| **Meine Website bearbeiten** | öffnet die Bearbeiten-Seite (`http://localhost:8080/_admin/`) |

## Die Bearbeiten-Seite

- **Design hochladen** – ZIP, HTML-Datei(en) oder Ordner per Drag & Drop.
  Steckt alles in einem Unterordner, wird der automatisch „ausgepackt“.
  Heißt die Seite nicht `index.html`, wird eine Startseite angelegt, die dorthin weiterleitet.
- **Bisherige Website ersetzen** – die alte Version wird vorher in `backups\` gesichert
  (die letzten 15 bleiben erhalten).
- **Bearbeiten** – Datei links anklicken, ändern, `Strg+S`. Die Vorschau rechts
  aktualisiert sich sofort.
- **+ Neu / Löschen** – Seiten und Dateien anlegen oder entfernen.
- **Ordner öffnen** – die Dateien direkt im Explorer, z. B. um sie mit VS Code zu bearbeiten.

## Was wird wo installiert?

```
C:\Users\<du>\Meine Website\
  website\                 deine Website-Dateien (frei bearbeitbar)
  backups\                 automatische Sicherungen
  app\                     der kleine Webserver + Bearbeiten-Seite
  Website starten.bat
  Website bearbeiten.bat
  Deinstallieren.bat
  LIESMICH.txt
```

Im Modus [1] läuft die Website, solange das (minimierte) PowerShell-Fenster in der Taskleiste
offen ist. Sie ist nur auf diesem PC erreichbar. Nochmal installieren
(gleicher Name) aktualisiert nur das Programm – deine Website bleibt, wie sie ist.

Um die Seite später ins Internet zu stellen, einfach den Inhalt von `website\`
bei einem Hoster hochladen (z. B. Netlify, GitHub Pages, Cloudflare Pages –
per Drag & Drop).

## WordPress

Alles, was WordPress braucht, landet portabel im Website-Ordner. Ins System wird nichts
installiert, außer bei Bedarf der Visual-C++-Laufzeit von Microsoft, die PHP braucht.

| Teil | Wofür |
|---|---|
| **PHP 8.3** (offizieller Windows-Build) | darin läuft WordPress, mit 4 Prozessen für mehrere Besucher gleichzeitig |
| **Caddy** | schneller Webserver, reicht Anfragen an PHP weiter |
| **WordPress (deutsch)** | direkt von de.wordpress.org |
| **SQLite Database Integration** | offizielles Plugin vom WordPress-Team, Datenbank als Datei statt MySQL |

Der Installer fragt nach Benutzername, E-Mail und Passwort für WordPress und richtet
alles fertig ein: deutsche Datums-/Zeitformate, schöne Links (`/meine-seite/`) und ein
kleines Schutz-Plugin. Das Plugin sperrt die Anmeldung nach 5 falschen Passwörtern
15 Minuten lang und schaltet XML-RPC ab. Die Datenbank, `wp-config.php` und
`xmlrpc.php` liefert der Webserver nie aus.

WordPress läuft im Hintergrund und startet mit Windows, auch lokal. Deshalb fragt Windows
einmal nach Administrator-Rechten. Bearbeiten geht unter `…/wp-admin/`.

**Dein Claude-Design in WordPress:** In WordPress kommt das Aussehen aus einem *Theme*.
Aus deinem Claude-Design-Export kann Claude ein WordPress-Theme machen. Das lädst du dann unter
**Design → Themes → Theme hochladen** hoch. Danach bearbeitest du Texte und Bilder
direkt im WordPress-Editor.

Hinweise:

- WordPress kann von diesem PC aus keine E-Mails verschicken (z. B. „Passwort vergessen“).
  Leg dir am besten einen zweiten Admin-Benutzer als Reserve an.
- Sichern: den ganzen Ordner `website\` kopieren. Die Datenbank liegt in
  `website\wp-content\database\`.
- Wechselst du von lokal auf deine Domain (Installer erneut mit [2] starten), zieht der
  Installer die Adresse in WordPress samt Links in Beiträgen mit um.

## Online mit eigener Domain

Der PC wird über einen **Cloudflare Tunnel** mit deiner Domain verbunden. Das ist kostenlos,
bringt HTTPS automatisch mit, und du musst am Router nichts einstellen.
Deine Heim-IP-Adresse bleibt dabei verborgen.

**Einmalig vorher (ca. 10 Minuten):**

1. Kostenloses Konto auf [dash.cloudflare.com](https://dash.cloudflare.com/sign-up) anlegen.
2. „Domain hinzufügen“ → deine Domain → Tarif **Free**.
3. Cloudflare zeigt zwei Nameserver an. Die trägst du bei deinem Domain-Anbieter
   (IONOS, Strato, GoDaddy …) unter „Nameserver“ ein.
4. Warten, bis Cloudflare die Domain als **aktiv** meldet (Minuten bis 24 Stunden).

**Dann:** Installer starten, **[2]** wählen und den Anweisungen folgen. Der Installer

- fragt bei der einfachen Website ein Passwort für die Bearbeiten-Seite ab (gespeichert nur als
  PBKDF2-Hash). Bei WordPress schützt WordPress selbst die Anmeldung,
- lädt `cloudflared` herunter und öffnet den Browser für die Cloudflare-Anmeldung,
- legt den Tunnel an und setzt die DNS-Einträge für `deine-domain.de` und `www.deine-domain.de`,
- richtet eine Windows-Aufgabe ein, die Webserver (bzw. PHP + Caddy) und Tunnel **beim Hochfahren startet**
  (auch ohne Anmeldung) und bei Absturz neu startet,
- schaltet den Standby am Stromnetz ab, damit der Server wach bleibt.

Dafür braucht der Installer einmal Administrator-Rechte (Windows fragt nach).

Gut zu wissen:

- Der PC muss eingeschaltet und mit dem Internet verbunden sein, sonst ist die Seite offline.
- Nach 5 falschen Passwörtern ist die Anmeldung für diese IP-Adresse 15 Minuten gesperrt.
- Probleme? In `logs\` stehen `tunnel.log` und `server.log`.
- Passwort ändern: Installer erneut starten, gleichen Namen, **[2]**, „Einstellungen behalten“ → J.
- Für eine öffentliche Seite in Deutschland brauchst du je nach Inhalt ein **Impressum**
  und eine **Datenschutzerklärung**.

## Für Entwickler

Die Quellen liegen in `src/`. Nach Änderungen die Installer-Datei neu bauen:

```
python build.py
```

`build.py` packt `install.ps1` samt `server.ps1`, `host.ps1`, `uninstall.ps1`,
`admin.html`, `login.html`, `start.html` und den Dateien in `src/wordpress/`
(Base64) in `Website-Installer.bat`.
