"""FastAPI application: routes, authentication, rate limiting and error handling."""

import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.config import Settings, get_settings
from app.data.db import Database
from app.data.seed import ensure_seed
from app.llm.client import AnthropicLLM, Ledger, LLMClient
from app.observability import (
    BUDGET_LIMIT,
    BUDGET_SPENT,
    FEEDBACK,
    HTTP_REQUESTS,
    bind_gauge,
    log_event,
    request_id_var,
    setup_logging,
    setup_tracing,
    tracer,
)
from app.orchestrator import Orchestrator, OrchestratorError
from app.rag.store import default_retriever, retriever_loaded
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    Feedback,
    HealthResponse,
    MeResponse,
    OperatorReply,
    ReadyResponse,
)
from app.security.auth import AuthError, Principal, decode_token, require_scope
from app.security.guardrails import redact
from app.security.ratelimit import RateLimiter

log = logging.getLogger("getnet")
bearer = HTTPBearer(auto_error=False)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers


def _error(
    request: Request, status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse.model_validate(
        {
            "error": {"code": code, "message": message},
            "request_id": getattr(request.state, "request_id", None),
        }
    )
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    """Build the app. `llm` overrides the provider (tests inject a scripted fake)."""
    settings = settings or get_settings()
    setup_logging()
    tracing = setup_tracing()
    db = Database(settings.db_path)
    limiter = RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_global_per_minute)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.init()
        ensure_seed(db, settings.today(), settings.tz)
        client = llm
        if client is None and settings.anthropic_api_key is not None:
            ledger = Ledger(db, settings.llm_budget_usd)
            bind_gauge(BUDGET_SPENT, ledger.spent)
            BUDGET_LIMIT.set(settings.llm_budget_usd)
            client = AnthropicLLM(
                settings.anthropic_api_key.get_secret_value(), ledger, model=settings.llm_model
            )
        app.state.orchestrator = Orchestrator(settings, db, client) if client else None
        if settings.warm_knowledge_index:  # load the embedding model once, off the request path
            threading.Thread(target=default_retriever, name="kb-warmup", daemon=True).start()
        log_event(log, "startup", llm_configured=client is not None, tracing=tracing)
        yield

    app = FastAPI(
        title="Getnet Multi-Agent Support",
        version=__version__,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    app.state.settings, app.state.db, app.state.limiter = settings, db, limiter

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            with tracer.start_as_current_span(f"HTTP {request.method}") as span:
                response = await call_next(request)
                route = getattr(request.scope.get("route"), "path", "unmatched")
                span.update_name(f"{request.method} {route}")
                span.set_attributes(
                    {
                        "http.route": route,
                        "request_id": rid,
                        "http.status_code": response.status_code,
                    }
                )
        finally:
            request_id_var.reset(token)
        if route != "/metrics":
            HTTP_REQUESTS.labels(route, str(response.status_code)).inc()
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(AuthError)
    async def _auth_error(request: Request, exc: AuthError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return _error(request, exc.status, exc.code, exc.message, headers)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error(request, exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"msg": "invalid request"}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return _error(request, 422, "invalid_request", f"{loc}: {first['msg']}".strip(": "))

    def principal(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Principal:
        if creds is None:
            raise AuthError(401, "missing_token", "Authorization: Bearer <token> is required.")
        p = decode_token(settings, creds.credentials)
        if db.is_revoked(p.jti):
            raise AuthError(401, "token_revoked", "Token revoked.")
        return p

    def rate_limited(p: Annotated[Principal, Depends(principal)]) -> Principal:
        wait = limiter.check(p.sub)
        if wait is not None:
            retry = str(max(1, round(wait)))
            raise ApiError(429, "rate_limited", "Too many requests.", {"Retry-After": retry})
        return p

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.get(
        "/ready",
        response_model=ReadyResponse,
        tags=["ops"],
        responses={503: {"model": ReadyResponse}},
    )
    def ready() -> JSONResponse:
        checks = {"database": db.ping(), "llm": app.state.orchestrator is not None}
        if settings.warm_knowledge_index:
            checks["knowledge_index"] = retriever_loaded()
        body = ReadyResponse(ready=all(checks.values()), checks=checks)
        return JSONResponse(body.model_dump(), status_code=200 if body.ready else 503)

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> Response:
        """Prometheus scrape endpoint (no merchant data; publish only on the internal network)."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/feedback", status_code=204, tags=["chat"])
    def feedback(body: Feedback, p: Annotated[Principal, Depends(principal)]) -> Response:
        """Merchant rating of an answer: an online quality signal next to the offline evals."""
        require_scope(p, "chat:use")
        comment = redact(body.comment)[0] if body.comment else None
        db.add_feedback(body.request_id, p.sub, body.rating, comment)
        FEEDBACK.labels(body.rating).inc()
        return Response(status_code=204)

    @app.get("/me", response_model=MeResponse, tags=["auth"])
    def me(p: Annotated[Principal, Depends(principal)]) -> MeResponse:
        return MeResponse(sub=p.sub, tenant=p.tenant, scopes=sorted(p.scopes))

    @app.get("/me/memory", tags=["auth"])
    def my_memory(p: Annotated[Principal, Depends(principal)]) -> dict[str, str]:
        """Facts the assistant saved about this merchant (allow-listed categories)."""
        require_scope(p, "chat:use")
        return orch().memory.get(p.tenant, p.sub)

    @app.delete("/me/memory", status_code=204, tags=["auth"])
    def forget_me(p: Annotated[Principal, Depends(principal)]) -> Response:
        """Erase everything the assistant saved about this merchant."""
        require_scope(p, "chat:use")
        orch().memory.clear(p.tenant, p.sub)
        return Response(status_code=204)

    @app.post(
        "/chat",
        tags=["chat"],
        response_model=ChatResponse,
        responses={503: {"model": ErrorResponse}},
    )
    def chat(
        body: ChatRequest, request: Request, p: Annotated[Principal, Depends(rate_limited)]
    ) -> ChatResponse:
        require_scope(p, "chat:use")
        if body.user_id != p.sub:
            raise AuthError(403, "user_mismatch", "user_id does not match the authenticated token.")
        if len(body.message) > settings.max_message_chars:
            raise ApiError(
                422, "message_too_long", f"message exceeds {settings.max_message_chars} characters."
            )
        ensure_seed(db, settings.today(), settings.tz)
        try:
            return orch().run(
                p, body.message, request.state.request_id, body.session_id or "default"
            )
        except OrchestratorError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc

    def orch() -> Orchestrator:
        orchestrator: Orchestrator | None = app.state.orchestrator
        if orchestrator is None:
            raise ApiError(503, "llm_not_configured", "Set ANTHROPIC_API_KEY to enable the agents.")
        return orchestrator

    @app.delete("/sessions/{session_id}", status_code=204, tags=["chat"])
    def reset_session(session_id: str, p: Annotated[Principal, Depends(principal)]) -> Response:
        require_scope(p, "chat:use")
        orch().reset(p, session_id)
        return Response(status_code=204)

    @app.get("/sessions/{session_id}/events", tags=["chat"])
    def session_events(
        session_id: str,
        request: Request,
        p: Annotated[Principal, Depends(principal)],
        after: int = 0,
        wait_s: int = 25,
    ) -> StreamingResponse:
        """Server-sent events for the merchant (e.g. the operator's answer to a handoff)."""
        require_scope(p, "chat:use")
        store = orch().hitl
        last = int(request.headers.get("last-event-id") or after)

        def stream() -> Iterator[str]:
            nonlocal last
            deadline = time.monotonic() + max(1, min(wait_s, 60))
            while time.monotonic() < deadline:
                for event in store.events_after(p.sub, session_id, last):
                    last = event["id"]
                    data = json.dumps(event["payload"], ensure_ascii=False)
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {data}\n\n"
                time.sleep(1)
            yield ": keep-alive\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/handoffs/{handoff_id}", tags=["handoff"])
    def get_handoff(handoff_id: str, p: Annotated[Principal, Depends(principal)]) -> dict[str, Any]:
        require_scope(p, "chat:use")
        handoff = orch().hitl.handoff(handoff_id)
        if handoff is None or handoff["merchant_id"] != p.sub:
            raise ApiError(404, "not_found", "Handoff not found.")
        return {
            k: handoff[k]
            for k in ("id", "status", "reason", "created_at", "replied_at", "final_answer")
        }

    @app.get("/operator/handoffs", tags=["operator"])
    def operator_queue(
        p: Annotated[Principal, Depends(principal)], status: str | None = "pending"
    ) -> list[dict[str, Any]]:
        require_scope(p, "operator")
        hidden = {"scopes", "thread_id"}
        return [
            {k: v for k, v in h.items() if k not in hidden} for h in orch().hitl.handoffs(status)
        ]

    @app.post(
        "/operator/handoffs/{handoff_id}/reply", tags=["operator"], response_model=ChatResponse
    )
    def operator_reply(
        handoff_id: str,
        body: OperatorReply,
        request: Request,
        p: Annotated[Principal, Depends(principal)],
    ) -> ChatResponse:
        require_scope(p, "operator")
        handoff = orch().hitl.handoff(handoff_id)
        if handoff is None:
            raise ApiError(404, "not_found", "Handoff not found.")
        try:
            return orch().resume(
                handoff, p.sub, body.action, body.message, request.state.request_id
            )
        except OrchestratorError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc

    @app.post("/tickets/{ticket_id}/confirm", tags=["tickets"])
    def confirm_ticket(
        ticket_id: str, p: Annotated[Principal, Depends(principal)]
    ) -> dict[str, Any]:
        """Second phase of a write: only the merchant can confirm what the agent proposed."""
        require_scope(p, "tickets:write")
        ticket = orch().hitl.confirm_ticket(p.sub, ticket_id)
        if ticket is None:
            raise ApiError(404, "not_found", "Ticket proposal not found.")
        if ticket["status"] == "expired":
            raise ApiError(410, "proposal_expired", "Proposal expired; ask the assistant again.")
        return ticket

    @app.get("/tickets", tags=["tickets"])
    def list_tickets(p: Annotated[Principal, Depends(principal)]) -> list[dict[str, Any]]:
        require_scope(p, "tickets:read")
        return orch().hitl.tickets(p.sub)

    return app
