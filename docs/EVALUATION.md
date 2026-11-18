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

Datasets: `original` (the 10 challenge questions), `dev` (40: PT/EN knowledge, public data, merchant data, multi-intent, clarification, guardrail, isolation), `multi_turn` (12 conversations), `handoff` (8 that must escalate, 8 that must not) and `holdout_answers` (20 official FAQ questions with the official answer as reference, run once). Deterministic checks on the last turn cover the expected outcome (answer, clarify, handoff or block), the agents and tools used, and required or forbidden terms. The judge is a different model family (`openai/gpt-5-mini` via OpenRouter). It receives a blind packet: the conversation, the reply, the evidence the system retrieved, and the official reference when there is one. It never sees the expected agents or tools, nor the generator model.

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
- **Weakest set: the holdout (80%).** The failures are mostly "not found in the knowledge base" for answers that live inside the 46,000-character FAQ page. It is the same weakness the retrieval holdout shows (recall@5 0.58, `docs/RAG.md`). The next fix is question/answer-aware chunking for FAQ pages, measured on a fresh holdout. It was not tuned on this one.
- **Judge variance.** Re-judging the same answers moves pass rates by 3-10 points (for example original 97-100%, holdout 70-80%), so differences smaller than that are noise.

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
