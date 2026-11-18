# Eval report: `multi_turn-claude-sonnet-5-5`

- Generated: 2026-11-17 21:17 UTC
- Runs: 36 (12 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 92% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 92% |
| pass^3 (case passes in every repeat) | 92% |
| Latency per case p50 / p95 | 22.8s / 36.5s |
| LLM calls per turn (mean, last turn) | 5.1 |
| Cost per case (mean / total) | US$ 0.0388 / US$ 1.3969 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| M01 | 3/3 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary / ask_support, get_sales_summary |  |
| M02 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| M03 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| M04 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| M05 | 3/3 | answered | supervisor, support | ask_support, get_receivables |  |
| M06 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| M07 | 0/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| M08 | 3/3 | answered | supervisor, support | ask_support, get_recent_transactions, get_terminal_status / ask_support, get_terminal_status |  |
| M09 | 3/3 | answered | supervisor |  |  |
| M10 | 3/3 | answered | supervisor, support | ask_support, get_receivables |  |
| M11 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| M12 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
