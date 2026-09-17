# platform/windows/ — Phase 2+

Noch nicht implementiert. Geplanter Inhalt:

- `ReadDirectoryChangesW`-Anbindung für Echtzeit-Dateiüberwachung
- Prozess-/Registry-/Service-/Scheduled-Task-Zugriff über dokumentierte
  Windows-APIs (`windows`-Crate) für Prozessmonitor und Persistenzüberwachung
- ACL-Härtung für Quarantäne-Blobs und Konfigurationsdateien (Selbstschutz)
- Handhabung von `%PROGRAMDATA%`, Dienstregistrierung

Ausdrücklich **nicht** geplant: eigene Kernel-Hacks oder Anti-EDR-Techniken.
Es werden ausschließlich dokumentierte, offizielle Windows-Mechanismen
verwendet (siehe Vorgabe „Selbstschutz" in der Aufgabenstellung).
