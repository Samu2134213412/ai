"""Approval broker.

Claude Code is launched with ``--permission-prompt-tool``, so whenever its own
permission model decides an operation needs a human, it calls our MCP tool. That
tool (a separate process, see ``permission_mcp.py``) posts here; we raise a
``tool.approval_required`` event on the phone and block until someone decides or
the request times out.

Nothing here weakens Claude Code's permission model: operations Claude Code
already considers allowed never reach this broker, and a timeout denies.
"""

from __future__ import annotations

import asyncio
import uuid

from ..db import Database
from ..events import (EventHub, TOOL_APPROVAL_REQUIRED, TOOL_APPROVAL_RESOLVED)

ALLOW = "allow"
DENY = "deny"


class ApprovalBroker:
    def __init__(self, db: Database, hub: EventHub, timeout: int = 300):
        self.db = db
        self.hub = hub
        self.timeout = timeout
        self._waiters: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def request(self, session_id: str, tool_name: str, tool_input: dict,
                      suggestions: list | None = None) -> dict:
        """Ask the phone. Returns an Anthropic permission-tool decision dict."""
        session = self.db.get_session(session_id)
        if session is None:
            return self._deny("CodePilot does not know this session")

        approval_id = str(uuid.uuid4())
        self.db.create_approval(approval_id, session_id, tool_name, tool_input)

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        async with self._lock:
            self._waiters[approval_id] = future

        await self.hub.publish(session_id, TOOL_APPROVAL_REQUIRED, {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "summary": summarize(tool_name, tool_input),
            "suggestions": suggestions or [],
            "timeout_seconds": self.timeout,
        })

        try:
            decision = await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.db.decide_approval(approval_id, "timeout", "no answer from the phone")
            await self.hub.publish(session_id, TOOL_APPROVAL_RESOLVED, {
                "approval_id": approval_id, "decision": "timeout",
                "reason": f"no answer within {self.timeout}s",
            })
            return self._deny(
                f"CodePilot: nobody approved this within {self.timeout} seconds, so it was denied.")
        finally:
            async with self._lock:
                self._waiters.pop(approval_id, None)

        return decision

    async def resolve(self, approval_id: str, approve: bool, reason: str | None = None,
                      updated_input: dict | None = None) -> bool:
        """Called by the API when the phone taps Approve/Reject."""
        record = self.db.get_approval(approval_id)
        if record is None or record["status"] != "pending":
            return False
        status = "approved" if approve else "rejected"
        self.db.decide_approval(approval_id, status, reason)

        if approve:
            decision = {"behavior": "allow",
                        "updatedInput": updated_input if updated_input is not None
                        else record["tool_input"]}
        else:
            decision = {"behavior": "deny",
                        "message": reason or "Denied from the CodePilot mobile app."}

        await self.hub.publish(record["session_id"], TOOL_APPROVAL_RESOLVED, {
            "approval_id": approval_id, "decision": status, "reason": reason,
        })

        async with self._lock:
            future = self._waiters.get(approval_id)
        if future is not None and not future.done():
            future.set_result(decision)
            return True
        # The waiter is gone (server restarted, or it already timed out). The
        # decision is still recorded for the history view.
        return False

    async def cancel_session(self, session_id: str, reason: str) -> None:
        """Deny everything still pending for a session that is stopping."""
        for record in self.db.pending_approvals(session_id):
            await self.resolve(record["id"], approve=False, reason=reason)

    @staticmethod
    def _deny(message: str) -> dict:
        return {"behavior": "deny", "message": message}


def summarize(tool_name: str, tool_input: dict) -> str:
    """A one-line, human-readable description for the approval card."""
    if tool_name == "Bash":
        return (tool_input.get("command") or "").strip() or "run a shell command"
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        return f"{tool_name} {tool_input.get('file_path') or tool_input.get('notebook_path') or ''}".strip()
    if tool_name == "Read":
        return f"Read {tool_input.get('file_path', '')}".strip()
    if tool_name in ("Grep", "Glob"):
        return f"{tool_name} {tool_input.get('pattern', '')}".strip()
    if tool_name == "WebFetch":
        return f"Fetch {tool_input.get('url', '')}".strip()
    for key in ("command", "description", "prompt", "query", "url"):
        if isinstance(tool_input.get(key), str) and tool_input[key].strip():
            return tool_input[key].strip()[:300]
    return tool_name
