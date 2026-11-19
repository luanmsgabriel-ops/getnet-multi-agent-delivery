# Eval report: `holdout_answers_v3`

- Generated: 2026-11-19 20:47 UTC
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
| Latency per case p50 / p95 | 14.8s / 22.6s |
| LLM calls per turn (mean, last turn) | 5.3 |
| Cost per case (mean / total) | US$ 0.0322 / US$ 1.9319 |

## Per case

| Case | Pass | Outcome | Agents | Tools | Notes |
|---|---|---|---|---|---|
| H01 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H02 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H03 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H04 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H05 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H06 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H07 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H08 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H09 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H10 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H11 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H12 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H13 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H14 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H15 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H16 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H17 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H18 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H19 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H20 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H21 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H22 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H23 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H24 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H25 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H26 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H27 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H28 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H29 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H30 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H31 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H32 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H33 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H34 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H35 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H36 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H37 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H38 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H39 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H40 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H41 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H42 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H43 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H44 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H45 | 0/1 | clarify | supervisor |  |  |
| H46 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H47 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H48 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H49 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H50 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H51 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H52 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H53 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H54 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H55 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H56 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H57 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H58 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H59 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
| H60 | 1/1 | answered | supervisor, knowledge | ask_knowledge, search_kb, verify_answer |  |
