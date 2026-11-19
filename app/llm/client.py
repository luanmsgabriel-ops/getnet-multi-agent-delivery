"""LLM access: one provider adapter, a spend ledger and per-request usage tracking.

Every call goes through `LLMClient.create`, which
  1. refuses to run when the global budget or the per-chat cap would be exceeded,
  2. calls Claude (SDK retries 429/5xx; server-side fallback on refusals),
  3. records tokens, cost and latency in the request tracker and the ledger.
Responses are converted to plain dicts so agent state stays serializable and testable.
"""

import contextvars
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

import anthropic
from opentelemetry import trace

from app.data.db import Database
from app.llm.pricing import cost_usd
from app.observability import (
    LLM_CALLS,
    LLM_COST,
    LLM_ERRORS,
    LLM_LATENCY,
    LLM_TOKENS,
    tracer,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Claude Haiku 5.5 has no server-side refusal fallback: sending the parameter would fail.
NO_SERVER_FALLBACK = ("claude-haiku",)
RESERVE_USD = 0.05  # headroom kept before each call so a single call cannot overshoot


class BudgetExceeded(Exception):
    """Spend cap reached (global ledger or per-chat)."""


class ConversationBudgetExceeded(BudgetExceeded):
    """Per-turn cap reached (the global budget may still have room)."""


class LLMUnavailable(Exception):
    """Provider failed after SDK retries, or refused."""


@dataclass
class CallRecord:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_searches: int
    cost_usd: float
    latency_ms: int
    stop_reason: str


@dataclass
class UsageTracker:
    """Collects the LLM calls of one /chat request (shared across agent threads)."""

    max_cost_usd: float
    calls: list[CallRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def add(self, record: CallRecord) -> None:
        with self._lock:
            self.calls.append(record)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def summary(self) -> dict[str, Any]:
        return {
            "llm_calls": len(self.calls),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
            "web_searches": sum(c.web_searches for c in self.calls),
            "cost_usd": round(self.cost_usd, 5),
        }


def observe_call(record: CallRecord) -> None:
    LLM_CALLS.labels(record.agent, record.model, record.stop_reason).inc()
    LLM_COST.labels(record.agent, record.model).inc(record.cost_usd)
    LLM_LATENCY.labels(record.agent).observe(record.latency_ms / 1000)
    for kind, value in (
        ("input", record.input_tokens),
        ("output", record.output_tokens),
        ("cache_read", record.cache_read_tokens),
        ("cache_write", record.cache_write_tokens),
    ):
        LLM_TOKENS.labels(record.agent, kind).inc(value)


current_usage: contextvars.ContextVar[UsageTracker | None] = contextvars.ContextVar(
    "current_usage", default=None
)


@dataclass
class LLMResult:
    content: list[dict[str, Any]]
    stop_reason: str
    model: str


class LLMClient(Protocol):
    def create(
        self,
        *,
        agent: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        effort: str,
        max_tokens: int = 16000,
        tool_choice: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResult: ...


class Ledger:
    """Persistent spend ledger; the global budget survives restarts."""

    def __init__(self, db: Database, budget_usd: float) -> None:
        self.db = db
        self.budget_usd = budget_usd
        with db.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_ledger (ts TEXT NOT NULL, agent TEXT NOT NULL, "
                "model TEXT NOT NULL, cost_usd REAL NOT NULL)"
            )

    def spent(self) -> float:
        with self.db.connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM llm_ledger").fetchone()
        return float(row["s"])

    def check(self) -> None:
        if self.spent() + RESERVE_USD > self.budget_usd:
            raise BudgetExceeded(f"LLM budget of US$ {self.budget_usd:.2f} reached.")

    def record(self, agent: str, model: str, cost: float) -> None:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "INSERT INTO llm_ledger VALUES (?, ?, ?, ?)",
                    (datetime.now(UTC).isoformat(), agent, model, cost),
                )
        except sqlite3.Error:  # accounting must never break an answer already paid for
            pass


def _block_to_dict(block: Any) -> dict[str, Any]:
    data: dict[str, Any] = block.to_dict()
    return {k: v for k, v in data.items() if v is not None}


class AnthropicLLM:
    def __init__(
        self,
        api_key: str,
        ledger: Ledger,
        model: str = "claude-sonnet-5-5",
        timeout_s: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.ledger = ledger
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    def create(
        self,
        *,
        agent: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        effort: str,
        max_tokens: int = 16000,
        tool_choice: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResult:
        model = model or self.model
        tracker = current_usage.get()
        self.ledger.check()
        if tracker is not None and tracker.cost_usd + RESERVE_USD > tracker.max_cost_usd:
            raise ConversationBudgetExceeded("Per-conversation cost cap reached.")
        with tracer.start_as_current_span(f"llm.{agent}") as span:
            span.set_attributes(
                {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": model,
                    "agent": agent,
                    "effort": effort,
                }
            )
            try:
                result = self._call(
                    agent,
                    system,
                    messages,
                    tools,
                    effort,
                    max_tokens,
                    tool_choice,
                    output_schema,
                    tracker,
                    model,
                )
            except LLMUnavailable as exc:
                LLM_ERRORS.labels(agent, str(exc)).inc()
                span.set_attribute("error.type", str(exc))
                raise
            span.set_attribute("gen_ai.response.finish_reason", result.stop_reason)
            return result

    def _call(
        self,
        agent: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        effort: str,
        max_tokens: int,
        tool_choice: dict[str, Any] | None,
        output_schema: dict[str, Any] | None,
        tracker: "UsageTracker | None",
        model: str,
    ) -> LLMResult:
        started = time.monotonic()
        try:
            request: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "system": [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
                "messages": messages,
                "output_config": {"effort": effort},
            }
            if not model.startswith(NO_SERVER_FALLBACK):
                request["betas"] = [FALLBACK_BETA]
                request["fallbacks"] = "default"
            if tools:
                request["tools"] = tools
                request["tool_choice"] = tool_choice or {"type": "auto"}
            if output_schema is not None:
                request["output_config"]["format"] = {
                    "type": "json_schema",
                    "schema": output_schema,
                }
            response = self._client.beta.messages.create(**request)
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"provider_error_{exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("provider_unreachable") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = response.usage
        searches = 0
        if usage.server_tool_use is not None:
            searches = int(getattr(usage.server_tool_use, "web_search_requests", 0) or 0)
        cost = cost_usd(
            response.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
            searches,
        )
        record = CallRecord(
            agent=agent,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            web_searches=searches,
            cost_usd=cost,
            latency_ms=latency_ms,
            stop_reason=str(response.stop_reason),
        )
        self.ledger.record(agent, response.model, cost)
        trace.get_current_span().set_attributes(
            {
                "gen_ai.response.model": response.model,
                "gen_ai.usage.input_tokens": usage.input_tokens,
                "gen_ai.usage.output_tokens": usage.output_tokens,
                "gen_ai.usage.cache_read_tokens": record.cache_read_tokens,
                "cost_usd": cost,
                "web_searches": searches,
            }
        )
        observe_call(record)
        if tracker is not None:
            tracker.add(record)
        if response.stop_reason == "refusal":
            raise LLMUnavailable("model_refusal")
        return LLMResult(
            content=[_block_to_dict(b) for b in response.content],
            stop_reason=str(response.stop_reason),
            model=response.model,
        )
