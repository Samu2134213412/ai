"""The staged diagnosis — especially its failure paths, which are the point."""

from __future__ import annotations

import httpx
import pytest

from codepilot import doctor
from codepilot.doctor import FAIL, PASS, SKIP, WARN


def _mock_ollama(monkeypatch, *, version="0.14.2", models=("qwen3-coder:30b",),
                 messages_status=200, messages_body=None, ps_context=32768,
                 ps_supported=True, timeout_on_messages=False):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": version})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        if path == "/api/ps":
            if not ps_supported:
                return httpx.Response(404, json={})
            entry = {"name": models[0], "model": models[0]}
            if ps_context is not None:
                entry["context_length"] = ps_context
            return httpx.Response(200, json={"models": [entry]})
        if path == "/v1/messages":
            if timeout_on_messages:
                raise httpx.ReadTimeout("too slow", request=request)
            body = messages_body if messages_body is not None else {
                "content": [{"type": "text", "text": "PONG"}]}
            return httpx.Response(messages_status, json=body)
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Patched(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)


# ------------------------------------------------------------------ happy path
async def test_all_ollama_stages_pass(monkeypatch, store):
    _mock_ollama(monkeypatch)
    settings = store.current
    assert (await doctor.stage_ollama_reachable(settings)).status == PASS
    assert (await doctor.stage_model_present(settings)).status == PASS

    answered = await doctor.stage_model_answers(settings)
    assert answered.status == PASS
    assert "PONG" in answered.proved

    assert (await doctor.stage_context_window(settings)).status == PASS


# --------------------------------------------------------------- failure paths
async def test_old_ollama_is_a_hard_stop(monkeypatch, store):
    _mock_ollama(monkeypatch, version="0.11.0")
    stage = await doctor.stage_ollama_reachable(store.current)
    assert stage.status == FAIL
    assert "Anthropic-compatible" in stage.detail
    assert "0.14.0" in stage.fix


async def test_offline_ollama_says_how_to_start_it(store):
    store.update({"ollama_url": "http://127.0.0.1:1"})
    stage = await doctor.stage_ollama_reachable(store.current)
    assert stage.status == FAIL
    assert "ollama serve" in stage.fix


async def test_missing_model_gives_the_pull_command_and_near_matches(monkeypatch, store):
    _mock_ollama(monkeypatch, models=("qwen3-coder:7b", "llama3:8b"))
    stage = await doctor.stage_model_present(store.current)
    assert stage.status == FAIL
    assert "ollama pull qwen3-coder:30b" in stage.fix
    assert "qwen3-coder:7b" in stage.fix          # offers what is already there
    assert "18 GB" in stage.fix                   # and never downloads it itself


async def test_404_on_messages_points_at_the_ollama_version(monkeypatch, store):
    _mock_ollama(monkeypatch, messages_status=404, messages_body={"error": "nope"})
    stage = await doctor.stage_model_answers(store.current)
    assert stage.status == FAIL
    assert "0.14.0" in stage.fix


async def test_timeout_suggests_warming_the_model(monkeypatch, store):
    _mock_ollama(monkeypatch, timeout_on_messages=True)
    stage = await doctor.stage_model_answers(store.current)
    assert stage.status == FAIL
    assert "ollama run qwen3-coder:30b" in stage.fix


async def test_empty_answer_warns_but_does_not_stop(monkeypatch, store):
    _mock_ollama(monkeypatch, messages_body={"content": []})
    stage = await doctor.stage_model_answers(store.current)
    assert stage.status == WARN
    assert not stage.fatal


# ------------------------------------------------------- the context-size trap
async def test_smaller_ollama_window_is_flagged(monkeypatch, store):
    """The quiet failure that just looks like 'the model behaves oddly'."""
    _mock_ollama(monkeypatch, ps_context=4096)
    stage = await doctor.stage_context_window(store.current)
    assert stage.status == WARN
    assert "4096" in stage.detail and "32768" in stage.detail
    assert "setx OLLAMA_CONTEXT_LENGTH 32768" in stage.fix
    assert not stage.fatal


async def test_context_check_is_skipped_when_unsupported(monkeypatch, store):
    _mock_ollama(monkeypatch, ps_supported=False)
    assert (await doctor.stage_context_window(store.current)).status == SKIP


async def test_context_check_is_skipped_when_model_not_loaded(monkeypatch, store):
    _mock_ollama(monkeypatch, ps_context=None)
    assert (await doctor.stage_context_window(store.current)).status == SKIP


# --------------------------------------------------------------- reachability
async def test_loopback_bind_fails_the_phone_stage(store):
    stage = await doctor.stage_phone_reachable(store.current)
    assert stage.status == FAIL
    assert "--bind-mode private" in stage.fix


async def test_private_bind_reports_addresses(store):
    store.update({"bind_mode": "private"})
    stage = await doctor.stage_phone_reachable(store.current)
    # Tailscale is absent in CI, so this warns rather than passes — but it must
    # still tell the user where the phone can reach them on the LAN.
    assert stage.status in (PASS, WARN)
    assert not stage.fatal


# ------------------------------------------------------------------ the runner
async def test_run_stops_at_the_first_failure(store, monkeypatch, capsys):
    """Later stages must be skipped, not run against a broken foundation."""
    store.update({"ollama_url": "http://127.0.0.1:1"})
    results = await doctor.run(store.current)

    assert len(results) == len(doctor.STAGES)
    assert results[0].status == PASS or results[0].status == FAIL  # claude may be absent
    failures = [r for r in results if r.status == FAIL]
    assert failures, "an unreachable Ollama must fail a stage"
    first_failure = results.index(failures[0])
    assert all(r.status == SKIP for r in results[first_failure + 1:])


async def test_summarise_reports_the_first_failure(capsys):
    results = [
        doctor.Stage("Claude Code is installed", PASS, proved="ok"),
        doctor.Stage("Ollama is running", FAIL, detail="nothing there",
                     fix="start ollama"),
        doctor.Stage("later", SKIP),
    ]
    assert doctor.summarise(results) is False
    out = capsys.readouterr().out
    assert "Stopped at: Ollama is running" in out
    assert "start ollama" in out


async def test_summarise_reports_success(capsys):
    results = [doctor.Stage("a", PASS), doctor.Stage("b", PASS), doctor.Stage("c", WARN)]
    assert doctor.summarise(results) is True
    assert "All good" in capsys.readouterr().out
