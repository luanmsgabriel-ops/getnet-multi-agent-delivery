# Evaluation

Everything below was measured on 2026-11-17/18 with real model calls. Raw responses, traces, costs and judge grades are committed under `evals/results/`; what was seen or tuned is logged in `evals/EXPOSURE.md`.

## Strategy

| Layer | What it proves | How to run |
|---|---|---|
| Unit and contract tests (offline) | auth, scopes, isolation, tool contracts, guardrail rules, retrieval single-load | `uv run pytest` (CI on every push) |
| Integration with a scripted LLM (offline) | the orchestration itself: parallel delegation, replanning, step limits, typed tool errors, memory, handoff interrupt/resume, restarts, provider outage | `uv run pytest` |
| Chaos-style tests | breaker on public APIs, provider failure during resume, budget exhaustion | `uv run pytest` |
| Real-model eval (paid, deliberate) | answer quality, routing, tools, outcomes, stability, latency and cost | `uv run python -m evals.run --split dev --repeats 3` |
| Independent LLM judge | correctness, groundedness, relevance, completeness, policy | `uv run python -m evals.judge <run dir>` |
| Human calibration of the judge | whether the judge can be trusted | `uv run python -m evals.calibration score` |
| Retrieval and guardrail evals | recall@k / MRR on official questions; attack block and false-positive rates | `evals.retrieval`, `evals.security` |
| Regression gate | a real-model run did not drop below the thresholds in `evals/gates.json` (checks, judge pass, policy violations, cost per case) | `uv run python -m evals.gate <run dir> --split original`; in CI, `.github/workflows/eval.yml` runs eval, judge and gate weekly or on demand |

The gate thresholds sit below the committed results by more than the measured judge noise, so a failure points to a real regression. All committed Sonnet runs pass it. The paid workflow does not run on every push: one `original` run costs about US$ 0.33. Without the API key secrets, it reports that and stops.

Datasets: `original` (the 10 challenge questions), `dev` (40: PT/EN knowledge, public data, merchant data, multi-intent, clarification, guardrail, isolation), `multi_turn` (12 conversations), `handoff` (8 that must escalate, 8 that must not) `holdout_answers` (20 official FAQ questions with the official answer as reference, run once) and `holdout_answers_v2` (20 more from inside help and product pages, run once). Deterministic checks on the last turn cover the expected outcome (answer, clarify, handoff or block), the agents and tools used, and required or forbidden terms. The judge is a different model family (`openai/gpt-5-mini` via OpenRouter). It receives a blind packet: the conversation, the reply, the evidence the system retrieved, and the official reference when there is one. It never sees the expected agents or tools, nor the generator model.

## Results (Claude Sonnet 5.5 for all agents)

| Set | Runs | Checks pass | pass^k | Judge pass | Correctness | Groundedness | Latency p50 | Cost / case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| original (the 10 challenge questions) | 30 | **100%** | 100% | 97% | 4.63 | 4.53 | 14 s | US$ 0.027 |
| dev | 120 | 98% | 98% | 98% | 4.81 | 4.67 | 12 s | US$ 0.022 |
| multi_turn | 36 | 92% | 92% | 94% | 4.64 | 4.63 | 23 s (2 turns) | US$ 0.039 |
| handoff (must / must not escalate) | 48 | **100%** | 100% | 100% | 4.88 | 4.88 | 13 s | US$ 0.024 |
| **holdout: official FAQ** (once) | 20 | 90% | n/a | 80% | 4.25 | 4.44 | 14 s | US$ 0.024 |
| **holdout v2: Q&A inside help and product pages** (once, after the RAG changes) | 20 | 100% | n/a | 90% | 4.55 | 4.50 | 12 s | US$ 0.031 |
| **holdout v3: product Q&A from blog posts and manuals** (once, v4 retrieval) | 60 | 98% | n/a | **97%** | 4.85 | 4.78 | n/a | US$ 0.03 |
| original on **Claude Opus 5.5** | 30 | 97% | 90% | 93% | 4.62 | 4.52 | 23 s | US$ 0.107 |

Correctness and groundedness are means on a 1-5 scale. The judge found zero policy violations (refund or deadline promises, other merchants' data) in the final runs.

Reading the table:
- **Model choice (ADR 008).** Sonnet matches Opus on these cases at about a quarter of the cost and half the latency, so it is the default (`LLM_MODEL`).
- **Router.** A keyword router (`evals/baseline.py`) gets the exact agent set right on 74% of the same single-turn cases and covers 3 of 5 multi-intent cases. The supervisor used the expected agents in 98-100% of runs.
- **Known routing ambiguity.** "What does decline code 05 mean?" goes to the Knowledge Agent (help-center pages) rather than the Support Agent (decline-code table). The answer is still judged correct; the expectation was left as written.
- **Weakest set: the first holdout (80%).** The failures are mostly "not found in the knowledge base" for answers that live inside the 46,000-character FAQ page. It is the same weakness the retrieval holdout shows (recall@5 0.58, `docs/RAG.md`). Question/answer-aware chunking was then tried on dev and reverted (no gain). Retrieving 8 passages and a figure check were kept. A fresh holdout from other pages scored 90%. Its questions differ, so part of the gain may come from easier pages.
- **Judge variance.** Re-judging the same answers moves pass rates by 3-10 points (for example original 97-100%, holdout 70-80%), so differences smaller than that are noise.

## Prompt ablation: does the supervisor's guidance earn its tokens?

The same 40 dev cases were run with a **minimal** supervisor prompt, keeping only the role, the tool list and the security lines. The "How to decide" and "Final answer" guidance was dropped (`evals/ablation.py`). Everything else stayed the same. The comparison is against the first repeat of the committed full-prompt run.

| Supervisor prompt | Checks pass | Judge pass | Correctness | Groundedness | Unsupported claims / case | Cost / case |
|---|---:|---:|---:|---:|---:|---:|
| **Full** (current) | **97.5%** | 97.5% | **4.80** | **4.66** | **0.55** | **US$ 0.022** |
| Minimal | 95% | 100% | 4.58 | 4.35 | 0.85 | US$ 0.025 |

- **Kept: the full prompt.** Without the guidance, answers carry about 55% more claims the judge cannot find in the evidence. Correctness and groundedness drop by 0.2-0.3, and each case costs about 15% more.
- **Clarification lost structure.** For "Quanto está a cotação hoje?", the minimal prompt asked "which currency?" in plain text instead of using `ask_user`. The merchant sees the same question, but the API reports `answered` instead of `clarify`.
- **Judge pass did not separate the two.** Both are within judge noise (3-10 points). The rubric scores are more sensitive than the pass/fail verdict for prompt changes.
- **Caveats.** One repeat of 40 cases, run once, about US$ 1.10 with the judge. The differences are consistent across metrics, but small samples can mislead.

## Final-answer verifier (v4)

The verifier ([ADR 012](adr/012-final-answer-verifier.md)) was measured on the 40 dev cases with the verifier off and on. It was then tuned on an offline bench that re-checks recorded answers against the judge (`evals/verifier_bench.py`, a few cents per run).

| Dev | Off | Tuned verifier |
|---|---:|---:|
| Unsupported claims (judge) | 20 | 19 |
| Groundedness / correctness | 4.72 / 4.85 | 4.67 / 4.85 |
| Deterministic checks | 95% | **98%** |
| Latency p50 / p95 | 10.7 s / 18.8 s | 12.8 s / 32.2 s |
| Cost per case | US$ 0.024 | US$ 0.029 |

Measured cleanly, the judge sees no change on dev. On the bench, the verifier catches errors in the merchant's figures and dates, and its false alarms on answers the judge found fully supported fell from 10/25 to 2/25 after tuning.

## Judge calibration against two humans (v4)

**Setup** (`evals/calibration.py`, `evals/calibration/calibration_v4.md`):
- 70 new answers from v4 runs. Questions already labelled in v3 were excluded.
- The sample is stratified: every judge failure, the judge passes that were doubtful (correctness 4 or below, or unsupported claims listed) and clean passes. v4 answers rarely fail, and a nearly constant label makes kappa unstable.
- Rater 1 labelled all 70 items. A second person labelled the 50 items of the **measurement half**, independently, without seeing either the judge's grades or rater 1's labels, and without AI help (stated by the author).
- The measurement half was never used to tune the judge.
- 95% intervals come from a bootstrap with 2,000 resamples.

| Pair (measurement half, 50 items) | Agreement | Cohen's kappa (95% CI) | Gwet's AC1 (95% CI) |
|---|---:|---:|---:|
| Judge vs rater 1 | 98% | 0.85 (0.00 to 1.00) | **0.98 (0.92 to 1.00)** |
| Judge vs rater 2 | **100%** | 1.00 | 1.00 |
| Rater 1 vs rater 2 | 98% | 0.85 (0.00 to 1.00) | 0.98 (0.92 to 1.00) |

**Reading.**
- The judge agrees with each human about as well as the two humans agree with each other: rater 1 vs rater 2 is the ceiling.
- Correctness scores from the judge and rater 1 fall within 1 point of each other on 96% of items.
- Only 3 or 4 of the 50 answers fail, so a single item moves kappa a lot. Its interval runs from 0 to 1, while AC1, which is robust to a rare class, stays between 0.92 and 1.00.
- The one disagreement in the measurement half (D06, a R$ 1 fee condition) has the judge and rater 2 passing and rater 1 failing.

**As a deploy gate,** the judge is reliable for pass/fail on answers like these. The thresholds in `evals/gates.json` sit well below the measured levels, and deterministic checks run alongside it.

## Tool accuracy per tool (v4)

`uv run python -m evals.tools` sends 40 merchant requests (`evals/datasets/tools.jsonl`, 4 per tool, Portuguese and English) to the Customer Support Agent with the real model. A case passes **selection** when the expected tool is called and no forbidden tool is (a simulation must not create a proposal). It passes **arguments** when that call's arguments match, with relative dates resolved against today.

| Tool | Selection | Arguments |
|---|---:|---:|
| sales, receivables, terminals, recent transactions, decline codes, tickets (8 tools) | 100% | 100% |
| `propose_anticipation`, `propose_terminal_service` | 100% | 100% |
| `simulate_anticipation` | 100% | 75% (3/4) |
| **All (40)** | **100%** | **98%** |

Run `evals/results/20261119T163642Z-tools`: Claude Sonnet 5.5, one run, US$ 0.27. The one miss was ambiguous wording ("the next 60 days, starting tomorrow" read as tomorrow + 60); the case was kept as written. With 4 cases per tool, these are smoke-level numbers per tool, not tight estimates.

## Final v4 regression (2026-11-19)

The final code was run on five sets with the real model, then judged. `uv run python -m evals.stats` gives the 95% intervals.

| Run | n | Checks pass | Judge pass | Correctness | Groundedness | Unsupported | Latency p50 (s) | Latency p95 (s) | Cost/run (US$) |
|---|---:|---|---|---|---|---:|---|---|---|
| `20261119T202349Z-original-final` | 30 | 100% [89-100] | 100% [89-100] | 4.87 [4.73-4.97] | 4.83 [4.70-4.97] | 11 | 15.9 [14.7-17.2] | 33.0 [19.7-34.3] | 0.031 [0.025-0.037] |
| `20261119T202936Z-handoff-final` | 48 | 90% [78-95] | 100% [92-100] | 4.91 [4.81-4.98] | 4.88 [4.77-4.98] | 8 | 13.8 [10.8-16.9] | 23.9 [20.5-24.4] | 0.025 [0.020-0.032] |
| `20261119T203415Z-multi_turn-final` | 12 | 83% [55-95] | 100% [76-100] | 4.92 [4.75-5.00] | 4.75 [4.50-4.92] | 6 | 12.5 [9.3-15.2] | 23.4 [15.2-23.4] | 0.043 [0.030-0.056] |
| `20261119T203912Z-dev-final` | 40 | 98% [87-100] | 98% [87-100] | 4.67 [4.50-4.83] | 4.56 [4.33-4.75] | 23 | 14.7 [11.5-15.9] | 26.4 [19.8-35.7] | 0.024 [0.020-0.029] |
| `20261119T204749Z-holdout_answers_v3-final` | 60 | 98% [91-100] | 97% [89-99] | 4.75 [4.60-4.88] | 4.71 [4.56-4.85] | 20 | 14.8 [13.2-16.8] | 22.6 [21.8-25.2] | 0.032 [0.030-0.035] |

Brackets: 95% intervals (Wilson for rates; bootstrap, 2,000 resamples, for means and percentiles).

Notes:
- **Handoff, 90% checks.** All five failures are HTTP 400 errors from the model provider, on two cases that must *not* escalate (H15 ×2, H16 ×3). A rerun of both passed. The client did not log the provider's error text then; it does now (`llm_provider_error`). The run is reported as it was.
- **Multi-turn, 83% checks.** One of the two misses was the checker: the answer wrote "Wi-Fi" with a non-breaking hyphen (U+2011). The checker now normalizes Unicode dashes and spaces, which makes the same answers 11/12 (92%). The other miss is real: an answer about decline code 57 without routing to the Support Agent.
- **Real misses elsewhere.** D29 explained decline code 05 from general knowledge instead of calling the decline-code tool. H45 (holdout) asked a clarifying question on an ambiguous official question ("which step?").
- **Latency.** These are in-process runs with three conversations in parallel. Latency under concurrent load is in the next section.

## Load and latency (v4)

`make load` runs 10 concurrent merchants for 5 minutes over `/chat/stream` against the full compose stack (Postgres, Redis, OIDC) with the real model. The conversations come from the 10 scenarios and the 40 dev cases, with 5 s between turns.

| Run | Change | Availability | p95 | First specialist p95 | Cost/turn |
|---|---|---:|---:|---:|---:|
| `20261119T191921Z-load-10` | baseline | 93.6% | 33.5 s | 5.3 s | US$ 0.026 |
| `20261119T194315Z-load-10-infra` | + 4 CPUs, keep-alive 75 s | 100% | 44.0 s | 11.0 s | US$ 0.027 |
| `20261119T200036Z-load-10-replan-deadline` | + replan deadline 12 s | 100% | **27.3 s** | 7.9 s | US$ 0.026 |

How each lever was found and measured, and the quality check behind the replan deadline, are in [ADR 018](adr/018-latency-levers-under-load.md). SLO targets and alerts are in [SLO.md](SLO.md). Screenshots from the first run are in `docs/observability/`.

## Judge calibration against a human (v3)

A person labelled 30 sampled answers (pass/fail plus a 1-5 correctness score) without seeing the judge's grades. They used the same rules and exactly the same evidence the judge receives (`evals/calibration/labels.csv`, `evals/calibration/calibration.md`).

| Judge version | Agreement (pass/fail) | Cohen's kappa | Correctness within 1 point |
|---|---:|---:|---:|
| Before adding caller identity to the packet | 73% | 0.17 | 73% |
| **Current** (packet states the authenticated merchant) | **87%** | **0.44** | 87% |

The first comparison exposed a judge bug: it did not know who the caller was, so it failed correct refusals of another merchant's data. The fix came after seeing the labels, so the second number is not fully independent.

The 4 remaining disagreements all go the same way: **the judge is more lenient than the human**. The human passed 24 of 30 answers and the judge 28 of 30. One of the 4 is a clear judge miss: it accepted a reply that omitted the official FAQ definition. Judge pass rates should therefore be read as an **upper bound**, a few points above what a strict human reviewer would give.

## Other measured sets

| Set | Result | Details |
|---|---|---|
| Input guardrail: 60 attacks + 60 benign look-alikes | 98.3% blocked, **0% false positives**, US$ 0.0016/message | `docs/SECURITY.md` |
| Indirect prompt injection (poisoned KB passage, end to end) | not followed; the merchant was warned | `docs/SECURITY.md` |
| Retrieval, English questions over the Portuguese corpus | hybrid recall@5 0.90 vs lexical 0.60 | `docs/RAG.md` |
| Retrieval, official FAQ holdout (102 questions) | hybrid recall@5 0.58, recall@10 0.70 | `docs/RAG.md` |
| Retrieval, fresh holdout of Q&A inside help and product pages (121 questions) | hybrid recall@5 0.63, recall@10 0.73 | `docs/RAG.md` |
| Long-term memory and long-chat summary (real model, in-process) | 6/6 checks. Lasting facts were saved with `remember` while the sales question was still answered with merchant data. A protocol from the first message was recalled after 10 turns, past the summary. Erasure worked. The saved "prefer short answers" did **not** visibly shorten a later answer: memory informs, but does not yet steer style. US$ 0.17 | `evals/memory_flow.py`, `evals/results/*-memory-flow` |
| Validation of the `original` set after adding memory | 10/10 checks, judge 90%. The failure (PTAX sell rate reported as "could not confirm") was a figure-check bug: `6.372` from JSON was read as thousands. It was fixed with a regression test, and the rerun scored 5/5 | `evals/results/20261118T214724Z-original`, `...215048Z-original` |
| Memory and handoff end to end (real model, Compose) | follow-up resolved from memory; dispute escalated, operator reply resumed the graph, merchant notified | `evals/results/*-e2e-flows` |

## Bugs the evals found, fixed with tests

| Found by | Bug | Fix |
|---|---|---|
| First full run | English questions sometimes answered in Portuguese | Reply language detected by the guardrail is passed in the request context |
| First full run | The output guardrail redacted legitimate text ("Esqueceu a senha: ...") | Outputs only redact real key, card and CPF formats |
| Opus sample | The per-turn cost cap returned HTTP 503 | An honest "please split the question" answer with outcome `limit` |
| Smoke run | Mock sales for "today" were generated in the future | Today's mock sales are mornings only |
| Concurrent run with observability | The API was OOM-killed when concurrent requests loaded the embedding model | One locked warm-up at startup; readiness waits for it |
| Human calibration | The judge did not know the assistant's scope or the caller | Scope and caller added to the judge packet |
| v4 regression run | The judge rebuilt 5 passages per search while the agent had received 8 since late v3, so it flagged supported facts (fees on the rental page) as invented | The judge uses the agent's `KB_PASSAGES`. Re-judged: original 90% → 100%, holdout v3 95% → 97%. v3 runs judged after the switch to 8 passages were slightly understated. |
| v4 calibration export | The judge packet listed the verifier's own verdict (`verify_answer`) as evidence, which flattered the verifier (15 unsupported claims instead of 19) | The verdict is excluded from the packet and the labelling evidence; verifier runs re-judged |
| v4 load test | Uvicorn's 5 s keep-alive reset reused client connections (6.4% of turns failed before reaching the server) | Keep-alive 75 s, longer than a load balancer's idle timeout |
| v4 load test | Turns with a verifier replan had p95 72 s | Replan only while the turn is under 12 s; otherwise trim unsupported sentences (ADR 018) |
| v4 final regression | The checker missed "Wi-Fi" written with a non-breaking hyphen | Unicode dashes and spaces normalized; unit test |
| v4 final regression | A provider HTTP 400 gave no reason in the logs | The provider's error type and message are logged (no request content) |
| Regression gate run after the memory change | The figure check read the JSON value `6.372` as 6372, so a correct exchange rate was withheld | Numbers compared by value, with both readings of a 3-digit group |
