# Eval report: `holdout_answers_v3`

- Generated: 2026-11-19 12:53 UTC
- Runs: 60 (60 cases x 1 repeats). Deterministic checks on the last turn; LLM-judge scores are in `judge.md` when present.

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Outcome as expected (answer / clarify / handoff / block) | 98% |
| Routing (expected agents used) | 98% |
| Tools (expected tools called) | 98% |
| Content (required terms, no forbidden terms) | 100% |
| All checks passed (per run) | 98% |
| pass^1 (case passes in every repeat) | 98% |
| Latency per case p50 / p95 | 14.4s / 18.5s |
| LLM calls per turn (mean, last turn) | 5.0 |
| Cost per case (mean / total) | US$ 0.0312 / US$ 1.8699 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| H01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H08 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H20 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H21 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H22 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H23 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H24 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H25 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H26 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H27 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H28 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H29 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H30 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H31 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H32 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H33 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H34 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H35 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H36 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H37 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H38 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H39 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H40 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H41 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H42 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H43 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H44 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H45 | 0/1 | clarify | supervisor |  |  |
| H46 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H47 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H48 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H49 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H50 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H51 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H52 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H53 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H54 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H55 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H56 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H57 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H58 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
| H59 | 1/1 | answered | supervisor, knowledge | ask_knowledge, get_exchange_rate, search_kb |  |
| H60 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb |  |
