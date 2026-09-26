//! Hash/signature scanner (spec section 1 and phase-1 item 3): SHA-256
//! always, SHA-1/MD5 only when the config asks for them for compatibility
//! with legacy malware databases that never published SHA-256.
//!
//! The known-bad database here is a flat local blocklist -- distinct from
//! the (later, Phase 2+) reputation engine, which tracks a trust *score*
//! for arbitrary files over time. This one only ever says yes/no against a
//! fixed list, which is why it's simple enough to ship in Phase 1.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;

use guardian_core::{Finding, FindingSource};
use sha2::Sha256;

#[derive(Debug, Clone)]
pub struct HashReport {
    pub sha256: String,
    pub sha1: Option<String>,
    pub md5: Option<String>,
}

/// Streams the file once, computing every requested digest in the same
/// pass -- important once files can be large (spec section 21: large files
/// must be handled sensibly, not read into memory three times).
pub fn compute(path: &Path, legacy: bool) -> std::io::Result<HashReport> {
    // sha2::Digest, sha1::Digest and md5::Digest are all re-exports of the
    // same `digest::Digest` trait, so importing it once brings `.update()`
    // and `.finalize()` into scope for all three hasher types below.
    use sha2::Digest as _;

    let mut reader = BufReader::new(File::open(path)?);
    let mut sha256 = Sha256::new();
    let mut sha1 = sha1::Sha1::new();
    let mut md5 = md5::Md5::new();
    let mut buf = [0u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buf)?;
        if read == 0 {
            break;
        }
        sha256.update(&buf[..read]);
        if legacy {
            sha1.update(&buf[..read]);
            md5.update(&buf[..read]);
        }
    }
    Ok(HashReport {
        sha256: hex(&sha256.finalize()),
        sha1: legacy.then(|| hex(&sha1.finalize())),
        md5: legacy.then(|| hex(&md5.finalize())),
    })
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// A local flat-file blocklist: one `<sha256-hex>  <description>` pair per
/// line. Blank lines and lines starting with `#` are ignored, so the file
/// can be hand-edited and commented like the YARA rules next to it.
#[derive(Debug, Default, Clone)]
pub struct HashDatabase {
    known_bad: HashMap<String, String>,
}

impl HashDatabase {
    pub fn empty() -> Self {
        Self::default()
    }

    /// A missing database file means "nothing known yet", not an error --
    /// Guardian must still start and run its other engines.
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        if !path.is_file() {
            return Ok(Self::empty());
        }
        let raw = std::fs::read_to_string(path)?;
        let mut known_bad = HashMap::new();
        for line in raw.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let mut parts = line.splitn(2, char::is_whitespace);
            let Some(hash) = parts.next() else { continue };
            let description = parts.next().unwrap_or("known-bad hash").trim();
            known_bad.insert(hash.to_ascii_lowercase(), description.to_string());
        }
        Ok(Self { known_bad })
    }

    pub fn lookup(&self, sha256: &str) -> Option<&str> {
        self.known_bad
            .get(&sha256.to_ascii_lowercase())
            .map(String::as_str)
    }

    pub fn len(&self) -> usize {
        self.known_bad.len()
    }

    pub fn is_empty(&self) -> bool {
        self.known_bad.is_empty()
    }
}

/// A hash match is treated as strong, direct evidence -- high weight, but
/// deliberately still below the auto-quarantine threshold on its own, so it
/// combines with (rather than bypasses) the scoring pipeline.
pub const KNOWN_BAD_HASH_POINTS: i32 = 60;

pub fn scan(report: &HashReport, db: &HashDatabase) -> Vec<Finding> {
    match db.lookup(&report.sha256) {
        Some(description) => vec![Finding::new(
            FindingSource::Hash,
            "known_bad_hash",
            format!("SHA-256 matches known-bad entry: {description}"),
            KNOWN_BAD_HASH_POINTS,
        )],
        None => Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn computes_the_correct_sha256() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("a.txt");
        std::fs::write(&path, b"hello world").unwrap();

        let report = compute(&path, false).unwrap();
        // Independently known SHA-256 of the literal bytes "hello world".
        assert_eq!(
            report.sha256,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
        assert!(report.sha1.is_none());
        assert!(report.md5.is_none());
    }

    #[test]
    fn legacy_hashes_are_only_computed_when_asked_for() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("a.txt");
        std::fs::write(&path, b"hello world").unwrap();

        let report = compute(&path, true).unwrap();
        assert!(report.sha1.is_some());
        assert!(report.md5.is_some());
    }

    #[test]
    fn known_bad_hash_is_flagged_with_its_description() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("hashes.txt");
        std::fs::write(
            &db_path,
            "# comment\nb94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9  test-signature\n",
        )
        .unwrap();
        let db = HashDatabase::load(&db_path).unwrap();
        assert_eq!(db.len(), 1);

        let report = HashReport {
            sha256: "B94D27B9934D3E08A52E52D7DA7DABFAC484EFE37A5380EE9088F7ACE2EFCDE9".to_string(),
            sha1: None,
            md5: None,
        };
        let findings = scan(&report, &db);
        assert_eq!(findings.len(), 1);
        assert!(findings[0].description.contains("test-signature"));
        assert_eq!(findings[0].points, KNOWN_BAD_HASH_POINTS);
    }

    #[test]
    fn unknown_hash_produces_no_finding() {
        let db = HashDatabase::empty();
        let report = HashReport {
            sha256: "deadbeef".to_string(),
            sha1: None,
            md5: None,
        };
        assert!(scan(&report, &db).is_empty());
    }

    #[test]
    fn missing_database_file_loads_as_empty_not_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let db = HashDatabase::load(&dir.path().join("nope.txt")).unwrap();
        assert!(db.is_empty());
    }
}
