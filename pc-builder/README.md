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
python -m http.server 8080   # oder unter Windows: start.bat doppelklicken
# oder: npx serve .
```

Dann <http://localhost:8080> öffnen. Kein Build-Schritt, keine Installation – three.js und das Anthropic-SDK kommen per CDN.

Auf dem Handy: PC und Handy im selben WLAN, dann `http://<IP-des-PCs>:8080` öffnen. Der Foto-Button öffnet direkt die Kamera.

## Alle Teile von PCPartPicker laden

Der eingebaute Katalog hat nur ~55 Beispielteile. Für den vollen Katalog (~46.000 Teile) einmal ausführen (Node 18+):

```bash
cd pc-builder
node tools/import-pcpp.mjs                 # alle Teile, auch ältere ohne Preis
node tools/import-pcpp.mjs --nur-mit-preis # nur ~10.000 aktuell erhältliche Teile
```

Das Skript lädt den Datensatz [docyx/pc-part-dataset](https://github.com/docyx/pc-part-dataset), der die PCPartPicker-Daten enthält, und schreibt `js/parts-db.js`. Die App nutzt die Datei automatisch, wenn sie vorhanden ist. Sie ist in `.gitignore` eingetragen und nur für den privaten Gebrauch gedacht.

Hinweise zu den Daten:
- Die Preise sind US-Preise, grob in EUR umgerechnet.
- Felder, die im Datensatz fehlen, werden abgeleitet: der CPU-Sockel aus der Architektur, der RAM-Typ des Mainboards aus Sockel und Name, die GPU-Leistungsaufnahme aus einer Tabelle von Referenzwerten und die Gehäusemaße aus dem Gehäusetyp. Größenprobleme beim Gehäuse werden deshalb nur als Warnung gezeigt.
- Zum Aktualisieren das Skript einfach erneut ausführen.

## Neue Teile (seit Juli 2025)

Der PCPartPicker-Datensatz endet im Juli 2025. Neuere Teile stehen in `js/parts-extra.js` und erscheinen im Katalog oben mit „Neu“. Dazu gehören Ryzen 7 9850X3D, Ryzen 9 9950X3D2, Core Ultra 200S Plus, RX 9050/9060, Arc Pro B70 und Samsung 9100 Pro. Die Datei enthält außerdem genaue GPU- und Kühler-Freiräume für beliebte Gehäuse, damit dort nicht geschätzt wird. Die Quellen stehen in der Datei.

## Aktuelle Preise

„Aktuelle Preise abrufen“ im Bereich „Dein PC“ sucht mit Claude und Websuche die günstigsten lieferbaren Preise für alle Teile im Build. Gesucht wird auf deutschen Preisvergleichen und Shops: Geizhals, idealo, Mindfactory, Alternate, Caseking und weiteren. Jeder Preis bekommt einen Link zum Angebot und wird im Browser gespeichert. Ist er älter als einen Tag, steht ein Hinweis dabei. Ohne Live-Preis gilt der Katalogpreis.

Eine Abfrage kostet einige Cent API-Guthaben (Websuche plus Tokens). Sie nutzt denselben API-Schlüssel wie die Foto-Erkennung.

## Foto-Erkennung

Braucht einen Anthropic-API-Schlüssel (<https://console.anthropic.com>). Er wird im Foto-Dialog eingetragen, nur im `localStorage` dieses Browsers gespeichert und direkt an `api.anthropic.com` geschickt. Für eine öffentlich gehostete Version sollte der Aufruf stattdessen über einen eigenen Server laufen, damit der Schlüssel nicht im Browser liegt.

Das Foto wird vor dem Senden auf max. 1568 px verkleinert. Claude bekommt die je 60 beliebtesten Teile pro Kategorie als Liste; alle anderen werden danach lokal über den Namen im vollen Katalog gesucht. Die Antwort kommt als strukturiertes JSON (Kategorie, Katalog-ID, Sicherheit, Begründung, geschätzte Daten). Erkennungen mit niedriger Sicherheit sind standardmäßig abgewählt.

## Aufbau

| Datei | Inhalt |
|---|---|
| `js/parts.js` | Beispielkatalog, lädt `js/parts-db.js` falls vorhanden |
| `tools/import-pcpp.mjs` | Import des PCPartPicker-Datensatzes |
| `js/check.js` | Stromverbrauch, Netzteilempfehlung, Kompatibilitätsregeln |
| `js/scene3d.js` | 3D-Modell (three.js) |
| `js/parts-extra.js` | recherchierte neue Teile und Gehäusemaße |
| `js/prices.js` | Live-Preise über Claude mit Websuche |
| `js/recognize.js` | Foto-Erkennung über die Claude API |
| `js/icons.js` | generierte Produktbilder (SVG) |
| `js/app.js` | Oberfläche, Drag & Drop, Speichern |

## Grenzen

- Katalogpreise sind Richtwerte. Echte Tagespreise gibt es über „Aktuelle Preise abrufen“.
- Der Stromverbrauch ist eine Schätzung aus TDP-Werten, keine Messung.
- Drag & Drop geht am Handy nicht (Browser-Einschränkung) – dort Teile antippen.
