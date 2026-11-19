# Eval report: `original`

- Generated: 2026-11-19 20:23 UTC
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
| Latency per case p50 / p95 | 16.1s / 27.6s |
| LLM calls per turn (mean, last turn) | 6.1 |
| Cost per case (mean / total) | US$ 0.0309 / US$ 0.9262 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| O01 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| O02 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather, verify_answer |  |
| O03 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary, verify_answer |  |
| O04 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| O05 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb, verify_answer |  |
| O06 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| O07 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, verify_answer |  |
| O08 | 3/3 | answered | supervisor, support | ask_support, get_recent_transactions, get_terminal_status, get_tickets, lookup_decline_code, verify_answer |  |
| O09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| O10 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
