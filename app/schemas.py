"""Public HTTP contracts."""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1, examples=["When will the money from yesterday's sales be deposited?"]
    )
    user_id: str = Field(min_length=1, max_length=64, examples=["cliente1988"])
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    answer: str
    outcome: str = Field(description="answered | clarify | limit | blocked")
    agents_used: list[str]
    tool_calls: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    guardrails: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int
    request_id: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, bool]


class MeResponse(BaseModel):
    sub: str
    tenant: str
    scopes: list[str]
