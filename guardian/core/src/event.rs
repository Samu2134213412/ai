//! The structured event that every log line and UI update is built from
//! (spec section 16), and the sink trait that lets any component publish
//! one without depending on how it's stored.

use serde::{Deserialize, Serialize};

use crate::finding::Finding;
use crate::scoring::Score;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreatEvent {
    /// RFC 3339 timestamp.
    pub timestamp: String,
    /// e.g. "scan_clean", "threat_detected", "quarantined", "restored".
    pub event: String,
    pub file: Option<String>,
    pub sha256: Option<String>,
    pub score: Option<u8>,
    pub reasons: Vec<String>,
    pub action: String,
}

impl ThreatEvent {
    pub fn now(event: impl Into<String>, action: impl Into<String>) -> Self {
        Self {
            timestamp: chrono::Local::now().to_rfc3339(),
            event: event.into(),
            file: None,
            sha256: None,
            score: None,
            reasons: Vec::new(),
            action: action.into(),
        }
    }

    pub fn with_file(mut self, path: impl Into<String>) -> Self {
        self.file = Some(path.into());
        self
    }

    pub fn with_sha256(mut self, sha256: impl Into<String>) -> Self {
        self.sha256 = Some(sha256.into());
        self
    }

    /// Builds the event straight from a completed [`Score`], so the
    /// `reasons` list always matches exactly what the score was computed
    /// from -- never a paraphrase written separately from the real findings.
    pub fn from_score(
        event: impl Into<String>,
        action: impl Into<String>,
        file: impl Into<String>,
        sha256: impl Into<String>,
        score: &Score,
    ) -> Self {
        Self {
            timestamp: chrono::Local::now().to_rfc3339(),
            event: event.into(),
            file: Some(file.into()),
            sha256: Some(sha256.into()),
            score: Some(score.value),
            reasons: score.findings.iter().map(Finding::explain).collect(),
            action: action.into(),
        }
    }
}

/// Anything that can receive [`ThreatEvent`]s: the JSONL logger, later a
/// live GUI feed, later still a remote SIEM forwarder. Emitting must never
/// be allowed to panic the caller -- a broken sink loses its own events,
/// not the detection that produced them.
pub trait EventSink: Send + Sync {
    fn emit(&self, event: &ThreatEvent);
}

/// Fans one event out to every registered sink.
#[derive(Default)]
pub struct EventBus {
    sinks: Vec<Box<dyn EventSink>>,
}

impl EventBus {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, sink: Box<dyn EventSink>) {
        self.sinks.push(sink);
    }

    pub fn emit(&self, event: &ThreatEvent) {
        for sink in &self.sinks {
            sink.emit(event);
        }
    }
}
