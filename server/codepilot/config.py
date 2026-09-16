"""Persistent configuration for CodePilot Remote.

Config and secrets live outside the repository (``~/.codepilot`` by default, or
``$CODEPILOT_HOME``) so nothing sensitive can be committed by accident.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

DEFAULT_MODEL = "qwen3-coder:30b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

#: Context sizes offered in the UI. 32K is the default because a 30B model at
#: Q4 already occupies most of a 24 GB card; 256K is intentionally absent.
CONTEXT_CHOICES = [8192, 16384, 32768, 65536]

BIND_LOCAL = "local"      # 127.0.0.1 — dashboard only, phone cannot reach it
BIND_PRIVATE = "private"  # 0.0.0.0 — reachable over LAN and Tailscale
BIND_CHOICES = [BIND_LOCAL, BIND_PRIVATE]

APPROVAL_MODES = ["manual", "acceptEdits", "plan"]


def config_home() -> Path:
    override = os.environ.get("CODEPILOT_HOME")
    return Path(override) if override else Path.home() / ".codepilot"


@dataclass
class Settings:
    # --- networking -------------------------------------------------------
    bind_mode: str = BIND_LOCAL
    port: int = 8765

    # --- model provider ---------------------------------------------------
    provider: str = "ollama"
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_model: str = DEFAULT_MODEL
    context_length: int = 32768
    model_timeout: int = 600

    #: Sit between Claude Code and Ollama to answer /v1/messages/count_tokens
    #: locally. Works around ollama/ollama#13949. See docs/OLLAMA.md.
    compat_proxy_enabled: bool = True

    # --- claude code ------------------------------------------------------
    claude_binary: str = "claude"
    default_permission_mode: str = "manual"
    #: Seconds an approval request waits on the phone before auto-denying.
    approval_timeout: int = 300

    # --- secrets (generated, never committed) -----------------------------
    server_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    llm_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    internal_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))

    # ------------------------------------------------------------------ io
    @classmethod
    def _known(cls) -> set[str]:
        return {f.name for f in fields(cls)}

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_home() / "config.json"
        if not path.exists():
            settings = cls()
            settings.save(path)
            return settings
        raw = json.loads(path.read_text("utf-8"))
        known = cls._known()
        settings = cls(**{k: v for k, v in raw.items() if k in known})
        # A config written by an older version may be missing new secrets.
        if not raw.keys() >= known:
            settings.save(path)
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or config_home() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), "utf-8")
        tmp.replace(path)
        _restrict(path)

    # -------------------------------------------------------------- helpers
    def host(self) -> str:
        return "0.0.0.0" if self.bind_mode == BIND_PRIVATE else "127.0.0.1"

    def public_fields(self) -> dict:
        """Everything except secrets — this is what the API hands out."""
        secret_names = {"server_secret", "llm_token", "internal_token"}
        return {k: v for k, v in asdict(self).items() if k not in secret_names}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.bind_mode not in BIND_CHOICES:
            errors.append(f"bind_mode must be one of {BIND_CHOICES}")
        if not 1 <= self.port <= 65535:
            errors.append("port must be between 1 and 65535")
        if not self.ollama_url.startswith(("http://", "https://")):
            errors.append("ollama_url must start with http:// or https://")
        if self.context_length < 2048:
            errors.append("context_length must be at least 2048")
        if self.model_timeout < 10:
            errors.append("model_timeout must be at least 10 seconds")
        if self.default_permission_mode not in APPROVAL_MODES:
            errors.append(f"default_permission_mode must be one of {APPROVAL_MODES}")
        return errors


def _restrict(path: Path) -> None:
    """Best-effort 0600. Windows ignores POSIX modes; that is acceptable."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


class SettingsStore:
    """Thread-safe holder so the running app sees live setting edits."""

    def __init__(self, path: Path | None = None):
        self.path = path or config_home() / "config.json"
        self._lock = threading.Lock()
        self._settings = Settings.load(self.path)

    @property
    def current(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, changes: dict) -> Settings:
        with self._lock:
            known = Settings._known() - {"server_secret", "llm_token", "internal_token"}
            merged = asdict(self._settings)
            merged.update({k: v for k, v in changes.items() if k in known})
            candidate = Settings(**merged)
            errors = candidate.validate()
            if errors:
                raise ValueError("; ".join(errors))
            candidate.save(self.path)
            self._settings = candidate
            return candidate
