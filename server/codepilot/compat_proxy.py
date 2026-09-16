"""Anthropic-API compatibility proxy that sits between Claude Code and Ollama.

Why this exists
---------------
Ollama v0.14+ serves ``POST /v1/messages`` natively, so Claude Code can talk to
it directly. But Claude Code also calls ``POST /v1/messages/count_tokens``, which
Ollama does not implement; the resulting 404s have been reported to degrade and
eventually hang the Ollama server (ollama/ollama#13949).

This proxy therefore:

* answers ``count_tokens`` locally with a character-based estimate,
* streams ``/v1/messages`` straight through, byte for byte, both for SSE and
  plain JSON responses,
* translates ``/v1/models`` from Ollama's ``/api/tags``,
* refuses every other path immediately, so unsupported endpoints never reach
  Ollama at all.

It is a transport shim only: it never rewrites prompts, tools or responses, so
Claude Code's agent loop is untouched. Disable it in Settings
(``compat_proxy_enabled = false``) to talk to Ollama directly.
"""

from __future__ import annotations

import hmac
import json
import math

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

#: Rough bytes-per-token for code-heavy content. Only used for the local
#: count_tokens estimate, which Claude Code uses for context budgeting.
CHARS_PER_TOKEN = 3.6


def estimate_tokens(payload: dict) -> int:
    """Character-based token estimate over an Anthropic Messages request body."""
    chars = 0

    def walk(node) -> None:
        nonlocal chars
        if isinstance(node, str):
            chars += len(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload.get("system"))
    walk(payload.get("messages"))
    walk(payload.get("tools"))
    return max(1, math.ceil(chars / CHARS_PER_TOKEN))


def build_router(get_settings) -> APIRouter:
    """``get_settings`` is a callable returning the live Settings object."""
    router = APIRouter()

    def authorize(api_key: str | None, authorization: str | None) -> None:
        settings = get_settings()
        expected = settings.llm_token
        presented = api_key
        if not presented and authorization:
            parts = authorization.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                presented = parts[1].strip()
        if not presented or not hmac.compare_digest(presented, expected):
            raise HTTPException(status_code=401, detail="invalid model-gateway token")

    def upstream() -> str:
        return get_settings().ollama_url.rstrip("/")

    @router.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request,
                           x_api_key: str | None = Header(default=None),
                           authorization: str | None = Header(default=None)):
        """Served locally — the upstream does not implement this endpoint."""
        authorize(x_api_key, authorization)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="request body is not valid JSON")
        return JSONResponse({"input_tokens": estimate_tokens(body)})

    @router.post("/v1/messages")
    async def messages(request: Request,
                       x_api_key: str | None = Header(default=None),
                       authorization: str | None = Header(default=None)):
        authorize(x_api_key, authorization)
        settings = get_settings()
        body = await request.body()
        headers = {
            "content-type": "application/json",
            "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
            # Ollama accepts but does not validate the key.
            "x-api-key": "ollama",
            "authorization": "Bearer ollama",
        }
        timeout = httpx.Timeout(settings.model_timeout, connect=10.0)
        client = httpx.AsyncClient(timeout=timeout)
        url = f"{upstream()}/v1/messages"
        try:
            req = client.build_request("POST", url, content=body, headers=headers)
            resp = await client.send(req, stream=True)
        except httpx.ConnectError:
            await client.aclose()
            return JSONResponse(
                status_code=502,
                content={"type": "error", "error": {
                    "type": "api_error",
                    "message": f"CodePilot could not reach Ollama at {upstream()}. "
                               f"Is `ollama serve` running?"}},
            )
        except httpx.HTTPError as exc:
            await client.aclose()
            return JSONResponse(
                status_code=502,
                content={"type": "error", "error": {
                    "type": "api_error",
                    "message": f"CodePilot could not reach Ollama: {exc}"}},
            )

        async def body_stream():
            try:
                async for chunk in resp.aiter_raw():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        passthrough = {
            k: v for k, v in resp.headers.items()
            if k.lower() in {"content-type", "cache-control", "anthropic-ratelimit-requests-remaining"}
        }
        return StreamingResponse(body_stream(), status_code=resp.status_code,
                                 headers=passthrough,
                                 media_type=resp.headers.get("content-type"))

    @router.get("/v1/models")
    async def models(x_api_key: str | None = Header(default=None),
                     authorization: str | None = Header(default=None)):
        """Anthropic-shaped model list, derived from Ollama's /api/tags."""
        authorize(x_api_key, authorization)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{upstream()}/api/tags")
                resp.raise_for_status()
                tags = resp.json().get("models", [])
        except httpx.HTTPError as exc:
            return JSONResponse(status_code=502, content={
                "type": "error",
                "error": {"type": "api_error", "message": f"cannot list Ollama models: {exc}"}})
        return {"data": [{"type": "model", "id": t["name"], "display_name": t["name"]}
                         for t in tags if t.get("name")],
                "has_more": False}

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def unsupported(path: str):
        """Short-circuit anything else so it never reaches the Ollama server."""
        return JSONResponse(
            status_code=404,
            content={"type": "error", "error": {
                "type": "not_found_error",
                "message": f"/{path} is not served by the CodePilot model gateway"}},
        )

    return router
