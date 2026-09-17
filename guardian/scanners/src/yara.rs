//! YARA scanner (spec section 3): compiles every `.yar`/`.yara` file found
//! by [`guardian_intelligence::RuleManager`] using the pure-Rust `yara-x`
//! engine (no libyara C dependency to build or link, which matters for a
//! Windows-first project with a modular Linux future).
//!
//! Rule authors weight their own findings: a rule's `meta.score` becomes the
//! finding's points (default 40 if unset), and `meta.description` becomes
//! the human-readable reason. That keeps the weighting decision where the
//! domain knowledge actually lives -- in the rule -- instead of hard-coded
//! in this scanner.

use std::path::{Path, PathBuf};

use guardian_core::{Finding, FindingSource};
use yara_x::MetaValue;

pub struct YaraScanner {
    rules: yara_x::Rules,
    file_count: usize,
    version: String,
}

const DEFAULT_YARA_POINTS: i32 = 40;

impl YaraScanner {
    /// Compiles the given rule files into one rule set. `version` is an
    /// opaque tag from [`guardian_intelligence::RuleManager::version`],
    /// stored so callers (and `guardian status`) can display which rule
    /// revision is actually loaded right now.
    pub fn compile(files: &[PathBuf], version: impl Into<String>) -> anyhow::Result<Self> {
        let mut compiler = yara_x::Compiler::new();
        for file in files {
            let source = std::fs::read_to_string(file)
                .map_err(|e| anyhow::anyhow!("reading {}: {e}", file.display()))?;
            compiler
                .add_source(source.as_str())
                .map_err(|e| anyhow::anyhow!("compiling {}: {e}", file.display()))?;
        }
        let rules = compiler.build();
        Ok(Self {
            rules,
            file_count: files.len(),
            version: version.into(),
        })
    }

    /// Compiles directly from a directory, for callers (tests, small tools)
    /// that don't need `RuleManager`'s versioning separately.
    pub fn compile_dir(dir: &Path) -> anyhow::Result<Self> {
        let manager = guardian_intelligence::RuleManager::new(dir);
        let files = manager.discover_rule_files()?;
        let version = manager.version()?;
        Self::compile(&files, version)
    }

    pub fn rule_file_count(&self) -> usize {
        self.file_count
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn scan_file(&self, path: &Path) -> anyhow::Result<Vec<Finding>> {
        let mut scanner = yara_x::Scanner::new(&self.rules);
        let results = scanner
            .scan_file(path)
            .map_err(|e| anyhow::anyhow!("scanning {}: {e}", path.display()))?;

        let mut findings = Vec::new();
        for rule in results.matching_rules() {
            let mut points = DEFAULT_YARA_POINTS;
            let mut description = None;
            for (key, value) in rule.metadata() {
                match (key, value) {
                    ("score", MetaValue::Integer(n)) => points = n as i32,
                    ("description", MetaValue::String(s)) => description = Some(s.to_string()),
                    _ => {}
                }
            }
            let description =
                description.unwrap_or_else(|| format!("YARA rule matched: {}", rule.identifier()));
            findings.push(Finding::new(
                FindingSource::Yara,
                rule.identifier(),
                description,
                points,
            ));
        }
        Ok(findings)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_rule(dir: &Path, name: &str, body: &str) {
        std::fs::write(dir.join(name), body).unwrap();
    }

    #[test]
    fn matching_rule_becomes_a_weighted_finding() {
        let dir = tempfile::tempdir().unwrap();
        write_rule(
            dir.path(),
            "test.yar",
            r#"
            rule contains_marker {
              meta:
                description = "contains the test marker string"
                score = 55
              strings:
                $m = "MARKER-STRING"
              condition:
                $m
            }
            "#,
        );
        let scanner = YaraScanner::compile_dir(dir.path()).unwrap();
        assert_eq!(scanner.rule_file_count(), 1);

        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("sample.txt");
        std::fs::write(&target, b"before MARKER-STRING after").unwrap();

        let findings = scanner.scan_file(&target).unwrap();
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].points, 55);
        assert!(findings[0].description.contains("test marker"));
    }

    #[test]
    fn non_matching_file_produces_no_findings() {
        let dir = tempfile::tempdir().unwrap();
        write_rule(
            dir.path(),
            "test.yar",
            r#"rule marker { strings: $m = "MARKER-STRING" condition: $m }"#,
        );
        let scanner = YaraScanner::compile_dir(dir.path()).unwrap();

        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("sample.txt");
        std::fs::write(&target, b"nothing interesting here").unwrap();

        assert!(scanner.scan_file(&target).unwrap().is_empty());
    }

    #[test]
    fn rule_without_score_metadata_falls_back_to_the_default() {
        let dir = tempfile::tempdir().unwrap();
        write_rule(
            dir.path(),
            "test.yar",
            r#"rule any_marker { strings: $m = "X" condition: $m }"#,
        );
        let scanner = YaraScanner::compile_dir(dir.path()).unwrap();

        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("sample.txt");
        std::fs::write(&target, b"X").unwrap();

        let findings = scanner.scan_file(&target).unwrap();
        assert_eq!(findings[0].points, DEFAULT_YARA_POINTS);
    }

    #[test]
    fn empty_rules_directory_compiles_to_a_scanner_that_matches_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let scanner = YaraScanner::compile_dir(dir.path()).unwrap();
        assert_eq!(scanner.rule_file_count(), 0);

        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("sample.txt");
        std::fs::write(&target, b"anything").unwrap();
        assert!(scanner.scan_file(&target).unwrap().is_empty());
    }
}
