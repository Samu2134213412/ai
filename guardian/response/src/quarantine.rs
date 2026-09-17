//! Quarantine (spec section 10): the only place in Phase 1 that moves a
//! user's file. Every action here is reversible -- store moves the file and
//! writes a metadata record; restore reads that record and moves the file
//! back. Nothing in this module ever deletes the original content.
//!
//! A quarantined file gets a random internal name and loses its execute bit
//! (and its original extension), so double-clicking it in the quarantine
//! folder does not run it. Full ACL-level hardening (blocking execution
//! even if the extension were restored) is Windows-specific work tracked in
//! `platform/windows` for a later phase; see ARCHITECTURE.md.

use std::fs::{self, OpenOptions};
use std::path::{Path, PathBuf};

use chrono::Local;
use guardian_core::Score;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuarantineRecord {
    pub id: String,
    pub original_path: String,
    pub original_filename: String,
    pub sha256: String,
    pub detection_reason: String,
    pub detection_time: String,
    pub threat_score: u8,
    pub restored: bool,
}

pub struct Quarantine {
    root: PathBuf,
}

impl Quarantine {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    fn blobs_dir(&self) -> PathBuf {
        self.root.join("blobs")
    }

    fn records_dir(&self) -> PathBuf {
        self.root.join("records")
    }

    fn ensure_dirs(&self) -> anyhow::Result<()> {
        fs::create_dir_all(self.blobs_dir())?;
        fs::create_dir_all(self.records_dir())?;
        Ok(())
    }

    /// Moves `original_path` into quarantine and records why. Returns the
    /// record so the caller (CLI, future real-time monitor) can log or
    /// display it immediately.
    pub fn store(
        &self,
        original_path: &Path,
        sha256: &str,
        score: &Score,
    ) -> anyhow::Result<QuarantineRecord> {
        self.ensure_dirs()?;
        if !original_path.is_file() {
            anyhow::bail!(
                "nichts zu isolieren, Datei nicht gefunden: {}",
                original_path.display()
            );
        }

        let id = new_id();
        let blob_path = self.blobs_dir().join(&id); // no extension, on purpose
        fs::rename(original_path, &blob_path)
            .or_else(|_| {
                fs::copy(original_path, &blob_path).and_then(|_| fs::remove_file(original_path))
            })
            .map_err(|e| anyhow::anyhow!("Datei konnte nicht isoliert werden: {e}"))?;
        harden_permissions(&blob_path)?;

        let record = QuarantineRecord {
            id: id.clone(),
            original_path: original_path.to_string_lossy().to_string(),
            original_filename: original_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default(),
            sha256: sha256.to_string(),
            detection_reason: score
                .findings
                .iter()
                .map(|f| f.explain())
                .collect::<Vec<_>>()
                .join(" · "),
            detection_time: Local::now().to_rfc3339(),
            threat_score: score.value,
            restored: false,
        };
        self.write_record(&record)?;
        Ok(record)
    }

    fn write_record(&self, record: &QuarantineRecord) -> anyhow::Result<()> {
        let path = self.records_dir().join(format!("{}.json", record.id));
        let rendered = serde_json::to_string_pretty(record)?;
        fs::write(path, rendered)?;
        Ok(())
    }

    pub fn list(&self) -> anyhow::Result<Vec<QuarantineRecord>> {
        if !self.records_dir().is_dir() {
            return Ok(Vec::new());
        }
        let mut records = Vec::new();
        for entry in fs::read_dir(self.records_dir())? {
            let entry = entry?;
            if entry.path().extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            let raw = fs::read_to_string(entry.path())?;
            records.push(serde_json::from_str(&raw)?);
        }
        records.sort_by(|a: &QuarantineRecord, b: &QuarantineRecord| {
            a.detection_time.cmp(&b.detection_time)
        });
        Ok(records)
    }

    pub fn get(&self, id: &str) -> anyhow::Result<QuarantineRecord> {
        let path = self.records_dir().join(format!("{id}.json"));
        let raw = fs::read_to_string(&path)
            .map_err(|_| anyhow::anyhow!("keine Quarantäne mit der ID '{id}'"))?;
        Ok(serde_json::from_str(&raw)?)
    }

    /// Moves the file back to `original_path`. Refuses to overwrite an
    /// existing file at the destination -- if something is already there,
    /// the human needs to decide, Guardian doesn't silently clobber it.
    pub fn restore(&self, id: &str) -> anyhow::Result<PathBuf> {
        let mut record = self.get(id)?;
        if record.restored {
            anyhow::bail!("'{id}' wurde bereits wiederhergestellt");
        }
        let blob_path = self.blobs_dir().join(id);
        if !blob_path.is_file() {
            anyhow::bail!("Quarantänedatei für '{id}' fehlt auf der Festplatte");
        }
        let destination = PathBuf::from(&record.original_path);
        if destination.exists() {
            anyhow::bail!(
                "Wiederherstellung abgebrochen: am Originalpfad liegt bereits eine Datei: {}",
                destination.display()
            );
        }
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::rename(&blob_path, &destination)
            .or_else(|_| {
                fs::copy(&blob_path, &destination).and_then(|_| fs::remove_file(&blob_path))
            })
            .map_err(|e| anyhow::anyhow!("Wiederherstellung fehlgeschlagen: {e}"))?;
        restore_permissions(&destination)?;

        record.restored = true;
        self.write_record(&record)?;
        Ok(destination)
    }
}

fn new_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let mut file = OpenOptions::new().read(true).open("/dev/urandom").ok();
    let mut random_tail = String::new();
    if let Some(f) = file.as_mut() {
        use std::io::Read;
        let mut buf = [0u8; 4];
        if f.read_exact(&mut buf).is_ok() {
            random_tail = buf.iter().map(|b| format!("{b:02x}")).collect();
        }
    }
    if random_tail.is_empty() {
        random_tail = format!("{:08x}", nanos as u32);
    }
    format!("q-{nanos:x}-{random_tail}")
}

/// Strips the ability to run the quarantined blob without deleting its
/// content. Read-only works cross-platform via `std::fs`; a proper
/// Windows ACL denying execute is `platform/windows` work for a later
/// phase (see ARCHITECTURE.md self-protection notes).
fn harden_permissions(path: &Path) -> anyhow::Result<()> {
    let mut perms = fs::metadata(path)?.permissions();
    perms.set_readonly(true);
    fs::set_permissions(path, perms)?;
    Ok(())
}

// `Permissions::set_readonly(false)` is correct on Windows (it just clears
// the DOS read-only attribute) but on Unix it clears *all* mode bits down to
// world-writable, which is not what "un-quarantine this file" should do.
// Restore a normal, non-executable mode explicitly there instead.
#[cfg(windows)]
fn restore_permissions(path: &Path) -> anyhow::Result<()> {
    let mut perms = fs::metadata(path)?.permissions();
    perms.set_readonly(false);
    fs::set_permissions(path, perms)?;
    Ok(())
}

#[cfg(unix)]
fn restore_permissions(path: &Path) -> anyhow::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o644))?;
    Ok(())
}

#[cfg(not(any(windows, unix)))]
fn restore_permissions(_path: &Path) -> anyhow::Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use guardian_core::{score_findings, Finding, FindingSource, ThreatThresholds};

    fn sample_score() -> Score {
        let findings = vec![Finding::new(
            FindingSource::Hash,
            "known_bad_hash",
            "SHA-256 matches known-bad entry: test",
            90,
        )];
        score_findings(findings, &ThreatThresholds::default())
    }

    #[test]
    fn store_moves_the_file_out_of_its_original_location() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let original = source_dir.path().join("evil.exe");
        std::fs::write(&original, b"payload").unwrap();

        let quarantine = Quarantine::new(quarantine_dir.path());
        let record = quarantine
            .store(&original, "abc123", &sample_score())
            .unwrap();

        assert!(!original.exists());
        assert_eq!(record.original_filename, "evil.exe");
        assert_eq!(record.threat_score, 90);
        assert!(record.detection_reason.contains("known-bad"));
    }

    #[test]
    fn quarantined_blob_is_read_only() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let original = source_dir.path().join("evil.exe");
        std::fs::write(&original, b"payload").unwrap();

        let quarantine = Quarantine::new(quarantine_dir.path());
        let record = quarantine
            .store(&original, "abc123", &sample_score())
            .unwrap();
        let blob_path = quarantine_dir.path().join("blobs").join(&record.id);
        assert!(fs::metadata(&blob_path).unwrap().permissions().readonly());
    }

    #[test]
    fn restore_puts_the_file_back_exactly_where_it_came_from() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let original = source_dir.path().join("evil.exe");
        std::fs::write(&original, b"payload").unwrap();

        let quarantine = Quarantine::new(quarantine_dir.path());
        let record = quarantine
            .store(&original, "abc123", &sample_score())
            .unwrap();
        let restored_path = quarantine.restore(&record.id).unwrap();

        assert_eq!(restored_path, original);
        assert_eq!(std::fs::read(&original).unwrap(), b"payload");
        assert!(quarantine.get(&record.id).unwrap().restored);
    }

    #[test]
    fn restore_refuses_to_overwrite_a_file_that_reappeared_at_the_original_path() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let original = source_dir.path().join("evil.exe");
        std::fs::write(&original, b"payload").unwrap();

        let quarantine = Quarantine::new(quarantine_dir.path());
        let record = quarantine
            .store(&original, "abc123", &sample_score())
            .unwrap();

        // Something else now occupies the original path.
        std::fs::write(&original, b"unrelated new file").unwrap();

        assert!(quarantine.restore(&record.id).is_err());
        // And the unrelated file must survive untouched.
        assert_eq!(std::fs::read(&original).unwrap(), b"unrelated new file");
    }

    #[test]
    fn restoring_twice_is_rejected_not_silently_repeated() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let original = source_dir.path().join("evil.exe");
        std::fs::write(&original, b"payload").unwrap();

        let quarantine = Quarantine::new(quarantine_dir.path());
        let record = quarantine
            .store(&original, "abc123", &sample_score())
            .unwrap();
        quarantine.restore(&record.id).unwrap();

        assert!(quarantine.restore(&record.id).is_err());
    }

    #[test]
    fn list_reflects_every_stored_item() {
        let source_dir = tempfile::tempdir().unwrap();
        let quarantine_dir = tempfile::tempdir().unwrap();
        let quarantine = Quarantine::new(quarantine_dir.path());

        for name in ["a.exe", "b.exe", "c.exe"] {
            let path = source_dir.path().join(name);
            std::fs::write(&path, b"x").unwrap();
            quarantine.store(&path, "hash", &sample_score()).unwrap();
        }

        assert_eq!(quarantine.list().unwrap().len(), 3);
    }

    #[test]
    fn empty_quarantine_lists_as_empty_not_an_error() {
        let quarantine_dir = tempfile::tempdir().unwrap();
        let quarantine = Quarantine::new(quarantine_dir.path());
        assert!(quarantine.list().unwrap().is_empty());
    }
}
