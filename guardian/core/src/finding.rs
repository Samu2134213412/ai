//! A [`Finding`] is one independent piece of evidence about a scan target.
//!
//! No single finding is ever treated as a verdict by itself -- the scoring
//! module sums the points of every finding a target collected, and only the
//! total decides what happens. That is the mechanism behind the project's
//! core rule against reacting to a single unreliable heuristic.

use serde::{Deserialize, Serialize};

/// Which detection engine produced a [`Finding`].
///
/// Variants beyond `Hash`, `Yara` and `Metadata` are declared now so the
/// architecture is stable across phases, even though only the file-scanning
/// engines (Phase 1) currently construct findings. Phase 2/3 engines
/// (process trees, behaviour, canaries, reputation, network, persistence)
/// will produce `Finding`s of the matching variant without needing any
/// change to this enum or to the scoring code that consumes it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FindingSource {
    Metadata,
    Hash,
    Yara,
    Heuristic,
    ProcessTree,
    Behavior,
    Canary,
    Reputation,
    Network,
    Persistence,
    JavaSecureMode,
}

impl FindingSource {
    pub fn as_str(&self) -> &'static str {
        match self {
            FindingSource::Metadata => "metadata",
            FindingSource::Hash => "hash",
            FindingSource::Yara => "yara",
            FindingSource::Heuristic => "heuristic",
            FindingSource::ProcessTree => "process_tree",
            FindingSource::Behavior => "behavior",
            FindingSource::Canary => "canary",
            FindingSource::Reputation => "reputation",
            FindingSource::Network => "network",
            FindingSource::Persistence => "persistence",
            FindingSource::JavaSecureMode => "java_secure_mode",
        }
    }
}

/// One independent piece of evidence, with the points it contributes to the
/// total threat score. `points` may be negative -- a valid signature or a
/// long, uneventful history are legitimate reasons to *lower* a score, not
/// just raise it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub source: FindingSource,
    /// Short machine-friendly label, e.g. the matched YARA rule's name.
    pub label: String,
    /// Human-readable explanation shown to the user (False-Positive-Schutz,
    /// Anforderung 24: every detection must be able to say *why*).
    pub description: String,
    pub points: i32,
}

impl Finding {
    pub fn new(
        source: FindingSource,
        label: impl Into<String>,
        description: impl Into<String>,
        points: i32,
    ) -> Self {
        Self {
            source,
            label: label.into(),
            description: description.into(),
            points,
        }
    }

    /// Rendered as the `"+35 yara_match"` style line used in explanations
    /// (see spec section 24).
    pub fn explain(&self) -> String {
        format!("{:+} {}", self.points, self.description)
    }
}
