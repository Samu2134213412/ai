from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codepilot.app import create_app  # noqa: E402
from codepilot.config import SettingsStore  # noqa: E402
from codepilot.db import Database  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    path = tmp_path / "cphome"
    path.mkdir()
    monkeypatch.setenv("CODEPILOT_HOME", str(path))
    return path


@pytest.fixture
def store(home):
    return SettingsStore(home / "config.json")


@pytest.fixture
def db(home):
    database = Database(home / "test.db")
    yield database
    database.close()


@pytest.fixture
def app(store, db):
    return create_app(store, db)


@pytest.fixture
def client(app):
    """A client that appears to come from the PC itself (loopback)."""
    from fastapi.testclient import TestClient
    with TestClient(app, client=("127.0.0.1", 45001)) as c:
        yield c


@pytest.fixture
def remote_client(app):
    """A client that appears to come from another host, i.e. the phone."""
    from fastapi.testclient import TestClient
    with TestClient(app, client=("192.168.178.42", 45002)) as c:
        yield c


@pytest.fixture
def paired(client):
    """A client with a real device token, obtained through real pairing."""
    token = client.post("/api/pairing/token").json()["token"]
    resp = client.post("/api/pair", json={"token": token, "device_name": "Test Phone"})
    assert resp.status_code == 200
    device_token = resp.json()["device_token"]
    client.headers.update({"Authorization": f"Bearer {device_token}"})
    return device_token


@pytest.fixture
def git_project(tmp_path):
    """A real throwaway git repo with one Python file."""
    import subprocess
    root = tmp_path / "demo-project"
    root.mkdir()
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    (root / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", "utf-8")
    for cmd in (["git", "init", "-q", "-b", "main"],
                ["git", "config", "user.email", "test@example.invalid"],
                ["git", "config", "user.name", "Test"],
                ["git", "add", "-A"],
                ["git", "commit", "-qm", "initial"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    return root
