# Eval report: `handoff`

- Generated: 2026-11-19 20:29 UTC
- Runs: 48 (16 cases x 3 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 90% |
| Outcome as expected (answer / clarify / handoff / block) | 90% |
| Routing (expected agents used) | 90% |
| Tools (expected tools called) | 90% |
| Content (required terms, no forbidden terms) | 90% |
| All checks passed (per run) | 90% |
| pass^3 (case passes in every repeat) | 88% |
| Latency per case p50 / p95 | 13.8s / 21.2s |
| LLM calls per turn (mean, last turn) | 4.9 |
| Cost per case (mean / total) | US$ 0.0284 / US$ 1.2219 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| H01 | 3/3 | handoff | supervisor, escalation | escalate_to_human |  |
| H02 | 3/3 | handoff | supervisor, escalation, knowledge, support / supervisor, escalation, support | ask_knowledge, ask_support, escalate_to_human, get_recent_transactions, get_sales_summary, search_kb / ask_support, escalate_to_human, get_recent_transactions, get_sales_summary |  |
| H03 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_sales_summary |  |
| H04 | 3/3 | handoff | supervisor, escalation | escalate_to_human |  |
| H05 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_terminal_status, get_tickets / ask_support, escalate_to_human, get_terminal_status, get_tickets / ask_support, escalate_to_human, get_terminal_status, get_tickets, propose_terminal_service |  |
| H06 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_receivables, get_sales_summary |  |
| H07 | 3/3 | handoff | supervisor, escalation | escalate_to_human |  |
| H08 | 3/3 | handoff | supervisor, escalation, support | ask_support, escalate_to_human, get_recent_transactions, get_sales_summary |  |
| H09 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H10 | 3/3 | answered | supervisor, support | ask_support, get_sales_summary, verify_answer |  |
| H11 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H12 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H13 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H14 | 3/3 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H15 | 1/3 | None / answered |  / supervisor, knowledge |  / ask_knowledge, search_kb, verify_answer | {"code": "llm_unavailable", "message": "provider_error_400"} |
| H16 | 0/3 | None |  |  | {"code": "llm_unavailable", "message": "provider_error_400"} |
