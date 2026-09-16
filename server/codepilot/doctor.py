"""``python -m codepilot --doctor`` — a staged end-to-end diagnosis.

``--check`` answers "is everything installed?". This answers the harder question
you actually have when something is wrong at 11pm with nobody to ask: **which
link in the chain is broken?**

It walks the chain in order and stops at the first failure, because every later
stage depends on the earlier ones:

    Claude Code → Git → Ollama reachable → Ollama speaks /v1/messages
    → the model is pulled → the model actually answers
    → Claude Code can reach the model through that endpoint
    → the phone can reach this PC

Each stage says what it proved and, on failure, exactly what to do next. Nothing
here downloads a model or changes any setting.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass

import httpx

from . import detect
from .providers import get_provider

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"

_MARK = {PASS: "✓", FAIL: "✗", WARN: "!", SKIP: "-"}


@dataclass
class Stage:
    name: str
    status: str
    proved: str = ""
    detail: str = ""
    fix: str = ""
    elapsed: float = 0.0

    @property
    def fatal(self) -> bool:
        return self.status == FAIL


def _fmt(stage: Stage, index: int, total: int) -> str:
    head = (f"[{index}/{total}] {_MARK[stage.status]} {stage.name}"
            f"{f'  ({stage.elapsed:.1f}s)' if stage.elapsed >= 0.1 else ''}")
    lines = [head]
    if stage.status == PASS and stage.proved:
        lines.append(f"        {stage.proved}")
    if stage.detail:
        for line in stage.detail.splitlines():
            lines.append(f"        {line}")
    if stage.fix:
        lines.append("")
        for line in stage.fix.splitlines():
            lines.append(f"        -> {line}")
    return "\n".join(lines)


async def _timed(coro):
    start = time.monotonic()
    stage = await coro
    stage.elapsed = time.monotonic() - start
    return stage


# --------------------------------------------------------------------- stages
async def stage_claude(settings) -> Stage:
    status = await detect.detect_claude(settings.claude_binary)
    if not status.available:
        return Stage("Claude Code is installed", FAIL, detail=status.detail or "",
                     fix=(status.remedy or "") + "\n"
                         "If it is installed somewhere unusual, set claude_binary in Settings "
                         "to its full path.")
    return Stage("Claude Code is installed", PASS,
                 proved=f"version {status.version} at {status.extra.get('path')}")


async def stage_git(settings) -> Stage:
    status = await detect.detect_git()
    if not status.available:
        return Stage("Git is installed", FAIL, detail=status.detail or "",
                     fix=status.remedy or "")
    return Stage("Git is installed", PASS, proved=f"version {status.version}")


async def stage_ollama_reachable(settings) -> Stage:
    status = await detect.detect_ollama(settings.ollama_url)
    if not status.available:
        return Stage("Ollama is running", FAIL, detail=status.detail or "",
                     fix=(status.remedy or "") + "\n"
                         "Check the Ollama tray icon, or run `ollama serve` in a terminal.")
    if not status.extra.get("anthropic_api"):
        return Stage("Ollama is running", FAIL,
                     detail=f"Ollama {status.version} is running, but it has no "
                            f"Anthropic-compatible /v1/messages endpoint.",
                     fix="Update Ollama to 0.14.0 or newer: https://ollama.com/download\n"
                         "Nothing further can work until this is done.")
    return Stage("Ollama is running", PASS,
                 proved=f"version {status.version} at {settings.ollama_url}, "
                        f"{len(status.extra.get('models', []))} model(s) installed")


async def stage_model_present(settings) -> Stage:
    status = await detect.detect_ollama(settings.ollama_url)
    model = detect.model_status(status, settings.ollama_model)
    if model.available:
        return Stage("The configured model is pulled", PASS,
                     proved=f"{settings.ollama_model} is installed")
    near = model.extra.get("near_matches") or []
    installed = model.extra.get("installed") or []
    fix = f"{model.remedy}\nThat is roughly 18 GB; CodePilot will never start it for you."
    if near:
        fix += ("\nOr switch to a tag you already have, on the Models page: "
                + ", ".join(near))
    elif installed:
        fix += "\nInstalled right now: " + ", ".join(installed[:8])
    return Stage("The configured model is pulled", FAIL, detail=model.detail or "", fix=fix)


async def stage_model_answers(settings) -> Stage:
    """The decisive test: does Ollama serve this model over /v1/messages?"""
    url = settings.ollama_url.rstrip("/") + "/v1/messages"
    payload = {
        "model": settings.ollama_model,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    }
    timeout = httpx.Timeout(max(60.0, float(settings.model_timeout)), connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers={
                "content-type": "application/json",
                "x-api-key": "ollama",
                "anthropic-version": "2023-06-01",
            })
    except httpx.TimeoutException:
        return Stage("The model answers over the Anthropic API", FAIL,
                     detail=f"no response within {settings.model_timeout}s",
                     fix="A 30B model can take a while to load into VRAM the first time.\n"
                         "Run `ollama run " + settings.ollama_model + "` once to warm it up, "
                         "then try again.\nIf it is still slow, raise model_timeout in Settings.")
    except httpx.HTTPError as exc:
        return Stage("The model answers over the Anthropic API", FAIL,
                     detail=f"{type(exc).__name__}: {exc}",
                     fix="Check that ollama_url in Settings points at your Ollama server.")

    if resp.status_code == 404:
        return Stage("The model answers over the Anthropic API", FAIL,
                     detail="Ollama returned 404 for /v1/messages",
                     fix="This Ollama build does not serve the Anthropic API. "
                         "Update to 0.14.0 or newer: https://ollama.com/download")
    if resp.status_code >= 400:
        body = resp.text[:400]
        return Stage("The model answers over the Anthropic API", FAIL,
                     detail=f"HTTP {resp.status_code}: {body}",
                     fix="If it mentions the model, check the exact tag on the Models page.")
    try:
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if isinstance(b, dict))
    except (json.JSONDecodeError, AttributeError):
        return Stage("The model answers over the Anthropic API", FAIL,
                     detail=f"unreadable response: {resp.text[:300]}")
    if not text.strip():
        return Stage("The model answers over the Anthropic API", WARN,
                     detail="the endpoint replied, but with no text content",
                     fix="Unusual but not fatal. Continue and see whether sessions work.")
    return Stage("The model answers over the Anthropic API", PASS,
                 proved=f"{settings.ollama_model} replied: {text.strip()[:60]!r}")


async def stage_context_window(settings) -> Stage:
    """Best-effort read of the window Ollama actually loaded the model with."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(settings.ollama_url.rstrip("/") + "/api/ps")
            resp.raise_for_status()
            running = resp.json().get("models", [])
    except httpx.HTTPError:
        return Stage("Ollama's context window", SKIP,
                     detail="could not read /api/ps on this Ollama version")

    match = next((m for m in running
                  if m.get("name") == settings.ollama_model
                  or m.get("model") == settings.ollama_model), None)
    if match is None:
        return Stage("Ollama's context window", SKIP,
                     detail="the model is not loaded right now, so its window is unknown")

    actual = match.get("context_length")
    if not actual:
        return Stage("Ollama's context window", SKIP,
                     detail="this Ollama version does not report context_length")
    if actual < settings.context_length:
        return Stage("Ollama's context window", WARN,
                     detail=f"Ollama loaded the model with {actual} tokens, but CodePilot "
                            f"is configured for {settings.context_length}.",
                     fix=f"Ollama's window is set on its own server process, not per request.\n"
                         f"Windows:  setx OLLAMA_CONTEXT_LENGTH {settings.context_length}\n"
                         f"then fully restart Ollama (quit the tray icon and reopen it).\n"
                         f"Until you do, the smaller number is what binds.")
    return Stage("Ollama's context window", PASS,
                 proved=f"loaded with {actual} tokens (CodePilot wants "
                        f"{settings.context_length})")


async def stage_claude_to_model(settings) -> Stage:
    """The end-to-end proof: Claude Code itself, thinking with the local model."""
    binary = shutil.which(settings.claude_binary)
    if binary is None:
        return Stage("Claude Code reaches the local model", SKIP,
                     detail="Claude Code was not found, so this cannot be tested")

    provider = get_provider(settings)
    env = dict(os.environ)
    for stale in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                  "ANTHROPIC_MODEL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        env.pop(stale, None)
    # Deliberately bypasses the compatibility proxy: this stage is about the
    # documented Claude Code -> Ollama contract, with nothing of ours in between.
    env.update(provider.claude_env())
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    timeout = max(90.0, float(settings.model_timeout))
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "--print", "--model", settings.ollama_model,
            "Reply with exactly: PONG",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    except OSError as exc:
        return Stage("Claude Code reaches the local model", FAIL,
                     detail=f"could not start Claude Code: {exc}")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return Stage("Claude Code reaches the local model", FAIL,
                     detail=f"Claude Code produced no answer within {timeout:.0f}s",
                     fix="If the previous stage passed, Ollama is fine and this is the\n"
                         "count_tokens hang (ollama/ollama#13949). Leave CodePilot's\n"
                         "compatibility proxy ON — sessions go through it and are unaffected.\n"
                         "See docs/OLLAMA.md.")

    stdout = out.decode(errors="replace").strip()
    stderr = err.decode(errors="replace").strip()
    if proc.returncode != 0:
        return Stage("Claude Code reaches the local model", FAIL,
                     detail=(stderr or stdout or f"exit code {proc.returncode}")[:600],
                     fix="Run `claude doctor` to check the installation itself.")
    if "PONG" not in stdout.upper():
        return Stage("Claude Code reaches the local model", WARN,
                     detail=f"answered, but not as asked: {stdout[:200]!r}",
                     fix="The connection works; the model simply did not follow a trivial\n"
                         "instruction. Expect it to struggle with long agentic tasks too.")
    return Stage("Claude Code reaches the local model", PASS,
                 proved=f"Claude Code answered {stdout[:40]!r} using {settings.ollama_model}")


async def stage_phone_reachable(settings) -> Stage:
    tailscale = await detect.detect_tailscale()
    addresses = detect.server_addresses(settings, tailscale)
    lan = [a for a in addresses if a["kind"] == "lan"]
    tail = [a for a in addresses if a["kind"] == "tailscale"]

    if settings.bind_mode != "private":
        return Stage("Your phone can reach this PC", FAIL,
                     detail="the server is bound to 127.0.0.1, so nothing outside this "
                            "machine can connect",
                     fix="Start with:  start.bat --bind-mode private\n"
                         "or change Network access in Settings and restart.")
    if not lan and not tail:
        return Stage("Your phone can reach this PC", WARN,
                     detail="no usable LAN or Tailscale address was found",
                     fix="Check that this PC is actually on a network.")

    parts = []
    if lan:
        parts.append("on the home Wi-Fi: " + ", ".join(a["url"] for a in lan))
    if tail:
        parts.append("from anywhere: " + ", ".join(a["url"] for a in tail))
    else:
        return Stage("Your phone can reach this PC", WARN,
                     proved="; ".join(parts),
                     detail="Tailscale is not set up, so this only works on the home Wi-Fi.",
                     fix="To use it from school, see docs/REMOTE_ACCESS.md.")
    return Stage("Your phone can reach this PC", PASS, proved="; ".join(parts))


STAGES = [
    stage_claude,
    stage_git,
    stage_ollama_reachable,
    stage_model_present,
    stage_model_answers,
    stage_context_window,
    stage_claude_to_model,
    stage_phone_reachable,
]


async def run(settings, stop_on_failure: bool = True) -> list[Stage]:
    """Run the chain. Later stages are skipped once an earlier one fails."""
    results: list[Stage] = []
    total = len(STAGES)
    failed = False
    for index, stage_fn in enumerate(STAGES, start=1):
        if failed and stop_on_failure:
            results.append(Stage(stage_fn.__name__, SKIP,
                                 detail="skipped: an earlier stage failed"))
            continue
        stage = await _timed(stage_fn(settings))
        results.append(stage)
        print(_fmt(stage, index, total), flush=True)
        print(flush=True)
        if stage.fatal:
            failed = True
    return results


def summarise(results: list[Stage]) -> bool:
    passed = sum(1 for r in results if r.status == PASS)
    failed = [r for r in results if r.status == FAIL]
    warned = [r for r in results if r.status == WARN]

    print("-" * 68)
    if not failed:
        print(f"All good — {passed} stage(s) passed"
              + (f", {len(warned)} warning(s)" if warned else "") + ".")
        print("Start the server and pair your phone: start.bat --bind-mode private")
        return True
    first = failed[0]
    print(f"Stopped at: {first.name}")
    if first.detail:
        print(f"  {first.detail.splitlines()[0]}")
    if first.fix:
        print("\nDo this next:")
        for line in first.fix.splitlines():
            print(f"  {line}")
    print("\nEverything after this point was skipped, because it depends on this stage.")
    return False
