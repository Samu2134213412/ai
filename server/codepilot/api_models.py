"""Request/response schemas for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PairRequest(BaseModel):
    token: str = Field(..., min_length=8, description="One-time pairing token from the QR code")
    device_name: str = Field("Phone", max_length=64)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    path: str = Field(..., min_length=1)


class SessionCreate(BaseModel):
    project_id: str
    prompt: str = Field(..., min_length=1, max_length=20000)
    model: str | None = None
    permission_mode: str | None = None
    context_length: int | None = None
    resume_session_id: str | None = None


class MessageIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


class ApprovalDecision(BaseModel):
    approve: bool
    reason: str | None = Field(None, max_length=2000)


class SettingsUpdate(BaseModel):
    bind_mode: str | None = None
    port: int | None = None
    ollama_url: str | None = None
    ollama_model: str | None = None
    context_length: int | None = None
    model_timeout: int | None = None
    compat_proxy_enabled: bool | None = None
    claude_binary: str | None = None
    default_permission_mode: str | None = None
    approval_timeout: int | None = None


class InternalApprovalRequest(BaseModel):
    session_id: str
    tool_name: str
    tool_input: dict = Field(default_factory=dict)
    suggestions: list = Field(default_factory=list)
