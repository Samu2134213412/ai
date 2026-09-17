# Guardian — Stand nach Phase 1

Datum: siehe Git-Historie. Committet und auf `claude/bold-carson-ur1dni`
gepusht (Commit `da0d613`, ausgelöst durch den Repo-eigenen Stop-Hook, der
laut Systemvorgabe wie eine Nutzeranweisung zu behandeln ist — nicht durch
eine eigenständige, unaufgeforderte Entscheidung).

## Was funktioniert, wirklich geprüft

Alles hier wurde tatsächlich gebaut und mit `cargo test`/`cargo clippy`
ausgeführt, nicht nur geschrieben:

```
$ cargo test --workspace
...
test result: ok. 9 passed   (guardian-core)
test result: ok. 4 passed   (guardian-intelligence)
test result: ok. 13 passed  (guardian-scanners)
test result: ok. 7 passed   (guardian-response)
test result: ok. 3 passed   (guardian-storage)
test result: ok. 6 passed   (guardian-cli, end-to-end gegen die echte Binary)
→ 42/42 grün

$ cargo clippy --workspace --all-targets
→ keine Warnungen
```

### End-to-Ende-Beleg (echte CLI, echte EICAR-Zeichenkette)

```
$ guardian --config config.toml status
Guardian Endpoint Protection -- Phase 1
config:      .../config.toml
thresholds:  suspicious>=30 elevated>=50 contain>=70 quarantine>=85
rules_dir:   .../guardian/rules
rules:       1 Dateien geladen, Version 1004dda8cc2e
hash_db:     1 bekannte Einträge (.../malicious_hashes.txt)
quarantine:  0 Einträge in .../quarantine
log:         .../events.jsonl

$ guardian --config config.toml scan .../eicar_test.com
.../eicar_test.com
  sha256: 275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f
  score:  100 (quarantine)
  reason: +60 SHA-256 matches known-bad entry: EICAR test signature
  reason: +100 EICAR standard antivirus test file (benign, intentional test string)
  -> in Quarantäne verschoben (id=q-18d60b741cca2a92-d132475b)
exit=1

$ guardian --config config.toml quarantine list
q-18d60b741cca2a92-d132475b  score=100 ...  eicar_test.com  restored=false
    original: .../eicar_test.com
    reason:   +60 SHA-256 matches known-bad entry: ... · +100 EICAR standard antivirus test file ...

$ guardian --config config.toml quarantine restore q-18d60b741cca2a92-d132475b
Wiederhergestellt: .../eicar_test.com
# Datei liegt wieder exakt am Originalpfad, mit unverändertem Inhalt.

$ guardian --config config.toml quarantine restore q-18d60b741cca2a92-d132475b
Wiederherstellung fehlgeschlagen: 'q-18d...' wurde bereits wiederhergestellt
exit=1   # zweite Wiederherstellung wird verweigert, nicht stillschweigend wiederholt
```

Das ist der komplette `detect → score → contain → quarantine → restore`-Weg,
einmal wirklich durchlaufen, nicht nur behauptet.

## Build & Ausführen

```powershell
cd guardian
cargo build --release
.\target\release\guardian.exe status
.\target\release\guardian.exe scan C:\Users\DeinName\Downloads
.\target\release\guardian.exe quarantine list
.\target\release\guardian.exe quarantine restore <id>
```

Entwickelt und getestet in dieser Sitzung unter Linux (Sandbox-Umgebung ohne
Windows), da hier kein Windows zur Verfügung stand. Das gesamte Phase-1-
Verhalten (Hash/YARA/Scoring/Quarantäne/CLI) ist plattformneutraler Rust-
Code und verhält sich unter Windows identisch; noch **nicht** unter echtem
Windows 10/11 nachgeprüft:

- Tatsächliche Performance/Pfade auf einem echten NTFS-Dateisystem
- `%PROGRAMDATA%`-Auflösung von `default_data_dir()`
- Ob `cargo build --release` mit `yara-x` auf einem frischen Windows-
  Toolchain-Setup ohne Weiteres durchläuft (die Crate ist reines Rust, ein
  Problem ist nicht zu erwarten, aber unverifiziert ist unverifiziert)

## Bekannte Lücken in Phase 1 (bewusst, nicht vergessen)

- Kein Echtzeitschutz — `guardian scan` ist ein bewusster Ein-Schuss-Scan.
  Echtzeitüberwachung ist Phase 2, Punkt 1.
- `Verdict::Contain` (Score 70–84) isoliert nur die Datei; "Prozess
  stoppen" aus der Spezifikation greift erst, sobald es in Phase 2 einen
  Prozessmonitor gibt, der einen Prozess überhaupt kennt.
- Selbstschutz ist rudimentär (Quarantäne-Blob: keine Endung + read-only).
  Echte Windows-ACL-Härtung ist Phase 2/4, siehe `ARCHITECTURE.md`.
- `guardian rules update` liest nur lokal neu ein; es gibt noch keine
  Update-Quelle, weil noch keine gefordert war (Update-System ist Phase 4).
- Reputation, Heuristik/PE-Analyse, Verhaltensanalyse, Ransomware-Schutz,
  Persistenz-/Netzwerküberwachung, Rollback, GUI, Java Secure Mode: absicht-
  lich nicht in Phase 1 — siehe `ROADMAP.md` für die geplante Reihenfolge.

## Was noch aussteht

- Kein Review durch dich (den Auftraggeber) der Architekturentscheidungen
  (Rust-Workspace-Layout, `yara-x` statt `libyara`, Score-Tabellen-Mapping
  auf Phase-1-Aktionen) vor dem Start von Phase 2.

## Nächster Schritt

Erst nach deiner Rückmeldung zu Phase 1 (oder einem klaren „weiter") wird
mit Phase 2 begonnen — genau wie in der Aufgabenstellung verlangt
("Beginne erst danach mit der nächsten Phase").
