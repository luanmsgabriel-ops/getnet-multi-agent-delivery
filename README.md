# Getnet Multi-Agent Support

[![CI](https://github.com/luanmsgabriel-ops/getnet-multi-agent-delivery/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/luanmsgabriel-ops/getnet-multi-agent-delivery/actions/workflows/ci.yml)

A support assistant for Getnet merchants. An LLM **supervisor** (the Router) decomposes each message and delegates to specialist agents, which it calls as tools:
- **Knowledge**: hybrid RAG over Getnet's official site, plus web search, weather and the BCB exchange rate.
- **Support**: the merchant's own sales, receivables, terminals and tickets.
- **Escalation**: human handoff with pause and resume.

The supervisor reads the specialists' results, decides again and writes the answer. Every route is authenticated, guarded, traced and costed.

**Presentation video (v3, about 4.5 min, Portuguese):** [watch on Google Drive](https://drive.google.com/drive/folders/1zeak-GvFBgDZp9MjQNwX-xRvVy_HyQbq)

## Results (v4 final regression, real model calls, committed under `evals/results/`)

Claude Sonnet 5.5 for the agents, Claude Haiku 5.5 for the answer verifier. 95% intervals in brackets (Wilson for rates); `uv run python -m evals.stats <runs>` rebuilds the table.

| Eval set | Checks pass | Judge pass¹ | Correctness (1-5) | Latency p50 | Cost per case |
|---|---|---|---:|---:|---:|
| The 10 challenge questions (× 3 repeats) | **100%** [89-100] | **100%** [89-100] | 4.87 | 16 s | US$ 0.031 |
| 40 dev cases: PT/EN, multi-intent, clarify, guardrail | 98% [87-100] | 98% [87-100] | 4.67 | 15 s | US$ 0.024 |
| 12 multi-turn conversations | 83% → 92%² [55-95] | 100% [76-100] | 4.92 | 13 s | US$ 0.043 |
| Human handoff: 8 must escalate, 8 must not (× 3) | 90% [78-95]³ | 100% [92-100] | 4.91 | 14 s | US$ 0.025 |
| Holdout v3: 60 official Q&A, frozen before the v4 code | 98% [91-100] | 97% [89-99] | 4.75 | 15 s | US$ 0.032 |
| Tool selection / arguments, 40 requests (10 tools) | 100% / 98% | | | | US$ 0.007 |
| Load: 10 concurrent merchants, 5 min | 100% available | | | p95 **27.3 s** | US$ 0.026 |
| Guardrail, our set: 60 attacks + 60 benign look-alikes | 98.3% blocked, **0% false positives** | | | | |
| Guardrail, public sets (deepset, Lakera, PT sample): 278 prompts | 90.6% blocked, **0% false positives** | | | | |
| Indirect injection at scale / multi-turn attacks / memory poisoning | 0/20 obeyed · 0/6 failed · 0 stored | | | | |

¹ The judge is from another model family (GPT via OpenRouter) and grades a blind packet. Two human raters labelled the same 50 answers independently. The judge agreed with the first rater on 98% (Cohen's kappa 0.85, Gwet's AC1 0.98) and with the second on 100%. The two raters agreed with each other on 98% ([docs/EVALUATION.md](docs/EVALUATION.md)).
² One miss was in the checker, not the answer: "Wi-Fi" was written with a non-breaking hyphen. The checker now normalizes Unicode dashes; 83% is the score as first recorded.
³ The 5 failures are provider HTTP 400 errors on two "must not escalate" cases. A rerun passed 2/2. The provider's error text is now logged, so the next one will be explained.

A regression gate (`evals/gates.json`) fails any run below its thresholds, and `.github/workflows/eval.yml` runs eval, judge and gate weekly or on demand.

## What changed since v3

Each change answers a point from the v3 evaluation and was decided by the author before it was built ([docs/DECISIONS.md](docs/DECISIONS.md)).

| Area | v3 | v4 | Evidence |
|---|---|---|---|
| Retrieval | MiniLM, recall@5 about 0.6 | EmbeddingGemma-300m. Holdout v3 recall@5 0.73 (target 0.8, not met), recall@10 0.81, MRR 0.34 → 0.52. Rerankers measured and rejected: 15-50 s per query on CPU | [ADR 011](docs/adr/011-embedding-model-instead-of-reranker.md) |
| Answer verification | grounding check on figures only | Claude Haiku checks higher-risk claims against the same evidence. One replan if the turn is young; otherwise unsupported sentences are removed with a limitation | [ADR 012](docs/adr/012-final-answer-verifier.md), [ADR 018](docs/adr/018-latency-levers-under-load.md) |
| Streaming | none | `POST /chat/stream` (SSE). The input classifier runs in parallel with the first supervisor step | [ADR 013](docs/adr/013-parallel-classifier-and-streaming.md) |
| Judge calibration | 30 labels, one rater, kappa 0.44 | 70 + 50 labels, two independent raters, stratified sample, kappa and AC1 with intervals | [docs/EVALUATION.md](docs/EVALUATION.md) |
| State and identity | SQLite, in-process rate limit, local HS256 signer | Postgres (conversations, handoffs, memory, ledger), Redis (shared rate limits), OIDC tokens checked against the issuer's JWKS | [ADR 014](docs/adr/014-postgres-state-redis-rate-limits.md), [ADR 015](docs/adr/015-oidc-tokens-via-jwks.md) |
| Saved style preference | saved, but the answer did not change (v3 gap) | followed: with "short answers, no tables" saved, answers are 33-41% of their usual length, 3-5 lines, no tables, facts and citations kept (two runs, `evals.style_preference`) | `evals/results/20261119T235309Z-style-preference-run1`, `20261119T235502Z-style-preference-run2` |
| Human oversight | API only | Operator console, Telegram channel with replies, 15/60 min deadlines with reminders, audit trail. The operator's text is screened too; tested end to end with a real bot | [ADR 016](docs/adr/016-operator-console-telegram-deadlines.md), [docs/HITL.md](docs/HITL.md) |
| Actions | tickets only | Anticipation of receivables and terminal service, in two phases: the model proposes, only the merchant confirms, idempotent and audited | [ADR 017](docs/adr/017-two-phase-actions.md) |
| Security evidence | our own 120 prompts | Public datasets, indirect injection at scale, multi-turn attacks, memory poisoning | [docs/SECURITY.md](docs/SECURITY.md) |
| Latency and SLOs | p95 85 s with 3 clients (on Opus) | p95 27.3 s with 10 clients; SLOs with burn-rate alerts | [docs/SLO.md](docs/SLO.md) |

Bugs the v4 work found and fixed with tests:
- An ES256 token naming an RSA key returned 500 instead of 401.
- Postgres rejected positional row access, which SQLite had hidden.
- The Redis container could not start with all capabilities dropped.
- The judge's evidence packet leaked the verifier's verdict.
- The judge rebuilt 5 passages where the agent saw 8.
- Uvicorn's 5 s keep-alive reset connections under load.
- The eval checker missed Unicode hyphens.

## Quickstart

Requires Docker with Compose v2. The first build downloads the embedding model and indexes the knowledge base (a few minutes).

```bash
make setup                    # creates .env with random secrets
# edit .env: set ANTHROPIC_API_KEY
make up                       # API on http://127.0.0.1:8000 (Swagger at /docs)
TOKEN=$(make -s token)        # token for the fictitious merchant cliente1988
curl -s http://127.0.0.1:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message": "When will the money from yesterday'\''s sales be deposited?", "user_id": "cliente1988"}'
```

Without `make`, run `python scripts/setup_env.py`, then `docker compose up --build -d`, then `docker compose exec -T api python -m app.security.tokens issue --sub cliente1988`.

`docker compose up` starts the API, Postgres, Redis, a development OIDC provider and a webhook sink. Tokens come from the OIDC provider: `make token` asks it for one, and local HS256 tokens are switched off in compose. `make load` runs the 10-client load test against the running stack; it uses the real model and costs about US$ 4.

To add Prometheus, Grafana (dashboard provisioned) and Jaeger with tracing on, run `make obs`. For the human-operator side, `make operator-token` issues a token with the `operator` scope; paste it into the console at http://127.0.0.1:8000/operator.

```jsonc
// POST /chat response (abridged)
{
  "answer": "Yesterday's (16/11) approved sales come to R$ 2,934.66 net... Debit: today, 17/11 ...",
  "outcome": "answered",            // answered | clarify | limit | blocked | handoff | handoff_resolved
  "session_id": "default",
  "agents_used": ["supervisor", "support"],
  "tool_calls": [{"agent": "support", "tool": "get_receivables", "status": "ok", "latency_ms": 12}],
  "sources": [],                     // [{"id": "S1", "title", "url", "retrieved_at"}] for knowledge answers
  "guardrails": {"input": {"category": "ok", "redacted": []}, "output": {"flags": []}},
  "usage": {"llm_calls": 4, "input_tokens": 4016, "output_tokens": 1506, "cost_usd": 0.0519},
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "latency_ms": 13420, "request_id": "..."
}
```

## Architecture and message flow

```text
POST /chat or /chat/stream (SSE) {message, user_id} + Bearer token from the OIDC issuer (checked against its JWKS)
  -> auth: identity from the token; user_id must match; scopes; rate limit (Redis, shared by replicas)
  -> redact card/CPF/secrets; the LLM input classifier (injection, fraud, off-topic) runs in parallel
     with the supervisor's first step and must allow the turn before any tool runs
  -> LangGraph turn (checkpointer in Postgres, per tenant:merchant:session):
       prepare (summary + last turns + saved merchant facts) -> SUPERVISOR --tool calls, parallel--> specialists -> SUPERVISOR -> ...
                                   |                                   |
                                   |  ask_knowledge: Knowledge Agent (search_kb, web_search,
                                   |                 get_weather, get_exchange_rate)
                                   |  ask_support:   Support Agent (sales, receivables, terminal,
                                   |                 transactions, decline codes, tickets,
                                   |                 anticipation and terminal-service proposals)
                                   |  ask_user:      clarifying question, ends the turn
                                   '- escalate_to_human: Escalation Agent -> handoff -> webhook + Telegram
                                         -> interrupt() ... operator (console or Telegram, screened) -> resume
  -> VERIFY: Claude Haiku checks figures, dates and merchant data against the same evidence;
             one replan while the turn is under 12 s, otherwise unsupported sentences are removed
  -> output guardrail: citations exist, no prompt leak, no refund/deadline promises, redaction
  -> JSON answer (or SSE status/delta/final events) with agents, tool calls, sources, usage, cost and trace_id
```

- **Supervisor.** An LLM with five tools (the four specialists above plus `remember`). It identifies every need in the message and calls specialists in parallel when needs are independent. It reads their structured observations (`status`, `coverage`, `answer`), retries a different way when a result is partial, and writes the final answer in the merchant's language with `[S#]` citations. It is bounded by step, per-turn cost and global budget limits. Its prompt holds general principles only (`app/graph/supervisor.py`).
- **Specialists.** Each specialist is an agent with its own prompt, tools and loop (`app/agents/`). Tools have strict JSON schemas, typed errors (`not_found`, `invalid_argument`, `upstream_timeout`, ...), timeouts and retries, and a circuit breaker on public APIs. No tool takes a merchant id: data access is filtered by the token subject in `app/data/support_repo.py`.
- **Writes and humans.** Agents never write on their own. A ticket, an anticipation of receivables or a terminal replacement/technician visit is a proposal until the merchant confirms it (`POST /tickets/{id}/confirm`, `POST /actions/{id}/confirm` with `Idempotency-Key`); proposals expire in 10 minutes and every action is audited (`GET /actions/{id}`). The anticipation fee in the demo data is fictitious and labelled as such ([ADR 017](docs/adr/017-two-phase-actions.md)). Disputes, suspected fraud and requests for a person pause the graph and notify an operator through a webhook signed with HMAC. The operator works from a console at `/operator` (queue, case with the facts already checked, reply, audit trail) or from Telegram (`/reply`, `/instruct`, `/close`); both go through `/operator/handoffs/{id}/reply` (`reply`, `instruct` or `close`) and the operator's text passes its own guardrail. Unanswered handoffs are raised to urgent after 15 min (high) or 60 min (normal), with a reminder ([docs/HITL.md](docs/HITL.md)). The supervisor resumes, and the merchant gets the result via SSE (`/sessions/{id}/events`) and a webhook. No deadlines or refunds are ever promised.
- **Memory.** The conversation is stored per `tenant:merchant:session` with LangGraph's checkpointer: Postgres in `docker compose`, shared by replicas, or a local SQLite file when `STATE_DATABASE_URL` is unset (tests, a quick local run, [ADR 014](docs/adr/014-postgres-state-redis-rate-limits.md)). It survives restarts, including a pending handoff, and `DELETE /sessions/{id}` resets it. Past 8 turns, the oldest are folded into a rolling summary, so long chats keep their facts. Across sessions, the supervisor can `remember` a few allow-listed facts per merchant (business profile, communication preference, recurring context). They are redacted, scoped to the token's merchant, and can be listed or erased with `GET/DELETE /me/memory` ([ADR 009](docs/adr/009-summary-and-merchant-memory.md)).

## RAG pipeline (ingestion -> storage -> retrieval -> generation)

1. **Ingestion** (`app/rag/ingest.py`): a crawler reads the sitemaps of `site.getnet.com.br` (help center, product pages, blog), the product manuals (PDF) and `getnet.net/en`. It strips repeated boilerplate.
2. **Storage**: 171 snapshots in `corpus/docs/` with URL, capture date and SHA-256, committed so builds are reproducible and offline.
3. **Retrieval** (`app/rag/store.py`):
   - 1,058 section-aware chunks, embedded with `google/embeddinggemma-300m` (local ONNX, built into the image) and ranked by cosine similarity;
   - each search returns 8 passages, and BM25 stays as the fallback;
   - recall@5 is 0.73 on the frozen holdout (v3: 0.52), with recall@10 0.81 and MRR 0.52;
   - cross-encoder rerankers were measured and rejected: 15-50 s per query on CPU ([docs/RAG.md](docs/RAG.md), [ADR 011](docs/adr/011-embedding-model-instead-of-reranker.md)).
4. **Generation**: the Knowledge Agent answers only from retrieved passages and cites them. If they do not cover the question it reports `not_found`, and the supervisor can use web search.

## How the LLMs are used

All agents use Claude through the official `anthropic` SDK inside LangGraph nodes (`app/llm/client.py`). The calls use tool use, strict schemas, structured outputs (guardrail), prompt caching, a per-agent effort level and server-side fallback on refusals.

The default model is **Claude Sonnet 5.5**. On the same cases it matched Claude Opus 5.5 at about a quarter of the cost and half the latency ([ADR 008](docs/adr/008-model-per-agent-by-measurement.md)). Switch with `LLM_MODEL`.

The answer verifier uses **Claude Haiku 5.5** (`VERIFIER_MODEL`). It checks the higher-risk claims of each answer against the evidence the agents gathered, before the answer leaves ([ADR 012](docs/adr/012-final-answer-verifier.md)). The input classifier and the operator-text classifier use the default model with low effort.

Every call is recorded in a spend ledger with a hard cap (`LLM_BUDGET_USD`).

## Tests and evaluation

```bash
uv sync && uv run pytest        # 158 tests: unit, contract, scripted-LLM integration, chaos (live ones need TEST_*_URL)
make lint                       # ruff + mypy --strict
uv run python -m evals.run --split dev --repeats 3        # real model, costs money
uv run python -m evals.judge evals/results/<run>          # independent judge (OPENROUTER_API_KEY)
uv run python -m evals.gate evals/results/<run> --split dev   # regression gate
```

CI runs on every push:
- lint, types and the full offline test suite;
- an image build plus a smoke test of the hardened container;
- pip-audit, bandit, gitleaks and Trivy;
- `promtool` unit tests for the alert rules.

Real-model evals are a deliberate, budgeted step. They run manually or weekly through `.github/workflows/eval.yml` and stop at the regression gate. Their results are committed.

## Observability and operations

- **Tracing:** OpenTelemetry spans per agent, tool and LLM call, with tokens and cost, exported to Jaeger.
- **Metrics:** Prometheus at `/metrics`, with no merchant ids in labels.
- **Logs:** JSON, with `request_id` and `trace_id`.
- **Dashboard:** a provisioned Grafana dashboard.
- **Alerts:** 13 alert rules, including SLO burn-rate alerts, each with a `promtool` test and a runbook entry ([RUNBOOK.md](RUNBOOK.md), [docs/SLO.md](docs/SLO.md)).

On the first concurrent run these signals caught an OOM kill and CPU contention in retrieval. Both are fixed ([docs/OBSERVABILITY.md](docs/OBSERVABILITY.md)).

## Security

Tokens come from an OIDC issuer and are checked against its JWKS (a development provider runs in compose, [ADR 015](docs/adr/015-oidc-tokens-via-jwks.md)), with scopes, expiry and revocation. Identity comes from the token. Every data read is scoped and filtered by merchant. Rate limits. PII and secrets are redacted before the model. The prompt-injection classifier is measured on our own set (98.3% blocked, 0% false positives) and on public sets we did not write (90.6% blocked, 0% false positives, [docs/SECURITY.md](docs/SECURITY.md)). Indirect injection at scale (0/20 obeyed), multi-turn attacks (0/6) and memory poisoning (0 stored) are measured end to end. The container runs non-root and read-only with all capabilities dropped. See [docs/SECURITY.md](docs/SECURITY.md) for the STRIDE table.

## Design decisions and limits

Decisions with alternatives and consequences are in [docs/adr/](docs/adr/).

Current limits:
- Merchant data is fictitious: three merchants, regenerated daily relative to today.
- Retrieval recall@5 is 0.73 on the frozen holdout (target 0.8, not met). Cross-encoder rerankers would help but take 15-50 s per query on CPU, so they wait for a GPU or a hosted reranker ([ADR 011](docs/adr/011-embedding-model-instead-of-reranker.md)).
- The input classifier blocks 90.6% of public attack prompts (target 95%). The misses do not reach any data, because authorization does not depend on the classifier ([docs/SECURITY.md](docs/SECURITY.md)).
- The OIDC provider in compose is a development stand-in that issues tokens to any client; production points `OIDC_ISSUER` at the company's identity provider.
- Latency is dominated by model calls in sequence: under 10 concurrent merchants, p50 14.7 s and p95 27.3 s per turn (`make load`, [ADR 018](docs/adr/018-latency-levers-under-load.md)). The first specialist starts within 7.9 s at p95, above the 5 s target ([docs/SLO.md](docs/SLO.md)).

## Changelog

- **v1** (2026-11-12): rule-based router and editorial answers; weather and FX declined.
- **v2** (2026-11-16): LLM supervisor added, but off by default and without real-run evidence.
- **v3** (2026-11-18): rebuilt around an always-on supervisor with specialists as tools, hybrid RAG over 171 official documents, measured guardrails, human handoff with resume, OpenTelemetry/Prometheus, and committed real-model evals with a human-calibrated judge. About 3,900 non-blank lines of application code in `app/`, down from 11,300.
- **v4** (this version, 2026-11-19): the changes in the table above, measured with the real model under load. About 5,650 non-blank lines in `app/`; the growth is the operator console, two-phase actions, OIDC and the Postgres/Redis state layer.

AI assistance: Claude Code was used to plan, implement and test this version. Design decisions, the evaluation labels and the review are the author's.
