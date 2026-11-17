"""Runs chat turns through the supervisor graph: guardrails, memory, handoff and resume."""

import re
import sqlite3
import time
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agents.base import ToolContext
from app.config import Settings
from app.data.db import Database
from app.graph.supervisor import build_graph
from app.hitl import notify
from app.hitl.store import HitlStore
from app.llm.client import BudgetExceeded, LLMClient, LLMUnavailable, UsageTracker, current_usage
from app.schemas import ChatResponse
from app.security.auth import Principal
from app.security.guardrails import InputDecision, OutputDecision, check_input, check_output

_CITATION = re.compile(r"\[(S\d+)\]")

HANDOFF_ACK = {
    "pt": "Encaminhei seu caso para um especialista da Getnet (protocolo {id}). A resposta vai "
    "aparecer aqui nesta conversa assim que ele responder.",
    "en": "I've passed your case to a Getnet specialist (protocol {id}). Their answer will appear "
    "here in this conversation as soon as they reply.",
}
HANDOFF_WAIT = {
    "pt": "Seu caso (protocolo {id}) está com um especialista. Assim que ele responder, eu "
    "continuo por aqui.",
    "en": "Your case (protocol {id}) is with a specialist. I'll continue here as soon as they "
    "reply.",
}


class OrchestratorError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _pick(texts: dict[str, str], language: str) -> str:
    return texts.get(language, texts["en"])


class Orchestrator:
    def __init__(self, settings: Settings, db: Database, llm: LLMClient) -> None:
        self.settings, self.db, self.llm = settings, db, llm
        self.hitl = HitlStore(db)
        conn = sqlite3.connect(settings.data_dir / "checkpoints.db", check_same_thread=False)
        self.checkpointer = SqliteSaver(conn)
        self.graph = build_graph(self.checkpointer)

    # -- helpers ------------------------------------------------------------------------
    def notify(self, target: str, event: str, payload: dict[str, Any]) -> None:
        url = (
            self.settings.operator_webhook_url
            if target == "operator"
            else self.settings.merchant_webhook_url
        )
        secret = self.settings.webhook_secret
        notify.send(url, secret.get_secret_value() if secret else None, event, payload)

    @staticmethod
    def thread_id(principal: Principal, session_id: str) -> str:
        return f"{principal.tenant}:{principal.sub}:{session_id}"

    def _context(self, principal: Principal, session_id: str, language: str) -> ToolContext:
        return ToolContext(
            principal=principal,
            db=self.db,
            now=self.settings.now(),
            llm=self.llm,
            session_id=session_id,
            language=language,
            services={"hitl": self.hitl, "notify": self.notify},
        )

    def _invoke(self, payload: Any, ctx: ToolContext, thread: str) -> dict[str, Any]:
        try:
            state: dict[str, Any] = self.graph.invoke(
                payload,
                config={"configurable": {"ctx": ctx, "thread_id": thread}, "recursion_limit": 30},
            )
            return state
        except BudgetExceeded as exc:
            raise OrchestratorError(503, "budget_exceeded", str(exc)) from exc
        except LLMUnavailable as exc:
            raise OrchestratorError(503, "llm_unavailable", str(exc)) from exc

    # -- merchant turn ------------------------------------------------------------------
    def run(
        self, principal: Principal, message: str, request_id: str, session_id: str = "default"
    ) -> ChatResponse:
        started = time.monotonic()
        tracker = UsageTracker(max_cost_usd=self.settings.max_cost_per_chat_usd)
        token = current_usage.set(tracker)
        try:
            screened = check_input(self.llm, message)
            ctx = self._context(principal, session_id, screened.language)
            if screened.blocked:
                return self._response(
                    screened.refusal(),
                    "blocked",
                    ctx,
                    tracker,
                    started,
                    request_id,
                    screened,
                    OutputDecision(""),
                )
            waiting = self.hitl.pending_for(principal.sub, session_id)
            if waiting is not None:
                text = _pick(HANDOFF_WAIT, screened.language).format(id=waiting["id"])
                return self._response(
                    text,
                    "handoff_pending",
                    ctx,
                    tracker,
                    started,
                    request_id,
                    screened,
                    OutputDecision(""),
                    handoff={"id": waiting["id"], "status": "pending"},
                )
            now = ctx.now
            user_turn = (
                f"<context>merchant_id={principal.sub}; now={now:%A %Y-%m-%d %H:%M} "
                f"America/Sao_Paulo</context>\n\n{screened.text}"
            )
            state = self._invoke(
                {
                    "user_message": screened.text,
                    "user_turn": user_turn,
                    "steps": 0,
                    "answer": None,
                    "outcome": None,
                    "pending": [],
                    "escalation": None,
                    "handoff_id": None,
                },
                ctx,
                self.thread_id(principal, session_id),
            )
        finally:
            current_usage.reset(token)

        if state.get("__interrupt__"):
            handoff_id = str(state.get("handoff_id"))
            text = _pick(HANDOFF_ACK, screened.language).format(id=handoff_id)
            return self._response(
                text,
                "handoff",
                ctx,
                tracker,
                started,
                request_id,
                screened,
                OutputDecision(""),
                handoff={"id": handoff_id, "status": "pending"},
            )
        checked = check_output(
            str(state.get("answer") or "").strip(), {s.id for s in ctx.sources}, screened.language
        )
        outcome = "blocked" if checked.blocked else str(state.get("outcome") or "answered")
        return self._response(
            checked.text, outcome, ctx, tracker, started, request_id, screened, checked
        )

    # -- operator reply -> resume the paused conversation --------------------------------
    def resume(
        self, handoff: dict[str, Any], operator: str, action: str, message: str, request_id: str
    ) -> ChatResponse:
        if not self.hitl.claim_reply(handoff["id"], operator, action, message):
            raise OrchestratorError(409, "handoff_not_pending", "Handoff already answered.")
        started = time.monotonic()
        merchant = Principal(
            handoff["merchant_id"],
            handoff["tenant"],
            frozenset(handoff["scopes"].split()),
            jti=f"handoff:{handoff['id']}",
        )
        tracker = UsageTracker(max_cost_usd=self.settings.max_cost_per_chat_usd)
        token = current_usage.set(tracker)
        ctx = self._context(merchant, handoff["session_id"], handoff["language"])
        try:
            state = self._invoke(
                Command(resume={"operator_action": action, "operator_message": message}),
                ctx,
                handoff["thread_id"],
            )
        except Exception:
            self.hitl.release(handoff["id"])
            raise
        finally:
            current_usage.reset(token)
        checked = check_output(
            str(state.get("answer") or "").strip(), {s.id for s in ctx.sources}, handoff["language"]
        )
        self.hitl.resolve(handoff["id"], checked.text)
        event = {"handoff_id": handoff["id"], "answer": checked.text, "request_id": request_id}
        self.hitl.add_event(merchant.sub, handoff["session_id"], "handoff.resolved", event)
        self.notify("merchant", "handoff.resolved", {**event, "merchant_id": merchant.sub})
        screened = InputDecision(message, "ok", handoff["language"])
        return self._response(
            checked.text,
            "handoff_resolved",
            ctx,
            tracker,
            started,
            request_id,
            screened,
            checked,
            handoff={"id": handoff["id"], "status": "resolved"},
        )

    def reset(self, principal: Principal, session_id: str) -> None:
        self.checkpointer.delete_thread(self.thread_id(principal, session_id))

    def _response(
        self,
        answer: str,
        outcome: str,
        ctx: ToolContext,
        tracker: UsageTracker,
        started: float,
        request_id: str,
        screened: InputDecision,
        checked: OutputDecision,
        handoff: dict[str, Any] | None = None,
    ) -> ChatResponse:
        cited = set(_CITATION.findall(answer))
        sources = [s for s in ctx.sources if s.id in cited] or ctx.sources
        delegated = {e.tool.removeprefix("ask_") for e in ctx.trace if e.agent == "supervisor"}
        delegated = {"escalation" if d == "escalate_to_human" else d for d in delegated}
        return ChatResponse(
            answer=answer.strip(),
            outcome=outcome,
            session_id=ctx.session_id,
            agents_used=["supervisor", *sorted(delegated - {"user"})],
            tool_calls=[
                {
                    "agent": e.agent,
                    "tool": e.tool,
                    "status": e.status,
                    "latency_ms": e.latency_ms,
                    "arguments": e.arguments,
                }
                for e in ctx.trace
            ],
            sources=[s.model_dump() for s in sources] if outcome != "blocked" else [],
            handoff=handoff,
            guardrails={
                "input": {"category": screened.category, "redacted": screened.redacted},
                "output": {"flags": checked.flags},
            },
            usage=tracker.summary(),
            latency_ms=int((time.monotonic() - started) * 1000),
            request_id=request_id,
        )
