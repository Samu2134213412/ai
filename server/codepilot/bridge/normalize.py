"""Turn Claude Code's ``stream-json`` output into CodePilot's typed events.

Claude Code emits one JSON object per line when run with
``--print --output-format stream-json --verbose``. Those objects are a
structured interface, so nothing here scrapes console text. The only heuristic
in this module is the test-summary extractor, and events it produces are marked
``heuristic: true`` so the UI can label them honestly.
"""

from __future__ import annotations

import re

from .. import events as E

#: Tools whose completion means the working tree may have changed.
MUTATING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

#: Commands that plausibly ran a test suite.
_TEST_HINT = re.compile(
    r"\b(pytest|jest|vitest|mocha|go test|cargo test|npm (run )?test|yarn test|"
    r"pnpm test|dotnet test|gradle test|mvn test|unittest|tox)\b", re.I)

#: Ordered most-specific first: a jest "Tests:" line also matches the looser
#: pytest pattern, but only the specific one captures the trailing total.
_TEST_PATTERNS = [
    # jest/vitest: "Tests:  1 failed, 17 passed, 18 total"
    re.compile(r"Tests?:\s*(?P<body>.+)", re.I),
    # pytest: "18 passed, 1 failed, 2 skipped in 3.21s"
    re.compile(r"(?P<body>(?:\d+\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed|deselected)[,\s]*)+)"
               r"(?:in\s[\d.]+s)?", re.I),
    # go test summary lines
    re.compile(r"^(?P<body>(ok|FAIL)\s+\S+.*)$", re.M),
]

_COUNT = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|total|xfailed|xpassed)", re.I)


def extract_test_result(command: str, output: str) -> dict | None:
    """Best-effort test summary from a Bash tool result. ``None`` if not a test run."""
    if not command or not _TEST_HINT.search(command):
        return None
    tail = "\n".join(output.strip().splitlines()[-40:])
    for pattern in _TEST_PATTERNS:
        match = pattern.search(tail)
        if not match:
            continue
        body = match.group("body").strip()
        counts = {}
        for number, label in _COUNT.findall(body):
            key = label.lower().rstrip("s") if label.lower() != "total" else "total"
            key = {"error": "errors"}.get(key, key)
            counts[key] = int(number)
        failed = counts.get("failed", 0) + counts.get("errors", 0)
        if not counts and "FAIL" in body.upper():
            failed = 1
        return {
            "command": command,
            "summary": body[:300],
            "counts": counts,
            "passed": failed == 0,
            "heuristic": True,
        }
    return None


def _text_of(content) -> str:
    """Flatten an Anthropic content array (or string) into plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def normalize(line: dict, state: dict) -> list[tuple[str, dict]]:
    """Map one stream-json object to zero or more ``(event_type, payload)``.

    ``state`` is a per-session dict the caller owns; it is used to correlate
    ``tool_use`` ids with their later ``tool_result``.
    """
    kind = line.get("type")
    out: list[tuple[str, dict]] = []

    if kind == "system":
        subtype = line.get("subtype")
        if subtype == "init":
            out.append((E.SESSION_STATUS, {
                "phase": "initialized",
                "claude_session_id": line.get("session_id"),
                "model": line.get("model"),
                "cwd": line.get("cwd"),
                "tools": line.get("tools", []),
                "permission_mode": line.get("permissionMode"),
                "mcp_servers": line.get("mcp_servers", []),
            }))
        elif subtype == "status":
            out.append((E.SESSION_STATUS, {"phase": line.get("status")}))
        elif subtype == "post_turn_summary":
            out.append((E.SESSION_STATUS, {
                "phase": "turn_complete",
                "status_category": line.get("status_category"),
                "detail": line.get("status_detail"),
            }))
        return out

    if kind == "assistant":
        message = line.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text", "").strip():
                out.append((E.ASSISTANT_MESSAGE, {
                    "text": block["text"],
                    "model": message.get("model"),
                }))
            elif btype == "thinking" and block.get("thinking", "").strip():
                out.append((E.ASSISTANT_THINKING, {"text": block["thinking"]}))
            elif btype == "tool_use":
                tool_id = block.get("id")
                name = block.get("name", "unknown")
                tool_input = block.get("input") or {}
                state.setdefault("tools", {})[tool_id] = {
                    "name": name, "input": tool_input,
                }
                out.append((E.TOOL_STARTED, {
                    "tool_use_id": tool_id,
                    "tool_name": name,
                    "input": tool_input,
                }))
        return out

    if kind == "user":
        message = line.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                tool_id = block.get("tool_use_id")
                started = (state.get("tools") or {}).pop(tool_id, {})
                text = _text_of(block.get("content"))
                is_error = bool(block.get("is_error"))
                out.append((E.TOOL_FINISHED, {
                    "tool_use_id": tool_id,
                    "tool_name": started.get("name", "unknown"),
                    "input": started.get("input", {}),
                    "is_error": is_error,
                    "output": text[:20000],
                    "truncated": len(text) > 20000,
                }))
                if started.get("name") == "Bash" and not is_error:
                    result = extract_test_result(
                        (started.get("input") or {}).get("command", ""), text)
                    if result:
                        out.append((E.TEST_RESULT, result))
        elif isinstance(content, str) and content.strip():
            out.append((E.USER_MESSAGE, {"text": content}))
        return out

    if kind == "result":
        subtype = line.get("subtype")
        payload = {
            "subtype": subtype,
            "is_error": bool(line.get("is_error")),
            "duration_ms": line.get("duration_ms"),
            "duration_api_ms": line.get("duration_api_ms"),
            "num_turns": line.get("num_turns"),
            "total_cost_usd": line.get("total_cost_usd"),
            "usage": line.get("usage"),
            "result": line.get("result"),
            "claude_session_id": line.get("session_id"),
        }
        if line.get("is_error") or subtype not in (None, "success"):
            out.append((E.SESSION_FAILED, payload))
        else:
            out.append((E.SESSION_COMPLETED, payload))
        return out

    if kind in ("stream_event", "active_goal", "autocompact_state", "rate_limit_event",
                "control_response", "prompt_suggestion"):
        # Useful for debugging, too noisy for the session view.
        out.append((E.RAW, {"kind": kind, "line": line}))
        return out

    out.append((E.RAW, {"kind": kind or "unknown", "line": line}))
    return out
