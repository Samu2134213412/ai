# Guardian

Lokales Antiviren-/Endpoint-Protection-System für Windows 10/11 x64,
modular für eine spätere Linux-Unterstützung. Ausschließlich defensiv:
kein Code hier greift an, umgeht fremde Sicherheitssoftware oder baut
Malware/Persistenztechniken nach.

**Stand:** Phase 1 abgeschlossen und getestet (45/45 Tests grün). Siehe
`STATUS.md` für den vollständigen Nachweis und `ROADMAP.md` für die
restlichen Phasen. `ARCHITECTURE.md` erklärt Aufbau und Entscheidungen.

## Schnellstart

```bash
cargo build --workspace
cargo test --workspace
./target/debug/guardian status
./target/debug/guardian scan <Datei-oder-Ordner>
./target/debug/guardian quarantine list
./target/debug/guardian quarantine restore <id>
./target/debug/guardian rules update
./target/debug/guardian events
```

**Für Programme statt Menschen:** `--json` (bei jedem Befehl) gibt genau ein
JSON-Dokument auf stdout aus statt Text -- Exit-Codes bleiben gleich,
Warnungen gehen weiterhin auf stderr und stehen zusätzlich im JSON.
`scan --no-quarantine` ist ein echter Probelauf: jede Datei wird wirklich
bewertet, aber nichts verschoben und nichts protokolliert. Beides nutzt
**Jarvis** (`../jarvis`, Werkzeuge `guardian.*`), um Guardian per Chat zu
bedienen, ohne Textausgabe raten zu müssen.

Ohne `--config <pfad>` benutzt Guardian `%PROGRAMDATA%\Guardian\config.toml`
unter Windows (bzw. `~/.guardian/config.toml` in einer Entwicklungsumgebung
ohne Windows) und legt beim ersten Lauf sinnvolle Vorgaben an, wenn die
Datei fehlt.

## Grundprinzip

Kein einzelnes Merkmal entscheidet. Jede Erkennungsart liefert unabhängige
Findings mit eigener Gewichtung; erst die Summe (0–100) bestimmt die
Reaktion, und die Reaktion ist immer reversibel, solange es irgend geht:

```
detect → score → contain → quarantine → investigate → remediate
```

Siehe `ARCHITECTURE.md` für die Scan-Pipeline und die Score-Tabelle.

## Aufbau

| Crate/Ordner    | Inhalt                                              |
|------------------|------------------------------------------------------|
| `core/`          | Findings, Scoring, Konfiguration, Event Bus          |
| `scanners/`      | Metadata-, Hash-, YARA-Scanner, Scan-Pipeline        |
| `intelligence/`  | YARA-Regelverwaltung (Ordnerlayout, Versionierung)   |
| `response/`      | Quarantäne (reversibel)                              |
| `storage/`       | JSONL-Ereignisprotokoll                              |
| `cli/`           | Binary `guardian` (siehe `cli/src/main.rs`)          |
| `rules/`         | YARA-Regeln, kategorisiert                           |
| `demo/`          | Interaktive Live-Preview mit simulierten Events (siehe unten) |
| `monitoring/`, `platform/windows/`, `gui/` | angelegt, Inhalt folgt in Phase 2–4 |

## Live-Demo / Preview

`demo/` enthält eine eigenständige, rein clientseitige Web-Oberfläche
(Dashboard, Java Secure Mode, Event-Timeline), die zeigt, wie Guardian sich
später anfühlen wird — mit Buttons wie „Simulate Suspicious JAR" oder
„Simulate Ransomware Behaviour", die ausschließlich harmlose, simulierte
Ereignisse im Browser erzeugen. Keine echte Datei- oder Prozessüberwachung,
keine Verbindung zur `guardian`-Binary, keine Schadsoftware.

```bash
cd demo
npm run dev   # kein npm install nötig, keine Abhängigkeiten
```

Details, Bedienung und die bewusste Abgrenzung zu Phase 2–4 stehen in
`demo/README.md`.

## Sicherheitsregeln, die im Code erzwungen werden

- Keine Datei wird allein wegen einer unsicheren Heuristik dauerhaft
  gelöscht — Guardian verschiebt in eine reversible Quarantäne, löscht nie.
- Ein einzelnes schwaches Signal erreicht nie die Quarantäne-Schwelle
  (siehe Test `a_single_weak_signal_never_reaches_containment`).
- Jede Wiederherstellung verweigert das Überschreiben einer inzwischen
  neu angelegten Datei am Originalpfad.
- Jeder Fund erklärt sich selbst (`Finding::explain()` → `"+60 SHA-256
  matches known-bad entry: ..."`) — nichts wird als Bedrohung gemeldet,
  ohne dass die Begründung für den Nutzer sichtbar ist.
