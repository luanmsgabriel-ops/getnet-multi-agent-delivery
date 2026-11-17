"""Public HTTP contracts."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1, examples=["When will the money from yesterday's sales be deposited?"]
    )
    user_id: str = Field(min_length=1, max_length=64, examples=["cliente1988"])
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    answer: str
    outcome: str = Field(
        description="answered | clarify | limit | blocked | handoff | handoff_pending | "
        "handoff_resolved"
    )
    session_id: str
    agents_used: list[str]
    tool_calls: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    handoff: dict[str, Any] | None = None
    guardrails: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int
    request_id: str


class OperatorReply(BaseModel):
    action: Literal["reply", "instruct", "close"] = Field(
        description="reply: message for the merchant; instruct: guidance for the assistant "
        "(it may use tools); close: case closed with a final note."
    )
    message: str = Field(min_length=1, max_length=4000)


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
