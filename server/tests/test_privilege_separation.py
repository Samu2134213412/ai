"""A paired phone must not be able to widen its own access."""

from __future__ import annotations


def _pair(local_client, remote_client):
    token = local_client.post("/api/pairing/token").json()["token"]
    device_token = local_client.post(
        "/api/pair", json={"token": token, "device_name": "Phone"}).json()["device_token"]
    remote_client.headers.update({"Authorization": f"Bearer {device_token}"})
    return device_token


def test_phone_cannot_touch_admin_endpoints(client, remote_client, tmp_path):
    _pair(client, remote_client)
    forbidden = [
        ("post", "/api/pairing/token", None),
        ("delete", "/api/pairing/token", None),
        ("get", "/api/devices", None),
        ("get", "/api/settings", None),
        ("put", "/api/settings", {"bind_mode": "private"}),
        ("post", "/api/projects", {"name": "X", "path": str(tmp_path)}),
        ("get", "/api/status/local", None),
        ("get", "/api/projects/local", None),
        ("get", "/api/sessions/local", None),
        ("get", "/api/models/local", None),
    ]
    for method, path, body in forbidden:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(remote_client, method)(path, **kwargs)
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


def test_phone_cannot_add_or_delete_projects(client, remote_client, git_project):
    _pair(client, remote_client)
    project = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)}).json()["project"]
    # It can read the allowlist...
    assert remote_client.get("/api/projects").status_code == 200
    # ...but not change it.
    assert remote_client.delete(f"/api/projects/{project['id']}").status_code == 403


def test_phone_can_do_session_work(client, remote_client, git_project):
    """The phone keeps exactly the powers it needs: read state, drive sessions."""
    _pair(client, remote_client)
    client.post("/api/projects", json={"name": "Demo", "path": str(git_project)})
    for path in ["/api/projects", "/api/sessions", "/api/status", "/api/models",
                 "/api/approvals"]:
        assert remote_client.get(path).status_code == 200, path


def test_internal_approval_endpoint_is_loopback_only(client, remote_client):
    token = client.app.state.store.current.internal_token
    resp = remote_client.post(
        "/internal/approvals/request",
        headers={"x-codepilot-internal": token},
        json={"session_id": "x", "tool_name": "Bash", "tool_input": {}})
    assert resp.status_code == 403
