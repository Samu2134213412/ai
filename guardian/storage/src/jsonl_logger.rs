//! Append-only JSONL event log (spec section 16). One `ThreatEvent` per
//! line, so `guardian events` and any future GUI can tail or grep it with
//! ordinary tools even before there's a database.

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use guardian_core::{EventSink, ThreatEvent};

pub struct JsonlLogger {
    path: PathBuf,
    lock: Mutex<()>,
}

impl JsonlLogger {
    pub fn new(path: impl Into<PathBuf>) -> anyhow::Result<Self> {
        let path = path.into();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        Ok(Self {
            path,
            lock: Mutex::new(()),
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Reads the last `limit` events, oldest of the returned batch first.
    /// A missing log file is not an error -- it means nothing has happened
    /// yet, not that logging is broken.
    pub fn read_recent(&self, limit: usize) -> anyhow::Result<Vec<ThreatEvent>> {
        let _guard = self.lock.lock().unwrap();
        if !self.path.is_file() {
            return Ok(Vec::new());
        }
        let file = std::fs::File::open(&self.path)?;
        let lines: Vec<String> = BufReader::new(file).lines().collect::<Result<_, _>>()?;
        let start = lines.len().saturating_sub(limit);
        let mut events = Vec::new();
        for line in &lines[start..] {
            if line.trim().is_empty() {
                continue;
            }
            events.push(serde_json::from_str(line)?);
        }
        Ok(events)
    }
}

impl EventSink for JsonlLogger {
    fn emit(&self, event: &ThreatEvent) {
        let _guard = self.lock.lock().unwrap();
        let Ok(line) = serde_json::to_string(event) else {
            return;
        };
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
        {
            let _ = writeln!(file, "{line}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn emitted_events_come_back_in_order() {
        let dir = tempfile::tempdir().unwrap();
        let logger = JsonlLogger::new(dir.path().join("events.jsonl")).unwrap();
        logger.emit(&ThreatEvent::now("scan_clean", "none"));
        logger.emit(&ThreatEvent::now("threat_detected", "quarantined"));

        let events = logger.read_recent(10).unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].event, "scan_clean");
        assert_eq!(events[1].event, "threat_detected");
    }

    #[test]
    fn missing_log_file_reads_as_empty_not_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let logger = JsonlLogger::new(dir.path().join("never-written.jsonl")).unwrap();
        assert!(logger.read_recent(10).unwrap().is_empty());
    }

    #[test]
    fn read_recent_respects_the_limit() {
        let dir = tempfile::tempdir().unwrap();
        let logger = JsonlLogger::new(dir.path().join("events.jsonl")).unwrap();
        for i in 0..5 {
            logger.emit(&ThreatEvent::now(format!("event_{i}"), "none"));
        }
        let events = logger.read_recent(2).unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].event, "event_3");
        assert_eq!(events[1].event, "event_4");
    }
}
