//! Black-box end-to-end test: drives the actual compiled `guardian` binary
//! exactly the way a user would, against the EICAR standard antivirus test
//! file -- a benign string published for exactly this purpose (spec section
//! 23 forbids using real malware in automated tests).
//!
//! This is the test the project brief asked for by name ("Tests mit
//! EICAR"): detect -> score -> quarantine -> restore, driven through the
//! real CLI process, the real filesystem, and the real (repo-shipped) YARA
//! rule, not through internal function calls.

use std::path::Path;

use assert_cmd::Command;
use predicates::prelude::PredicateBooleanExt;

/// The official EICAR test string. Not malware; a AV self-test standard.
const EICAR: &[u8] = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*";
const EICAR_SHA256: &str = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f";

struct TestHome {
    dir: tempfile::TempDir,
}

impl TestHome {
    fn new() -> Self {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("downloads")).unwrap();
        std::fs::create_dir_all(dir.path().join("data/signatures")).unwrap();

        // Repo-shipped rules, exactly as a real install would ship them.
        let repo_rules = Path::new(env!("CARGO_MANIFEST_DIR")).join("../rules");
        let config = format!(
            r#"
rules_dir = {rules_dir:?}
quarantine_dir = {quarantine_dir:?}
log_path = {log_path:?}
hash_db_path = {hash_db_path:?}
scan_roots = [{scan_root:?}]
extensions = ["exe","dll","sys","msi","ps1","bat","cmd","vbs","js","jar","scr","com","zip","rar","7z"]
compute_legacy_hashes = false

[thresholds]
suspicious = 30
elevated = 50
contain = 70
quarantine = 85
"#,
            rules_dir = repo_rules.to_string_lossy(),
            quarantine_dir = dir.path().join("data/quarantine").to_string_lossy(),
            log_path = dir.path().join("data/events.jsonl").to_string_lossy(),
            hash_db_path = dir
                .path()
                .join("data/signatures/malicious_hashes.txt")
                .to_string_lossy(),
            scan_root = dir.path().join("downloads").to_string_lossy(),
        );
        std::fs::write(dir.path().join("config.toml"), config).unwrap();
        std::fs::write(
            dir.path().join("data/signatures/malicious_hashes.txt"),
            format!("{EICAR_SHA256}  EICAR test signature\n"),
        )
        .unwrap();

        Self { dir }
    }

    fn config_path(&self) -> std::path::PathBuf {
        self.dir.path().join("config.toml")
    }

    fn eicar_path(&self) -> std::path::PathBuf {
        self.dir.path().join("downloads/eicar_test.com")
    }

    fn guardian(&self) -> Command {
        let mut cmd = Command::cargo_bin("guardian").unwrap();
        cmd.arg("--config").arg(self.config_path());
        cmd
    }
}

#[test]
fn status_reports_the_real_loaded_rule_and_the_given_config_path() {
    let home = TestHome::new();
    home.guardian()
        .arg("status")
        .assert()
        .success()
        .stdout(predicates::str::contains(
            home.config_path().to_string_lossy().to_string(),
        ))
        .stdout(predicates::str::contains("1 Dateien geladen"));
}

#[test]
fn eicar_is_detected_and_quarantined_end_to_end() {
    let home = TestHome::new();
    std::fs::write(home.eicar_path(), EICAR).unwrap();

    home.guardian()
        .arg("scan")
        .arg(home.eicar_path())
        .assert()
        .failure() // non-zero exit: a threat was found, scriptable by callers
        .stdout(predicates::str::contains(EICAR_SHA256))
        .stdout(predicates::str::contains("100 (quarantine)"))
        .stdout(predicates::str::contains("in Quarantäne verschoben"));

    // The file must actually be gone from its original location -- not just
    // reported as gone.
    assert!(!home.eicar_path().exists());

    home.guardian()
        .arg("quarantine")
        .arg("list")
        .assert()
        .success()
        .stdout(predicates::str::contains("eicar_test.com"))
        .stdout(predicates::str::contains("score=100"));

    home.guardian()
        .arg("events")
        .assert()
        .success()
        .stdout(
            predicates::str::contains("threat_detected")
                .or(predicates::str::contains("scan_flagged")),
        )
        .stdout(predicates::str::contains("quarantined"));
}

#[test]
fn quarantine_round_trips_back_to_the_original_path() {
    let home = TestHome::new();
    std::fs::write(home.eicar_path(), EICAR).unwrap();
    home.guardian()
        .arg("scan")
        .arg(home.eicar_path())
        .assert()
        .failure();
    assert!(!home.eicar_path().exists());

    let list = home
        .guardian()
        .arg("quarantine")
        .arg("list")
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&list.stdout);
    let id = stdout
        .lines()
        .next()
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap();

    home.guardian()
        .arg("quarantine")
        .arg("restore")
        .arg(id)
        .assert()
        .success()
        .stdout(predicates::str::contains("Wiederhergestellt"));

    assert!(home.eicar_path().exists());
    assert_eq!(std::fs::read(home.eicar_path()).unwrap(), EICAR);

    // Restoring the same id twice must be refused, not silently repeated.
    home.guardian()
        .arg("quarantine")
        .arg("restore")
        .arg(id)
        .assert()
        .failure();
}

#[test]
fn a_clean_file_is_left_alone_and_reported_as_clean() {
    let home = TestHome::new();
    let clean_path = home.dir.path().join("downloads/clean.com");
    std::fs::write(&clean_path, b"nothing interesting here at all").unwrap();

    home.guardian()
        .arg("scan")
        .arg(&clean_path)
        .assert()
        .success()
        .stdout(predicates::str::contains("score:  0 (clean)"));

    assert!(clean_path.exists(), "a clean file must never be moved");
}

#[test]
fn full_scan_walks_the_configured_scan_root() {
    let home = TestHome::new();
    std::fs::write(home.eicar_path(), EICAR).unwrap();

    home.guardian().arg("scan").arg("--full").assert().failure();
    assert!(
        !home.eicar_path().exists(),
        "the scan root's eicar file should have been quarantined"
    );
}

fn json_of(output: &std::process::Output) -> serde_json::Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|e| {
        panic!(
            "stdout ist kein JSON ({e}): {}",
            String::from_utf8_lossy(&output.stdout)
        )
    })
}

#[test]
fn json_scan_reports_the_real_verdict_and_quarantine_id() {
    let home = TestHome::new();
    std::fs::write(home.eicar_path(), EICAR).unwrap();

    let out = home
        .guardian()
        .args(["--json", "scan"])
        .arg(home.eicar_path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1), "Bedrohung gefunden -> Exit 1");
    let doc = json_of(&out);
    assert_eq!(doc["worst"], "quarantine");
    assert_eq!(doc["report_only"], false);
    let result = &doc["results"][0];
    assert_eq!(result["sha256"], EICAR_SHA256);
    assert_eq!(result["score"], 100);
    assert_eq!(result["action"], "quarantined");
    let id = result["quarantine_id"]
        .as_str()
        .expect("quarantine_id fehlt");
    assert!(!home.eicar_path().exists());

    let list = json_of(
        &home
            .guardian()
            .args(["--json", "quarantine", "list"])
            .output()
            .unwrap(),
    );
    assert_eq!(list["entries"][0]["id"], id);

    let restored = home
        .guardian()
        .args(["--json", "quarantine", "restore", id])
        .output()
        .unwrap();
    assert!(restored.status.success());
    assert_eq!(
        json_of(&restored)["restored"],
        home.eicar_path().to_string_lossy().as_ref()
    );
    assert!(home.eicar_path().exists());

    let again = home
        .guardian()
        .args(["--json", "quarantine", "restore", id])
        .output()
        .unwrap();
    assert!(!again.status.success());
    assert!(json_of(&again)["error"].is_string());
}

#[test]
fn no_quarantine_scans_for_real_but_moves_and_logs_nothing() {
    let home = TestHome::new();
    std::fs::write(home.eicar_path(), EICAR).unwrap();

    let out = home
        .guardian()
        .args(["--json", "scan", "--no-quarantine"])
        .arg(home.eicar_path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    let doc = json_of(&out);
    assert_eq!(doc["report_only"], true);
    assert_eq!(doc["results"][0]["action"], "would_quarantine");
    assert!(doc["results"][0]["quarantine_id"].is_null());

    assert!(
        home.eicar_path().exists(),
        "ein Probelauf darf nichts verschieben"
    );
    let events = json_of(&home.guardian().args(["--json", "events"]).output().unwrap());
    assert_eq!(
        events["events"].as_array().unwrap().len(),
        0,
        "ein Probelauf darf nichts protokollieren"
    );
}

#[test]
fn json_status_and_errors_are_machine_readable() {
    let home = TestHome::new();
    let status = json_of(&home.guardian().args(["--json", "status"]).output().unwrap());
    assert_eq!(status["rule_files"], 1);
    assert_eq!(status["quarantine_entries"], 0);
    assert_eq!(
        status["config"],
        home.config_path().to_string_lossy().as_ref()
    );

    let bad = home.guardian().args(["--json", "scan"]).output().unwrap();
    assert!(!bad.status.success());
    assert!(json_of(&bad)["error"].is_string());
}

#[test]
fn rules_update_recompiles_and_reports_the_version() {
    let home = TestHome::new();
    home.guardian()
        .arg("rules")
        .arg("update")
        .assert()
        .success()
        .stdout(predicates::str::contains("Regeln neu geladen"));
}
