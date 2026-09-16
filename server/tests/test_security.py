"""Authentication, pairing and filesystem containment."""

from __future__ import annotations

import time

import pytest

from codepilot import security
from codepilot.security import (AuthError, PairingManager, PathNotAllowed, ensure_within,
                                extract_bearer, normalize_project_path)


def test_pairing_token_is_single_use():
    manager = PairingManager()
    token = manager.issue()
    manager.redeem(token.token)
    with pytest.raises(AuthError):
        manager.redeem(token.token)


def test_pairing_token_expires(monkeypatch):
    manager = PairingManager()
    token = manager.issue()
    monkeypatch.setattr(time, "time", lambda: token.created_at + security.PAIRING_TTL_SECONDS + 1)
    with pytest.raises(AuthError):
        manager.redeem(token.token)


def test_unknown_pairing_token_rejected():
    manager = PairingManager()
    manager.issue()
    with pytest.raises(AuthError):
        manager.redeem("not-a-real-token")


def test_extract_bearer():
    assert extract_bearer("Bearer abc123") == "abc123"
    assert extract_bearer("bearer abc123") == "abc123"
    assert extract_bearer("Basic abc123") is None
    assert extract_bearer(None) is None
    assert extract_bearer("Bearer") is None


def test_ensure_within_allows_child(tmp_path):
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "app.py"
    target.write_text("x = 1")
    assert ensure_within(tmp_path, "src/app.py") == target.resolve()


@pytest.mark.parametrize("attempt", [
    "../outside.txt",
    "src/../../outside.txt",
    "/etc/passwd",
    "src/../../../etc/hosts",
])
def test_ensure_within_blocks_escape(tmp_path, attempt):
    (tmp_path / "src").mkdir()
    with pytest.raises(PathNotAllowed):
        ensure_within(tmp_path, attempt)


def test_ensure_within_blocks_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    project = tmp_path / "project"
    project.mkdir()
    try:
        (project / "link").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/user")
    with pytest.raises(PathNotAllowed):
        ensure_within(project, "link/secret.txt")


def test_normalize_project_path_requires_existing_dir(tmp_path):
    assert normalize_project_path(str(tmp_path)) == tmp_path.resolve()
    with pytest.raises(PathNotAllowed):
        normalize_project_path(str(tmp_path / "missing"))
    with pytest.raises(PathNotAllowed):
        normalize_project_path("relative/path")
    with pytest.raises(PathNotAllowed):
        normalize_project_path("")


def test_normalize_project_path_rejects_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(PathNotAllowed):
        normalize_project_path(str(f))


def test_device_token_is_hashed_at_rest(db):
    auth = security.DeviceAuth(db)
    device, raw = auth.register("Pixel")
    stored = db.query_one("SELECT token_hash FROM devices WHERE id = ?", (device["id"],))
    assert stored["token_hash"] != raw
    assert stored["token_hash"] == security.hash_token(raw)
    assert auth.authenticate(raw)["id"] == device["id"]


def test_revoked_device_cannot_authenticate(db):
    auth = security.DeviceAuth(db)
    device, raw = auth.register("Pixel")
    db.revoke_device(device["id"])
    with pytest.raises(AuthError):
        auth.authenticate(raw)
