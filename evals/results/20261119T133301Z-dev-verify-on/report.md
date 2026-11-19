# Eval report: `dev`

- Generated: 2026-11-19 13:33 UTC
- Runs: 40 (40 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 98% |
| Tools (expected tools called) | 95% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 95% |
| pass^1 (case passes in every repeat) | 95% |
| Latency per case p50 / p95 | 14.9s / 29.4s |
| LLM calls per turn (mean, last turn) | 6.7 |
| Cost per case (mean / total) | US$ 0.0300 / US$ 1.1989 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| D01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D08 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather, verify_answer |  |
| D17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, verify_answer |  |
| D18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather, verify_answer |  |
| D19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, verify_answer |  |
| D20 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, verify_answer |  |
| D21 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather, verify_answer |  |
| D22 | 1/1 | answered | supervisor, support | ask_support, get_sales_summary, verify_answer |  |
| D23 | 1/1 | answered | supervisor, support | ask_support, get_receivables, verify_answer |  |
| D24 | 1/1 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary, verify_answer |  |
| D25 | 1/1 | answered | supervisor, support | ask_support, get_recent_transactions, lookup_decline_code, verify_answer |  |
| D26 | 1/1 | answered | supervisor, support | ask_support, get_terminal_status, verify_answer |  |
| D27 | 1/1 | answered | supervisor, support | ask_support, get_receivables, verify_answer |  |
| D28 | 1/1 | answered | supervisor, support | ask_support, get_recent_transactions, lookup_decline_code, verify_answer |  |
| D29 | 0/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| D30 | 1/1 | answered | supervisor, support | ask_support, get_tickets, verify_answer |  |
| D31 | 1/1 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary, verify_answer |  |
| D32 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_sales_summary, get_weather, verify_answer |  |
| D33 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb, verify_answer |  |
| D34 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_receivables, get_sales_summary, search_kb, verify_answer |  |
| D35 | 1/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_exchange_rate, get_sales_summary, verify_answer |  |
| D36 | 0/1 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_recent_transactions, search_kb, verify_answer |  |
| D37 | 1/1 | clarify | supervisor |  |  |
| D38 | 1/1 | clarify | supervisor |  |  |
| D39 | 1/1 | blocked | supervisor |  |  |
| D40 | 1/1 | blocked | supervisor |  |  |
