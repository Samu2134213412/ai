"""Claude Code stream-json -> CodePilot typed events."""

from __future__ import annotations

from codepilot import events as E
from codepilot.bridge.normalize import extract_test_result, normalize


def run(lines):
    state: dict = {}
    out = []
    for line in lines:
        out.extend(normalize(line, state))
    return out, state


def test_init_carries_session_and_cwd():
    (events, _) = run([{"type": "system", "subtype": "init", "session_id": "abc",
                        "cwd": "/repo", "model": "qwen3-coder:30b",
                        "tools": ["Read", "Bash"]}])
    assert events[0][0] == E.SESSION_STATUS
    assert events[0][1]["claude_session_id"] == "abc"
    assert events[0][1]["cwd"] == "/repo"


def test_assistant_text_and_thinking_are_separate_events():
    (events, _) = run([{"type": "assistant", "message": {"model": "qwen3-coder:30b", "content": [
        {"type": "thinking", "thinking": "let me look"},
        {"type": "text", "text": "I'll inspect the auth code."},
    ]}}])
    kinds = [e[0] for e in events]
    assert kinds == [E.ASSISTANT_THINKING, E.ASSISTANT_MESSAGE]
    assert events[1][1]["text"] == "I'll inspect the auth code."
    assert events[1][1]["model"] == "qwen3-coder:30b"


def test_empty_text_blocks_are_dropped():
    (events, _) = run([{"type": "assistant", "message": {"content": [
        {"type": "text", "text": "   "}, {"type": "thinking", "thinking": ""}]}}])
    assert events == []


def test_tool_use_and_result_are_correlated():
    events, state = run([
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Read",
             "input": {"file_path": "src/auth.py"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": [{"type": "text", "text": "def login(): ..."}]}]}},
    ])
    assert events[0][0] == E.TOOL_STARTED
    assert events[0][1]["tool_name"] == "Read"
    assert events[1][0] == E.TOOL_FINISHED
    # The result event is enriched with the input from the matching tool_use.
    assert events[1][1]["tool_name"] == "Read"
    assert events[1][1]["input"] == {"file_path": "src/auth.py"}
    assert events[1][1]["is_error"] is False
    assert state["tools"] == {}          # correlation entry cleaned up


def test_tool_error_is_flagged():
    events, _ = run([
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "false"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
             "content": "exit code 1"}]}},
    ])
    assert events[1][1]["is_error"] is True
    assert events[1][1]["output"] == "exit code 1"


def test_pytest_summary_becomes_a_test_result_event():
    events, _ = run([
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "python -m pytest -q"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": "....F\n18 passed, 1 failed in 3.21s"}]}},
    ])
    kinds = [e[0] for e in events]
    assert E.TEST_RESULT in kinds
    payload = dict(events)[E.TEST_RESULT]
    assert payload["counts"] == {"passed": 18, "failed": 1}
    assert payload["passed"] is False
    assert payload["heuristic"] is True


def test_non_test_bash_produces_no_test_event():
    assert extract_test_result("ls -la", "a\nb\nc") is None
    assert extract_test_result("", "18 passed") is None


def test_jest_summary_is_recognised():
    result = extract_test_result("npm test", "Tests:  1 failed, 17 passed, 18 total")
    assert result["counts"]["failed"] == 1
    assert result["counts"]["total"] == 18
    assert result["passed"] is False


def test_all_green_pytest_is_marked_passed():
    result = extract_test_result("pytest", "5 passed in 0.10s")
    assert result["passed"] is True


def test_success_result_completes_the_session():
    events, _ = run([{"type": "result", "subtype": "success", "is_error": False,
                      "session_id": "abc", "result": "done", "num_turns": 3}])
    assert events[0][0] == E.SESSION_COMPLETED
    assert events[0][1]["claude_session_id"] == "abc"


def test_error_result_fails_the_session():
    events, _ = run([{"type": "result", "subtype": "error_during_execution",
                      "is_error": True, "result": "model timed out"}])
    assert events[0][0] == E.SESSION_FAILED
    assert events[0][1]["result"] == "model timed out"


def test_unknown_frames_are_kept_as_raw_not_dropped():
    events, _ = run([{"type": "some_future_event", "value": 1}])
    assert events[0][0] == E.RAW
    assert events[0][1]["kind"] == "some_future_event"
