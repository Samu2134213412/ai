# Anzeigen-Picker

Funktioniert wie PCPartPicker, nur für Kleinanzeigen: Du fügst Links zu Anzeigen ein, und
der Picker zeigt dir für jedes PC-Teil Preis, Versand, Gesamtsumme, den aktuellen
Marktpreis und ein **Scam-Risiko** mit Begründung.

## Starten

Voraussetzung: [Node.js](https://nodejs.org) ab Version 18. Weitere Pakete braucht es nicht.

- **Windows:** `start.bat` doppelklicken
- **Mac/Linux:** `./start.sh` oder `npm start`

Danach öffnet sich der Browser mit http://localhost:3000.
Läuft auf Port 3000 schon etwas anderes, nimm einen anderen Port: `PORT=3001 npm start`.

## Bedienung

- Link oben einfügen und auf **+ Hinzufügen** klicken. Die Anzeige wird automatisch
  einsortiert (CPU, Grafikkarte …). Du kannst auch über „+ CPU wählen“ eine bestimmte
  Zeile füllen. Die Share-Texte aus der App gehen ebenfalls.
- Mit einem Klick auf den **Titel** oder das **Risiko-Badge** öffnen sich die Details:
  Gründe für die Bewertung, Vergleichsangebote, Beschreibung und Felder zum Anpassen
  (Preis nach Verhandlung, Versand, Abholung, eigener Marktpreis, Komponente).
- Deine Liste bleibt im Browser gespeichert. Mit **Export/Import** kannst du sie als
  Datei sichern, mit **Text kopieren** z. B. in einen Chat einfügen.

## So wird gerechnet

| Feld | Herkunft |
|---|---|
| Preis | Aus der Anzeige („VB“ wird markiert), lässt sich überschreiben |
| Versand | „Versand ab X €“ aus der Anzeige. Steht dort nur „Versand möglich“, wird je nach Paketgröße geschätzt (5,49 / 6,99 / 10,49 / 16,99 €). Bei „Nur Abholung“: 0 € |
| Marktpreis | Median ähnlicher Angebote aus der Kleinanzeigen-Suche. Gesuche, Defekte, „Ti“-/„Super“-Varianten, Komplett-PCs und Ausreißer werden dabei herausgefiltert |

## Scam-Risiko (0–100)

Ab 25 Punkten gilt eine Anzeige als **mittel**, ab 50 als **hoch**. Punkte gibt es unter anderem für:

- einen Preis weit unter dem Marktpreis (bis +45)
- ein sehr neues Verkäuferkonto (bis +25)
- Treuhand, Zahlungslinks, „PayPal Freunde“, Gutscheine oder Western Union (+25)
- Kontakt außerhalb von Kleinanzeigen wie WhatsApp, E-Mail oder Telefonnummer (+15)
- „bin im Ausland“ oder „nur Versand“, vor allem in Kombination mit einem sehr niedrigen Preis
- keine oder wenige Fotos und eine sehr kurze Beschreibung

Punkte abgezogen werden für ein altes Konto, gute Bewertungs-Abzeichen und „Nur Abholung“.
Verneinungen wie „kein Mining“ oder „nicht defekt“ werden erkannt. Hinweise auf Defekte
oder Mining erscheinen als **Zustandswarnung** und zählen nicht als Scam-Signal.

Der Score ist eine Faustregel und kein Beweis.

## Grenzen

- Kleinanzeigen hat keine offizielle Schnittstelle. Der Picker liest deshalb die normale
  Webseite aus. Ändert Kleinanzeigen das Layout, fehlen eventuell einzelne Felder. Bei
  „Bot-Schutz“-Fehlern kurz warten oder über **Manuell eintragen** selbst ausfüllen.
- Die Abrufe laufen einzeln mit kurzer Pause hintereinander und werden 10 Minuten
  zwischengespeichert, damit der Picker nicht wie ein Bot wirkt.
- Der Server ist nur von deinem eigenen Rechner aus erreichbar (localhost) und ruft
  ausschließlich kleinanzeigen.de ab.

## Entwicklung

```
npm test        # Parser, Risiko-Logik, Server (mit nachgebauten Testseiten)
```

- `lib/parse.js`: liest Anzeigen- und Suchseiten aus (mit Fallbacks über Meta-Tags und Text)
- `public/js/risk.js`: Risiko-Score
- `public/js/query.js`: erkennt das Modell, baut die Vergleichssuche und filtert Treffer
- `public/js/categories.js`: Komponenten, automatische Einsortierung und Versandschätzung

Die HTML-Dateien in `test/fixtures/` sind nach dem Aufbau von Kleinanzeigen nachgebaut
und stammen nicht aus echten Anzeigen. Wenn sich ein Feld auf echten Seiten nicht mehr
auslesen lässt, ist `lib/parse.js` die Stelle zum Nachbessern.
