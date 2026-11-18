# Eval report: `original`

- Generated: 2026-11-18 21:50 UTC
- Runs: 1 (1 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^1 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 10.4s / 10.4s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0090 / US$ 0.0090 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| O07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
