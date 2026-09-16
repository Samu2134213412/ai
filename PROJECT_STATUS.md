# CodePilot Remote — Project Status

Last updated: 2026-09-16

## 1. Environment inspection (actually measured)

The build/inspection ran inside the Claude Code cloud container (Linux), **not**
on the target Windows PC. Everything below is what was actually observed here.

| Component | Result in build environment | Notes |
|---|---|---|
| Claude Code | **2.1.273** (`/opt/node22/bin/claude`) | Present, working, `--print --output-format stream-json` verified live |
| Node.js | **v22.22.2**, npm 10.9.7 | Present |
| Python | **3.11.15** | Present |
| Git | **2.43.0** | Present |
| Ollama | **not installed here** | Detection is implemented and runs at server startup on your PC |
| Qwen3-Coder 30B | **not present here** | Cannot be downloaded in this container; server reports status + exact pull command |
| Tailscale | **not installed here** | Detection implemented (`tailscale ip -4` / `tailscale status --json`) |

> Nothing about Ollama/Qwen status is faked. The dashboard and mobile app display
> whatever the live detector returns on your machine, including "Missing".

## 2. Chosen Claude Code ↔ Ollama integration (documented, not invented)

Ollama **v0.14.0+** serves Anthropic's Messages API natively at `POST /v1/messages`.
The documented way to point Claude Code at it is environment variables only —
no special CLI flags, and there is **no** `ollama launch claude` command in the
official docs, so it is not used.

```
ANTHROPIC_BASE_URL=http://127.0.0.1:11434
ANTHROPIC_AUTH_TOKEN=ollama          # required by Claude Code, ignored by Ollama
ANTHROPIC_DEFAULT_OPUS_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3-coder:30b
OLLAMA_CONTEXT_LENGTH=32768          # set on the `ollama serve` process
```

Sources:
- <https://github.com/ollama/ollama/blob/main/docs/api/anthropic-compatibility.mdx>
- <https://docs.ollama.com/integrations/claude-code>

### Known upstream bug we work around
Claude Code calls `POST /v1/messages/count_tokens?beta=true`, which Ollama does
not implement; the resulting 404 storm has been reported to degrade and hang the
Ollama server (ollama/ollama#13949). CodePilot therefore ships an **optional
compatibility proxy** (`compat_proxy_enabled`, default **on**) that sits between
Claude Code and Ollama, answers `count_tokens` locally with an estimate, passes
`/v1/messages` straight through (streaming included), and short-circuits every
other path instead of letting it reach Ollama. Turn it off in Settings to talk to
Ollama directly.

## 3. Component status

| Component | State |
|---|---|
| Desktop server (FastAPI + WS) | Implemented |
| Environment detection | Implemented |
| Claude Code bridge (stream-json, typed events) | Implemented |
| Remote tool approval (`--permission-prompt-tool` + MCP server) | Implemented |
| Ollama provider + compat proxy | Implemented |
| Auth / pairing / project allowlist | Implemented |
| Web dashboard (6 pages, dark) | Implemented |
| Expo mobile app (Android-first) | Implemented |
| Diffs, git status, session history | Implemented |
| Tailscale remote access | Implemented (address discovery + docs) |
| Backend test suite | Implemented, **passing** — see below |

## 4. What has been verified, and what has not

### Verified by actually running it, in this environment

| Check | Result |
|---|---|
| Backend suite (`pytest -q`) | **77 passed, 2 skipped** (the 2 skips are the opt-in live tests) |
| Real Claude Code session through the bridge | **passed** — real `claude` subprocess, real `Read`/`Edit`/`Bash` tools, real edits on disk, real diff |
| Independent re-run of the tests Claude Code wrote | **2 passed** |
| CodePilot MCP approval server loads in Claude Code | **`{"name": "codepilot", "status": "connected"}`** in the session `init` frame |
| Approval round-trip through the real MCP child process | **passed** — the card reached the phone API; *Reject* returned `deny`, *Approve* returned `allow` with untouched input |
| Claude Code raising real approval prompts | **observed** — in one run Claude Code asked before `python -m pytest`, and the request appeared on the phone API |
| Event log ordering | gapless `seq` 1..N asserted on a real session |
| Reconnect-and-replay | asserted: 6 events published across a disconnect, replay from cursor returned exactly 3,4,5,6 |
| Privilege separation | a non-loopback client gets 403 on all 10 admin endpoints |
| Path traversal | `../`, absolute paths and symlink escapes all rejected |
| Server smoke test | real uvicorn: dashboard 200, auth gate 401, pairing + QR SVG, device pairing, gateway `count_tokens` 200 / unauthorized 401 / unknown path 404 |
| Mobile app compiles | `npx expo export --platform android` produced a 2.64 MB Hermes bundle — every screen and import resolves |
| Expo config | `npx expo config` resolves all plugins |

Three real bugs were found and fixed this way:

1. The WebSocket envelope spread the event dict over `{"type": "event", ...}`, so
   the event's own `type` clobbered the envelope's. Frames now carry `event_type`
   separately.
2. A jest `Tests: 1 failed, 17 passed, 18 total` line was matched by the looser
   pytest pattern first and lost the total. Patterns are now ordered
   most-specific-first.
3. `expo-router@5.0.2` failed to bundle: it requires `query-string`, which the
   current `@react-navigation/native` no longer pulls in. Pinned explicitly.

### Not verified here, because this environment cannot

* **Claude Code talking to Ollama / qwen3-coder:30b.** No Ollama, no GPU, and the
  model is ~18 GB — deliberately not downloaded. The wiring is exactly the
  documented env-var contract above, and `docs/VERIFY.md` is a ten-minute
  checklist that proves it on your PC. The live test suite runs against the local
  model with `CODEPILOT_LIVE_USE_OLLAMA=1 CODEPILOT_LIVE_MODEL=qwen3-coder:30b`.
* **Tailscale connectivity from a phone.** Detection code is written against
  `tailscale status --json`; Tailscale is not installed here.
* **The Expo app on a physical Android device.** It compiles, but no device or
  emulator exists in this container, so no screen has been rendered.
* **Whether a 30B local model is strong enough** for long agentic tool chains in
  your Agent Factory project. That is a model-capability question, not a wiring
  one, and only your hardware can answer it.

## 5. Next step for you
Follow `docs/VERIFY.md` — it is a 10-minute checklist that proves the Ollama half
on your own machine.
