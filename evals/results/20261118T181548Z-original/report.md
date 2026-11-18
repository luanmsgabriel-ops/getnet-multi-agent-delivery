# Eval report: `original`

- Generated: 2026-11-18 18:15 UTC
- Runs: 10 (10 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^1 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 14.9s / 18.3s |
| LLM calls per turn (mean, last turn) | 5.5 |
| Cost per case (mean / total) | US$ 0.0338 / US$ 0.3385 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| O01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| O03 | 1/1 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| O04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O05 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb |  |
| O06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| O08 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, get_terminal_status, lookup_decline_code, search_kb |  |
| O09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
