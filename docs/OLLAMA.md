# Connecting Claude Code to Ollama

## The supported method

Ollama **v0.14.0+** implements a subset of Anthropic's Messages API at
`POST /v1/messages`. Claude Code talks to any Anthropic-compatible endpoint if
you point it there with environment variables. That is the entire integration.

From Ollama's own documentation
([`docs/api/anthropic-compatibility.mdx`](https://github.com/ollama/ollama/blob/main/docs/api/anthropic-compatibility.mdx)):

```shell
export ANTHROPIC_AUTH_TOKEN=ollama  # required but ignored
export ANTHROPIC_BASE_URL=http://localhost:11434
```

Claude Code appends `/v1/messages` itself, so the base URL carries no path.

There is **no** `ollama launch claude` command in the official documentation, so
CodePilot does not use one. No undocumented Claude Code flags are used either —
everything CodePilot passes (`--print`, `--output-format stream-json`,
`--input-format stream-json`, `--model`, `--permission-mode`, `--mcp-config`,
`--permission-prompt-tool`, `--session-id`, `--resume`) appears in `claude --help`.

## Model aliases

Claude Code resolves its model *tiers* through three variables, and uses the
small tier for background work such as summarisation. CodePilot points all three
at your local model so a session never silently falls back to a cloud model:

```
ANTHROPIC_DEFAULT_OPUS_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3-coder:30b
ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3-coder:30b
ANTHROPIC_API_KEY=
```

`ANTHROPIC_API_KEY` is blanked deliberately: if an Anthropic credential were left
in the environment, a misconfiguration could route your "local" session to the
cloud and bill you for it.

## Context length — the knob that matters most

Ollama decides the context window on its **server** process, not per request. If
you leave it at the default, Claude Code's system prompt and tool definitions
alone will overflow it and everything will behave strangely.

Set it before starting Ollama:

```powershell
# Windows, permanent
setx OLLAMA_CONTEXT_LENGTH 32768
# then restart the Ollama service / tray app
```

```bash
# macOS / Linux
export OLLAMA_CONTEXT_LENGTH=32768
ollama serve
```

### Why 32K is the default here

A 30B model at 4-bit quantisation occupies roughly 18 GB. On a 24 GB card that
leaves a few GB for the KV cache, which is what the context window actually
costs. 32K fits comfortably. 64K is offered in the UI and will usually work, but
it is tight once a long tool transcript builds up — if you see the GPU spill into
system RAM and generation crawl, that is the cause. 256K is deliberately not
offered: it will not fit.

CodePilot's `context_length` setting is passed to Claude Code sessions and shown
in the UI, but **Ollama's own `OLLAMA_CONTEXT_LENGTH` is what binds**. Set both
to the same value.

## The compatibility proxy

Claude Code calls `POST /v1/messages/count_tokens?beta=true` to budget context.
Ollama does not implement it, and the 404s have been reported to degrade and
eventually hang the Ollama server
([ollama/ollama#13949](https://github.com/ollama/ollama/issues/13949)).

So by default CodePilot puts a thin proxy in between, at
`http://127.0.0.1:<port>/llm`:

| Path | What happens |
|---|---|
| `POST /v1/messages` | forwarded to Ollama byte-for-byte, streaming included |
| `POST /v1/messages/count_tokens` | answered locally with a character-based estimate |
| `GET /v1/models` | translated from Ollama's `/api/tags` |
| anything else | 404 immediately, never reaches Ollama |

It is a transport shim: it never rewrites prompts, tools or responses, so Claude
Code's agent loop is untouched. It is protected by a generated token so that even
when the server is bound to `0.0.0.0`, nobody on your network gets a free model
endpoint.

Turn it off in **Settings → Compatibility proxy** if you would rather talk to
Ollama directly (or once the upstream issue is fixed).

## Troubleshooting

**"Ollama: OFFLINE"** — `ollama serve` is not running, or `ollama_url` in
Settings points somewhere else. CodePilot checks `GET /api/version`.

**"Anthropic API: NOT supported"** — your Ollama predates v0.14.0. Update from
<https://ollama.com/download>; nothing else will work until you do.

**"Model status: Missing"** — the dashboard shows the exact command
(`ollama pull qwen3-coder:30b`). CodePilot will never start an 18 GB download on
its own. If you have a different Qwen tag installed, the dashboard lists it and
you can select it on the Models page.

**Sessions time out** — raise `model_timeout` in Settings. A 30B model on a first,
cold, long-context request can take a while before the first token appears.

**Ollama becomes unresponsive** — check whether the compatibility proxy is off.
That is the failure mode ollama/ollama#13949 describes.

**The model ignores tools or loops** — this is a model-capability limit, not a
wiring problem. Local 30B models are meaningfully weaker at long agentic tool
chains than frontier models. Smaller, more specific tasks work far better. You
can verify the wiring itself independently with `docs/VERIFY.md`.

## Using a different backend later

`server/codepilot/providers/` defines a `ModelProvider` interface with three
methods: `health()`, `list_models()` and `claude_env()`. Anything that can speak
the Anthropic Messages API — the Claude API itself, an OpenAI-compatible gateway
in front of a translator, Agent Factory, another local runtime — becomes a new
class plus one line in the `PROVIDERS` registry. Nothing outside that package
mentions Ollama or `qwen3-coder`.
