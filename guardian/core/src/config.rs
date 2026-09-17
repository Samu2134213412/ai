//! Guardian's configuration: one TOML file, loaded once at startup.
//!
//! Mirrors a rule this team already applies elsewhere: missing config file
//! means "use the defaults", a malformed one is a hard, explained error, and
//! every threshold that changes behaviour is user-editable, not baked in.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::scoring::ThreatThresholds;

/// File extensions Guardian actively scans (spec section 1).
pub fn default_extensions() -> Vec<String> {
    [
        "exe", "dll", "sys", "msi", "ps1", "bat", "cmd", "vbs", "js", "jar", "scr", "com", "zip",
        "rar", "7z",
    ]
    .into_iter()
    .map(String::from)
    .collect()
}

fn default_data_dir() -> PathBuf {
    if cfg!(windows) {
        std::env::var_os("PROGRAMDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(r"C:\ProgramData"))
            .join("Guardian")
    } else {
        // Development/testing fallback outside Windows -- production target
        // is Windows 10/11 (see platform/windows).
        dirs_home().join(".guardian")
    }
}

fn dirs_home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn default_rules_dir() -> PathBuf {
    default_data_dir().join("rules")
}

fn default_quarantine_dir() -> PathBuf {
    default_data_dir().join("quarantine")
}

fn default_log_path() -> PathBuf {
    default_data_dir().join("logs").join("events.jsonl")
}

fn default_hash_db_path() -> PathBuf {
    default_data_dir()
        .join("signatures")
        .join("malicious_hashes.txt")
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct GuardianConfig {
    pub thresholds: ThreatThresholds,
    pub rules_dir: PathBuf,
    pub quarantine_dir: PathBuf,
    pub log_path: PathBuf,
    pub hash_db_path: PathBuf,
    /// Roots `guardian scan --full` walks. Empty by default until the user
    /// (or the Windows installer, in a later phase) fills in real folders --
    /// Guardian never guesses at directories to touch.
    pub scan_roots: Vec<PathBuf>,
    pub extensions: Vec<String>,
    /// Compute SHA-1/MD5 too, only for matching against legacy malware
    /// databases that don't publish SHA-256 (spec section 1).
    pub compute_legacy_hashes: bool,
}

impl Default for GuardianConfig {
    fn default() -> Self {
        Self {
            thresholds: ThreatThresholds::default(),
            rules_dir: default_rules_dir(),
            quarantine_dir: default_quarantine_dir(),
            log_path: default_log_path(),
            hash_db_path: default_hash_db_path(),
            scan_roots: Vec::new(),
            extensions: default_extensions(),
            compute_legacy_hashes: false,
        }
    }
}

impl GuardianConfig {
    pub fn default_config_path() -> PathBuf {
        default_data_dir().join("config.toml")
    }

    /// Loads the config from `path`, or from the default location, falling
    /// back to defaults if no file exists there. A file that exists but
    /// cannot be parsed is a hard error -- we don't silently run with
    /// defaults the user thinks they overrode.
    pub fn load(path: Option<&Path>) -> anyhow::Result<Self> {
        let target = path
            .map(Path::to_path_buf)
            .unwrap_or_else(Self::default_config_path);
        if !target.is_file() {
            return Ok(Self::default());
        }
        let raw = std::fs::read_to_string(&target).map_err(|e| {
            anyhow::anyhow!("Konfiguration nicht lesbar: {}: {e}", target.display())
        })?;
        let config: GuardianConfig = toml::from_str(&raw)
            .map_err(|e| anyhow::anyhow!("Konfiguration ungültig: {}: {e}", target.display()))?;
        Ok(config)
    }

    pub fn save(&self, path: Option<&Path>) -> anyhow::Result<PathBuf> {
        let target = path
            .map(Path::to_path_buf)
            .unwrap_or_else(Self::default_config_path);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let rendered = toml::to_string_pretty(self)?;
        std::fs::write(&target, rendered)?;
        Ok(target)
    }

    /// Problems the user should know about before Guardian relies on this
    /// configuration -- same spirit as [`ThreatThresholds::validate`].
    pub fn validate(&self) -> Vec<String> {
        let mut problems = self.thresholds.validate();
        if self.extensions.is_empty() {
            problems.push("extensions is empty -- Guardian would scan nothing".to_string());
        }
        problems
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_have_no_validation_problems() {
        assert!(GuardianConfig::default().validate().is_empty());
    }

    #[test]
    fn missing_file_falls_back_to_defaults_instead_of_failing() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("does-not-exist.toml");
        let config = GuardianConfig::load(Some(&path)).unwrap();
        assert_eq!(config.thresholds.quarantine, 85);
    }

    #[test]
    fn round_trips_through_save_and_load() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        let mut config = GuardianConfig::default();
        config.thresholds.quarantine = 90;
        config.scan_roots.push(PathBuf::from("/tmp/watched"));
        config.save(Some(&path)).unwrap();

        let loaded = GuardianConfig::load(Some(&path)).unwrap();
        assert_eq!(loaded.thresholds.quarantine, 90);
        assert_eq!(loaded.scan_roots, vec![PathBuf::from("/tmp/watched")]);
    }

    #[test]
    fn malformed_file_is_a_hard_error_not_a_silent_default() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        std::fs::write(&path, "this is not valid toml {{{").unwrap();
        assert!(GuardianConfig::load(Some(&path)).is_err());
    }
}
