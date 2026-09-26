//! `guardian`: the Phase-1 command-line interface (spec section 18).
//!
//! Every subcommand here only ever reports what actually happened: a scan
//! prints the real findings behind a score, `status` reads real state, and
//! `quarantine restore` either really moved the file back or says exactly
//! why it didn't. Nothing is claimed without the corresponding action
//! having run and returned success -- the same rule this team has already
//! built one assistant around, applied here to an antivirus.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use guardian_core::{EventSink, GuardianConfig, ThreatEvent, Verdict};
use guardian_intelligence::RuleManager;
use guardian_response::Quarantine;
use guardian_scanners::hash::HashDatabase;
use guardian_scanners::yara::YaraScanner;
use guardian_scanners::{run_scan, ScanContext};
use guardian_storage::JsonlLogger;
use serde_json::{json, Value};

#[derive(Parser)]
#[command(
    name = "guardian",
    version,
    about = "Guardian Endpoint Protection -- Phase 1 CLI"
)]
struct Cli {
    /// Path to config.toml. Defaults to the platform data directory.
    #[arg(long, global = true)]
    config: Option<PathBuf>,
    /// Print exactly one JSON document on stdout instead of text -- for
    /// callers such as Jarvis that must not guess from prose. Exit codes stay
    /// the same; warnings still go to stderr and are repeated in the JSON.
    #[arg(long, global = true)]
    json: bool,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Scan a single file, or every watched-extension file under a folder.
    Scan {
        path: Option<PathBuf>,
        /// Scan every configured scan_root instead of a given path.
        #[arg(long)]
        full: bool,
        /// Report only: score every file for real, but never move anything
        /// into quarantine and never write to the event log -- a true dry run.
        #[arg(long)]
        no_quarantine: bool,
    },
    /// Show configuration, loaded rules, and counts -- all read live, never cached guesses.
    Status,
    #[command(subcommand)]
    Quarantine(QuarantineCmd),
    #[command(subcommand)]
    Rules(RulesCmd),
    /// Show the most recent logged events.
    Events {
        #[arg(long, default_value_t = 20)]
        limit: usize,
    },
}

#[derive(Subcommand)]
enum QuarantineCmd {
    List,
    Restore { id: String },
}

#[derive(Subcommand)]
enum RulesCmd {
    /// Recompile the local YARA rule set and report its version -- there is
    /// no remote rule feed yet, so this validates and hot-reloads what's on
    /// disk (see ROADMAP.md for the planned update source).
    Update,
}

struct Engines {
    config: GuardianConfig,
    config_path: PathBuf,
    hash_db: HashDatabase,
    yara: Option<YaraScanner>,
    logger: JsonlLogger,
    /// Everything also printed as "Warnung:" on stderr, kept so `--json`
    /// can hand it to the caller instead of losing it.
    warnings: Vec<String>,
}

fn warn(warnings: &mut Vec<String>, message: String) {
    eprintln!("Warnung: {message}");
    warnings.push(message);
}

fn load_engines(config_path: Option<&Path>) -> anyhow::Result<Engines> {
    let resolved_config_path = config_path
        .map(Path::to_path_buf)
        .unwrap_or_else(GuardianConfig::default_config_path);
    let config = GuardianConfig::load(config_path)?;
    let mut warnings = Vec::new();
    for problem in config.validate() {
        warn(&mut warnings, problem.to_string());
    }

    let rule_manager = RuleManager::new(&config.rules_dir);
    rule_manager.ensure_layout()?;
    let yara = match YaraScanner::compile_dir(&config.rules_dir) {
        Ok(scanner) => Some(scanner),
        Err(e) => {
            warn(
                &mut warnings,
                format!(
                    "YARA-Regeln konnten nicht geladen werden ({e}). \
                     Scan läuft ohne YARA-Erkennung weiter -- Hash-Erkennung bleibt aktiv."
                ),
            );
            None
        }
    };

    let hash_db = HashDatabase::load(&config.hash_db_path)?;
    let logger = JsonlLogger::new(&config.log_path)?;

    Ok(Engines {
        config,
        config_path: resolved_config_path,
        hash_db,
        yara,
        logger,
        warnings,
    })
}

fn print_json(value: &Value) {
    println!("{value}");
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let json = cli.json;
    match run(cli) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("Fehler: {e:#}");
            if json {
                print_json(&json!({ "error": format!("{e:#}") }));
            }
            ExitCode::FAILURE
        }
    }
}

fn run(cli: Cli) -> anyhow::Result<ExitCode> {
    let config = cli.config.as_deref();
    let json = cli.json;
    match cli.command {
        Command::Scan {
            path,
            full,
            no_quarantine,
        } => cmd_scan(config, path, full, no_quarantine, json),
        Command::Status => cmd_status(config, json),
        Command::Quarantine(QuarantineCmd::List) => cmd_quarantine_list(config, json),
        Command::Quarantine(QuarantineCmd::Restore { id }) => {
            cmd_quarantine_restore(config, &id, json)
        }
        Command::Rules(RulesCmd::Update) => cmd_rules_update(config, json),
        Command::Events { limit } => cmd_events(config, limit, json),
    }
}

fn collect_targets(root: &Path, extensions: &[String]) -> Vec<PathBuf> {
    if root.is_file() {
        return vec![root.to_path_buf()];
    }
    walkdir::WalkDir::new(root)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|e| e.file_type().is_file())
        .map(|e| e.into_path())
        .filter(|p| {
            p.extension()
                .and_then(|e| e.to_str())
                .map(|e| extensions.iter().any(|w| w.eq_ignore_ascii_case(e)))
                .unwrap_or(false)
        })
        .collect()
}

fn cmd_scan(
    config_path: Option<&Path>,
    path: Option<PathBuf>,
    full: bool,
    report_only: bool,
    json: bool,
) -> anyhow::Result<ExitCode> {
    let mut engines = load_engines(config_path)?;

    // Nothing to scan is not an error, but it is also not "clean": the JSON
    // says so explicitly instead of looking like a successful empty scan.
    let nothing_scanned = |engines: &Engines, message: String| -> anyhow::Result<ExitCode> {
        if json {
            print_json(&json!({
                "scanned": 0, "worst": Value::Null, "report_only": report_only,
                "results": [], "failed": [], "message": message,
                "warnings": engines.warnings,
            }));
        } else {
            println!("{message}");
        }
        Ok(ExitCode::SUCCESS)
    };

    let roots: Vec<PathBuf> = match (path, full) {
        (Some(_), true) => anyhow::bail!("--full und ein Pfad schließen sich aus"),
        (None, false) => anyhow::bail!("gib einen Pfad an oder benutze --full"),
        (Some(p), false) => vec![p],
        (None, true) => {
            if engines.config.scan_roots.is_empty() {
                let message = format!(
                    "Keine scan_roots konfiguriert -- trage sie in {} ein.",
                    engines.config_path.display()
                );
                return nothing_scanned(&engines, message);
            }
            engines.config.scan_roots.clone()
        }
    };

    let mut targets = Vec::new();
    for root in &roots {
        if !root.exists() {
            warn(
                &mut engines.warnings,
                format!("{} existiert nicht, wird übersprungen", root.display()),
            );
            continue;
        }
        targets.extend(collect_targets(root, &engines.config.extensions));
    }

    if targets.is_empty() {
        return nothing_scanned(&engines, "Keine passenden Dateien gefunden.".to_string());
    }

    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    let ctx = ScanContext {
        hash_db: &engines.hash_db,
        yara: engines.yara.as_ref(),
        thresholds: &engines.config.thresholds,
        watched_extensions: &engines.config.extensions,
        compute_legacy_hashes: engines.config.compute_legacy_hashes,
    };

    let mut worst = Verdict::Clean;
    let mut results = Vec::new();
    let mut failed = Vec::new();
    for target in &targets {
        let outcome = match run_scan(target, &ctx) {
            Ok(o) => o,
            Err(e) => {
                eprintln!("{}: Scan fehlgeschlagen: {e}", target.display());
                failed.push(json!({ "path": target.to_string_lossy(), "error": e.to_string() }));
                continue;
            }
        };
        if !json {
            print_outcome(target, &outcome);
        }

        let event_kind = if outcome.score.verdict == Verdict::Clean {
            "scan_clean"
        } else {
            "scan_flagged"
        };
        let mut action = "logged".to_string();
        let mut quarantine_id = None;
        let mut quarantine_error = None;

        if outcome.score.verdict.warrants_containment() {
            if report_only {
                action = "would_quarantine".to_string();
                if !json {
                    println!("  -> würde in Quarantäne verschoben (--no-quarantine)");
                }
            } else {
                match quarantine.store(target, &outcome.hashes.sha256, &outcome.score) {
                    Ok(record) => {
                        action = "quarantined".to_string();
                        if !json {
                            println!("  -> in Quarantäne verschoben (id={})", record.id);
                        }
                        quarantine_id = Some(record.id);
                    }
                    Err(e) => {
                        action = "quarantine_failed".to_string();
                        eprintln!("  -> Quarantäne fehlgeschlagen: {e}");
                        quarantine_error = Some(e.to_string());
                    }
                }
            }
        }

        // A dry run leaves no trace: the event log is the record of what
        // Guardian actually did, and in report-only mode it did nothing.
        if !report_only {
            let logged_action = match &quarantine_error {
                Some(e) => format!("quarantine_failed: {e}"),
                None => action.clone(),
            };
            let event = ThreatEvent::from_score(
                event_kind,
                &logged_action,
                target.to_string_lossy(),
                &outcome.hashes.sha256,
                &outcome.score,
            );
            engines.logger.emit(&event);
        }

        results.push(json!({
            "path": target.to_string_lossy(),
            "sha256": outcome.hashes.sha256,
            "score": outcome.score.value,
            "verdict": outcome.score.verdict,
            "reasons": outcome.score.findings.iter().map(|f| f.explain()).collect::<Vec<_>>(),
            "action": action,
            "quarantine_id": quarantine_id,
            "quarantine_error": quarantine_error,
        }));

        if score_rank(outcome.score.verdict) > score_rank(worst) {
            worst = outcome.score.verdict;
        }
    }

    if json {
        print_json(&json!({
            "scanned": results.len(), "worst": worst, "report_only": report_only,
            "results": results, "failed": failed, "warnings": engines.warnings,
        }));
    }

    Ok(if worst == Verdict::Clean {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    })
}

fn score_rank(v: Verdict) -> u8 {
    match v {
        Verdict::Clean => 0,
        Verdict::Suspicious => 1,
        Verdict::Elevated => 2,
        Verdict::Contain => 3,
        Verdict::Quarantine => 4,
    }
}

fn print_outcome(target: &Path, outcome: &guardian_scanners::pipeline::ScanOutcome) {
    println!("{}", target.display());
    println!("  sha256: {}", outcome.hashes.sha256);
    println!(
        "  score:  {} ({})",
        outcome.score.value, outcome.score.verdict
    );
    if outcome.score.findings.is_empty() {
        println!("  reasons: keine");
    } else {
        for finding in &outcome.score.findings {
            println!("  reason: {}", finding.explain());
        }
    }
}

fn cmd_status(config_path: Option<&Path>, json: bool) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    let rule_manager = RuleManager::new(&engines.config.rules_dir);

    if json {
        print_json(&json!({
            "config": engines.config_path.to_string_lossy(),
            "thresholds": engines.config.thresholds,
            "rules_dir": engines.config.rules_dir.to_string_lossy(),
            "rule_files": engines.yara.as_ref().map(|y| y.rule_file_count()).unwrap_or(0),
            "rules_version": engines.yara.as_ref().map(|y| y.version()),
            "rule_root_version": rule_manager.version().ok(),
            "hash_db_entries": engines.hash_db.len(),
            "hash_db_path": engines.config.hash_db_path.to_string_lossy(),
            "quarantine_entries": quarantine.list()?.len(),
            "quarantine_dir": engines.config.quarantine_dir.to_string_lossy(),
            "log_path": engines.logger.path().to_string_lossy(),
            "warnings": engines.warnings,
        }));
        return Ok(ExitCode::SUCCESS);
    }

    println!("Guardian Endpoint Protection -- Phase 1");
    println!("config:      {}", engines.config_path.display());
    println!(
        "thresholds:  suspicious>={} elevated>={} contain>={} quarantine>={}",
        engines.config.thresholds.suspicious,
        engines.config.thresholds.elevated,
        engines.config.thresholds.contain,
        engines.config.thresholds.quarantine
    );
    println!("rules_dir:   {}", engines.config.rules_dir.display());
    println!(
        "rules:       {} Dateien geladen, Version {}",
        engines
            .yara
            .as_ref()
            .map(|y| y.rule_file_count())
            .unwrap_or(0),
        engines
            .yara
            .as_ref()
            .map(|y| y.version())
            .unwrap_or("n/a (Regeln nicht geladen)"),
    );
    println!(
        "rule_root_version: {}",
        rule_manager.version().unwrap_or_else(|_| "n/a".to_string())
    );
    println!(
        "hash_db:     {} bekannte Einträge ({})",
        engines.hash_db.len(),
        engines.config.hash_db_path.display()
    );
    println!(
        "quarantine:  {} Einträge in {}",
        quarantine.list()?.len(),
        engines.config.quarantine_dir.display()
    );
    println!("log:         {}", engines.logger.path().display());
    Ok(ExitCode::SUCCESS)
}

fn cmd_quarantine_list(config_path: Option<&Path>, json: bool) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    let records = quarantine.list()?;
    if json {
        print_json(&json!({ "entries": records, "warnings": engines.warnings }));
        return Ok(ExitCode::SUCCESS);
    }
    if records.is_empty() {
        println!("Quarantäne ist leer.");
        return Ok(ExitCode::SUCCESS);
    }
    for record in records {
        println!(
            "{}  score={:<3} {}  {}  restored={}",
            record.id,
            record.threat_score,
            record.detection_time,
            record.original_filename,
            record.restored
        );
        println!("    original: {}", record.original_path);
        println!("    reason:   {}", record.detection_reason);
    }
    Ok(ExitCode::SUCCESS)
}

fn cmd_quarantine_restore(
    config_path: Option<&Path>,
    id: &str,
    json: bool,
) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    match quarantine.restore(id) {
        Ok(path) => {
            if json {
                print_json(&json!({ "id": id, "restored": path.to_string_lossy() }));
            } else {
                println!("Wiederhergestellt: {}", path.display());
            }
            engines.logger.emit(
                &ThreatEvent::now("quarantine_restored", "restored")
                    .with_file(path.to_string_lossy()),
            );
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => {
            eprintln!("Wiederherstellung fehlgeschlagen: {e}");
            if json {
                print_json(&json!({ "id": id, "error": e.to_string() }));
            }
            Ok(ExitCode::FAILURE)
        }
    }
}

fn cmd_rules_update(config_path: Option<&Path>, json: bool) -> anyhow::Result<ExitCode> {
    let config = GuardianConfig::load(config_path)?;
    let rule_manager = RuleManager::new(&config.rules_dir);
    rule_manager.ensure_layout()?;
    let before = rule_manager.version().unwrap_or_default();
    match YaraScanner::compile_dir(&config.rules_dir) {
        Ok(scanner) => {
            if json {
                print_json(&json!({
                    "rule_files": scanner.rule_file_count(),
                    "version": scanner.version(),
                    "previous": before,
                }));
            } else {
                println!(
                    "Regeln neu geladen: {} Dateien, Version {} (vorher {})",
                    scanner.rule_file_count(),
                    scanner.version(),
                    before
                );
            }
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => {
            eprintln!("Regeln konnten nicht kompiliert werden: {e}");
            if json {
                print_json(&json!({ "error": e.to_string() }));
            }
            Ok(ExitCode::FAILURE)
        }
    }
}

fn cmd_events(config_path: Option<&Path>, limit: usize, json: bool) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let events = engines.logger.read_recent(limit)?;
    if json {
        print_json(&json!({ "events": events, "warnings": engines.warnings }));
        return Ok(ExitCode::SUCCESS);
    }
    if events.is_empty() {
        println!("Noch keine Ereignisse protokolliert.");
        return Ok(ExitCode::SUCCESS);
    }
    for event in events {
        println!(
            "{}  {:<14} score={:<4} action={:<20} {}",
            event.timestamp,
            event.event,
            event
                .score
                .map(|s| s.to_string())
                .unwrap_or_else(|| "-".to_string()),
            event.action,
            event.file.unwrap_or_default(),
        );
    }
    Ok(ExitCode::SUCCESS)
}
