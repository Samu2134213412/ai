//! First pipeline stage: cheap, purely informational facts about a file.
//!
//! This stage deliberately produces **no** [`Finding`]s of its own. An
//! unusual extension or a large file is context for later stages (and for
//! the future PE/heuristic analyzer in Phase 3), not evidence by itself --
//! scoring something just for being a `.ps1` file would make every
//! PowerShell script on the machine "suspicious", which is exactly the kind
//! of single-weak-signal reasoning the project rules forbid.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct FileMetadata {
    pub path: PathBuf,
    pub extension: Option<String>,
    pub size_bytes: u64,
    pub is_watched_extension: bool,
}

pub fn inspect(path: &Path, watched_extensions: &[String]) -> std::io::Result<FileMetadata> {
    let meta = std::fs::metadata(path)?;
    let extension = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase());
    let is_watched_extension = extension
        .as_deref()
        .map(|e| watched_extensions.iter().any(|w| w == e))
        .unwrap_or(false);
    Ok(FileMetadata {
        path: path.to_path_buf(),
        extension,
        size_bytes: meta.len(),
        is_watched_extension,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reports_extension_and_size() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("sample.PS1");
        std::fs::write(&path, b"Write-Host hi").unwrap();

        let meta = inspect(&path, &["ps1".to_string()]).unwrap();
        assert_eq!(meta.extension.as_deref(), Some("ps1"));
        assert!(meta.is_watched_extension);
        assert_eq!(meta.size_bytes, 13);
    }

    #[test]
    fn unwatched_extension_is_reported_but_not_flagged() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("notes.txt");
        std::fs::write(&path, b"hello").unwrap();

        let meta = inspect(&path, &["ps1".to_string()]).unwrap();
        assert!(!meta.is_watched_extension);
    }
}
