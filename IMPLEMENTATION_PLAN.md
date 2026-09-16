# CodePilot Remote — Implementation Plan

Status legend: `[x]` done · `[~]` done but unverifiable in this environment · `[ ]` not done

## Phase 1 — Desktop backend, Claude Code + Ollama integration, streaming
- [x] FastAPI app, `python -m codepilot`, single command starts API + dashboard
- [x] Persistent config at `~/.codepilot/config.json` (never in git)
- [x] SQLite store: projects, sessions, events, approvals, devices
- [x] Environment detection: Claude Code, Git, Ollama, Ollama models, Tailscale, LAN IPs
- [x] Model provider abstraction (`ModelProvider`) + `OllamaProvider`
- [x] Anthropic-compat guard proxy (fixes ollama/ollama#13949 `count_tokens` hang)
- [x] Claude Code bridge: `claude -p --output-format stream-json --input-format stream-json`
- [x] Typed event normalisation (no console-text scraping)
- [x] Stop / follow-up message / resume (`--resume`)

## Phase 2 — Auth, pairing, project restrictions
- [x] 32-byte server secret, generated once, 0600 on POSIX
- [x] Device tokens (48-byte urlsafe, sha256-hashed at rest), bearer auth on REST + WS
- [x] One-time pairing token, 5-minute TTL, single use, QR payload
- [x] Project allowlist + real-path containment check (blocks `..`, symlink escapes)
- [x] Session authorization: a session is bound to a project; `--add-dir` never widened

## Phase 3 — Desktop web dashboard
- [x] Dark developer UI, no build step, served by the backend
- [x] Pages: Dashboard · Projects · Sessions · Models · Settings · Pair Device
- [x] Live status strip driven purely by real detector output

## Phase 4 — React Native (Expo) mobile app
- [x] Expo + expo-router, Android-first, iOS-compatible structure
- [x] QR pairing (expo-camera) + expo-secure-store credential storage
- [x] Screens: Home · Projects · Project · New Task · Session · Diff · Settings
- [x] Multi-address failover (LAN ↔ Tailscale) + auto-reconnect on network change

## Phase 5 — Approvals, diffs, history, reconnection
- [x] `--permission-prompt-tool` + stdio MCP server -> phone approval cards
- [x] Approve Once / Reject / Reject with feedback; Claude Code's own model untouched
- [x] Diff list (+adds/-dels per file) and per-file diff with highlighting
- [x] Session history with status running/completed/failed/cancelled
- [x] Event log persisted with a monotonic sequence -> replay-from-cursor on reconnect
- [x] Sessions keep running when the phone is closed

## Phase 6 — Tests, integration validation, docs
- [x] Unit/integration test suite (`pytest server/tests`) — 77 passed, 2 skipped
- [x] Live Claude Code bridge test against a throwaway repo (opt-in flag) — passing
- [x] Live MCP approval round-trip test against a real uvicorn server — passing
- [x] Mobile app verified to bundle (`expo export --platform android`)
- [~] End-to-end with Ollama + qwen3-coder:30b — scripted in `docs/VERIFY.md`, must run on the Windows PC
- [x] README, REMOTE_ACCESS.md (Tailscale), SECURITY.md, VERIFY.md

## Deliberately out of scope (v1)
- Automatic git push / PR creation (read-only git inspection only)
- Public-internet exposure, router port-forwarding, UPnP
- Providers other than Ollama (abstraction is in place; nothing else implemented)
