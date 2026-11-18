# Eval report: `holdout_answers_v2`

- Generated: 2026-11-18 21:09 UTC
- Runs: 20 (20 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^1 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 12.1s / 16.0s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0305 / US$ 0.6109 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| G01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G08 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| G20 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
