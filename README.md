# CodePilot Remote

Run a **real Claude Code session** on your Windows PC, driven from your Android
phone, with a **local Qwen3-Coder 30B** model served by Ollama.

```
Android phone
   │  (home Wi-Fi, or anywhere via Tailscale)
   ▼
CodePilot server  ──►  Claude Code (the actual CLI, with all its tools)
   │                       │
   │                       ▼
   └──────────────►  Ollama  ──►  qwen3-coder:30b
                           │
                           ▼
                 your repository / files / terminal
```

CodePilot is **not** a chat front-end for Ollama. It starts the real
`claude` CLI in your project directory and streams its structured output. Claude
Code still does the reading, searching, editing, test running and multi-step
work; the local model is simply what it thinks with, and your phone is the
screen and the approval button.

---

## Quick start

### 1. On the PC

```powershell
setup.bat
```

That is the whole first run. It checks Python, Node, Claude Code and Ollama;
offers to set `OLLAMA_CONTEXT_LENGTH=32768` (Ollama reads its context window from
its own server process, which is the single most common cause of odd behaviour);
offers to pull `qwen3-coder:30b` — **only if you say yes**, it is ~18 GB and
CodePilot never downloads it behind your back; installs the Python dependencies;
sets network access so your phone can connect; and finishes by diagnosing the
whole chain.

Then start it:

```powershell
start.bat
```

Open <http://127.0.0.1:8765/> and you should see something like:

```
Ollama: Online 0.14.2
Claude Code: Available 2.1.273
Git: Available 2.43.0
Model: qwen3-coder:30b
Model status: Available
```

### When something is wrong

```powershell
start.bat --doctor
```

`--check` tells you *what* is missing. `--doctor` tells you *which link is
broken*, by walking the chain in order and stopping at the first failure:

```
[1/8] ✓ Claude Code is installed     version 2.1.273
[2/8] ✓ Git is installed             version 2.43.0
[3/8] ✓ Ollama is running            version 0.14.2, 2 model(s) installed
[4/8] ✓ The configured model is pulled
[5/8] ✓ The model answers over the Anthropic API   replied: 'PONG'
[6/8] ! Ollama's context window
        Ollama loaded the model with 4096 tokens, but CodePilot wants 32768.
        -> Windows:  setx OLLAMA_CONTEXT_LENGTH 32768
        -> then fully restart Ollama (quit the tray icon and reopen it).
[7/8] ✓ Claude Code reaches the local model
[8/8] ✓ Your phone can reach this PC
```

Stage 7 is the decisive one: it runs the real `claude` binary against your real
Ollama and checks the answer. If that passes, the integration is correct and
anything left is a model-capability question, not a wiring one.

On macOS or Linux, use `./setup.sh` and `./start.sh`.

### 2. Let the phone in

Settings → **Network access** → *LAN + Tailscale*, then restart the server.
By default CodePilot binds to `127.0.0.1` and your phone cannot reach it at all.

### 3. Add a project

Projects → enter a name and an absolute path, e.g. `C:\Users\you\code\agent-factory`.
Claude Code is only ever allowed to run inside a directory on this list.

### 4. On the phone

```bash
cd mobile
npm install
npx expo start
```

Scan the Expo QR with **Expo Go**, then in the app tap *Pair with my PC* and scan
the pairing QR from the dashboard's **Pair Device** page.

### 5. Use it

Pick a project → **New task** → *"Find why the coder stage is failing and fix
it."* → **Start Claude Code**. Watch it read, search, edit and test. Approve or
reject anything it asks about. Inspect the diff. Close the app whenever you
like — the task keeps running on the PC, and reopening replays everything you
missed.

---

## How Claude Code is connected to Ollama

Ollama v0.14.0+ serves Anthropic's Messages API at `POST /v1/messages`, and
Claude Code can be pointed at any Anthropic-compatible endpoint through
environment variables. That is the whole integration — no undocumented flags,
and no `ollama launch claude` (that command does not exist in Ollama's docs).

CodePilot sets, per session:

```
ANTHROPIC_BASE_URL=http://127.0.0.1:8765/llm   # or the Ollama URL directly
ANTHROPIC_AUTH_TOKEN=<generated>
ANTHROPIC_DEFAULT_OPUS_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3-coder:30b
ANTHROPIC_API_KEY=                              # blanked, so no cloud fallback
```

By default the base URL points at CodePilot's own **compatibility proxy**, which
forwards `/v1/messages` untouched (streaming included) but answers
`/v1/messages/count_tokens` locally — Ollama does not implement that endpoint and
the resulting 404s have been reported to hang the server
([ollama/ollama#13949](https://github.com/ollama/ollama/issues/13949)). Turn it
off in Settings to talk to Ollama directly.

Details and troubleshooting: [`docs/OLLAMA.md`](docs/OLLAMA.md).

---

## Using it from school (or anywhere)

LAN-only is not enough if you are out of the house, so CodePilot is built for
**Tailscale**: install it on the PC and the phone, join the same tailnet, and the
PC becomes reachable at a private `100.x.y.z` address from anywhere — no port
forwarding, no public exposure. The pairing QR carries both the LAN and the
Tailscale address, and the app automatically uses whichever answers, switching
over on its own when you leave the house or move between Wi-Fi and mobile data.

Full instructions: [`docs/REMOTE_ACCESS.md`](docs/REMOTE_ACCESS.md).

---

## Security

Your phone can indirectly cause file edits and shell commands on your PC, so:

* nothing is anonymous — every request and every WebSocket carries a device token
* pairing tokens are single-use and expire after five minutes
* device tokens are 48 random bytes, stored hashed on the PC and in the Android
  keystore on the phone
* Claude Code is confined to the project allowlist, and diff paths are checked
  for `..` and symlink escapes
* the allowlist, settings, pairing and device revocation are **desktop-only** —
  a paired phone cannot widen its own access
* Claude Code's permission model is left intact; CodePilot only routes its
  prompts to your phone, and offers no "bypass permissions" switch
* no answer to an approval request means **denied**
* nothing is ever exposed to the public internet, and no firewall or router rule
  is touched

Full model and threat notes: [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Repository layout

```
server/                 FastAPI backend + web dashboard
  codepilot/
    app.py              REST API, WebSocket, routing
    config.py           settings & secrets (stored in ~/.codepilot)
    db.py               SQLite: projects, sessions, events, approvals, devices
    detect.py           live Claude Code / Git / Ollama / Tailscale detection
    events.py           typed event definitions and the fan-out hub
    compat_proxy.py     Anthropic-compatibility proxy in front of Ollama
    git_tools.py        read-only git status and diffs
    providers/          model-provider abstraction (Ollama today)
    bridge/
      claude_session.py the Claude Code subprocess and its event pump
      normalize.py      stream-json -> typed events
      approvals.py      approval broker
      permission_mcp.py stdio MCP server Claude Code calls for permission
    web/                dashboard (no build step)
  tests/                pytest suite, including a live Claude Code test
mobile/                 Expo / React Native app (Android first)
docs/                   OLLAMA, REMOTE_ACCESS, SECURITY, VERIFY, ARCHITECTURE
start.bat / start.sh    one command to start everything
```

## Tests

```bash
cd server
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest -q                      # unit + API + WebSocket + gateway

# Real Claude Code, against a throwaway repo:
CODEPILOT_LIVE_CLAUDE=1 python -m pytest tests/test_integration_claude.py -v -s
```

See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for exactly what has been verified
and what still needs to be confirmed on your own machine, and
[`docs/VERIFY.md`](docs/VERIFY.md) for the ten-minute checklist that proves the
Ollama half.

## Why React Native and not Flutter

Expo Go lets you run the app on a real Android phone straight from
`npx expo start`, with no APK build, no Android Studio and no signing. Flutter
would need a full toolchain install and a build for every change. Nothing in
this app needs Flutter's rendering engine, so Expo wins on the thing that
actually matters here: how fast you can try it.

## Not in v1

* pushing to GitHub or committing on your behalf (git is read-only)
* providers other than Ollama (the abstraction exists; nothing else is wired up)
* public-internet exposure or port forwarding, by design
