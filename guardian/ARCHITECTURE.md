# Guardian — Architektur

Lokales Antiviren-/Endpoint-Protection-System. Primärplattform Windows 10/11
x64, Architektur modular für eine spätere Linux-Unterstützung.

## Grundprinzip

Kein einzelner Erkennungsmechanismus entscheidet allein. Jede Engine liefert
unabhängige `Finding`s (Quelle, Beschreibung, Punktzahl); erst die Summe aller
Punkte ergibt einen Threat Score 0–100, und erst der Score (nicht ein
einzelner Fund) entscheidet über eine Reaktion:

```
File
  │
  ▼
Metadata Scanner  (Erweiterung, Größe — rein informativ, keine Punkte)
  │
  ▼
Hash Scanner      (SHA-256 gegen lokale Signatur-Datenbank)
  │
  ▼
YARA Scanner      (kompilierte Regeln aus rules/)
  │
  ▼           [Phase 2/3: Static Analyzer, Heuristik, Reputation]
  ▼
Threat Score  (Summe der Finding-Punkte, geklemmt auf 0–100)
  │
  ▼
Response      (Verdict → Aktion, siehe Schwellenwerte unten)
```

Das ist wörtlich `guardian-scanners::pipeline::run_scan`. Scanner erzeugen
**nur** `Finding`s; keiner von ihnen bewegt eine Datei. Das Verschieben in
Quarantäne passiert ausschließlich in `guardian-response`, nach der
Score-Berechnung — Erkennung und Reaktion sind bewusst getrennte, unabhängig
testbare Schritte.

## Threat Score → Verdict

Aus der Spezifikation, als Code in `guardian-core::scoring`:

| Score  | Verdict      | Phase-1-Verhalten                                   |
|--------|--------------|------------------------------------------------------|
| 0–29   | Clean        | nichts, Ereignis geloggt                             |
| 30–49  | Suspicious   | nur geloggt                                           |
| 50–69  | Elevated     | nur geloggt (künftig: engmaschigere Beobachtung)     |
| 70–84  | Contain      | Datei in Quarantäne (kein laufender Prozess in Phase 1) |
| 85–100 | Quarantine   | Datei in Quarantäne                                   |

Die Schwellenwerte liegen in `GuardianConfig.thresholds` (TOML, siehe
`STATUS.md`) und sind zur Laufzeit editierbar — keine Konstante im Code.

**Wichtig, ehrlich benannt:** "Prozess stoppen" aus der Spezifikation für
70–84 existiert in Phase 1 noch nicht, weil es noch keine
Prozessüberwachung gibt (das ist Phase 2). Phase 1 scannt Dateien im Ruhe-
zustand, nicht laufende Prozesse. Sobald `monitoring/processes` in Phase 2
steht, wird `Verdict::Contain` zusätzlich zur Dateiisolierung auch den
auslösenden Prozess anhalten.

## Ordnerstruktur: Vorgabe vs. tatsächliche Ablage

Die Aufgabenstellung schlägt eine Ordnerstruktur vor. Umgesetzt als
Cargo-Workspace, mit einem Crate pro genanntem Bereich, so nah wie möglich
an der Vorgabe:

| Vorgabe                          | Tatsächlich                                | Stand   |
|-----------------------------------|---------------------------------------------|---------|
| `core/engine`, `core/scoring`, `core/event_bus` | Crate `core/` (Module `scoring`, `event`, `config`, `finding`) | Phase 1 |
| `scanners/hash`, `scanners/yara`   | Crate `scanners/` (Module `hash`, `yara`, `metadata`, `pipeline`) | Phase 1 |
| `scanners/pe`, `scanners/heuristic`| noch nicht angelegt                        | Phase 3 |
| `intelligence/rule_manager`        | Crate `intelligence/` (Modul `rule_manager`) | Phase 1 |
| `intelligence/reputation`          | noch nicht angelegt                        | Phase 2 |
| `response/quarantine`              | Crate `response/` (Modul `quarantine`)      | Phase 1 |
| `response/process_control`, `rollback`, `remediation` | noch nicht angelegt         | Phase 2/3 |
| `storage/logs`                     | Crate `storage/` (Modul `jsonl_logger`)     | Phase 1 |
| `storage/database`                 | noch nicht angelegt (Reputation/Events brauchen erst eine echte DB, wenn sie mehr als Anhängen brauchen) | Phase 2 |
| `cli/`                             | Crate `cli/`, Binary `guardian`             | Phase 1 |
| `monitoring/*`                     | Ordner angelegt, leer                       | Phase 2/3 |
| `platform/windows/`                | Ordner angelegt, leer                       | Phase 2+ |
| `gui/`                             | Ordner angelegt, leer                       | Phase 4 |
| `rules/`                           | angelegt, mit `malware/eicar.yar`           | Phase 1 |
| `tests/`                           | siehe unten — bewusste Abweichung           | Phase 1 |

**Bewusste Abweichung bei `tests/`:** Statt eines einzelnen Top-Level-
Ordners liegen Tests dort, wo Rust sie idiomatisch erwartet und `cargo test`
sie automatisch findet: Unit-Tests als `#[cfg(test)] mod tests` direkt neben
dem geprüften Code in jedem Crate, und die Ende-zu-Ende-Tests (EICAR über die
echte kompilierte Binary) in `cli/tests/end_to_end.rs`. Ein zusätzlicher
leerer `tests/`-Ordner nur der Optik wegen hätte keinen echten Zweck gehabt.

## Warum Rust (und wo Python später hinzukommt)

Begründung, wie in Schritt 4 der Vorgehensweise gefordert:

- **Rust** für alles, was in diesem Repo bisher existiert: Speichersicherheit
  ohne Garbage Collector ist für einen Prozess, der dauerhaft im Hintergrund
  läuft und Dateien/Prozesse anderer Programme anfasst, kein Nice-to-have,
  sondern eine Sicherheitsanforderung an sich (ein Speicherfehler im
  Virenschutz selbst wäre ein neuer Angriffsvektor). Rust liefert außerdem
  native Windows-API-Anbindung (`windows`-Crate, für Phase 2/3) ohne Laufzeit-
  Abhängigkeit, und mit `yara-x` eine vollständig in Rust geschriebene
  YARA-Engine — kein `libyara`-C-Build, den man für Windows erst noch
  cross-kompilieren müsste.
- **Python** ist bewusst noch nirgends im Code. Die Aufgabenstellung nennt es
  für Prototypen, Regelverwaltung und Analysewerkzeuge — alles Dinge, die
  *neben* dem laufenden Schutz stehen, nie in seinem Pfad. Sobald es einen
  echten Bedarf gibt (z. B. ein Regel-Autor-Werkzeug, das YARA-Regeln aus
  Malware-Samples vorschlägt), bekommt es ein eigenständiges Skript/Paket
  außerhalb des Cargo-Workspace, das YARA-Dateien nach `rules/` schreibt —
  nie eine Laufzeit-Abhängigkeit des Kernprozesses.

## Warum `yara-x` statt der klassischen `yara`-Bindings

`yara-x` ist eine vollständig in Rust neu geschriebene, zu ~99% kompatible
YARA-Engine von VirusTotal — keine C-Bibliothek (`libyara`) zu bauen oder für
Windows zu linken, aktiv gepflegt, memory-safe. Für ein Windows-first-Projekt
mit modularer Linux-Zukunft ist das der klar geringere Wartungsaufwand
gegenüber FFI-Bindings an eine C-Bibliothek.

## Selbstschutz — heutiger Stand und offene Punkte

Phase 1 implementiert bereits:

- Quarantäne-Blobs verlieren ihre Endung und werden read-only (Windows:
  DOS-Readonly-Attribut; Unix-Testumgebung: Dateimodus).
- Wiederherstellung verweigert das Überschreiben einer bereits existierenden
  Datei am Originalpfad — keine stille Datenvernichtung.

Noch offen (Phase 2, siehe `platform/windows`):

- Eine echte Windows-ACL, die Ausführung selbst dann verweigert, wenn jemand
  die Endung von Hand zurückändert.
- Hash-Prüfung der eigenen Binaries/Regeln gegen Manipulation.
- Geschützte Dateiberechtigungen für Konfiguration und Logs.

Diese Punkte stehen in `ROADMAP.md` unter Phase 2/3 und sind hier nicht
stillschweigend als erledigt behauptet.
