# Getnet Multi-Agent Support

[![CI](https://github.com/luanmsgabriel-ops/getnet-multi-agent-delivery/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/luanmsgabriel-ops/getnet-multi-agent-delivery/actions/workflows/ci.yml)

A support assistant for Getnet merchants. An LLM **supervisor** (the Router) decomposes each message and delegates to specialist agents, which it calls as tools:
- **Knowledge**: hybrid RAG over Getnet's official site, plus web search, weather and the BCB exchange rate.
- **Support**: the merchant's own sales, receivables, terminals and tickets.
- **Escalation**: human handoff with pause and resume.

The supervisor reads the specialists' results, decides again and writes the answer. Every route is authenticated, guarded, traced and costed.

**Presentation video (v3, about 4.5 min, Portuguese):** [watch on Google Drive](https://drive.google.com/drive/folders/1zeak-GvFBgDZp9MjQNwX-xRvVy_HyQbq)

## Results (real model calls, committed under `evals/results/`)

| Eval set | Checks pass | Judge pass¹ | Latency p50 | Cost per case |
|---|---:|---:|---:|---:|
| The 10 challenge questions (× 3 repeats) | **100%** | 97% | 14 s | US$ 0.027 |
| 40 dev cases: PT/EN, multi-intent, clarify, guardrail (× 3) | 98% | 98% | 12 s | US$ 0.022 |
| 12 multi-turn conversations (× 3) | 92% | 94% | 23 s | US$ 0.039 |
| Human handoff: 8 must escalate, 8 must not (× 3) | **100%** | 100% | 13 s | US$ 0.024 |
| Holdout: 20 official FAQ questions with official answers | 90% | 80% | 14 s | US$ 0.024 |
| Fresh holdout: 20 official Q&A from help and product pages (after the RAG changes) | **100%** | 90% | 12 s | US$ 0.031 |
| Long-term memory and long-chat summary (real model) | 6/6 | | | US$ 0.17 total |
| Guardrail: 60 attacks + 60 benign look-alikes | 98.3% blocked, **0% false positives** | | | US$ 0.0016 |

A prompt ablation keeps the current supervisor prompt. Without its guidance, answers carry 55% more unsupported claims, and correctness drops from 4.80 to 4.58. A regression gate (`evals/gates.json`) fails any run that drops below the thresholds, and `.github/workflows/eval.yml` runs eval, judge and gate weekly or on demand.

¹ The judge is from a different model family (GPT via OpenRouter) and grades a blind packet. Against 30 human labels it agrees 87% (Cohen's kappa 0.44) and is more lenient than the human, so read these rates as an upper bound. Details, the routing baseline and the bugs these evals found are in [docs/EVALUATION.md](docs/EVALUATION.md).

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

To add Prometheus, Grafana (dashboard provisioned) and Jaeger with tracing on, run `make obs`. For the human-operator side, `make operator-token` issues a token with the `operator` scope.

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
POST /chat {message, user_id} + Bearer JWT
  -> auth: identity from the token; user_id must match; scopes; rate limit
  -> input guardrail: redact card/CPF/secrets, then LLM classifier (injection, fraud, off-topic)
  -> LangGraph turn (SQLite checkpointer per merchant session):
       prepare (summary + last turns + saved merchant facts) -> SUPERVISOR --tool calls, parallel--> specialists -> SUPERVISOR -> ...
                                   |                                   |
                                   |  ask_knowledge: Knowledge Agent (search_kb, web_search,
                                   |                 get_weather, get_exchange_rate)
                                   |  ask_support:   Support Agent (sales, receivables, terminal,
                                   |                 transactions, decline codes, tickets)
                                   |  ask_user:      clarifying question, ends the turn
                                   '- escalate_to_human: Escalation Agent -> handoff + signed webhook
                                         -> interrupt() ... operator reply -> resume -> SUPERVISOR
  -> output guardrail: citations exist, no prompt leak, no refund/deadline promises, redaction
  -> JSON answer with agents, tool calls, sources, usage, cost and trace_id
```

- **Supervisor.** An LLM with five tools (the four specialists above plus `remember`). It identifies every need in the message and calls specialists in parallel when needs are independent. It reads their structured observations (`status`, `coverage`, `answer`), retries a different way when a result is partial, and writes the final answer in the merchant's language with `[S#]` citations. It is bounded by step, per-turn cost and global budget limits. Its prompt holds general principles only (`app/graph/supervisor.py`).
- **Specialists.** Each specialist is an agent with its own prompt, tools and loop (`app/agents/`). Tools have strict JSON schemas, typed errors (`not_found`, `invalid_argument`, `upstream_timeout`, ...), timeouts and retries, and a circuit breaker on public APIs. No tool takes a merchant id: data access is filtered by the token subject in `app/data/support_repo.py`.
- **Writes and humans.** Agents only read. A ticket is a proposal until the merchant confirms it (`POST /tickets/{id}/confirm`, idempotent). Disputes, suspected fraud and requests for a person pause the graph and notify an operator through a webhook signed with HMAC. The operator answers through `/operator/handoffs/{id}/reply` (`reply`, `instruct` or `close`). The supervisor resumes, and the merchant gets the result via SSE (`/sessions/{id}/events`) and a webhook. No deadlines or refunds are ever promised.
- **Memory.** The conversation is stored per `tenant:merchant:session` with LangGraph's SQLite checkpointer. It survives restarts, including a pending handoff, and `DELETE /sessions/{id}` resets it. Past 8 turns, the oldest are folded into a rolling summary, so long chats keep their facts. Across sessions, the supervisor can `remember` a few allow-listed facts per merchant (business profile, communication preference, recurring context). They are redacted, scoped to the token's merchant, and can be listed or erased with `GET/DELETE /me/memory` ([ADR 009](docs/adr/009-summary-and-merchant-memory.md)).

## RAG pipeline (ingestion -> storage -> retrieval -> generation)

1. **Ingestion** (`app/rag/ingest.py`): a crawler reads the sitemaps of `site.getnet.com.br` (help center, product pages, blog), the product manuals (PDF) and `getnet.net/en`. It strips repeated boilerplate.
2. **Storage**: 171 snapshots in `corpus/docs/` with URL, capture date and SHA-256, committed so builds are reproducible and offline.
3. **Retrieval** (`app/rag/store.py`): 1,058 section-aware chunks, BM25 plus local multilingual embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, ONNX, built into the image), fused by reciprocal rank. On English questions over the Portuguese corpus, hybrid recall@5 is 0.90 versus 0.60 for lexical. On the strict official-FAQ holdout it is 0.58 ([docs/RAG.md](docs/RAG.md)).
4. **Generation**: the Knowledge Agent answers only from retrieved passages and cites them. If they do not cover the question it reports `not_found`, and the supervisor can use web search.

## How the LLMs are used

All agents use Claude through the official `anthropic` SDK inside LangGraph nodes (`app/llm/client.py`). The calls use tool use, strict schemas, structured outputs (guardrail), prompt caching, a per-agent effort level and server-side fallback on refusals.

The default model is **Claude Sonnet 5.5**. On the same cases it matched Claude Opus 5.5 at about a quarter of the cost and half the latency ([ADR 008](docs/adr/008-model-per-agent-by-measurement.md)). Switch with `LLM_MODEL`.

Every call is recorded in a spend ledger with a hard cap (`LLM_BUDGET_USD`).

## Tests and evaluation

```bash
uv sync && uv run pytest        # 104 offline tests: unit, contract, scripted-LLM integration, chaos
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
- **Alerts:** 8 alert rules, each with a runbook entry ([RUNBOOK.md](RUNBOOK.md)).

On the first concurrent run these signals caught an OOM kill and CPU contention in retrieval. Both are fixed ([docs/OBSERVABILITY.md](docs/OBSERVABILITY.md)).

## Security

JWT with scopes, expiry and revocation. Identity comes from the token. Every data read is scoped and filtered by merchant. Rate limits. PII and secrets are redacted before the model. The prompt-injection classifier is measured (98.3% blocked, 0% false positives), and an end-to-end indirect-injection test passes. The container runs non-root and read-only with all capabilities dropped. See [docs/SECURITY.md](docs/SECURITY.md) for the STRIDE table.

## Design decisions and limits

Decisions with alternatives and consequences are in [docs/adr/](docs/adr/).

Current limits:
- Merchant data is fictitious: three merchants, regenerated daily relative to today.
- FAQ answers buried in very long pages are sometimes missed (first holdout 80%; retrieval recall@5 is about 0.6 on both holdouts). Question/answer-aware chunking was tried and gave no gain ([docs/RAG.md](docs/RAG.md)). A reranker is the next candidate.
- Saved style preferences (for example, short answers) are remembered but do not yet visibly change the answer style.
- Rate limits are in memory and the token signer is local. Production would use Redis and an OIDC provider.
- Latency is dominated by LLM calls (about 12-15 s p50 per turn).

## Changelog

- **v1** (2026-11-12): rule-based router and editorial answers; weather and FX declined.
- **v2** (2026-11-16): LLM supervisor added, but off by default and without real-run evidence.
- **v3** (this version): rebuilt around an always-on supervisor with specialists as tools, hybrid RAG over 171 official documents, measured guardrails, human handoff with resume, OpenTelemetry/Prometheus, and committed real-model evals with a human-calibrated judge. About 3,900 non-blank lines of application code in `app/`, down from 11,300.

AI assistance: Claude Code was used to plan, implement and test this version. Design decisions, the evaluation labels and the review are the author's.
