"""Metrics (Prometheus), traces (OpenTelemetry) and structured JSON logs.

Metrics are always on (`GET /metrics`). Traces are exported over OTLP/HTTP only when
OTEL_EXPORTER_OTLP_ENDPOINT is set (e.g. Jaeger in `docker compose --profile obs`).
Labels never carry merchant ids or message text (bounded cardinality, no PII).
"""

import json
import logging
import os
import sys
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LATENCY_BUCKETS = (0.25, 0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60, 90)

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["route", "status"])
CHAT_TURNS = Counter("chat_turns_total", "Chat turns by outcome", ["outcome"])
# Turns that failed on our side (5xx on /chat, an error event on /chat/stream): the SLO's bad
# events (docs/SLO.md). Client errors (4xx) are not counted.
CHAT_ERRORS = Counter("chat_turn_errors_total", "Chat turns that failed server-side", ["code"])
VERIFY = Counter("answer_verifications_total", "Final-answer checks", ["result", "checked_by"])
CHAT_LATENCY = Histogram(
    "chat_turn_seconds", "End-to-end chat turn latency", ["outcome"], buckets=LATENCY_BUCKETS
)
CHAT_COST = Histogram(
    "chat_turn_cost_usd",
    "LLM cost per chat turn",
    buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5),
)
LLM_CALLS = Counter("llm_calls_total", "LLM calls", ["agent", "model", "stop_reason"])
LLM_ERRORS = Counter("llm_errors_total", "LLM call failures", ["agent", "code"])
LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens", ["agent", "kind"])
LLM_COST = Counter("llm_cost_usd_total", "LLM spend in USD", ["agent", "model"])
LLM_LATENCY = Histogram("llm_call_seconds", "LLM call latency", ["agent"], buckets=LATENCY_BUCKETS)
TOOL_CALLS = Counter("tool_calls_total", "Tool executions", ["agent", "tool", "status"])
TOOL_LATENCY = Histogram(
    "tool_call_seconds",
    "Tool latency",
    ["tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
GUARDRAIL = Counter("guardrail_decisions_total", "Guardrail decisions", ["stage", "decision"])
HANDOFFS = Counter("handoffs_total", "Human handoffs opened", ["reason", "priority"])
HANDOFF_REPLY = Histogram(
    "handoff_reply_seconds",
    "Time from handoff to operator reply",
    buckets=(30, 60, 300, 900, 1800, 3600, 7200, 14400, 43200),
)
FEEDBACK = Counter("feedback_total", "Merchant feedback on answers", ["rating"])
BUDGET_SPENT = Gauge("llm_budget_spent_usd", "Total LLM spend recorded in the ledger")
BUDGET_LIMIT = Gauge("llm_budget_limit_usd", "Configured LLM budget")
HANDOFFS_PENDING = Gauge("handoffs_pending", "Handoffs waiting for an operator")
HANDOFF_SLA_BREACHED = Counter(
    "handoff_sla_breached_total",
    "Handoffs not answered within their deadline (by original priority)",
    ["priority"],
)
OPERATOR_NOTIFICATIONS = Counter(
    "operator_notifications_total", "Operator notifications sent", ["channel", "delivered"]
)

tracer = trace.get_tracer("getnet.agents")


def bind_gauge(gauge: Gauge, fn: Callable[[], float]) -> None:
    gauge.set_function(fn)


def setup_tracing(service: str = "getnet-agents") -> bool:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    return True


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if trace_id := current_trace_id():
            entry["trace_id"] = trace_id
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # HTTP client request lines include full URLs, and some carry secrets (the Telegram bot
    # token is part of its API path): keep those loggers at WARNING.
    for name in ("httpx2", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, msg: str, **fields: Any) -> None:
    """Structured log line; callers pass only non-sensitive fields."""
    logger.info(msg, extra={"fields": fields})
