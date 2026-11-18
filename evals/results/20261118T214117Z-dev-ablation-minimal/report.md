# Eval report: `dev`

- Generated: 2026-11-18 21:41 UTC
- Runs: 40 (40 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 98% |
| Routing (expected agents used) | 98% |
| Tools (expected tools called) | 98% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 95% |
| pass^1 (case passes in every repeat) | 95% |
| Latency per case p50 / p95 | 12.9s / 19.9s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0254 / US$ 1.0172 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| D01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D08 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D20 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| D21 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather |  |
| D22 | 1/1 | answered | supervisor, support | ask_support, get_sales_summary |  |
| D23 | 1/1 | answered | supervisor, support | ask_support, get_receivables |  |
| D24 | 1/1 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| D25 | 1/1 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary, lookup_decline_code |  |
| D26 | 1/1 | answered | supervisor, support | ask_support, get_terminal_status |  |
| D27 | 1/1 | answered | supervisor, support | ask_support, get_receivables |  |
| D28 | 1/1 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary, lookup_decline_code |  |
| D29 | 0/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| D30 | 1/1 | answered | supervisor, support | ask_support, get_tickets |  |
| D31 | 1/1 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| D32 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_sales_summary, get_weather |  |
| D33 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, search_kb |  |
| D34 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_receivables, get_sales_summary, search_kb |  |
| D35 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_exchange_rate, get_sales_summary |  |
| D36 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, lookup_decline_code, search_kb |  |
| D37 | 1/1 | clarify | supervisor |  |  |
| D38 | 0/1 | answered | supervisor |  |  |
| D39 | 1/1 | blocked | supervisor |  |  |
| D40 | 1/1 | blocked | supervisor |  |  |
