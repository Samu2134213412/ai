"""Stdio MCP server exposing a single ``approve`` tool to Claude Code.

Claude Code is started with::

    --mcp-config '{"mcpServers":{"codepilot":{...this module...}}}'
    --permission-prompt-tool mcp__codepilot__approve

When Claude Code's own permission model decides an operation needs a human, it
calls this tool with the tool name and input. We forward the request to the
CodePilot backend over loopback HTTP, which pushes an approval card to the phone
and blocks until someone decides.

The tool must return, as text content, a JSON object shaped like::

    {"behavior": "allow", "updatedInput": {...}}
    {"behavior": "deny",  "message": "..."}

This process speaks JSON-RPC 2.0 over stdin/stdout — the MCP stdio transport —
with no third-party dependency, so it starts fast and cannot drag extra packages
into the Claude Code process tree.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
TOOL_NAME = "approve"

BACKEND_URL = os.environ.get("CODEPILOT_BACKEND_URL", "")
INTERNAL_TOKEN = os.environ.get("CODEPILOT_INTERNAL_TOKEN", "")
SESSION_ID = os.environ.get("CODEPILOT_SESSION_ID", "")
# Slightly longer than the server-side approval timeout so the server, not this
# process, is the one that decides a request has expired.
HTTP_TIMEOUT = float(os.environ.get("CODEPILOT_APPROVAL_TIMEOUT", "300")) + 30


def _log(message: str) -> None:
    """MCP stdio reserves stdout for protocol frames; diagnostics go to stderr."""
    print(f"[codepilot-approval] {message}", file=sys.stderr, flush=True)


def ask_backend(tool_name: str, tool_input: dict, suggestions: list) -> dict:
    payload = json.dumps({
        "session_id": SESSION_ID,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "suggestions": suggestions,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{BACKEND_URL.rstrip('/')}/internal/approvals/request",
        data=payload,
        headers={"content-type": "application/json",
                 "x-codepilot-internal": INTERNAL_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _log(f"backend returned HTTP {exc.code}")
        return {"behavior": "deny",
                "message": f"CodePilot could not ask for approval (HTTP {exc.code}). Denied."}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _log(f"backend unreachable: {exc}")
        return {"behavior": "deny",
                "message": "CodePilot server is unreachable, so this operation was denied. "
                           "Nothing was run."}
    except json.JSONDecodeError:
        return {"behavior": "deny",
                "message": "CodePilot returned an unreadable approval response. Denied."}


# ------------------------------------------------------------- JSON-RPC layer
def respond(msg_id, result=None, error=None) -> None:
    frame = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        frame["error"] = error
    else:
        frame["result"] = result
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()


TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Ask the CodePilot Remote user, on their phone, whether Claude Code may "
        "perform this operation. Returns an allow/deny decision."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "description": "Tool Claude Code wants to use"},
            "input": {"type": "object", "description": "Input the tool would be called with"},
            "tool_use_id": {"type": "string"},
            "permission_suggestions": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["tool_name", "input"],
    },
}


def handle(message: dict) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return {"id": msg_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "codepilot", "version": "0.1.0"},
        }}
    if method in ("notifications/initialized", "initialized"):
        return None  # notification, no reply
    if method == "ping":
        return {"id": msg_id, "result": {}}
    if method == "tools/list":
        return {"id": msg_id, "result": {"tools": [TOOL_SCHEMA]}}
    if method == "tools/call":
        if params.get("name") != TOOL_NAME:
            return {"id": msg_id, "error": {"code": -32602,
                                            "message": f"unknown tool: {params.get('name')}"}}
        args = params.get("arguments") or {}
        decision = ask_backend(
            args.get("tool_name", "unknown"),
            args.get("input") or {},
            args.get("permission_suggestions") or [],
        )
        return {"id": msg_id, "result": {
            "content": [{"type": "text", "text": json.dumps(decision)}]}}

    if msg_id is None:
        return None  # unknown notification: ignore
    return {"id": msg_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}


def main() -> int:
    if not BACKEND_URL or not INTERNAL_TOKEN:
        _log("CODEPILOT_BACKEND_URL / CODEPILOT_INTERNAL_TOKEN are not set; "
             "every approval request will be denied.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _log(f"ignoring non-JSON frame: {line[:120]}")
            continue
        try:
            reply = handle(message)
        except Exception as exc:  # never let the transport die
            _log(f"handler error: {exc!r}")
            reply = {"id": message.get("id"), "error": {"code": -32603, "message": str(exc)}}
        if reply is not None:
            respond(reply.get("id"), reply.get("result"), reply.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
