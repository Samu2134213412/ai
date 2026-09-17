//! Orchestrates the Phase-1 scan stages in order (spec section 2):
//! Metadata -> Hash -> YARA -> Threat Score. Static/heuristic/reputation
//! stages are Phase 2/3 and slot in here later without changing this
//! function's signature -- they just contribute more `Finding`s to the same
//! list before scoring.
//!
//! This crate never touches quarantine or any other response action: a
//! scanner's only job is to produce a [`Score`], not to act on it. That
//! split keeps "detect" and "respond" independently testable, per the
//! project's detect -> score -> contain -> quarantine pipeline.

use std::path::Path;

use guardian_core::{score_findings, Finding, Score, ThreatThresholds};

use crate::hash::{self, HashDatabase, HashReport};
use crate::metadata::{self, FileMetadata};
use crate::yara::YaraScanner;

pub struct ScanContext<'a> {
    pub hash_db: &'a HashDatabase,
    pub yara: Option<&'a YaraScanner>,
    pub thresholds: &'a ThreatThresholds,
    pub watched_extensions: &'a [String],
    pub compute_legacy_hashes: bool,
}

pub struct ScanOutcome {
    pub metadata: FileMetadata,
    pub hashes: HashReport,
    pub score: Score,
}

pub fn run_scan(path: &Path, ctx: &ScanContext) -> anyhow::Result<ScanOutcome> {
    let metadata = metadata::inspect(path, ctx.watched_extensions)?;
    let hashes = hash::compute(path, ctx.compute_legacy_hashes)?;

    let mut findings: Vec<Finding> = Vec::new();
    findings.extend(hash::scan(&hashes, ctx.hash_db));
    if let Some(yara) = ctx.yara {
        findings.extend(yara.scan_file(path)?);
    }

    let score = score_findings(findings, ctx.thresholds);
    Ok(ScanOutcome {
        metadata,
        hashes,
        score,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use guardian_core::Verdict;

    fn ctx<'a>(
        hash_db: &'a HashDatabase,
        yara: &'a YaraScanner,
        thresholds: &'a ThreatThresholds,
        extensions: &'a [String],
    ) -> ScanContext<'a> {
        ScanContext {
            hash_db,
            yara: Some(yara),
            thresholds,
            watched_extensions: extensions,
            compute_legacy_hashes: false,
        }
    }

    #[test]
    fn clean_file_scores_zero() {
        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("clean.txt");
        std::fs::write(&target, b"just some ordinary text").unwrap();

        let hash_db = HashDatabase::empty();
        let rules_dir = tempfile::tempdir().unwrap();
        let yara = YaraScanner::compile_dir(rules_dir.path()).unwrap();
        let thresholds = ThreatThresholds::default();
        let extensions = vec!["txt".to_string()];

        let outcome = run_scan(&target, &ctx(&hash_db, &yara, &thresholds, &extensions)).unwrap();
        assert_eq!(outcome.score.value, 0);
        assert_eq!(outcome.score.verdict, Verdict::Clean);
    }

    #[test]
    fn combined_hash_and_yara_hits_reach_quarantine() {
        let target_dir = tempfile::tempdir().unwrap();
        let target = target_dir.path().join("bad.txt");
        std::fs::write(&target, b"MARKER-STRING").unwrap();

        let hashes = hash::compute(&target, false).unwrap();

        let hash_db_dir = tempfile::tempdir().unwrap();
        let hash_db_path = hash_db_dir.path().join("hashes.txt");
        std::fs::write(&hash_db_path, format!("{}  test-sample\n", hashes.sha256)).unwrap();
        let hash_db = HashDatabase::load(&hash_db_path).unwrap();

        let rules_dir = tempfile::tempdir().unwrap();
        std::fs::write(
            rules_dir.path().join("test.yar"),
            r#"rule marker { meta: score = 40 description = "marker string" strings: $m = "MARKER-STRING" condition: $m }"#,
        )
        .unwrap();
        let yara = YaraScanner::compile_dir(rules_dir.path()).unwrap();

        let thresholds = ThreatThresholds::default();
        let extensions = vec!["txt".to_string()];

        let outcome = run_scan(&target, &ctx(&hash_db, &yara, &thresholds, &extensions)).unwrap();
        // 60 (hash) + 40 (yara) = 100, clamped, well above quarantine (85).
        assert_eq!(outcome.score.value, 100);
        assert_eq!(outcome.score.verdict, Verdict::Quarantine);
        assert_eq!(outcome.score.findings.len(), 2);
    }
}
