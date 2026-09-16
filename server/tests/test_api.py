"""API surface: auth gating, pairing flow, project allowlist, sessions."""

from __future__ import annotations

import pytest


def test_every_data_endpoint_requires_auth(client):
    for method, path in [
        ("get", "/api/status"), ("get", "/api/projects"), ("get", "/api/sessions"),
        ("get", "/api/models"), ("get", "/api/approvals"),
        ("post", "/api/sessions"),
    ]:
        kwargs = {"json": {}} if method == "post" else {}
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}"


def test_health_is_public_but_reveals_nothing(client):
    body = client.get("/api/health").json()
    assert body["auth_required"] is True
    assert set(body) == {"service", "version", "auth_required"}


def test_pairing_flow_issues_a_working_credential(client):
    issued = client.post("/api/pairing/token").json()
    assert issued["token"]
    assert "qr_payload" in issued

    resp = client.post("/api/pair", json={"token": issued["token"], "device_name": "Pixel 8"})
    assert resp.status_code == 200
    token = resp.json()["device_token"]

    assert client.get("/api/projects", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # ...and the pairing token cannot be replayed.
    assert client.post("/api/pair", json={"token": issued["token"]}).status_code == 401


def test_bad_device_token_is_rejected(client, paired):
    resp = client.get("/api/projects", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_revoked_device_loses_access(client, paired):
    device_id = client.get("/api/devices").json()["devices"][0]["id"]
    client.delete(f"/api/devices/{device_id}")
    assert client.get("/api/projects").status_code == 401


def test_project_must_exist_on_disk(client, paired, tmp_path):
    resp = client.post("/api/projects",
                       json={"name": "Ghost", "path": str(tmp_path / "nope")})
    assert resp.status_code == 400
    assert "does not exist" in resp.json()["detail"]


def test_relative_project_path_rejected(client, paired):
    resp = client.post("/api/projects", json={"name": "Rel", "path": "some/where"})
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"]


def test_project_crud_and_git_status(client, paired, git_project):
    created = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)})
    assert created.status_code == 200
    project = created.json()["project"]
    assert project["git"]["is_repo"] is True
    assert project["git"]["branch"] == "main"
    assert project["git"]["clean"] is True

    # duplicates rejected
    assert client.post("/api/projects",
                       json={"name": "Dup", "path": str(git_project)}).status_code == 409

    (git_project / "calc.py").write_text("def add(a, b):\n    return a + b  # touched\n")
    (git_project / "new_file.py").write_text("x = 1\n")
    git = client.get(f"/api/projects/{project['id']}/git").json()["git"]
    assert git["clean"] is False
    paths = {f["path"]: f["status"] for f in git["files"]}
    assert paths["calc.py"] == "modified"
    assert paths["new_file.py"] == "untracked"

    changes = client.get(f"/api/projects/{project['id']}/changes").json()
    assert {f["path"] for f in changes["files"]} == {"calc.py", "new_file.py"}

    diff = client.get(f"/api/projects/{project['id']}/diff",
                      params={"path": "calc.py"}).json()["diff"]
    assert "# touched" in diff

    untracked_diff = client.get(f"/api/projects/{project['id']}/diff",
                                params={"path": "new_file.py"}).json()["diff"]
    assert "+x = 1" in untracked_diff

    assert client.delete(f"/api/projects/{project['id']}").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []


def test_diff_path_cannot_escape_project(client, paired, git_project, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("classified")
    project = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)}).json()["project"]
    for attempt in ["../secret.txt", str(secret), "../../etc/passwd"]:
        resp = client.get(f"/api/projects/{project['id']}/diff", params={"path": attempt})
        assert resp.status_code == 403, attempt


def test_session_requires_known_project(client, paired):
    resp = client.post("/api/sessions", json={"project_id": "nope", "prompt": "hi"})
    assert resp.status_code == 400
    assert "unknown project" in resp.json()["detail"]


def test_session_rejects_empty_prompt(client, paired, git_project):
    project = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)}).json()["project"]
    resp = client.post("/api/sessions", json={"project_id": project["id"], "prompt": "   "})
    assert resp.status_code in (400, 422)


def test_session_launch_failure_is_reported_not_faked(client, paired, git_project, store):
    """A missing Claude Code binary must surface as a real, explained failure."""
    store.update({"claude_binary": "definitely-not-installed-xyz"})
    project = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)}).json()["project"]
    resp = client.post("/api/sessions",
                       json={"project_id": project["id"], "prompt": "do something"})
    assert resp.status_code == 400
    assert "not found on PATH" in resp.json()["detail"]

    sessions = client.get("/api/sessions").json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "failed"
    events = client.get(f"/api/sessions/{sessions[0]['id']}/events").json()["events"]
    assert any(e["type"] == "session.failed" for e in events)


def test_unknown_session_is_404(client, paired):
    assert client.get("/api/sessions/does-not-exist").status_code == 404
    assert client.post("/api/sessions/does-not-exist/stop").status_code == 404


def test_settings_validation(client, paired):
    assert client.put("/api/settings", json={"port": 99999}).status_code == 400
    assert client.put("/api/settings", json={"ollama_url": "ftp://x"}).status_code == 400
    assert client.put("/api/settings", json={"context_length": 10}).status_code == 400

    ok = client.put("/api/settings", json={"bind_mode": "private", "context_length": 65536})
    assert ok.status_code == 200
    assert ok.json()["restart_required"] is True
    assert ok.json()["settings"]["context_length"] == 65536


def test_settings_never_leak_secrets(client, paired):
    body = client.get("/api/settings").json()["settings"]
    for secret in ("server_secret", "llm_token", "internal_token"):
        assert secret not in body


def test_internal_approval_endpoint_needs_the_internal_token(client, paired):
    resp = client.post("/internal/approvals/request",
                       json={"session_id": "x", "tool_name": "Bash", "tool_input": {}})
    assert resp.status_code == 401
