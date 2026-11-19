"""Shared agent machinery: typed tools, tool execution and the tool-use loop.

A specialist agent is a system prompt + a set of tools + this loop. The supervisor reuses
`execute_tools` inside its LangGraph node. Tools receive a `ToolContext` built from the
authenticated principal; the model never supplies identity.
"""

import contextvars
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.data.db import Database
from app.llm.client import BudgetExceeded, LLMClient, LLMUnavailable
from app.observability import TOOL_CALLS, TOOL_LATENCY, tracer
from app.security.auth import AuthError, Principal


class Source(BaseModel):
    id: str = ""
    title: str
    url: str
    retrieved_at: str


class ToolError(BaseModel):
    code: Literal[
        "not_found",
        "unauthorized",
        "invalid_argument",
        "upstream_timeout",
        "upstream_error",
        "rate_limited",
        "budget_exceeded",
    ]
    message: str
    retryable: bool = False


class ToolResult(BaseModel):
    status: Literal["ok", "not_found", "error"]
    data: Any = None
    error: ToolError | None = None
    sources: list[Source] = Field(default_factory=list)

    @classmethod
    def fail(cls, code: str, message: str, retryable: bool = False) -> "ToolResult":
        return cls(
            status="error",
            error=ToolError.model_validate(
                {"code": code, "message": message, "retryable": retryable}
            ),
        )


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class TraceEvent:
    agent: str
    tool: str
    status: str
    latency_ms: int
    arguments: dict[str, Any]
    result_preview: str = ""  # tool output excerpt; only exposed when evaluation mode is on


STATUS_TEXT: dict[str, dict[str, str]] = {
    "analyzing": {"pt": "Analisando sua pergunta", "en": "Reading your question"},
    "knowledge": {
        "pt": "Consultando o conteúdo oficial da Getnet",
        "en": "Checking Getnet's official content",
    },
    "support": {"pt": "Consultando os dados da sua conta", "en": "Checking your account data"},
    "escalation": {
        "pt": "Encaminhando para um especialista",
        "en": "Passing your case to a specialist",
    },
    "verifying": {
        "pt": "Conferindo a resposta com as fontes",
        "en": "Checking the answer against the sources",
    },
}


@dataclass
class ToolContext:
    principal: Principal
    db: Database
    now: datetime
    llm: LLMClient
    session_id: str = "default"
    language: str = "en"
    # Session services (handoff store, notifier); absent in unit tests of single tools.
    services: dict[str, Any] = field(default_factory=dict)
    # Progress listener for streaming (POST /chat/stream); None for plain /chat.
    emit: Callable[[str, dict[str, Any]], None] | None = None
    evidence: list[str] = field(default_factory=list)  # full tool outputs, for grounding checks
    trace: list[TraceEvent] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def add_source(self, source: Source) -> Source:
        """Register a source once per request and give it a stable id (S1, S2, ...)."""
        with self._lock:
            for existing in self.sources:
                if existing.url == source.url:
                    return existing
            registered = source.model_copy(update={"id": f"S{len(self.sources) + 1}"})
            self.sources.append(registered)
            return registered

    def record(self, event: TraceEvent) -> None:
        with self._lock:
            self.trace.append(event)

    def status(self, step: str) -> None:
        """Tell a streaming client what is happening now (never content, only the step)."""
        if self.emit is not None:
            self.emit(
                "status",
                {
                    "step": step,
                    "text": STATUS_TEXT[step].get(self.language, STATUS_TEXT[step]["en"]),
                },
            )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[ToolInput]
    run: Callable[[ToolContext, Any], ToolResult]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": _clean_schema(self.input_model.model_json_schema()),
            "strict": True,
        }


def _clean_schema(node: Any) -> Any:
    """Drop keys the strict tool schema does not need (titles, defaults, numeric limits)."""
    drop = {"title", "default", "minimum", "maximum", "minLength", "maxLength"}
    if isinstance(node, dict):
        cleaned = {k: _clean_schema(v) for k, v in node.items() if k not in drop}
        if cleaned.get("type") == "object":
            cleaned.setdefault("additionalProperties", False)
        return cleaned
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def _run_one(tool: Tool | None, block: dict[str, Any], ctx: ToolContext, agent: str) -> ToolResult:
    name = str(block.get("name"))
    with tracer.start_as_current_span(f"tool.{name}") as span:
        span.set_attribute("agent", agent)
        result = _execute(tool, block, ctx, agent)
        span.set_attribute("tool.status", result.status)
        if result.error is not None:
            span.set_attribute("error.type", result.error.code)
        return result


def _execute(tool: Tool | None, block: dict[str, Any], ctx: ToolContext, agent: str) -> ToolResult:
    started = time.monotonic()
    args = block.get("input") or {}
    if tool is None:
        result = ToolResult.fail("invalid_argument", f"Unknown tool '{block.get('name')}'.")
    else:
        try:
            result = tool.run(ctx, tool.input_model.model_validate(args))
        except ValidationError as exc:
            result = ToolResult.fail("invalid_argument", exc.errors()[0]["msg"])
        except AuthError as exc:
            result = ToolResult.fail("unauthorized", exc.message)
        except BudgetExceeded as exc:
            result = ToolResult.fail("budget_exceeded", str(exc))
        except LLMUnavailable as exc:
            result = ToolResult.fail("upstream_error", str(exc), retryable=False)
        except Exception as exc:  # a tool bug must not crash the conversation
            result = ToolResult.fail("upstream_error", f"{type(exc).__name__}")
    result.sources = [ctx.add_source(s) for s in result.sources]
    elapsed = time.monotonic() - started
    name = str(block.get("name"))
    TOOL_CALLS.labels(agent, name if tool else "unknown", result.status).inc()
    TOOL_LATENCY.labels(name if tool else "unknown").observe(elapsed)
    preview = json.dumps(result.model_dump(exclude_none=True), ensure_ascii=False, default=str)
    if not name.startswith("ask_"):
        with ctx._lock:
            ctx.evidence.append(preview)
    ctx.record(TraceEvent(agent, name, result.status, int(elapsed * 1000), args, preview[:4000]))
    return result


def execute_tools(
    blocks: list[dict[str, Any]], tools: dict[str, Tool], ctx: ToolContext, agent: str
) -> list[dict[str, Any]]:
    """Run every tool_use block (in parallel) and return all tool_result blocks in order."""
    calls = [b for b in blocks if b.get("type") == "tool_use"]
    if not calls:
        return []

    def run(block: dict[str, Any]) -> ToolResult:
        return _run_one(tools.get(str(block.get("name"))), block, ctx, agent)

    with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
        futures = [pool.submit(contextvars.copy_context().run, run, b) for b in calls]
        results = [f.result() for f in futures]
    return [
        {
            "type": "tool_result",
            "tool_use_id": block["id"],
            "content": json.dumps(
                result.model_dump(exclude_none=True), ensure_ascii=False, default=str
            ),
            **({"is_error": True} if result.status == "error" else {}),
        }
        for block, result in zip(calls, results, strict=True)
    ]


@dataclass
class AgentRun:
    text: str
    stop: Literal["done", "max_steps", "truncated"]
    steps: int
    web_sources: list[Source]


def text_of(content: list[dict[str, Any]]) -> str:
    return "\n".join(b["text"] for b in content if b.get("type") == "text").strip()


def web_citations(content: list[dict[str, Any]], retrieved_at: str) -> list[Source]:
    """Collect web-search citations Claude attached to its text blocks."""
    found: list[Source] = []
    for block in content:
        for cite in block.get("citations") or []:
            url = cite.get("url")
            if url and all(s.url != url for s in found):
                found.append(
                    Source(title=cite.get("title") or url, url=url, retrieved_at=retrieved_at)
                )
    return found


def cited_evidence(content: list[dict[str, Any]], ctx: "ToolContext") -> None:
    """Keep the text of each web citation as evidence (web page bodies arrive encrypted, so the
    cited passages are the only readable proof of a web-sourced claim)."""
    cited = [
        f"[web {c.get('url')}] {c['cited_text']}"
        for b in content
        for c in (b.get("citations") or [])
        if c.get("cited_text")
    ]
    if cited:
        with ctx._lock:
            ctx.evidence.extend(cited)


def run_agent(
    *,
    llm: LLMClient,
    agent: str,
    system: str,
    task: str,
    tools: list[Tool],
    ctx: ToolContext,
    effort: str,
    max_steps: int = 4,
    server_tools: list[dict[str, Any]] | None = None,
) -> AgentRun:
    """Tool-use loop for a specialist: call model, run tools, repeat until it answers."""
    with tracer.start_as_current_span(f"agent.{agent}") as span:
        run = _loop(llm, agent, system, task, tools, ctx, effort, max_steps, server_tools)
        span.set_attributes({"agent.steps": run.steps, "agent.stop": run.stop})
        return run


def _loop(
    llm: LLMClient,
    agent: str,
    system: str,
    task: str,
    tools: list[Tool],
    ctx: ToolContext,
    effort: str,
    max_steps: int,
    server_tools: list[dict[str, Any]] | None,
) -> AgentRun:
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools] + (server_tools or [])
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    web: list[Source] = []
    retrieved = ctx.now.date().isoformat()
    for step in range(1, max_steps + 1):
        result = llm.create(
            agent=agent, system=system, messages=messages, tools=schemas, effort=effort
        )
        messages.append({"role": "assistant", "content": result.content})
        web += [s for s in web_citations(result.content, retrieved) if s not in web]
        cited_evidence(result.content, ctx)
        if result.stop_reason == "pause_turn":
            continue
        if result.stop_reason != "tool_use":
            stop: Literal["done", "truncated"] = (
                "truncated" if result.stop_reason == "max_tokens" else "done"
            )
            return AgentRun(text_of(result.content), stop, step, web)
        messages.append(
            {"role": "user", "content": execute_tools(result.content, by_name, ctx, agent)}
        )
    # Out of steps: ask for the best answer with what was gathered, without more tools.
    final = llm.create(
        agent=agent,
        system=system,
        messages=messages,
        tools=schemas,
        effort=effort,
        tool_choice={"type": "none"},
    )
    web += [s for s in web_citations(final.content, retrieved) if s not in web]
    cited_evidence(final.content, ctx)
    return AgentRun(text_of(final.content), "max_steps", max_steps, web)
