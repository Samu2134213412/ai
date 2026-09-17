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
}

fn load_engines(config_path: Option<&Path>) -> anyhow::Result<Engines> {
    let resolved_config_path = config_path
        .map(Path::to_path_buf)
        .unwrap_or_else(GuardianConfig::default_config_path);
    let config = GuardianConfig::load(config_path)?;
    for problem in config.validate() {
        eprintln!("Warnung: {problem}");
    }

    let rule_manager = RuleManager::new(&config.rules_dir);
    rule_manager.ensure_layout()?;
    let yara = match YaraScanner::compile_dir(&config.rules_dir) {
        Ok(scanner) => Some(scanner),
        Err(e) => {
            eprintln!(
                "Warnung: YARA-Regeln konnten nicht geladen werden ({e}). \
                 Scan läuft ohne YARA-Erkennung weiter -- Hash-Erkennung bleibt aktiv."
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
    })
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(cli) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("Fehler: {e:#}");
            ExitCode::FAILURE
        }
    }
}

fn run(cli: Cli) -> anyhow::Result<ExitCode> {
    match cli.command {
        Command::Scan { path, full } => cmd_scan(cli.config.as_deref(), path, full),
        Command::Status => cmd_status(cli.config.as_deref()),
        Command::Quarantine(QuarantineCmd::List) => cmd_quarantine_list(cli.config.as_deref()),
        Command::Quarantine(QuarantineCmd::Restore { id }) => {
            cmd_quarantine_restore(cli.config.as_deref(), &id)
        }
        Command::Rules(RulesCmd::Update) => cmd_rules_update(cli.config.as_deref()),
        Command::Events { limit } => cmd_events(cli.config.as_deref(), limit),
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
) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;

    let roots: Vec<PathBuf> = match (path, full) {
        (Some(_), true) => anyhow::bail!("--full und ein Pfad schließen sich aus"),
        (None, false) => anyhow::bail!("gib einen Pfad an oder benutze --full"),
        (Some(p), false) => vec![p],
        (None, true) => {
            if engines.config.scan_roots.is_empty() {
                println!(
                    "Keine scan_roots konfiguriert -- trage sie in {} ein.",
                    engines.config_path.display()
                );
                return Ok(ExitCode::SUCCESS);
            }
            engines.config.scan_roots.clone()
        }
    };

    let mut targets = Vec::new();
    for root in &roots {
        if !root.exists() {
            eprintln!(
                "Warnung: {} existiert nicht, wird übersprungen",
                root.display()
            );
            continue;
        }
        targets.extend(collect_targets(root, &engines.config.extensions));
    }

    if targets.is_empty() {
        println!("Keine passenden Dateien gefunden.");
        return Ok(ExitCode::SUCCESS);
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
    for target in &targets {
        let outcome = match run_scan(target, &ctx) {
            Ok(o) => o,
            Err(e) => {
                eprintln!("{}: Scan fehlgeschlagen: {e}", target.display());
                continue;
            }
        };
        print_outcome(target, &outcome);

        let event_kind = if outcome.score.verdict == Verdict::Clean {
            "scan_clean"
        } else {
            "scan_flagged"
        };
        let mut action = "logged".to_string();

        if outcome.score.verdict.warrants_containment() {
            match quarantine.store(target, &outcome.hashes.sha256, &outcome.score) {
                Ok(record) => {
                    action = "quarantined".to_string();
                    println!("  -> in Quarantäne verschoben (id={})", record.id);
                }
                Err(e) => {
                    action = format!("quarantine_failed: {e}");
                    eprintln!("  -> Quarantäne fehlgeschlagen: {e}");
                }
            }
        }

        let event = ThreatEvent::from_score(
            event_kind,
            &action,
            target.to_string_lossy(),
            &outcome.hashes.sha256,
            &outcome.score,
        );
        engines.logger.emit(&event);

        if score_rank(outcome.score.verdict) > score_rank(worst) {
            worst = outcome.score.verdict;
        }
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

fn cmd_status(config_path: Option<&Path>) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    let rule_manager = RuleManager::new(&engines.config.rules_dir);

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

fn cmd_quarantine_list(config_path: Option<&Path>) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    let records = quarantine.list()?;
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

fn cmd_quarantine_restore(config_path: Option<&Path>, id: &str) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let quarantine = Quarantine::new(&engines.config.quarantine_dir);
    match quarantine.restore(id) {
        Ok(path) => {
            println!("Wiederhergestellt: {}", path.display());
            engines.logger.emit(
                &ThreatEvent::now("quarantine_restored", "restored")
                    .with_file(path.to_string_lossy()),
            );
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => {
            eprintln!("Wiederherstellung fehlgeschlagen: {e}");
            Ok(ExitCode::FAILURE)
        }
    }
}

fn cmd_rules_update(config_path: Option<&Path>) -> anyhow::Result<ExitCode> {
    let config = GuardianConfig::load(config_path)?;
    let rule_manager = RuleManager::new(&config.rules_dir);
    rule_manager.ensure_layout()?;
    let before = rule_manager.version().unwrap_or_default();
    match YaraScanner::compile_dir(&config.rules_dir) {
        Ok(scanner) => {
            println!(
                "Regeln neu geladen: {} Dateien, Version {} (vorher {})",
                scanner.rule_file_count(),
                scanner.version(),
                before
            );
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => {
            eprintln!("Regeln konnten nicht kompiliert werden: {e}");
            Ok(ExitCode::FAILURE)
        }
    }
}

fn cmd_events(config_path: Option<&Path>, limit: usize) -> anyhow::Result<ExitCode> {
    let engines = load_engines(config_path)?;
    let events = engines.logger.read_recent(limit)?;
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
