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

## Judge calibration against a human

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
| Regression gate run after the memory change | The figure check read the JSON value `6.372` as 6372, so a correct exchange rate was withheld | Numbers compared by value, with both readings of a 3-digit group |
