//! Threat scoring: turning a list of [`Finding`]s into one 0-100 score and a
//! [`Verdict`], against configurable thresholds.
//!
//! The default thresholds are exactly the ones from the project brief:
//!
//! | score  | verdict     | meaning                              |
//! |--------|-------------|---------------------------------------|
//! | 0-29   | Clean       | wahrscheinlich ungefährlich           |
//! | 30-49  | Suspicious  | verdächtig, protokollieren            |
//! | 50-69  | Elevated    | erhöhte Überwachung                   |
//! | 70-84  | Contain     | Prozess stoppen und Datei isolieren   |
//! | 85-100 | Quarantine  | sofortige Quarantäne + Remediation    |

use serde::{Deserialize, Serialize};

use crate::finding::Finding;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    Clean,
    Suspicious,
    Elevated,
    Contain,
    Quarantine,
}

impl Verdict {
    pub fn as_str(&self) -> &'static str {
        match self {
            Verdict::Clean => "clean",
            Verdict::Suspicious => "suspicious",
            Verdict::Elevated => "elevated",
            Verdict::Contain => "contain",
            Verdict::Quarantine => "quarantine",
        }
    }

    /// Whether this verdict is confident enough to justify touching the
    /// filesystem (moving a file into quarantine). Below this, Guardian only
    /// ever logs -- per the project rule, no file is moved on an unsure call.
    pub fn warrants_containment(&self) -> bool {
        matches!(self, Verdict::Contain | Verdict::Quarantine)
    }
}

impl std::fmt::Display for Verdict {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Configurable score boundaries. Each field is the *minimum* score that
/// reaches that verdict. Must satisfy `suspicious < elevated < contain <=
/// quarantine <= 100` -- see [`ThreatThresholds::validate`].
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(default)]
pub struct ThreatThresholds {
    pub suspicious: u8,
    pub elevated: u8,
    pub contain: u8,
    pub quarantine: u8,
}

impl Default for ThreatThresholds {
    fn default() -> Self {
        Self {
            suspicious: 30,
            elevated: 50,
            contain: 70,
            quarantine: 85,
        }
    }
}

impl ThreatThresholds {
    pub fn classify(&self, score: u8) -> Verdict {
        if score >= self.quarantine {
            Verdict::Quarantine
        } else if score >= self.contain {
            Verdict::Contain
        } else if score >= self.elevated {
            Verdict::Elevated
        } else if score >= self.suspicious {
            Verdict::Suspicious
        } else {
            Verdict::Clean
        }
    }

    /// Sanity-checks a user-edited configuration. Returns human-readable
    /// problems instead of silently clamping or refusing to start.
    pub fn validate(&self) -> Vec<String> {
        let mut problems = Vec::new();
        if self.suspicious >= self.elevated {
            problems.push(format!(
                "suspicious ({}) must be lower than elevated ({})",
                self.suspicious, self.elevated
            ));
        }
        if self.elevated >= self.contain {
            problems.push(format!(
                "elevated ({}) must be lower than contain ({})",
                self.elevated, self.contain
            ));
        }
        if self.contain > self.quarantine {
            problems.push(format!(
                "contain ({}) must be lower than or equal to quarantine ({})",
                self.contain, self.quarantine
            ));
        }
        if self.quarantine > 100 {
            problems.push(format!(
                "quarantine ({}) must be at most 100",
                self.quarantine
            ));
        }
        problems
    }
}

/// A scored batch of findings: the sum of points (clamped to 0..=100) plus
/// the verdict that sum reaches under the given thresholds.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Score {
    pub value: u8,
    pub verdict: Verdict,
    pub findings: Vec<Finding>,
}

pub fn score_findings(findings: Vec<Finding>, thresholds: &ThreatThresholds) -> Score {
    let raw: i32 = findings.iter().map(|f| f.points).sum();
    let value = raw.clamp(0, 100) as u8;
    let verdict = thresholds.classify(value);
    Score {
        value,
        verdict,
        findings,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::finding::FindingSource;

    #[test]
    fn default_boundaries_match_the_spec_table() {
        let t = ThreatThresholds::default();
        assert_eq!(t.classify(0), Verdict::Clean);
        assert_eq!(t.classify(29), Verdict::Clean);
        assert_eq!(t.classify(30), Verdict::Suspicious);
        assert_eq!(t.classify(49), Verdict::Suspicious);
        assert_eq!(t.classify(50), Verdict::Elevated);
        assert_eq!(t.classify(69), Verdict::Elevated);
        assert_eq!(t.classify(70), Verdict::Contain);
        assert_eq!(t.classify(84), Verdict::Contain);
        assert_eq!(t.classify(85), Verdict::Quarantine);
        assert_eq!(t.classify(100), Verdict::Quarantine);
    }

    #[test]
    fn score_is_clamped_and_never_negative() {
        let findings = vec![Finding::new(FindingSource::Hash, "a", "a", -40)];
        let score = score_findings(findings, &ThreatThresholds::default());
        assert_eq!(score.value, 0);
        assert_eq!(score.verdict, Verdict::Clean);
    }

    #[test]
    fn score_is_clamped_at_one_hundred_even_with_many_findings() {
        let findings = vec![
            Finding::new(FindingSource::Yara, "a", "a", 60),
            Finding::new(FindingSource::Hash, "b", "b", 60),
        ];
        let score = score_findings(findings, &ThreatThresholds::default());
        assert_eq!(score.value, 100);
        assert_eq!(score.verdict, Verdict::Quarantine);
    }

    #[test]
    fn a_single_weak_signal_never_reaches_containment() {
        // "Ein einzelnes verdächtiges Merkmal darf nicht automatisch
        // Malware bedeuten." -- one low-weight finding must stay far below
        // the containment threshold.
        let findings = vec![Finding::new(FindingSource::Heuristic, "a", "a", 15)];
        let score = score_findings(findings, &ThreatThresholds::default());
        assert!(!score.verdict.warrants_containment());
    }

    #[test]
    fn broken_threshold_order_is_reported_not_silently_accepted() {
        let bad = ThreatThresholds {
            suspicious: 60,
            elevated: 50,
            contain: 70,
            quarantine: 85,
        };
        let problems = bad.validate();
        assert!(!problems.is_empty());
    }
}
