# Eval report: `original-claude-sonnet-5-5`

- Generated: 2026-11-17 21:13 UTC
- Runs: 30 (10 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 97% |
| All checks passed (per run) | 97% |
| pass^3 (case passes in every repeat) | 90% |
| Latency per case p50 / p95 | 14.9s / 18.7s |
| LLM calls per turn (mean, last turn) | 5.6 |
| Cost per case (mean / total) | US$ 0.0276 / US$ 0.8275 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| O01 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O02 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| O03 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| O04 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O05 | 2/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb | [["Wi-Fi", "WiFi", "wifi"]] |
| O06 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O07 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| O08 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, get_terminal_status, get_tickets, lookup_decline_code, search_kb / ask_knowledge, ask_support, get_recent_transactions, get_terminal_status, lookup_decline_code, search_kb |  |
| O09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| O10 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
