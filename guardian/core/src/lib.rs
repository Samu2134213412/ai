//! Shared types for Guardian: findings, scoring, configuration and the
//! event bus that every other crate reports through.
//!
//! This crate has no side effects of its own -- it does not touch the
//! filesystem, spawn processes, or scan anything. It only defines the
//! vocabulary that the rest of the system uses to talk about what it found
//! and what it did about it.

pub mod config;
pub mod event;
pub mod finding;
pub mod scoring;

pub use config::GuardianConfig;
pub use event::{EventSink, ThreatEvent};
pub use finding::{Finding, FindingSource};
pub use scoring::{score_findings, Score, ThreatThresholds, Verdict};
