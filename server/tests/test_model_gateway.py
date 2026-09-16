"""Model provider detection and the Anthropic compatibility proxy."""

from __future__ import annotations

import json

import httpx
import pytest

from codepilot import detect
from codepilot.compat_proxy import estimate_tokens
from codepilot.detect import ComponentStatus, model_status
from codepilot.providers import get_provider


# ------------------------------------------------------------------- detection
def _ollama_mock(version="0.14.2", models=("qwen3-coder:30b", "llama3:8b")):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def mock_ollama(monkeypatch):
    def install(**kwargs):
        transport = _ollama_mock(**kwargs)
        original = httpx.AsyncClient

        class Patched(original):
            def __init__(self, *args, **kw):
                kw["transport"] = transport
                super().__init__(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", Patched)
    return install


async def test_detects_online_ollama_and_models(mock_ollama, store):
    mock_ollama()
    status = await detect.detect_ollama("http://127.0.0.1:11434")
    assert status.available is True
    assert status.version == "0.14.2"
    assert status.extra["anthropic_api"] is True
    assert "qwen3-coder:30b" in status.extra["models"]


async def test_flags_ollama_too_old_for_anthropic_api(mock_ollama):
    mock_ollama(version="0.9.0")
    status = await detect.detect_ollama("http://127.0.0.1:11434")
    assert status.available is True
    assert status.extra["anthropic_api"] is False
    assert "Anthropic-compatible" in status.detail
    assert "ollama.com/download" in status.remedy


async def test_offline_ollama_is_reported_not_guessed():
    status = await detect.detect_ollama("http://127.0.0.1:1")
    assert status.available is False
    assert "no server reachable" in status.detail
    assert "ollama serve" in status.remedy


def test_model_status_reports_missing_with_exact_command():
    online = ComponentStatus("Ollama", True, "0.14.2",
                             extra={"models": ["llama3:8b", "qwen3-coder:7b"]})
    status = model_status(online, "qwen3-coder:30b")
    assert status.available is False
    assert status.remedy == "ollama pull qwen3-coder:30b"
    assert "qwen3-coder:7b" in status.detail          # near match surfaced
    assert status.extra["near_matches"] == ["qwen3-coder:7b"]


def test_model_status_available():
    online = ComponentStatus("Ollama", True, "0.14.2",
                             extra={"models": ["qwen3-coder:30b"]})
    assert model_status(online, "qwen3-coder:30b").available is True


# -------------------------------------------------------------- provider wiring
def test_ollama_provider_emits_the_documented_env(store):
    provider = get_provider(store.current)
    env = provider.claude_env()
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:11434"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "ollama"
    for alias in ("OPUS", "SONNET", "HAIKU"):
        assert env[f"ANTHROPIC_DEFAULT_{alias}_MODEL"] == "qwen3-coder:30b"
    assert env["OLLAMA_CONTEXT_LENGTH"] == "32768"
    # An inherited cloud key must not survive into a local-model run.
    assert env["ANTHROPIC_API_KEY"] == ""


def test_provider_env_points_at_the_proxy_when_asked(store):
    provider = get_provider(store.current)
    env = provider.claude_env("http://127.0.0.1:8765/llm")
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8765/llm"
    assert env["ANTHROPIC_AUTH_TOKEN"] == store.current.llm_token


def test_unknown_provider_is_an_explicit_error(store):
    settings = store.current
    settings.provider = "not-real"
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider(settings)


# ----------------------------------------------------------------- compat proxy
def test_count_tokens_estimate_scales_with_content():
    small = estimate_tokens({"messages": [{"role": "user", "content": "hi"}]})
    big = estimate_tokens({"messages": [{"role": "user", "content": "x" * 3600}]})
    assert small >= 1
    assert 900 < big < 1100


def test_count_tokens_walks_nested_content_and_tools():
    payload = {
        "system": "you are helpful",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "a" * 100}]}],
        "tools": [{"name": "Bash", "description": "b" * 100}],
    }
    assert estimate_tokens(payload) > 50


def test_gateway_requires_the_llm_token(client, store):
    resp = client.post("/llm/v1/messages/count_tokens", json={"messages": []})
    assert resp.status_code == 401
    resp = client.post("/llm/v1/messages/count_tokens",
                       headers={"x-api-key": "wrong"}, json={"messages": []})
    assert resp.status_code == 401


def test_gateway_answers_count_tokens_locally(client, store):
    """Ollama does not implement this endpoint; we must not forward it."""
    resp = client.post("/llm/v1/messages/count_tokens",
                       headers={"x-api-key": store.current.llm_token},
                       json={"messages": [{"role": "user", "content": "hello world"}]})
    assert resp.status_code == 200
    assert resp.json()["input_tokens"] >= 1


def test_gateway_accepts_bearer_too(client, store):
    resp = client.post("/llm/v1/messages/count_tokens",
                       headers={"authorization": f"Bearer {store.current.llm_token}"},
                       json={"messages": []})
    assert resp.status_code == 200


def test_gateway_short_circuits_unknown_paths(client, store):
    resp = client.get("/llm/v1/complete")
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "not_found_error"


def test_gateway_reports_ollama_down_in_anthropic_error_shape(client, store):
    store.update({"ollama_url": "http://127.0.0.1:1"})
    resp = client.post("/llm/v1/messages",
                       headers={"x-api-key": store.current.llm_token},
                       json={"model": "qwen3-coder:30b", "max_tokens": 10,
                             "messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 502
    body = resp.json()
    assert body["type"] == "error"
    assert "ollama serve" in body["error"]["message"]


def test_gateway_streams_messages_through(client, store, monkeypatch):
    """A real SSE stream from the upstream must reach the client unchanged."""
    chunks = [
        b'event: message_start\ndata: {"type":"message_start"}\n\n',
        b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n',
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert json.loads(request.content)["model"] == "qwen3-coder:30b"
        return httpx.Response(200, stream=httpx.ByteStream(b"".join(chunks)),
                              headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Patched(original):
        def __init__(self, *args, **kw):
            kw["transport"] = transport
            super().__init__(*args, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)

    resp = client.post("/llm/v1/messages",
                       headers={"x-api-key": store.current.llm_token},
                       json={"model": "qwen3-coder:30b", "max_tokens": 10, "stream": True,
                             "messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.content == b"".join(chunks)
