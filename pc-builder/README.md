# PC Baukasten

Ein PC-Konfigurator im Browser, ähnlich wie PCPartPicker, nur visueller:

- **Teile als Bilder**: Katalog mit Prozessoren, Mainboards, RAM, Grafikkarten, SSDs/HDDs, Kühlern, Netzteilen und Gehäusen.
- **Per Drag & Drop einbauen**: Teil in die 3D-Ansicht oder in die Liste „Dein PC“ ziehen, oder einfach anklicken.
- **3D-Modell**: Das Gehäuse füllt sich mit den gewählten Teilen (Mainboard, CPU, Kühler, RAM, Grafikkarte, Netzteil, Laufwerke). Drehen, zoomen, über Teile fahren für den Namen, Bild speichern.
- **Preis und Stromverbrauch** werden live addiert, inklusive empfohlener Netzteilgröße (Verbrauch + 30 % Reserve).
- **Kompatibilitätsprüfung**: CPU-Sockel ↔ Mainboard, DDR4/DDR5, Formfaktor ↔ Gehäuse, Grafikkartenlänge, Kühlerhöhe und -leistung, M.2-Slots, Netzteil-Leistung. Unpassende Teile werden im Katalog markiert („nur passende“ blendet sie aus).
- **Teile per Foto erkennen**: Foto vom offenen PC oder von einzelnen Teilen machen. Claude liest Aufdrucke und Logos, ordnet die Teile dem Katalog zu und baut sie ein. Teile, die nicht im Katalog sind, werden mit geschätzten Daten übernommen.

Der Build wird automatisch im Browser gespeichert.

## Starten

ES-Module funktionieren nicht über `file://`, daher braucht die Seite einen kleinen Webserver:

```bash
cd pc-builder
python -m http.server 8080
# oder: npx serve .
```

Dann <http://localhost:8080> öffnen. Kein Build-Schritt, keine Installation – three.js und das Anthropic-SDK kommen per CDN.

Auf dem Handy: PC und Handy im selben WLAN, dann `http://<IP-des-PCs>:8080` öffnen. Der Foto-Button öffnet direkt die Kamera.

## Foto-Erkennung

Braucht einen Anthropic-API-Schlüssel (<https://console.anthropic.com>). Er wird im Foto-Dialog eingetragen, nur im `localStorage` dieses Browsers gespeichert und direkt an `api.anthropic.com` geschickt. Für eine öffentlich gehostete Version sollte der Aufruf stattdessen über einen eigenen Server laufen, damit der Schlüssel nicht im Browser liegt.

Das Foto wird vor dem Senden auf max. 1568 px verkleinert. Die Antwort kommt als strukturiertes JSON (Kategorie, Katalog-ID, Sicherheit, Begründung, geschätzte Daten). Erkennungen mit niedriger Sicherheit sind standardmäßig abgewählt.

## Aufbau

| Datei | Inhalt |
|---|---|
| `js/parts.js` | Teile-Katalog mit Preisen und technischen Daten |
| `js/check.js` | Stromverbrauch, Netzteilempfehlung, Kompatibilitätsregeln |
| `js/scene3d.js` | 3D-Modell (three.js) |
| `js/recognize.js` | Foto-Erkennung über die Claude API |
| `js/icons.js` | generierte Produktbilder (SVG) |
| `js/app.js` | Oberfläche, Drag & Drop, Speichern |

## Grenzen

- Die Preise sind feste Richtwerte. Für echte Tagespreise müsste man eine Preis-API (z. B. Geizhals, Händler-APIs) anbinden.
- Der Katalog ist eine Auswahl (~55 Teile). Neue Teile einfach in `js/parts.js` ergänzen.
- Der Stromverbrauch ist eine Schätzung aus TDP-Werten, keine Messung.
- Drag & Drop geht am Handy nicht (Browser-Einschränkung) – dort Teile antippen.
