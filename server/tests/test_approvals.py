"""Tool approval: the phone answers, and silence denies."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest

from codepilot.bridge.approvals import ApprovalBroker, summarize
from codepilot.events import EventHub


@pytest.fixture
def broker_setup(db, git_project):
    db.add_project("p1", "Demo", str(git_project))
    db.create_session(id="s1", project_id="p1", prompt="x", status="running",
                      model="qwen3-coder:30b", permission_mode="manual")
    hub = EventHub(db)
    return db, hub


async def test_approve_returns_allow(broker_setup):
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=5)

    task = asyncio.create_task(broker.request("s1", "Bash", {"command": "npm install left-pad"}))
    await asyncio.sleep(0.05)

    pending = db.pending_approvals("s1")
    assert len(pending) == 1
    assert pending[0]["tool_name"] == "Bash"

    assert await broker.resolve(pending[0]["id"], approve=True) is True
    decision = await task
    assert decision["behavior"] == "allow"
    assert decision["updatedInput"] == {"command": "npm install left-pad"}
    assert db.get_approval(pending[0]["id"])["status"] == "approved"


async def test_reject_returns_deny_with_reason(broker_setup):
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=5)
    task = asyncio.create_task(broker.request("s1", "Bash", {"command": "rm -rf /"}))
    await asyncio.sleep(0.05)
    approval_id = db.pending_approvals("s1")[0]["id"]
    await broker.resolve(approval_id, approve=False, reason="absolutely not")
    decision = await task
    assert decision["behavior"] == "deny"
    assert decision["message"] == "absolutely not"


async def test_timeout_denies(broker_setup):
    """No answer from the phone must deny, never allow."""
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=0.2)
    decision = await broker.request("s1", "Bash", {"command": "curl evil.example"})
    assert decision["behavior"] == "deny"
    assert "denied" in decision["message"]
    assert db.pending_approvals("s1") == []


async def test_unknown_session_denies(broker_setup):
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=1)
    decision = await broker.request("no-such-session", "Bash", {"command": "ls"})
    assert decision["behavior"] == "deny"


async def test_emits_events_for_the_phone(broker_setup):
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=5)
    task = asyncio.create_task(broker.request("s1", "Write", {"file_path": "/x/y.py"}))
    await asyncio.sleep(0.05)
    approval_id = db.pending_approvals("s1")[0]["id"]
    await broker.resolve(approval_id, approve=True)
    await task

    types = [e["type"] for e in db.get_events("s1")]
    assert "tool.approval_required" in types
    assert "tool.approval_resolved" in types
    required = next(e for e in db.get_events("s1") if e["type"] == "tool.approval_required")
    assert required["payload"]["summary"] == "Write /x/y.py"


async def test_stopping_a_session_denies_everything_pending(broker_setup):
    db, hub = broker_setup
    broker = ApprovalBroker(db, hub, timeout=5)
    task = asyncio.create_task(broker.request("s1", "Bash", {"command": "sleep 1"}))
    await asyncio.sleep(0.05)
    await broker.cancel_session("s1", "session stopped")
    assert (await task)["behavior"] == "deny"


def test_summarize_is_readable():
    assert summarize("Bash", {"command": "pytest -q"}) == "pytest -q"
    assert summarize("Edit", {"file_path": "src/app.py"}) == "Edit src/app.py"
    assert summarize("Grep", {"pattern": "login"}) == "Grep login"
    assert summarize("Mystery", {}) == "Mystery"


# ------------------------------------------------------------------ MCP server
def _rpc(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def test_permission_mcp_speaks_mcp_and_fails_closed():
    """With no backend configured the MCP tool must deny, never allow."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "codepilot.bridge.permission_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ".",
                        "CODEPILOT_BACKEND_URL": "http://127.0.0.1:1",
                        "CODEPILOT_INTERNAL_TOKEN": "t",
                        "CODEPILOT_APPROVAL_TIMEOUT": "1"})
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05"}})
        assert init["result"]["serverInfo"]["name"] == "codepilot"

        listed = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert [t["name"] for t in listed["result"]["tools"]] == ["approve"]

        called = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "approve",
                                        "arguments": {"tool_name": "Bash",
                                                      "input": {"command": "ls"}}}})
        decision = json.loads(called["result"]["content"][0]["text"])
        assert decision["behavior"] == "deny"
        assert "unreachable" in decision["message"]
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)


def test_permission_mcp_reports_unknown_method():
    proc = subprocess.Popen(
        [sys.executable, "-m", "codepilot.bridge.permission_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "."})
    try:
        reply = _rpc(proc, {"jsonrpc": "2.0", "id": 9, "method": "nope/nope"})
        assert reply["error"]["code"] == -32601
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)
