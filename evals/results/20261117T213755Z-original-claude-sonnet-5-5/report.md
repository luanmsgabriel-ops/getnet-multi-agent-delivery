# Eval report: `original-claude-sonnet-5-5`

- Generated: 2026-11-17 21:37 UTC
- Runs: 30 (10 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^3 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 14.1s / 20.0s |
| LLM calls per turn (mean, last turn) | 5.5 |
| Cost per case (mean / total) | US$ 0.0266 / US$ 0.7970 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| O01 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O02 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| O03 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| O04 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O05 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb |  |
| O06 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O07 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| O08 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, get_terminal_status, get_tickets, lookup_decline_code, search_kb |  |
| O09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O10 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
