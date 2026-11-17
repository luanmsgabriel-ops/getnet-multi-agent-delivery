# Runbook

Signals: Grafana dashboard **Getnet Multi-Agent Support** (`make obs`, http://127.0.0.1:3000), traces in Jaeger (http://127.0.0.1:16686, search by the `trace_id` returned by `/chat`), JSON logs (`docker compose logs api`, with `request_id` and `trace_id` on every line). Alert rules live in `ops/prometheus/alerts.yml` and are unit-tested in `ops/prometheus/alerts_test.yml`.

| Alert | What it means | First actions |
|---|---|---|
| **ChatErrorRateHigh** (page) | More than 5% of `/chat` calls return 5xx | Check the error `code` in the logs (`llm_unavailable`, `budget_exceeded`). Provider down: check `LLMProviderErrors` and the provider status page. Budget: see below. |
| **LLMProviderErrors** (page) | Claude calls failing (5xx, timeouts, refusals) | The SDK already retries 429/5xx and refusals fall back server-side. Check `llm_errors_total` by `code`. A persistent `provider_error_529` means overload: lower traffic or wait. A burst of `model_refusal` means you should inspect the traces of the affected requests. |
| **LLMBudgetNearlyExhausted** (ticket) | More than 80% of `LLM_BUDGET_USD` spent | Check `llm_cost_usd_total` by agent to find what grew. Raise the budget deliberately or reduce load. At 100% the API answers 503 `budget_exceeded` by design. |
| **CostPerChatHigh** (ticket) | Average cost per turn above US$ 0.20 over an hour | Look for many `web_search` calls or long agent loops in traces (`agent.steps`). Compare with the baseline in the latest eval report. |
| **ChatLatencyP95High** (ticket) | p95 turn latency above 60 s | Find the slowest span in Jaeger (usually `llm.knowledge` or a slow public API). Check `tool_call_seconds` for Open-Meteo or BCB timeouts. |
| **ToolFailureRateHigh** (ticket) | One tool fails in more than 20% of calls | Check `tool_calls_total{status="error"}`. External APIs (Open-Meteo, BCB) have a circuit breaker; answers degrade with an explicit message. For a database tool, check `/ready` and disk space on the `getnet_state` volume. |
| **HandoffsWaiting** (page) | More than 5 merchants waiting for a human for 15 min | Staff the operator queue (`GET /operator/handoffs`). Check that operator webhooks are delivered (`webhook event=... delivered=false` in the logs). |
| **GuardrailBlockSpike** (ticket) | More than 30% of messages blocked | Either an attack wave (same pattern, few senders) or false positives after a change. Sample the blocked requests in the logs (`guardrail` field) and compare with `evals/results/*-guardrail`. |

## Routine operations

| Task | Command |
|---|---|
| Issue a merchant token | `make token MERCHANT=cliente1988` |
| Issue an operator token | `make operator-token OPERATOR=ana` |
| Revoke a token | `docker compose exec api python -m app.security.tokens revoke --token <jwt>` |
| Refresh the knowledge base | `uv run --group ingest python -m app.rag.ingest`, review the diff of `corpus/`, rebuild the image |
| Re-run the evals | `uv run python -m evals.run --split original --repeats 3` (costs money; check the budget first) |
| Reset a conversation | `DELETE /sessions/{session_id}` with the merchant token |
