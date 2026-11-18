# Eval report: `dev`

- Generated: 2026-11-18 18:16 UTC
- Runs: 5 (5 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^1 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 4.9s / 13.5s |
| LLM calls per turn (mean, last turn) | 2.8 |
| Cost per case (mean / total) | US$ 0.0101 / US$ 0.0503 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| D02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D37 | 1/1 | clarify | supervisor |  |  |
| D39 | 1/1 | blocked | supervisor |  |  |
| D40 | 1/1 | blocked | supervisor |  |  |
