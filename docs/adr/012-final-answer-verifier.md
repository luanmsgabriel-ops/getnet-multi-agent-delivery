# ADR 012: An independent verifier checks higher-risk answers before they are sent

**Context.** The v3 evaluation noted that "the retry is guided by the supervisor itself; there is no independent verification of the final answer before it is sent, beyond the guardrails."

**Decision** (the author's choices are in `docs/DECISIONS.md`).
- A `verify` node runs between the supervisor's answer and `finalize`.
- It checks only higher-risk answers: figures, amounts, dates, identifiers or the merchant's own data.
- The checker is Claude Haiku 5.5. It sees only the answer and the evidence the agents gathered: tool outputs, cited web passages, the merchant's messages, an operator reply and date facts. It never sees the supervisor's prompt or reasoning, and it does not search again.
- Figures that a string match cannot find go to the checker as suspects, so totals the agent computed are judged by arithmetic, not by string matching.
- Failing once sends the list back to the supervisor for one replan. Failing twice removes the unsupported sentences and adds a limitation sentence.

**Measured** (dev, 40 cases, one repeat each; `evals/results/*-dev-verify-*`). The judge numbers for the verifier runs come from a **clean packet**. Until 2026-11-19 the judge packet listed the verifier's own verdict as evidence, which made the verifier look better (15 unsupported claims instead of 19); that leak is fixed and the runs were re-judged.

| Dev | Verifier off | **Tuned verifier** |
|---|---:|---:|
| Unsupported claims (judge) | 20 | 19 |
| Groundedness / correctness | 4.72 / 4.85 | 4.67 / 4.85 |
| Judge pass | 100% | 98% |
| Deterministic checks | 95% | **98%** |
| Latency p50 / p95 | 10.7 s / 18.8 s | 12.8 s / 32.2 s |
| Cost per case | US$ 0.024 | US$ 0.029 (+19%) |

**Read honestly:** on dev, where the judge already passes nearly everything, the verifier does not move the judge's scores. Its gains are narrower: errors in the merchant's own figures and dates are caught on the bench (cases D22 and D24), and deterministic checks rise from 95% to 98%. It costs 19% more per case and about 2 s at p50.

The first version raised false alarms on 10 of the 25 answers the judge found fully supported: relative dates, totals the agent computed and limitation sentences. An offline bench (`evals/verifier_bench.py`) re-checks recorded answers against the judge for a few cents per run. Tuning there brought false alarms to 2 of 25, and the merchant-data errors are still caught. Effort `low` was kept: `medium` caught fewer errors.

**Alternatives.**
- Self-critique in the supervisor's own prompt: not independent.
- A full judge in production: slower and costlier.
- Verifying every answer: pays for checks on greetings and how-tos.
- A model from another family: more independent, but another provider in production.

**Consequences.**
- Answers that state figures or merchant data are checked before the merchant sees them.
- The replan path adds 10 to 20 s in the cases that use it, which raises p95. The target of −40% unsupported claims was not reached; measured cleanly, the judge sees no change on dev.
- `VERIFY_ANSWERS=false` turns the node off. The metric `answer_verifications_total{result,checked_by}` shows pass, replan, fixed, limited and skipped.
