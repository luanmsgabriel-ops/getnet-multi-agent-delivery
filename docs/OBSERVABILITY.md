# Observability, reliability and cost

`make obs` starts the API with Prometheus (`:9090`), Grafana (`:3000`, dashboard provisioned) and Jaeger (`:16686`). All UIs bind to localhost.

| Signal | How |
|---|---|
| Traces | OpenTelemetry, OTLP/HTTP to Jaeger. Span tree: `POST /chat` → `llm.guardrail` → `llm.supervisor` → `tool.ask_*` → `agent.*` → `tool.*` and `llm.*`. LLM spans carry model, tokens (including cache reads) and cost. Every `/chat` response returns its `trace_id`. |
| Metrics | `GET /metrics`, scraped by Prometheus: turns by outcome, latency and cost per turn (histograms), LLM calls, tokens, cost, errors and latency per agent, tool calls and latency, guardrail decisions, handoffs opened, pending and time to operator reply, feedback, budget spent and limit. Labels never include merchant ids or text (tested). |
| Logs | JSON on stdout with `request_id` and `trace_id`. One `chat_turn` line per turn records outcome, agents, tools, cost, latency and guardrail result, never the message text (tested). |
| Dashboard | `ops/grafana/dashboards/getnet-agents.json`, 15 panels covering traffic, latency, cost, budget, agents, tools, guardrails, handoffs, feedback and errors. |
| Alerts | 8 Prometheus rules (`ops/prometheus/alerts.yml`), unit-tested with `promtool` in CI. Each one has a first-action entry in `RUNBOOK.md`. |
| Online quality | `POST /feedback` (up or down per `request_id`) complements the offline evals. |
| Cost control | A ledger with a hard cap (`LLM_BUDGET_USD`), a per-turn cap, and cost computed from real `usage` (cache reads and writes included). Prices are dated in `app/llm/pricing.py`. |

## What it caught (2026-11-17, real traffic)

1. **OOM under concurrency.** With 3 concurrent clients, the API container was killed (`oom`, exit 137). The embedding model takes about 0.6 GB and 49 s to load on one CPU, and it was loaded lazily without a lock, so concurrent first requests loaded several copies. Fix: one locked load in a background thread at startup; `/ready` waits for the index; regression test with 8 threads. After the fix the same traffic ran with 0 restarts, at about 720 MB.
2. **CPU contention in retrieval.** A trace showed one `tool.search_kb` taking 14 s. The ONNX query embedding was competing for the container's single CPU. Fix: one ONNX thread per query (about 170 ms each) and 2 CPUs for the API.
3. **Latency is dominated by LLM calls.** In the same trace, the supervisor's first decision took 18.6 s and one Support Agent step 17.5 s. The `ChatLatencyP95High` alert went to `pending` (p95 85 s with 3 concurrent clients). The levers are the reasoning effort per agent and the model per agent. They are measured on the eval set (see `docs/EVALUATION.md`), not changed by guesswork.

Snapshot with the full numbers and one trace: `evals/results/*-observability/`.
