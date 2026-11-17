"""Runs one chat turn through the supervisor graph and builds the API response."""

import re
import time
from typing import Any

from app.agents.base import ToolContext
from app.config import Settings
from app.data.db import Database
from app.graph.supervisor import build_graph
from app.llm.client import BudgetExceeded, LLMClient, LLMUnavailable, UsageTracker, current_usage
from app.schemas import ChatResponse
from app.security.auth import Principal

_CITATION = re.compile(r"\[(S\d+)\]")


class OrchestratorError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Orchestrator:
    def __init__(self, settings: Settings, db: Database, llm: LLMClient) -> None:
        self.settings, self.db, self.llm = settings, db, llm
        self.graph = build_graph()

    def run(self, principal: Principal, message: str, request_id: str) -> ChatResponse:
        started = time.monotonic()
        tracker = UsageTracker(max_cost_usd=self.settings.max_cost_per_chat_usd)
        token = current_usage.set(tracker)
        now = self.settings.now()
        ctx = ToolContext(principal=principal, db=self.db, now=now, llm=self.llm)
        user_turn = (
            f"<context>merchant_id={principal.sub}; now={now:%A %Y-%m-%d %H:%M} "
            f"America/Sao_Paulo</context>\n\n{message}"
        )
        try:
            state = self.graph.invoke(
                {"messages": [{"role": "user", "content": user_turn}], "steps": 0},
                config={"configurable": {"ctx": ctx}, "recursion_limit": 25},
            )
        except BudgetExceeded as exc:
            raise OrchestratorError(503, "budget_exceeded", str(exc)) from exc
        except LLMUnavailable as exc:
            raise OrchestratorError(503, "llm_unavailable", str(exc)) from exc
        finally:
            current_usage.reset(token)

        answer = str(state.get("answer", "")).strip()
        cited = set(_CITATION.findall(answer))
        sources = [s for s in ctx.sources if s.id in cited] or ctx.sources
        delegated = {e.tool.removeprefix("ask_") for e in ctx.trace if e.agent == "supervisor"}
        agents = ["supervisor", *sorted(delegated - {"user"})]
        return ChatResponse(
            answer=answer,
            outcome=state.get("outcome", "answered"),
            agents_used=agents,
            tool_calls=[_event(e) for e in ctx.trace],
            sources=[s.model_dump() for s in sources],
            usage=tracker.summary(),
            latency_ms=int((time.monotonic() - started) * 1000),
            request_id=request_id,
        )


def _event(e: Any) -> dict[str, Any]:
    return {
        "agent": e.agent,
        "tool": e.tool,
        "status": e.status,
        "latency_ms": e.latency_ms,
        "arguments": e.arguments,
    }
