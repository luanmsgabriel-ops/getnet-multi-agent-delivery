# Eval report: `dev-claude-sonnet-5-5`

- Generated: 2026-11-17 21:35 UTC
- Runs: 120 (40 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 98% |
| Tools (expected tools called) | 98% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 98% |
| pass^3 (case passes in every repeat) | 98% |
| Latency per case p50 / p95 | 11.8s / 17.5s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0219 / US$ 2.6332 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| D01 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D02 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D03 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D04 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D05 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D06 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D07 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D08 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D10 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D11 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D12 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D13 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D14 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D15 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D16 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D17 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D18 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D19 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D20 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D21 | 3/3 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D22 | 3/3 | answered | supervisor, support | ask_support, get_sales_summary |  |
| D23 | 3/3 | answered | supervisor, support | ask_support, get_receivables |  |
| D24 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| D25 | 3/3 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary, lookup_decline_code / ask_support, get_recent_transactions, lookup_decline_code |  |
| D26 | 3/3 | answered | supervisor, support | ask_support, get_terminal_status / ask_support, get_terminal_status, get_tickets |  |
| D27 | 3/3 | answered | supervisor, support | ask_support, get_receivables |  |
| D28 | 3/3 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary, lookup_decline_code / ask_support, get_recent_transactions, lookup_decline_code |  |
| D29 | 0/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D30 | 3/3 | answered | supervisor, support | ask_support, get_tickets |  |
| D31 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| D32 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_sales_summary, get_weather |  |
| D33 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb |  |
| D34 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_receivables, get_sales_summary, search_kb |  |
| D35 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_exchange_rate, get_sales_summary |  |
| D36 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, lookup_decline_code, search_kb |  |
| D37 | 3/3 | clarify | supervisor |  |  |
| D38 | 3/3 | clarify | supervisor |  |  |
| D39 | 3/3 | blocked | supervisor |  |  |
| D40 | 3/3 | blocked | supervisor |  |  |
