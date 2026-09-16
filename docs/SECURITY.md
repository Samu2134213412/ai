# Security model

A paired phone can cause Claude Code to read, edit and execute things on your PC.
That is the point of the product, and also the reason for every rule below.

## Threat model

**Defended against**

* Anyone on your Wi-Fi, or on your tailnet, who has not paired.
* A stolen or lost phone (the credential is revocable from the PC, and pairing
  tokens cannot be reused).
* A paired phone trying to escalate — reach files outside the allowlist, add new
  project roots, read secrets, or disable approvals.
* Accidental public exposure (bind is loopback by default, and nothing in the
  product opens a router or firewall).
* An operation running without your consent because the approval path failed.

**Not defended against**

* Someone with an interactive login on the PC. They already have everything
  CodePilot has, more directly.
* A malicious prompt persuading Claude Code to do something inside an allowlisted
  project. CodePilot constrains *where*, not *what* — the approval cards are your
  control here, which is why `manual` is the default mode.
* A compromised model or a compromised Ollama. CodePilot trusts whatever is
  answering at `ollama_url`.

## Authentication

| | |
|---|---|
| Pairing token | 32 random bytes (`secrets.token_urlsafe(32)`), **single use**, 5-minute TTL, memory only — a server restart invalidates it. Compared with `hmac.compare_digest`. |
| Device token | 48 random bytes. Returned exactly once at pairing. Stored **hashed** (SHA-256) on the PC; stored in the Android keystore (`expo-secure-store`) on the phone. |
| Server secret / gateway token / internal token | Generated on first run into `~/.codepilot/config.json`, `0600` on POSIX. Never returned by the API, never written into the repository. |

Every REST endpoint and the WebSocket require `Authorization: Bearer <device
token>` (the socket also accepts it as a query parameter, since browsers and RN
cannot set headers on a WebSocket handshake). There is no anonymous access and no
default credential. The single exception is `GET /api/health`, which exists so
the phone can probe candidate addresses; it returns a service name, a version and
`auth_required: true`, and nothing else.

## Privilege separation

A phone is a *client*, not an administrator. These are restricted to loopback —
that is, to the dashboard running on the PC itself:

* issuing and revoking pairing tokens
* listing and revoking paired devices
* reading and writing settings
* adding or deleting projects (the allowlist)
* the internal approval callback endpoint

A phone that tries any of them gets `403`. This is enforced by a dependency on
every such route and covered by `tests/test_privilege_separation.py`.

## Filesystem containment

* A project path must be absolute and must already exist; it is stored
  fully resolved.
* Claude Code is launched with `cwd` set to the project root and no `--add-dir`,
  so its own tools are already scoped.
* Any path that arrives from the phone (diff requests) is resolved and checked
  against the project root with `ensure_within()`. Because **both** sides are
  resolved, `../`, absolute paths and symlinks pointing outside the project are
  all rejected — not just literal `..` in the string.
* Git is invoked with fixed argument lists and an explicit `cwd`; no shell is
  involved, so nothing from the phone can be interpreted as a command.

## Claude Code's permission model

CodePilot does not weaken it. Specifically:

* Sessions run in one of Claude Code's own modes — `manual` (default),
  `acceptEdits` or `plan`. There is deliberately **no** option anywhere in the UI
  or the API for `bypassPermissions` or `--dangerously-skip-permissions`.
* Operations Claude Code already considers allowed run normally and never
  generate an approval card. Whether something needs approval is Claude Code's
  decision and your settings files', not CodePilot's.
* When Claude Code does want a human, it calls the MCP tool
  `mcp__codepilot__approve` (passed via `--permission-prompt-tool`). That tool
  runs as a separate process, posts to the backend over loopback with the
  internal token, and blocks.
* The backend raises a `tool.approval_required` event on your phone and waits.
* **Fail closed everywhere**: if the backend is unreachable, the MCP tool denies.
  If nobody answers within `approval_timeout`, the broker denies. If the session
  is stopped, everything pending is denied. There is no path where silence means
  "allow".

## Network exposure

* Default bind is `127.0.0.1`. Your phone genuinely cannot reach it until you opt
  in, and the pairing page says so explicitly.
* `private` mode binds `0.0.0.0`, which covers the LAN **and** the Tailscale
  interface. Authentication is unchanged — Tailscale is a second layer, not a
  replacement.
* Nothing configures UPnP, port forwarding or firewall rules. Remote access is
  documented as Tailscale-only; see `REMOTE_ACCESS.md`.
* The model gateway at `/llm` requires its own generated token, so binding to the
  LAN does not hand out a free inference endpoint.
* The API exposes no OpenAPI schema or docs UI.

## Secrets and git

Configuration and the session database live in `~/.codepilot` (or
`$CODEPILOT_HOME`), never in the repository. `.gitignore` additionally excludes
`config.json`, `*.db` and `.codepilot/` so a stray copy cannot be committed. No
API key is hardcoded anywhere in the source.

## Revocation

Dashboard → **Pair Device** → *Revoke* next to a device. It takes effect on the
next request: the token hash is marked revoked and authentication fails, closing
existing WebSockets too. Unpairing from the phone only forgets the local copy —
revoke on the PC if the phone is lost.

## Known gaps

* **Plain HTTP.** Traffic is unencrypted on the LAN. Over Tailscale it is inside
  WireGuard and therefore encrypted end to end; on your home Wi-Fi it is not. TLS
  with a self-signed certificate would mean certificate pinning in the app, which
  is not implemented in v1.
* **No rate limiting** on the pairing endpoint. The token is 32 random bytes with
  a 5-minute life, so guessing is not realistic, but a limiter would still be
  better.
* **Approvals are per-operation.** There is no "always allow this command"
  memory, by choice — it is the kind of convenience that quietly removes the
  control you installed this for.
