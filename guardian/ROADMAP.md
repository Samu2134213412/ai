# Guardian — Roadmap

Reihenfolge und Umfang exakt wie in der Aufgabenstellung vorgegeben. Jede
Phase wird erst begonnen, wenn die vorige vollständig implementiert,
getestet und dokumentiert ist.

## Phase 1 — abgeschlossen

- [x] Projektstruktur (Cargo-Workspace, sechs Crates, siehe `ARCHITECTURE.md`)
- [x] File Scanner (`scanners::metadata`, `scanners::pipeline`)
- [x] SHA-256 Scanner (`scanners::hash`, optional SHA-1/MD5 für Altsysteme)
- [x] YARA-Integration (`scanners::yara` auf `yara-x`, Regel-Ordnerstruktur
      und Versionierung in `intelligence::rule_manager`)
- [x] Threat Scoring (`core::scoring`, konfigurierbare Schwellenwerte)
- [x] Quarantäne (`response::quarantine`, reversibel, mit Restore)
- [x] CLI (`guardian scan|status|quarantine|rules|events`)
- [x] Tests mit EICAR (`cli/tests/end_to_end.rs`, echte Binary, echte
      EICAR-Zeichenkette, kein echtes Schadprogramm)

**Testergebnis:** 42/42 Tests grün (`cargo test --workspace`), `cargo
clippy --workspace --all-targets` ohne Warnungen. Details und ein
End-to-Ende-Transkript in `STATUS.md`.

**Nicht Teil von Phase 1** (laut Aufgabenstellung erst später, hier nicht
vorgezogen, um nichts halbfertig zu lassen): Echtzeitüberwachung,
Prozessmonitor, Verhaltensanalyse, Ransomware-Schutz, Persistenz- und
Netzwerküberwachung, Reputation, Rollback, GUI, Java Secure Mode.

## Phase 2 — als Nächstes

1. Echtzeit-Dateiüberwachung (`monitoring::filesystem`, plattformseitig
   Windows: `ReadDirectoryChangesW`, siehe `platform/windows`)
2. Prozessmonitor (`monitoring::processes`: Parent/Child, Executable-Pfad,
   Hash, Command Line, Nutzer)
3. Process Trees (Ketten wie `explorer.exe → browser.exe → powershell.exe`
   als eigener Findungs-Typ `FindingSource::ProcessTree`, bereits im
   Phase-1-Enum vorgesehen)
4. Reputation (`intelligence::reputation`, echte Datenbank in
   `storage::database`, `first_seen`/`last_seen`/`trust_score`)

Damit wird `Verdict::Contain` erstmals einen echten Prozess anhalten können
statt nur eine Datei zu isolieren — das ist der Punkt, an dem die in
`ARCHITECTURE.md` benannte Lücke ("Prozess stoppen" noch nicht umgesetzt)
geschlossen wird.

## Phase 3

1. Behaviour Engine (`monitoring::behavior`: Massenumbenennung, viele
   Dateiänderungen in kurzer Zeit, verdächtige Kombinationen)
2. Ransomware Detection (Canary-/Honeypot-Dateien, `monitoring::ransomware`)
3. Persistence Monitoring (Startup-Ordner, Run-Keys, Services, Scheduled
   Tasks — `monitoring::persistence`, mit Snapshot vor jeder Änderung)
4. Network Monitoring (`monitoring::network`: nur Beobachtung ausgehender
   Verbindungen, keine aktiven Scans gegen fremde Systeme)
5. Rollback (`response::rollback`: Registry-Backup, Autostart-Snapshot,
   Liste geänderter Dateien seit Beginn eines verdächtigen Verhaltens)
6. PE-/Heuristik-Scanner (`scanners::pe`, `scanners::heuristic`: Sections,
   Entropie, Imports, Packer-Merkmale — gewichtet, nie ein Einzelmerkmal
   als Verdikt)
7. **Java Secure Mode** (eigenständiges Verhaltensprofil für
   `java(w).exe`/`.jar`, JAR-Pre-Scan, Child-Process-Protection,
   Restrictive Mode für unbekannte JARs, Emergency Containment — siehe
   Aufgabenstellung; baut auf Prozessmonitor + Behaviour Engine + YARA aus
   Phase 1/2/3 auf, braucht aber ein eigenes Scoring-Profil, damit
   Minecraft/Mods/IDEs nicht grundlos blockiert werden)

## Phase 4

1. GUI (Dashboard, Scan/Protection/Quarantine/Events/Rules/Settings, wie in
   der Aufgabenstellung skizziert)
2. Performance-Optimierung (Hash-/Scan-Cache, Prioritätswarteschlangen,
   Rate-Limits — Grundgerüst dafür ist die bereits event-getriebene statt
   Full-Scan-lastige Architektur aus Phase 1)
3. Update-System für Regeln (heute deckt `guardian rules update` nur lokales
   Neuladen ab; ein echter Feed kommt hier dazu, weiterhin optional/lokal
   nach den Datenschutz-Vorgaben aus der Aufgabenstellung)
4. Erweiterte Regeln, Selbstschutz-Härtung (Windows-ACLs, Hash-Prüfung der
   eigenen Komponenten — siehe `ARCHITECTURE.md`)

## Sprachentscheidung (Begründung siehe `ARCHITECTURE.md`)

Rust für alles Sicherheitskritische/Performante (aktueller gesamter Code).
Python kommt erst hinzu, wenn ein konkretes Analyse-/Regelwerkzeug das
braucht, und dann als eigenständiges, vom laufenden Schutz unabhängiges
Skript — nie im Pfad des Kernprozesses.
