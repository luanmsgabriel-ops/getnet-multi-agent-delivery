# Eval report: `handoff-claude-sonnet-5-5`

- Generated: 2026-11-17 21:20 UTC
- Runs: 48 (16 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 100% |
| pass^3 (case passes in every repeat) | 100% |
| Latency per case p50 / p95 | 13.4s / 20.0s |
| LLM calls per turn (mean, last turn) | 4.7 |
| Cost per case (mean / total) | US$ 0.0240 / US$ 1.1499 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| H01 | 3/3 | handoff | supervisor, escalation | escalate_to_human |  |
| H02 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_sales_summary |  |
| H03 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_sales_summary, get_terminal_status, get_tickets / ask_support, escalate_to_human, get_recent_transactions, get_sales_summary, get_tickets |  |
| H04 | 3/3 | handoff | supervisor, escalation / supervisor, escalation, support | ask_support, escalate_to_human, get_sales_summary, get_tickets / escalate_to_human |  |
| H05 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_terminal_status, get_tickets / ask_support, escalate_to_human, get_terminal_status, get_tickets |  |
| H06 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_receivables, get_sales_summary |  |
| H07 | 3/3 | handoff | supervisor, escalation | escalate_to_human |  |
| H08 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions / ask_support, escalate_to_human, get_recent_transactions, get_sales_summary / ask_support, escalate_to_human, get_recent_transactions, get_tickets |  |
| H09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H10 | 3/3 | answered | supervisor, support | ask_support, get_receivables, get_sales_summary / ask_support, get_sales_summary |  |
| H11 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H12 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H13 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H14 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H15 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H16 | 3/3 | answered | supervisor, knowledge, support | ask_knowledge, ask_support, get_receivables, get_sales_summary, search_kb / ask_knowledge, ask_support, get_receivables, search_kb |  |
