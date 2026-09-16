"""Authentication, pairing and filesystem containment.

The mobile app can indirectly cause file edits and shell commands on the PC, so
every entry point is authenticated and every path is checked against the project
allowlist. There is no anonymous access and no default credential.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import Database

PAIRING_TTL_SECONDS = 300  # a pairing token is valid for 5 minutes, single use


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthError(Exception):
    """Raised for anything an unauthenticated caller must not distinguish."""


@dataclass
class PairingToken:
    token: str
    created_at: float
    used: bool = False

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.created_at > PAIRING_TTL_SECONDS


class PairingManager:
    """One-time pairing tokens. Held in memory only — a restart invalidates them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, PairingToken] = {}

    def issue(self) -> PairingToken:
        with self._lock:
            self._prune()
            token = PairingToken(token=secrets.token_urlsafe(32), created_at=time.time())
            self._tokens[token.token] = token
            return token

    def redeem(self, raw: str) -> None:
        """Consume a pairing token or raise AuthError. Constant-time compare."""
        with self._lock:
            self._prune()
            match = None
            for candidate in self._tokens.values():
                if hmac.compare_digest(candidate.token, raw):
                    match = candidate
                    break
            if match is None or match.used or match.expired():
                raise AuthError("pairing token is invalid, already used, or expired")
            match.used = True
            del self._tokens[match.token]

    def revoke_all(self) -> None:
        with self._lock:
            self._tokens.clear()

    def active(self) -> list[PairingToken]:
        with self._lock:
            self._prune()
            return list(self._tokens.values())

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, v in self._tokens.items() if v.expired(now) or v.used]:
            del self._tokens[key]


class DeviceAuth:
    """Bearer-token auth for paired devices."""

    def __init__(self, db: Database):
        self.db = db

    def register(self, name: str) -> tuple[dict, str]:
        """Create a device credential. The raw token is returned exactly once."""
        raw = secrets.token_urlsafe(48)
        device = self.db.add_device(str(uuid.uuid4()), name.strip() or "Unnamed device",
                                    hash_token(raw))
        return device, raw

    def authenticate(self, raw_token: str | None) -> dict:
        if not raw_token:
            raise AuthError("missing credential")
        device = self.db.device_by_token_hash(hash_token(raw_token))
        if device is None:
            raise AuthError("unknown or revoked credential")
        self.db.touch_device(device["id"])
        return device


def extract_bearer(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


# --------------------------------------------------------------------------
# Filesystem containment
# --------------------------------------------------------------------------

class PathNotAllowed(Exception):
    pass


def normalize_project_path(raw: str) -> Path:
    """Resolve a user-supplied project root to a real, existing directory."""
    if not raw or not raw.strip():
        raise PathNotAllowed("path is empty")
    path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
    if not path.is_absolute():
        raise PathNotAllowed("project path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise PathNotAllowed(f"path does not exist: {raw}") from exc
    if not resolved.is_dir():
        raise PathNotAllowed(f"path is not a directory: {raw}")
    return resolved


def ensure_within(root: str | Path, candidate: str | Path) -> Path:
    """Return the resolved candidate, or raise if it escapes ``root``.

    Resolving both sides means ``..`` segments and symlinks that point outside
    the project are rejected, not just literal ``..`` in the string.
    """
    root_resolved = Path(root).resolve()
    target = Path(candidate)
    if not target.is_absolute():
        target = root_resolved / target
    try:
        resolved = target.resolve()
    except OSError as exc:  # pragma: no cover - platform dependent
        raise PathNotAllowed(f"cannot resolve path: {candidate}") from exc
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise PathNotAllowed(f"path escapes the project root: {candidate}")
    return resolved


def resolve_in_allowlist(db: Database, project_id: str, relative: str) -> Path:
    """Resolve ``relative`` inside a registered project, or raise."""
    project = db.get_project(project_id)
    if project is None:
        raise PathNotAllowed("unknown project")
    return ensure_within(project["path"], relative)
