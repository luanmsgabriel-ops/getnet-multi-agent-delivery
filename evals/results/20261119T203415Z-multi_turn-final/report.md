# Eval report: `multi_turn`

- Generated: 2026-11-19 20:34 UTC
- Runs: 12 (12 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 92% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 92% |
| All checks passed (per run) | 83% |
| pass^1 (case passes in every repeat) | 83% |
| Latency per case p50 / p95 | 26.5s / 37.8s |
| LLM calls per turn (mean, last turn) | 6.2 |
| Cost per case (mean / total) | US$ 0.0429 / US$ 0.5154 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| M01 | 1/1 | answered | supervisor, support | ask_support, get_recent_transactions, get_sales_summary, lookup_decline_code, verify_answer |  |
| M02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather, verify_answer |  |
| M03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, verify_answer |  |
| M04 | 0/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer | [["Wi-Fi", "wifi", "WiFi"]] |
| M05 | 1/1 | answered | supervisor, support | ask_support, get_receivables, verify_answer |  |
| M06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| M07 | 0/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| M08 | 1/1 | answered | supervisor, support | ask_support, get_terminal_status, verify_answer |  |
| M09 | 1/1 | answered | supervisor | verify_answer |  |
| M10 | 1/1 | answered | supervisor, support | ask_support, get_receivables, simulate_anticipation, verify_answer |  |
| M11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_weather, remember, verify_answer |  |
| M12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
