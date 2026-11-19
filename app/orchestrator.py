"""Runs chat turns through the supervisor graph: guardrails, memory, handoff and resume."""

import contextvars
import json
import logging
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.actions import ActionStore
from app.agents.base import ToolContext
from app.config import Settings
from app.data.db import Database
from app.graph.supervisor import InputBlocked, build_graph
from app.hitl import notify
from app.hitl.store import HitlStore, due_at
from app.hitl.telegram import TelegramBot
from app.llm.client import (
    BudgetExceeded,
    ConversationBudgetExceeded,
    LLMClient,
    LLMUnavailable,
    UsageTracker,
    current_usage,
)
from app.memory import MemoryStore, render
from app.observability import (
    CHAT_COST,
    CHAT_LATENCY,
    CHAT_TURNS,
    GUARDRAIL,
    HANDOFF_REPLY,
    HANDOFF_SLA_BREACHED,
    HANDOFFS_PENDING,
    OPERATOR_NOTIFICATIONS,
    bind_gauge,
    current_trace_id,
    log_event,
)
from app.schemas import ChatResponse
from app.security.auth import Principal
from app.security.guardrails import (
    InputDecision,
    OutputDecision,
    check_operator,
    check_output,
    classify,
    detect_language,
    redact,
)

log = logging.getLogger("getnet.chat")
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


# The input classifier runs alongside the supervisor's first step (docs/adr/013).
SCREENING = ThreadPoolExecutor(max_workers=8, thread_name_prefix="screen")


def make_checkpointer(settings: Settings, state: Database) -> Any:
    """Conversation state per thread: Postgres when state lives there, else a local SQLite file."""
    if state.url is not None:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        pool: ConnectionPool[Any] = ConnectionPool(
            state.url,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=True,
        )
        saver = PostgresSaver(pool)
        saver.setup()
        return saver
    conn = sqlite3.connect(settings.data_dir / "checkpoints.db", check_same_thread=False)
    return SqliteSaver(conn)


class TurnLimit(Exception):
    """The per-turn cost cap was reached: answer honestly instead of failing."""


TURN_LIMIT = {
    "pt": "Essa solicitação ficou grande demais para eu concluir de uma vez. Pode dividir em "
    "perguntas menores? Assim consigo responder cada parte com os dados certos.",
    "en": "This request got too large for me to finish in one go. Could you split it into "
    "smaller questions? Then I can answer each part with the right data.",
}


class OrchestratorError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _readable(content: Any) -> str:
    """A tool result as the operator should read it: a specialist's answer as plain text,
    anything else as compact JSON."""
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except ValueError:
        return str(content)
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if isinstance(data, dict) and isinstance(data.get("answer"), str):
        return str(data["answer"])
    return json.dumps(data if data is not None else parsed, ensure_ascii=False)


def _pick(texts: dict[str, str], language: str) -> str:
    return texts.get(language, texts["en"])


class Orchestrator:
    def __init__(
        self, settings: Settings, db: Database, llm: LLMClient, state_db: Database | None = None
    ) -> None:
        self.settings, self.db, self.llm = settings, db, llm
        state = state_db or db
        self.hitl = HitlStore(state)
        self.actions = ActionStore(state, db)
        self.memory = MemoryStore(state)
        self.checkpointer = make_checkpointer(settings, state)
        self.graph = build_graph(self.checkpointer)
        bind_gauge(HANDOFFS_PENDING, lambda: float(len(self.hitl.handoffs("pending"))))
        token = settings.telegram_bot_token
        self.telegram = (
            TelegramBot(
                token.get_secret_value(),
                settings.telegram_chat_ids,
                settings.operator_console_url,
            )
            if token is not None and settings.telegram_chat_ids
            else None
        )

    # -- helpers ------------------------------------------------------------------------
    def notify(self, target: str, event: str, payload: dict[str, Any]) -> None:
        """Signed webhook to the operator queue or the merchant app; operator events also go to
        Telegram. Each delivery attempt on a handoff is written to its audit trail."""
        url = (
            self.settings.operator_webhook_url
            if target == "operator"
            else self.settings.merchant_webhook_url
        )
        secret = self.settings.webhook_secret
        channels: list[tuple[str, bool]] = []
        if url:
            ok = notify.send(url, secret.get_secret_value() if secret else None, event, payload)
            channels.append(("webhook", ok))
        if target == "operator" and self.telegram is not None:
            channels.append(("telegram", self.telegram.notify(event, payload)))
        handoff_id = payload.get("handoff_id")
        for channel, ok in channels:
            OPERATOR_NOTIFICATIONS.labels(channel, str(ok).lower()).inc()
            if handoff_id:
                self.hitl.audit(
                    str(handoff_id),
                    "notified",
                    "system",
                    channel=channel,
                    event=event,
                    target=target,
                    delivered=ok,
                )

    # -- operator side ------------------------------------------------------------------
    def sweep_overdue(self, now: datetime | None = None) -> list[str]:
        """Raise overdue handoffs to urgent and remind the operators (once per handoff)."""
        raised = []
        for h in self.hitl.overdue(now or datetime.now(UTC)):
            if not self.hitl.mark_breached(h["id"]):
                continue  # another replica got it first
            HANDOFF_SLA_BREACHED.labels(h["priority"]).inc()
            self.hitl.audit(
                h["id"],
                "sla_breached",
                "system",
                priority_before=h["priority"],
                due_at=due_at(h),
            )
            self.notify(
                "operator",
                "handoff.sla_breached",
                {
                    "handoff_id": h["id"],
                    "reason": h["reason"],
                    "priority": "urgent",
                    "merchant_id": h["merchant_id"],
                    "summary": h["summary"],
                },
            )
            raised.append(h["id"])
        return raised

    def case(self, handoff: dict[str, Any]) -> dict[str, Any]:
        """What the operator sees: the handoff, the conversation, the facts the assistant
        already checked (tool results, redacted) and the audit trail. No scopes or thread id."""
        snapshot = self.graph.get_state({"configurable": {"thread_id": handoff["thread_id"]}})
        values = snapshot.values or {}
        conversation = [
            {"merchant": t.get("user", ""), "assistant": t.get("assistant", "")}
            for t in values.get("turns", [])
        ]
        last = str(values.get("user_message") or "")
        if last and (not conversation or conversation[-1]["merchant"] != last):
            conversation.append({"merchant": last, "assistant": None})  # turn still paused
        names: dict[str, str] = {}
        facts = []
        # Results gathered before the pause wait in `pending` until the operator replies.
        held = [{"role": "user", "content": values.get("pending") or []}]
        for msg in [*values.get("messages", []), *held]:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "tool_use":
                    names[str(block.get("id"))] = str(block.get("name"))
                elif block.get("type") == "tool_result":
                    tool = names.get(str(block.get("tool_use_id")), "tool")
                    if tool == "escalate_to_human":
                        continue
                    text, _ = redact(_readable(block.get("content", "")))
                    facts.append({"tool": tool, "result": text[:1500]})
        hidden = {"scopes", "thread_id"}
        return {
            **{k: v for k, v in handoff.items() if k not in hidden},
            "due_at": due_at(handoff),
            "conversation": conversation,
            "facts": facts,
            "audit": self.hitl.audit_trail(handoff["id"]),
        }

    def operator_command(self, operator: str, action: str, handoff_id: str, text: str) -> str:
        """Telegram commands land here and use the same resume path as the console."""
        handoff = self.hitl.handoff(handoff_id)
        if handoff is None:
            return f"{handoff_id} não encontrado."
        try:
            result = self.resume(handoff, operator, action, text, f"tg-{uuid.uuid4().hex[:12]}")
        except OrchestratorError as exc:
            messages = {
                "handoff_not_pending": f"{handoff_id} já foi respondido.",
                "operator_message_blocked": "Mensagem bloqueada pelo filtro de segurança "
                "(tentativa de mudar regras, acessar outro lojista ou confirmar ação). "
                "Nada foi enviado ao lojista.",
            }
            return messages.get(exc.code, f"Não foi possível concluir: {exc.message}")
        return f"✅ {handoff_id} resolvido. O lojista recebeu:\n{result.answer[:1500]}"

    @staticmethod
    def thread_id(principal: Principal, session_id: str) -> str:
        return f"{principal.tenant}:{principal.sub}:{session_id}"

    def _context(
        self,
        principal: Principal,
        session_id: str,
        language: str,
        screening: "Future[InputDecision] | None" = None,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        request_id: str | None = None,
    ) -> ToolContext:
        return ToolContext(
            principal=principal,
            db=self.db,
            now=self.settings.now(),
            llm=self.llm,
            session_id=session_id,
            language=language,
            services={
                "hitl": self.hitl,
                "actions": self.actions,
                "request_id": request_id,
                "notify": self.notify,
                "memory": self.memory,
                "verifier_model": self.settings.verifier_model
                if self.settings.verify_answers
                else None,
                "screening": screening,
            },
            emit=emit,
        )

    @staticmethod
    def _screened(screening: "Future[InputDecision]") -> InputDecision:
        try:
            return screening.result(timeout=120)
        except BudgetExceeded as exc:
            raise OrchestratorError(503, "budget_exceeded", str(exc)) from exc
        except LLMUnavailable as exc:
            raise OrchestratorError(503, "llm_unavailable", str(exc)) from exc

    def _invoke(self, payload: Any, ctx: ToolContext, thread: str) -> dict[str, Any]:
        try:
            state: dict[str, Any] = self.graph.invoke(
                payload,
                config={"configurable": {"ctx": ctx, "thread_id": thread}, "recursion_limit": 30},
            )
            return state
        except ConversationBudgetExceeded as exc:
            raise TurnLimit(str(exc)) from exc
        except BudgetExceeded as exc:
            raise OrchestratorError(503, "budget_exceeded", str(exc)) from exc
        except LLMUnavailable as exc:
            raise OrchestratorError(503, "llm_unavailable", str(exc)) from exc

    # -- merchant turn ------------------------------------------------------------------
    def run(
        self,
        principal: Principal,
        message: str,
        request_id: str,
        session_id: str = "default",
        emit: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ChatResponse:
        started = time.monotonic()
        tracker = UsageTracker(max_cost_usd=self.settings.max_cost_per_chat_usd)
        token = current_usage.set(tracker)
        # Redaction is instant and must happen before any model sees the text; the LLM
        # classifier runs in parallel with the supervisor, gated before tools and answers.
        clean, found = redact(message)
        language = detect_language(clean)
        screening = SCREENING.submit(
            contextvars.copy_context().run, classify, self.llm, clean, found
        )
        ctx = self._context(principal, session_id, language, screening, emit, request_id)
        ctx.status("analyzing")
        try:
            waiting = self.hitl.pending_for(principal.sub, session_id)
            if waiting is not None:
                screened = self._screened(screening)
                if screened.blocked:
                    raise InputBlocked
                text = _pick(HANDOFF_WAIT, language).format(id=waiting["id"])
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
                f"America/Sao_Paulo; reply_language={language}</context>"
            )
            saved = render(self.memory.get(principal.tenant, principal.sub))
            if saved:
                user_turn += f"\n{saved}"
            user_turn += f"\n\n{clean}"
            state = self._invoke(
                {
                    "user_message": clean,
                    "user_turn": user_turn,
                    "steps": 0,
                    "answer": None,
                    "outcome": None,
                    "pending": [],
                    "escalation": None,
                    "handoff_id": None,
                    "verify_attempts": 0,
                },
                ctx,
                self.thread_id(principal, session_id),
            )
        except InputBlocked:
            screened = self._screened(screening)
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
        except TurnLimit:
            screened = self._screened(screening)
            text = _pick(TURN_LIMIT, language)
            return self._response(
                text, "limit", ctx, tracker, started, request_id, screened, OutputDecision("")
            )
        finally:
            current_usage.reset(token)
        screened = self._screened(screening)

        if state.get("__interrupt__"):
            handoff_id = str(state.get("handoff_id"))
            text = _pick(HANDOFF_ACK, language).format(id=handoff_id)
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
            str(state.get("answer") or "").strip(), {s.id for s in ctx.sources}, language
        )
        outcome = "blocked" if checked.blocked else str(state.get("outcome") or "answered")
        return self._response(
            checked.text, outcome, ctx, tracker, started, request_id, screened, checked
        )

    # -- operator reply -> resume the paused conversation --------------------------------
    def resume(
        self, handoff: dict[str, Any], operator: str, action: str, message: str, request_id: str
    ) -> ChatResponse:
        """Operator reply -> guardrail -> claim -> resume the paused graph -> notify."""
        if handoff["status"] != "pending":
            raise OrchestratorError(409, "handoff_not_pending", "Handoff already answered.")
        started = time.monotonic()
        tracker = UsageTracker(max_cost_usd=self.settings.max_cost_per_chat_usd)
        token = current_usage.set(tracker)
        try:
            # The operator is authenticated, but the text still goes through redaction and its
            # own classifier: it must not become a way into another merchant or around rules.
            try:
                screened = check_operator(self.llm, message, handoff["language"])
            except BudgetExceeded as exc:
                raise OrchestratorError(503, "budget_exceeded", str(exc)) from exc
            except LLMUnavailable as exc:
                raise OrchestratorError(503, "llm_unavailable", str(exc)) from exc
            GUARDRAIL.labels("operator", screened.category).inc()
            if screened.blocked:
                self.hitl.audit(
                    handoff["id"],
                    "reply_blocked",
                    operator,
                    action=action,
                    category=screened.category,
                    reason=screened.reason,
                )
                raise OrchestratorError(
                    422,
                    "operator_message_blocked",
                    "The message was blocked by the operator guardrail; nothing was sent.",
                )
            message = screened.text
            if not self.hitl.claim_reply(handoff["id"], operator, action, message):
                raise OrchestratorError(409, "handoff_not_pending", "Handoff already answered.")
            self.hitl.audit(
                handoff["id"],
                "replied",
                operator,
                action=action,
                message=message,
                redacted=screened.redacted,
            )
            merchant = Principal(
                handoff["merchant_id"],
                handoff["tenant"],
                frozenset(handoff["scopes"].split()),
                jti=f"handoff:{handoff['id']}",
            )
            ctx = self._context(
                merchant, handoff["session_id"], handoff["language"], request_id=request_id
            )
            try:
                state = self._invoke(
                    Command(resume={"operator_action": action, "operator_message": message}),
                    ctx,
                    handoff["thread_id"],
                )
            except TurnLimit as exc:
                self.hitl.release(handoff["id"])
                self.hitl.audit(handoff["id"], "resume_failed", "system", error="turn_limit")
                raise OrchestratorError(503, "turn_limit", "Per-turn cost cap reached.") from exc
            except Exception as exc:
                self.hitl.release(handoff["id"])
                self.hitl.audit(handoff["id"], "resume_failed", "system", error=type(exc).__name__)
                raise
        finally:
            current_usage.reset(token)
        checked = check_output(
            str(state.get("answer") or "").strip(), {s.id for s in ctx.sources}, handoff["language"]
        )
        self.hitl.resolve(handoff["id"], checked.text)
        self.hitl.audit(
            handoff["id"],
            "resolved",
            "assistant",
            answer_chars=len(checked.text),
            output_flags=checked.flags,
            cost_usd=round(tracker.cost_usd, 5),
        )
        opened = datetime.fromisoformat(handoff["created_at"])
        HANDOFF_REPLY.observe((datetime.now(UTC) - opened).total_seconds())
        event = {"handoff_id": handoff["id"], "answer": checked.text, "request_id": request_id}
        self.hitl.add_event(merchant.sub, handoff["session_id"], "handoff.resolved", event)
        self.notify("merchant", "handoff.resolved", {**event, "merchant_id": merchant.sub})
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
        agents = ["supervisor", *sorted(delegated - {"user", "remember"})]
        latency_s = time.monotonic() - started
        CHAT_TURNS.labels(outcome).inc()
        CHAT_LATENCY.labels(outcome).observe(latency_s)
        CHAT_COST.observe(tracker.cost_usd)
        GUARDRAIL.labels("input", screened.category).inc()
        for flag in checked.flags:
            GUARDRAIL.labels("output", flag).inc()
        log_event(
            log,
            "chat_turn",
            outcome=outcome,
            agents=agents,
            tools=[f"{e.agent}.{e.tool}:{e.status}" for e in ctx.trace],
            llm_calls=len(tracker.calls),
            cost_usd=round(tracker.cost_usd, 5),
            latency_ms=int(latency_s * 1000),
            guardrail=screened.category,
            redacted=screened.redacted,
            output_flags=checked.flags,
        )
        return ChatResponse(
            answer=answer.strip(),
            outcome=outcome,
            session_id=ctx.session_id,
            agents_used=agents,
            trace_id=current_trace_id(),
            tool_calls=[
                {
                    "agent": e.agent,
                    "tool": e.tool,
                    "status": e.status,
                    "latency_ms": e.latency_ms,
                    "arguments": e.arguments,
                    **({"result": e.result_preview} if self.settings.expose_tool_results else {}),
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
