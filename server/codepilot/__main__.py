"""Entry point: ``python -m codepilot``.

Starts the API, the WebSocket endpoint, the model gateway and the web dashboard
in a single process — one command, one terminal.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__, detect, doctor
from .app import create_app
from .config import BIND_CHOICES, BIND_PRIVATE, SettingsStore
from .providers import get_provider

BANNER = r"""
  ___         _     ___ _ _     _     ___                _
 / __|___  __| |___| _ (_) |___| |_  | _ \___ _ __  ___ | |_ ___
| (__/ _ \/ _` / -_)  _/ | / _ \  _| |   / -_) '  \/ _ \|  _/ -_)
 \___\___/\__,_\___|_| |_|_\___/\__| |_|_\___|_|_|_\___/ \__\___|
"""


def _mark(ok: bool) -> str:
    return "✓" if ok else "✗"


async def preflight(settings) -> bool:
    """Print the real status of every dependency. Never downloads anything."""
    env = await detect.gather_environment(settings)
    claude, git, ollama, model, tailscale = (
        env["claude"], env["git"], env["ollama"], env["model"], env["tailscale"])

    print("Environment")
    print(f"  {_mark(claude['available'])} Claude Code: "
          f"{'Available ' + (claude['version'] or '') if claude['available'] else 'MISSING'}")
    print(f"  {_mark(git['available'])} Git:         "
          f"{'Available ' + (git['version'] or '') if git['available'] else 'MISSING'}")
    print(f"  {_mark(ollama['available'])} Ollama:      "
          f"{'Online ' + (ollama['version'] or '') if ollama['available'] else 'OFFLINE'}"
          f"  ({settings.ollama_url})")
    print(f"  {_mark(model['available'])} Model:       {settings.ollama_model} — "
          f"{'Available' if model['available'] else 'MISSING'}")
    print(f"    Context: {settings.context_length} tokens · timeout {settings.model_timeout}s")
    print(f"  {_mark(tailscale['available'])} Tailscale:   "
          f"{'Connected' if tailscale['available'] else 'not available'}")

    problems = [c for c in (claude, git, ollama, model) if not c["available"]]
    for component in problems:
        if component.get("detail"):
            print(f"\n  ! {component['name']}: {component['detail']}")
        if component.get("remedy"):
            print(f"    -> {component['remedy']}")

    print("\nReachable at")
    for address in env["addresses"]:
        print(f"  {address['url']:<40} {address['note']}")
    if settings.bind_mode != BIND_PRIVATE:
        print("  (bound to 127.0.0.1 — your phone cannot reach this. "
              "Set network access to 'private' to allow LAN + Tailscale.)")

    # Claude Code is the only hard requirement to *start*; the rest are reported
    # live in the UI and can be fixed without restarting the server.
    return claude["available"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m codepilot",
                                     description="CodePilot Remote desktop server")
    parser.add_argument("--host", help="override the bind address for this run")
    parser.add_argument("--port", type=int, help="override the port for this run")
    parser.add_argument("--bind-mode", choices=BIND_CHOICES,
                        help="'local' = 127.0.0.1 only, 'private' = LAN + Tailscale")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="persist a setting, e.g. --set ollama_model=qwen3-coder:30b")
    parser.add_argument("--check", action="store_true",
                        help="run the quick environment check and exit")
    parser.add_argument("--doctor", action="store_true",
                        help="diagnose the whole chain step by step and exit — use this "
                             "when something is broken and you need to know which link")
    parser.add_argument("--version", action="version", version=f"CodePilot Remote {__version__}")
    args = parser.parse_args(argv)

    store = SettingsStore()

    changes: dict = {}
    for item in args.set:
        if "=" not in item:
            print(f"error: --set expects KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        if value.lower() in ("true", "false"):
            parsed: object = value.lower() == "true"
        elif value.isdigit():
            parsed = int(value)
        else:
            parsed = value
        changes[key.strip()] = parsed
    if args.bind_mode:
        changes["bind_mode"] = args.bind_mode
    if args.port:
        changes["port"] = args.port
    if changes:
        try:
            store.update(changes)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    settings = store.current
    print(BANNER)
    print(f"CodePilot Remote {__version__} — config: {store.path}\n")

    if args.doctor:
        print("Walking the chain from Claude Code all the way to your phone.")
        print("Nothing here downloads a model or changes a setting.\n")
        results = asyncio.run(doctor.run(settings))
        return 0 if doctor.summarise(results) else 1

    ok = asyncio.run(preflight(settings))
    if args.check:
        return 0 if ok else 1
    if not ok:
        print("\nClaude Code is required to run sessions. Fix the item above and try again.",
              file=sys.stderr)
        return 1

    provider = get_provider(settings)
    gateway = (f"http://127.0.0.1:{settings.port}/llm (CodePilot compatibility proxy)"
               if settings.compat_proxy_enabled else provider.upstream_url())
    print(f"\nClaude Code will use: {gateway}")
    print(f"Dashboard:            http://127.0.0.1:{settings.port}/\n")

    import uvicorn
    app = create_app(store)
    uvicorn.run(app, host=args.host or settings.host(), port=settings.port,
                log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
