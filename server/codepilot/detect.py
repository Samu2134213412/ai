"""Live detection of Claude Code, Git, Ollama, models, Tailscale and addresses.

Everything here reports what is actually on the machine. Nothing is stubbed, and
a missing component is reported as missing with an actionable remedy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field

import httpx

CLAUDE_MIN_NOTE = "Install with: npm install -g @anthropic-ai/claude-code"
OLLAMA_MIN_VERSION = (0, 14, 0)


@dataclass
class ComponentStatus:
    name: str
    available: bool
    version: str | None = None
    detail: str | None = None
    remedy: str | None = None
    extra: dict = field(default_factory=dict)


async def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        return 127, "", str(exc)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", f"timed out after {timeout}s"
    return proc.returncode or 0, out.decode(errors="replace").strip(), err.decode(errors="replace").strip()


def _which(binary: str) -> str | None:
    return shutil.which(binary)


# --------------------------------------------------------------------- claude
async def detect_claude(binary: str = "claude") -> ComponentStatus:
    path = _which(binary) or (binary if os.path.isabs(binary) and os.path.exists(binary) else None)
    if path is None:
        return ComponentStatus("Claude Code", False,
                               detail=f"'{binary}' not found on PATH", remedy=CLAUDE_MIN_NOTE)
    code, out, err = await _run([path, "--version"])
    if code != 0:
        return ComponentStatus("Claude Code", False, detail=err or out,
                               remedy="Run `claude doctor` to diagnose the installation")
    version = (re.search(r"(\d+\.\d+\.\d+)", out) or [None, None])[1] if out else None
    return ComponentStatus("Claude Code", True, version=version or out,
                           extra={"path": path})


# ------------------------------------------------------------------------ git
async def detect_git() -> ComponentStatus:
    path = _which("git")
    if path is None:
        return ComponentStatus("Git", False, detail="'git' not found on PATH",
                               remedy="Install Git from https://git-scm.com/downloads")
    code, out, err = await _run([path, "--version"])
    if code != 0:
        return ComponentStatus("Git", False, detail=err or out)
    version = (re.search(r"(\d+\.\d+\.\d+)", out) or [None, None])[1]
    return ComponentStatus("Git", True, version=version, extra={"path": path})


# --------------------------------------------------------------------- ollama
def _parse_version(text: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(g) for g in m.groups()) if m else None


async def detect_ollama(base_url: str, timeout: float = 5.0) -> ComponentStatus:
    url = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            ver_resp = await client.get(f"{url}/api/version")
            ver_resp.raise_for_status()
            version = ver_resp.json().get("version", "unknown")
            tags_resp = await client.get(f"{url}/api/tags")
            tags_resp.raise_for_status()
            models = [m.get("name") for m in tags_resp.json().get("models", []) if m.get("name")]
    except httpx.ConnectError:
        return ComponentStatus(
            "Ollama", False, detail=f"no server reachable at {url}",
            remedy="Start Ollama (`ollama serve`) and check OLLAMA_URL in Settings")
    except httpx.HTTPError as exc:
        return ComponentStatus("Ollama", False, detail=f"{type(exc).__name__}: {exc}",
                               remedy="Check that OLLAMA_URL points at an Ollama server")

    parsed = _parse_version(version)
    detail = None
    remedy = None
    if parsed and parsed < OLLAMA_MIN_VERSION:
        detail = (f"Ollama {version} has no Anthropic-compatible /v1/messages endpoint "
                  f"(added in {'.'.join(map(str, OLLAMA_MIN_VERSION))})")
        remedy = "Update Ollama: https://ollama.com/download"
    return ComponentStatus("Ollama", True, version=version, detail=detail, remedy=remedy,
                           extra={"models": models, "url": url,
                                  "anthropic_api": bool(parsed and parsed >= OLLAMA_MIN_VERSION)})


def model_status(ollama: ComponentStatus, wanted: str) -> ComponentStatus:
    """Is the configured model actually pulled? Never triggers a download."""
    if not ollama.available:
        return ComponentStatus("Model", False, version=wanted,
                               detail="cannot check while Ollama is offline",
                               remedy=ollama.remedy)
    installed = ollama.extra.get("models", [])
    if wanted in installed:
        return ComponentStatus("Model", True, version=wanted, extra={"installed": installed})
    # `qwen3-coder:30b` also satisfies a bare `qwen3-coder` request and vice versa.
    base = wanted.split(":")[0]
    near = [m for m in installed if m.split(":")[0] == base]
    detail = f"'{wanted}' is not pulled"
    if near:
        detail += f" (related tags present: {', '.join(near)})"
    return ComponentStatus(
        "Model", False, version=wanted, detail=detail,
        remedy=f"ollama pull {wanted}",
        extra={"installed": installed, "near_matches": near},
    )


# ------------------------------------------------------------------ addresses
def _is_usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified)


def lan_addresses() -> list[str]:
    """Best-effort local IPv4 addresses, most-likely-primary first."""
    found: list[str] = []
    # The UDP-connect trick reveals the interface used for outbound traffic.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found:
                found.append(ip)
    except socket.gaierror:
        pass
    return [ip for ip in found if _is_usable(ip)]


async def detect_tailscale() -> ComponentStatus:
    path = _which("tailscale")
    if path is None:
        return ComponentStatus(
            "Tailscale", False, detail="'tailscale' not found on PATH",
            remedy="Install Tailscale from https://tailscale.com/download to reach "
                   "this PC from outside your home network")
    code, out, err = await _run([path, "status", "--json"], timeout=10)
    if code != 0:
        return ComponentStatus("Tailscale", False, detail=err or out,
                               remedy="Run `tailscale up` and sign in")
    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        return ComponentStatus("Tailscale", False, detail="could not parse `tailscale status --json`")

    backend = status.get("BackendState", "Unknown")
    self_node = status.get("Self") or {}
    ips = [ip for ip in (self_node.get("TailscaleIPs") or []) if _is_usable(ip)]
    dns_name = (self_node.get("DNSName") or "").rstrip(".")
    if backend != "Running":
        return ComponentStatus("Tailscale", False, detail=f"backend state: {backend}",
                               remedy="Run `tailscale up` and sign in")
    return ComponentStatus("Tailscale", True, version=status.get("Version"),
                           extra={"ips": ips, "dns_name": dns_name, "magic_dns": bool(dns_name)})


async def gather_environment(settings) -> dict:
    """One shot of everything the dashboard and phone home screen display."""
    claude, git, ollama, tailscale = await asyncio.gather(
        detect_claude(settings.claude_binary),
        detect_git(),
        detect_ollama(settings.ollama_url),
        detect_tailscale(),
    )
    model = model_status(ollama, settings.ollama_model)
    return {
        "claude": asdict(claude),
        "git": asdict(git),
        "ollama": asdict(ollama),
        "model": asdict(model),
        "tailscale": asdict(tailscale),
        "addresses": server_addresses(settings, tailscale),
        "settings": settings.public_fields(),
    }


def server_addresses(settings, tailscale: ComponentStatus | None = None) -> list[dict]:
    """Every address the phone could plausibly use, labelled by reachability."""
    port = settings.port
    out: list[dict] = [{
        "kind": "local", "host": "127.0.0.1", "port": port,
        "url": f"http://127.0.0.1:{port}",
        "note": "this PC only",
    }]
    if settings.bind_mode == "private":
        for ip in lan_addresses():
            out.append({"kind": "lan", "host": ip, "port": port,
                        "url": f"http://{ip}:{port}", "note": "same Wi-Fi network"})
        if tailscale and tailscale.available:
            for ip in tailscale.extra.get("ips", []):
                out.append({"kind": "tailscale", "host": ip, "port": port,
                            "url": f"http://{ip}:{port}",
                            "note": "anywhere, via your Tailscale network"})
            dns_name = tailscale.extra.get("dns_name")
            if dns_name:
                out.append({"kind": "tailscale", "host": dns_name, "port": port,
                            "url": f"http://{dns_name}:{port}",
                            "note": "MagicDNS name, anywhere via Tailscale"})
    return out


def check_subprocess(cmd: list[str], cwd: str | None = None, timeout: float = 15.0):
    """Blocking helper for the few places where sync is simpler (git)."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
