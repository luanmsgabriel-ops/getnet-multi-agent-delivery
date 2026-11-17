# Eval report: `holdout_answers-claude-sonnet-5-5`

- Generated: 2026-11-17 21:21 UTC
- Runs: 20 (20 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 95% |
| Routing (expected agents used) | 90% |
| Tools (expected tools called) | 90% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 90% |
| pass^1 (case passes in every repeat) | 90% |
| Latency per case p50 / p95 | 13.7s / 18.6s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0242 / US$ 0.4839 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| F01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F08 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb |  |
| F09 | 0/1 | clarify | supervisor |  |  |
| F10 | 0/1 | answered | supervisor |  |  |
| F11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| F20 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, search_kb |  |
