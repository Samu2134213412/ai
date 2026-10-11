# 06 – Dashboard: Home Assistant oder eigenes Frontend?

## Entscheidung: Hybrid – HA-Dashboard als Basis, eigene Panels nur wo nötig

| Teil | Umsetzung |
|---|---|
| Räume, Licht, Heizung, Rollos, Szenen, Energie, Drucker-Kamera, Schreibtisch | **HA-Dashboard** (Sections-Ansicht) mit Bubble Card / Mushroom + `card-mod` für die Glas-Optik |
| Grundriss mit klickbaren Geräten | **HA** `picture-elements` mit einer SVG-Zeichnung deiner Zimmer (zeichne ich nach deinen Maßen) |
| KI-Chat | **HA Assist** mit `brain_router` als Agent – eingebaut, kein Extra-Code |
| Druckplaner (Projekte, Teile, Warteschlange, Zeitplan) und Aufräum-Ansicht | **Eigenes Panel** (Web-Komponente, von HA ausgeliefert) |

## Warum nicht komplett eigenes Frontend (React/Svelte)?

| Kriterium | HA-Dashboard | Eigenes Web-Frontend |
|---|---|---|
| Läuft zusätzlich auf dem Pi | nichts | eigener Webserver/Container → RAM auf 2-GB-Pi |
| Anmeldung & Sicherheit | HA-Login, 2FA, VPN – schon da | selbst bauen; Token im Browser = Risiko |
| Live-Zustände | eingebaut | WebSocket-Anbindung selbst bauen |
| Handy-App, Benachrichtigungen | HA Companion App | fehlt |
| Neues Gerät hinzufügen | Karte einfügen, fertig | Code ändern |
| Design-Freiheit | hoch mit Themes/card-mod, nicht grenzenlos | grenzenlos |
| Pflegeaufwand | gering | jedes HA-Update kann etwas brechen, du pflegst alles selbst |

Ein eigenes Frontend würde 80 % von dem nachbauen, was HA schon kann – für ein
paar Prozent mehr Gestaltungsfreiheit. Die Stellen, an denen HA-Karten wirklich
an Grenzen stoßen (Druckplaner, Aufräum-Ansicht), bekommen **eigene Panels**:
Das sind normale Web-Komponenten, die HA selbst ausliefert. Sie erhalten das
angemeldete `hass`-Objekt automatisch – keine eigene Anmeldung, kein eigener
Server, volle Gestaltungsfreiheit genau dort, wo sie gebraucht wird.

## Aufbau

```
Ansicht „Zuhause“      Räume-Kacheln · Szenen · Gehirn-Status · Energie heute
Ansicht „Grundriss“    beide Zimmer, Geräte antippbar, Temperatur/CO₂ als Overlay
Ansicht „Drucker“      Live-Kamera · Fortschritt · AMS-Filament · Warteschlange
Ansicht „Energie“      aktuelle Leistung je Gerät · Tag/Monat · Top-Verbraucher
Ansicht „Schreibtisch“ Höhe · Sitz/Steh · LED-Zonen · Steckdosen · Aufräum-Check
Ansicht „Tisch-Panel“  vereinfacht, große Buttons, für das Tablet am Tisch
Panel „Druckplaner“    eigenes Panel (M7)
KI-Chat                Assist-Dialog, auf jeder Ansicht per Button
```

## Design

- Dunkles Theme mit halbtransparenten Kacheln (`backdrop-filter: blur`), dezente Akzentfarbe pro Raum.
- Responsiv über das Sections-Raster von HA: Handy 1 Spalte, Tablet 2–3, Desktop 4.
- Tisch-Tablet: Fully Kiosk Browser oder Companion App im Vollbild; Bildschirm aus bei Abwesenheit (Präsenzsensor) → spart Strom und Displaylebensdauer.

## Benötigte Erweiterungen (über HACS)

Bubble Card, Mushroom, card-mod, ha-bambulab (Drucker), ApexCharts Card
(Energie-Diagramme). Alles lokal, keine Cloud.
