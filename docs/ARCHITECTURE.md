# Architecture

## The one design decision that matters

CodePilot **runs the real `claude` CLI**. It does not reimplement an agent, and
it never sends a prompt to Ollama itself. Claude Code keeps doing the reading,
searching, editing, test running and multi-step planning; Ollama is only the
model behind it, and the phone is only a screen plus an approval button.

Everything below follows from that.

## Processes

```
  CodePilot server (one Python process)
  ├── FastAPI: REST + WebSocket + dashboard         port 8765
  ├── /llm  : Anthropic-compatibility proxy ───────► Ollama :11434 ──► qwen3-coder:30b
  └── per session:
      └── claude --print --output-format stream-json ... (cwd = project)
          └── python -m codepilot.bridge.permission_mcp  (stdio MCP child)
              └── HTTP ──► back to the server's /internal/approvals/request
```

The Claude Code process is a child of the **server**, not of any socket. Phones
come and go; the task does not.

## Why `stream-json` and not a PTY

Claude Code's `--print --output-format stream-json --input-format stream-json
--verbose` mode emits one JSON object per line: `system/init`, `assistant`
messages with `text`/`thinking`/`tool_use` blocks, `user` messages carrying
`tool_result`, and a final `result`. That is a structured interface, so
`bridge/normalize.py` maps it onto typed events instead of scraping terminal
text. No ANSI parsing, no screen-size games, no guessing.

The `stream-json` **input** side matters just as much: it is what lets the phone
push another message into a turn that is already running ("Send another
message"), by writing a user frame to the process's stdin.

## Event model

```
session.started       tool.started              file.changed
session.status        tool.finished             test.result
assistant.message     tool.approval_required    session.completed
assistant.thinking    tool.approval_resolved    session.failed
user.message          claude.raw                session.cancelled
                                                session.error
```

Each event is appended to SQLite with a **monotonic per-session `seq`** *before*
it is broadcast. That single property is what makes the mobile experience work:

* a client reconnects with the last `seq` it saw,
* the server replays everything after it, in order,
* then the live stream resumes.

Nothing is lost to a locked screen, a backgrounded app, or a walk out of Wi-Fi
range. `claude.raw` carries frames we do not model yet (partial stream chunks,
rate-limit notices); clients only receive it if they ask for `verbose=1`, so the
protocol can grow without breaking older apps.

`test.result` is the one heuristic in the system — it pattern-matches pytest and
jest summaries out of `Bash` output. It carries `heuristic: true` so the UI can
be honest about it.

## Approvals

CodePilot has no opinion about what needs approval; that is Claude Code's
decision and your settings files'. It only answers the question when Claude Code
asks it, and it routes the question to your phone:

```
Claude Code decides a human is needed
  └─► calls MCP tool mcp__codepilot__approve      (--permission-prompt-tool)
        └─► permission_mcp.py POSTs to the server (loopback + internal token)
              └─► ApprovalBroker stores it, emits tool.approval_required, blocks
                    └─► phone shows a card, you tap Approve or Reject
                          └─► broker resolves the future
                                └─► MCP tool returns {"behavior": "allow"|"deny"}
```

Every failure mode denies: unreachable backend, timeout, stopped session. There
is no code path where silence allows.

The MCP server speaks JSON-RPC 2.0 over stdio by hand — about 150 lines and no
third-party dependency, so it starts instantly and drags nothing extra into the
Claude Code process tree.

## Provider abstraction

`providers/base.py` defines three methods:

* `health()` — is it up, is the model there, what should the user run if not
* `list_models()` — without downloading anything
* `claude_env()` — the environment variables that point Claude Code at it

`OllamaProvider` is the only implementation. Adding the Claude API, an
OpenAI-compatible gateway, Agent Factory or another local runtime is a new class
plus one registry line. Nothing outside `providers/` names Ollama or
`qwen3-coder`.

## The compatibility proxy

Optional, on by default, and purely a transport shim: it forwards `/v1/messages`
byte-for-byte (SSE included), answers `/v1/messages/count_tokens` locally because
Ollama does not implement it, and 404s everything else so unsupported paths never
reach the Ollama server. See `OLLAMA.md` for why that matters.

## Trust boundaries

| Boundary | Enforcement |
|---|---|
| Phone → server | device bearer token on every request and socket |
| Phone → admin actions | loopback only; a phone gets 403 |
| Phone → filesystem | project allowlist + resolved-path containment |
| Server → Claude Code | fixed argv, explicit `cwd`, no shell |
| Claude Code → the user | Claude Code's own permission model, unmodified |
| Server → Ollama | generated gateway token even on a LAN bind |

## Storage

| What | Where |
|---|---|
| Settings and secrets | `~/.codepilot/config.json` (0600) |
| Projects, sessions, events, approvals, devices | `~/.codepilot/codepilot.db` (SQLite, WAL) |
| Phone credential | Android keystore via `expo-secure-store` |
| Known server addresses | `AsyncStorage` on the phone |

Nothing sensitive is written inside the repository.

## Diagnosis

`python -m codepilot --doctor` walks the chain in dependency order — Claude Code,
Git, Ollama reachable, Ollama speaks `/v1/messages`, the model is pulled, the
model answers, Claude Code reaches it, the phone can reach the PC — and stops at
the first failure, skipping everything downstream. Each stage carries what it
proved and, on failure, the exact command to run next. Stage 7 spawns the real
`claude` binary with the real provider environment, so a pass there is end-to-end
evidence rather than a component check.

## Known limits

* One server process; if it restarts, its Claude Code children die. Those
  sessions are marked `failed` with an explanation, and *Continue session*
  resumes the same Claude Code context in a fresh turn.
* Events are kept forever. A very long-running session builds a large table; no
  pruning is implemented yet.
* Plain HTTP on the LAN (encrypted over Tailscale). See `SECURITY.md`.
