//! Discovers and versions the local YARA rule set (spec section 3).
//!
//! `RuleManager` never compiles rules itself -- that stays in
//! `guardian-scanners`, which is the only crate that knows about YARA. This
//! module only knows about the filesystem layout: where rules live, what
//! counts as a rule file, and whether the set has changed since it was last
//! checked, so the scanner can hot-reload without restarting Guardian.

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

/// The category layout from spec section 3. Created on first run so a fresh
/// install has somewhere sensible to drop rules into.
pub const RULE_CATEGORIES: &[&str] = &[
    "malware",
    "ransomware",
    "stealers",
    "trojans",
    "suspicious",
    "packers",
];

pub struct RuleManager {
    root: PathBuf,
}

impl RuleManager {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Creates the category subfolders if they don't exist yet. Idempotent.
    pub fn ensure_layout(&self) -> anyhow::Result<()> {
        for category in RULE_CATEGORIES {
            std::fs::create_dir_all(self.root.join(category))?;
        }
        Ok(())
    }

    /// All `.yar`/`.yara` files under the root, recursively, in a stable
    /// (sorted) order -- stable order matters so [`Self::version`] is
    /// reproducible across runs, not just across restarts.
    pub fn discover_rule_files(&self) -> anyhow::Result<Vec<PathBuf>> {
        if !self.root.is_dir() {
            return Ok(Vec::new());
        }
        let mut files: Vec<PathBuf> = walkdir::WalkDir::new(&self.root)
            .into_iter()
            .filter_map(Result::ok)
            .filter(|entry| entry.file_type().is_file())
            .map(|entry| entry.into_path())
            .filter(|path| {
                matches!(
                    path.extension().and_then(|e| e.to_str()),
                    Some("yar") | Some("yara")
                )
            })
            .collect();
        files.sort();
        Ok(files)
    }

    /// A short fingerprint of the current rule set's *content* (not just
    /// file names/mtimes), so editing a rule in place is detected the same
    /// way as adding or removing one. Used both to display a rule-set
    /// version and to detect "did anything change" for `guardian rules
    /// update`.
    pub fn version(&self) -> anyhow::Result<String> {
        let files = self.discover_rule_files()?;
        let mut hasher = Sha256::new();
        for file in &files {
            hasher.update(file.to_string_lossy().as_bytes());
            hasher.update(std::fs::read(file)?);
        }
        let digest = hasher.finalize();
        Ok(hex::encode(digest)[..12].to_string())
    }
}

// A tiny local hex encoder so this crate doesn't need a whole extra
// dependency just to render a digest as a hex string.
mod hex {
    pub fn encode(bytes: impl AsRef<[u8]>) -> String {
        bytes.as_ref().iter().map(|b| format!("{b:02x}")).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ensure_layout_creates_every_category() {
        let dir = tempfile::tempdir().unwrap();
        let manager = RuleManager::new(dir.path());
        manager.ensure_layout().unwrap();
        for category in RULE_CATEGORIES {
            assert!(dir.path().join(category).is_dir());
        }
    }

    #[test]
    fn discovers_only_yara_files_recursively() {
        let dir = tempfile::tempdir().unwrap();
        let manager = RuleManager::new(dir.path());
        manager.ensure_layout().unwrap();
        std::fs::write(
            dir.path().join("malware/one.yar"),
            "rule one { condition: true }",
        )
        .unwrap();
        std::fs::write(
            dir.path().join("suspicious/two.yara"),
            "rule two { condition: true }",
        )
        .unwrap();
        std::fs::write(dir.path().join("malware/notes.txt"), "not a rule").unwrap();

        let files = manager.discover_rule_files().unwrap();
        assert_eq!(files.len(), 2);
    }

    #[test]
    fn version_changes_when_a_rule_is_edited() {
        let dir = tempfile::tempdir().unwrap();
        let manager = RuleManager::new(dir.path());
        manager.ensure_layout().unwrap();
        let rule_path = dir.path().join("malware/one.yar");
        std::fs::write(&rule_path, "rule one { condition: true }").unwrap();
        let before = manager.version().unwrap();

        std::fs::write(&rule_path, "rule one { condition: false }").unwrap();
        let after = manager.version().unwrap();

        assert_ne!(before, after);
    }

    #[test]
    fn missing_rules_directory_is_an_empty_set_not_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let manager = RuleManager::new(dir.path().join("does-not-exist"));
        assert!(manager.discover_rule_files().unwrap().is_empty());
    }
}
