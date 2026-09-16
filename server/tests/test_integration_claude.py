"""End-to-end tests that launch a REAL Claude Code process through the bridge.

Opt-in, because they need a working Claude Code installation and spend model
tokens::

    CODEPILOT_LIVE_CLAUDE=1 pytest tests/test_integration_claude.py -v -s

Unlike the rest of the suite these run against a real uvicorn server on a real
port, because the approval path depends on Claude Code spawning our MCP server
as a child process which then calls back over loopback HTTP. A TestClient has no
port, so it cannot exercise that.

What they prove, against a throwaway git repo (never a real project):

* Claude Code receives the task and starts in the right working directory
* the CodePilot MCP approval server is loaded and reaches "connected"
* Claude Code inspects files and runs tools
* typed events reach the backend and are persisted, gapless and in order
* file changes really happen on disk
* the session reaches a terminal status and the diff is retrievable
* an approval request raised through the real MCP child reaches the phone API,
  and the phone's decision is what Claude Code gets back

``CODEPILOT_LIVE_MODEL`` overrides the model. On the Windows PC set
``CODEPILOT_LIVE_USE_OLLAMA=1`` and ``CODEPILOT_LIVE_MODEL=qwen3-coder:30b`` to
run the same tests against the local model; see docs/VERIFY.md.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from codepilot import events as E

LIVE = os.environ.get("CODEPILOT_LIVE_CLAUDE") == "1"
MODEL = os.environ.get("CODEPILOT_LIVE_MODEL", "claude-haiku-4-5-20251001")
USE_LOCAL_PROVIDER = os.environ.get("CODEPILOT_LIVE_USE_OLLAMA") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set CODEPILOT_LIVE_CLAUDE=1 to run the real Claude Code tests")

TASK = ("Add a function subtract(a, b) to calc.py that returns a - b, and add a "
        "unit test for it in test_calc.py. Keep the change small.")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveServer:
    """A real uvicorn server plus an authenticated HTTP client for it."""

    def __init__(self, base_url: str, client, store, db, port: int):
        self.base_url = base_url
        self.client = client
        self.store = store
        self.db = db
        self.port = port


@pytest.fixture
def live(home, tmp_path):
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed")
    import httpx
    import uvicorn

    from codepilot.app import create_app
    from codepilot.config import SettingsStore
    from codepilot.db import Database

    port = _free_port()
    store = SettingsStore(home / "config.json")
    changes = {"port": port, "approval_timeout": 90}
    if not USE_LOCAL_PROVIDER:
        # No Ollama on this machine: point Claude Code at whatever credential it
        # already has, so the *bridge* can still be exercised.
        changes["compat_proxy_enabled"] = False
    store.update(changes)

    if not USE_LOCAL_PROVIDER:
        from codepilot.providers.ollama import OllamaProvider
        original_env = OllamaProvider.claude_env
        OllamaProvider.claude_env = lambda self, base_url_override=None: {}

    db = Database(home / "live.db")
    app = create_app(store, db)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/api/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        pytest.fail("the live server never became reachable")

    client = httpx.Client(base_url=base_url, timeout=60)
    token = client.post("/api/pairing/token").json()["token"]
    device_token = client.post(
        "/api/pair", json={"token": token, "device_name": "Test Phone"}
    ).json()["device_token"]
    client.headers["Authorization"] = f"Bearer {device_token}"

    try:
        yield LiveServer(base_url, client, store, db, port)
    finally:
        client.close()
        server.should_exit = True
        thread.join(timeout=15)
        if not USE_LOCAL_PROVIDER:
            OllamaProvider.claude_env = original_env


def _wait_for_terminal(client, session_id: str, timeout: float = 540) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        status = client.get(f"/api/sessions/{session_id}").json()["session"]["status"]
        if status != "running":
            return status
    return "running"


def _print_transcript(events) -> None:
    for event in events:
        payload = event["payload"]
        if event["type"] == E.TOOL_STARTED:
            print(f"  TOOL   {payload['tool_name']}")
        elif event["type"] == E.ASSISTANT_MESSAGE:
            print(f"  CLAUDE {payload['text'][:110]}")
        elif event["type"] == E.TEST_RESULT:
            print(f"  TESTS  {payload['summary']}")
        elif event["type"] == E.TOOL_APPROVAL_REQUIRED:
            print(f"  ASK    {payload['summary']}")
        elif event["type"] in (E.SESSION_FAILED, E.ERROR):
            print(f"  ERROR  {str(payload)[:300]}")


def test_real_claude_code_session(live, git_project):
    client = live.client

    # Stand in for a person tapping "Approve Once" on the phone. Without this the
    # requests Claude Code raises would sit unanswered until they time out.
    approved: list = []
    stop_watching = threading.Event()

    def approver() -> None:
        while not stop_watching.wait(0.4):
            try:
                pending = client.get("/api/approvals").json()["approvals"]
            except Exception:
                continue
            for card in pending:
                print(f"  PHONE  approving {card['tool_name']}: "
                      f"{card['tool_input'].get('command', card['tool_input'])}")
                client.post(f"/api/approvals/{card['id']}/decide", json={"approve": True})
                approved.append(card["id"])

    watcher = threading.Thread(target=approver, daemon=True)
    watcher.start()

    project = client.post("/api/projects",
                          json={"name": "Calc Demo", "path": str(git_project)}
                          ).json()["project"]

    created = client.post("/api/sessions", json={
        "project_id": project["id"], "prompt": TASK, "model": MODEL,
        "permission_mode": "acceptEdits"})
    assert created.status_code == 201, created.text
    session_id = created.json()["session"]["id"]

    status = _wait_for_terminal(client, session_id)
    stop_watching.set()
    watcher.join(timeout=5)
    print(f"\n--- session finished with status={status}, "
          f"{len(approved)} approval(s) granted from the phone ---")

    events = client.get(f"/api/sessions/{session_id}/events?limit=5000").json()["events"]
    _print_transcript(events)
    kinds = [e["type"] for e in events]

    # Gapless ordering is what reconnect-and-replay depends on.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert E.SESSION_STARTED in kinds
    assert status == "completed", f"last event: {events[-1] if events else None}"

    # Claude Code loaded our approval MCP server.
    init = next(e["payload"] for e in events
                if e["type"] == E.SESSION_STATUS and e["payload"].get("phase") == "initialized")
    assert {"name": "codepilot", "status": "connected"} in init["mcp_servers"], init["mcp_servers"]
    assert init["cwd"] == str(git_project)

    tools_used = {e["payload"]["tool_name"] for e in events if e["type"] == E.TOOL_STARTED}
    assert tools_used, "no tool activity was streamed"
    print(f"  tools used: {sorted(tools_used)}")

    # Where Claude Code did ask, the phone's approval must have been honoured.
    asked = [e for e in events if e["type"] == E.TOOL_APPROVAL_REQUIRED]
    if asked:
        resolutions = [e["payload"]["decision"] for e in events
                       if e["type"] == E.TOOL_APPROVAL_RESOLVED]
        assert "approved" in resolutions, resolutions
        print(f"  {len(asked)} approval request(s) reached the phone and were granted")

    # Real edits landed on disk.
    assert "def subtract" in (git_project / "calc.py").read_text()

    changes = client.get(f"/api/sessions/{session_id}/changes").json()
    assert changes["files"] and changes["total_added"] > 0
    assert E.FILE_CHANGED in kinds

    diff = client.get(f"/api/projects/{project['id']}/diff",
                      params={"path": "calc.py"}).json()["diff"]
    assert "subtract" in diff

    # Independent verification that the resulting code actually works.
    verify = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=git_project,
                            capture_output=True, text=True)
    print("  independent pytest:", (verify.stdout.strip().splitlines() or ["(none)"])[-1])
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_real_mcp_approval_round_trip(live, git_project):
    """The real MCP child -> backend -> phone -> Claude Code decision path.

    This drives the same MCP server process that Claude Code spawns, with the
    same environment the bridge gives it, against the real running backend. It
    asserts the phone sees an approval card and that the phone's answer is what
    comes back out of the MCP tool.

    (Whether Claude Code *chooses* to ask for a given operation is decided by
    Claude Code's own permission model and the user's settings files — CodePilot
    deliberately does not override that, so this test drives the callback
    directly rather than trying to force a prompt.)
    """
    client = live.client
    project = client.post("/api/projects",
                          json={"name": "Calc Demo", "path": str(git_project)}
                          ).json()["project"]
    session = live.db.create_session(
        id="approval-probe", project_id=project["id"], prompt="probe",
        status="running", model=MODEL, permission_mode="manual")

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "CODEPILOT_BACKEND_URL": live.base_url,
        "CODEPILOT_INTERNAL_TOKEN": live.store.current.internal_token,
        "CODEPILOT_SESSION_ID": session["id"],
        "CODEPILOT_APPROVAL_TIMEOUT": "60",
    }
    proc = subprocess.Popen([sys.executable, "-m", "codepilot.bridge.permission_mcp"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)

    def rpc(payload):
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    try:
        assert rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {}})["result"]["serverInfo"]["name"] == "codepilot"

        decisions: dict = {}

        def call_tool():
            reply = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "approve", "arguments": {
                             "tool_name": "Bash",
                             "input": {"command": "npm install left-pad"}}}})
            decisions["result"] = json.loads(reply["result"]["content"][0]["text"])

        caller = threading.Thread(target=call_tool)
        caller.start()

        # The phone sees the card.
        deadline = time.time() + 30
        pending = []
        while time.time() < deadline and not pending:
            pending = client.get("/api/approvals").json()["approvals"]
            time.sleep(0.3)
        assert pending, "no approval request reached the phone API"
        card = pending[0]
        print(f"\n  phone was asked: {card['tool_name']} -> {card['tool_input']}")
        assert card["tool_input"]["command"] == "npm install left-pad"

        # The phone rejects it.
        client.post(f"/api/approvals/{card['id']}/decide",
                    json={"approve": False, "reason": "not from my phone, thanks"})
        caller.join(timeout=30)
        assert decisions["result"] == {"behavior": "deny",
                                       "message": "not from my phone, thanks"}

        events = live.db.get_events(session["id"])
        kinds = [e["type"] for e in events]
        assert E.TOOL_APPROVAL_REQUIRED in kinds
        assert E.TOOL_APPROVAL_RESOLVED in kinds
        assert live.db.get_approval(card["id"])["status"] == "rejected"

        # And an approval returns allow with the untouched input.
        def call_again():
            reply = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "approve", "arguments": {
                             "tool_name": "Bash", "input": {"command": "pytest -q"}}}})
            decisions["second"] = json.loads(reply["result"]["content"][0]["text"])

        caller = threading.Thread(target=call_again)
        caller.start()
        deadline = time.time() + 30
        pending = []
        while time.time() < deadline and not pending:
            pending = client.get("/api/approvals").json()["approvals"]
            time.sleep(0.3)
        assert pending
        client.post(f"/api/approvals/{pending[0]['id']}/decide", json={"approve": True})
        caller.join(timeout=30)
        assert decisions["second"] == {"behavior": "allow",
                                       "updatedInput": {"command": "pytest -q"}}
        print("  deny and allow both round-tripped correctly")
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)
