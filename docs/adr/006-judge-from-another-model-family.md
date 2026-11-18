# ADR 006: Measure with an independent judge and committed results

**Context.** v2 had an evaluation protocol but no results, and a same-model judge cannot show independence.
**Decision.** Deterministic checks (outcome, routing, tools, required terms) on every case, plus a blind LLM judge from another family (GPT via OpenRouter) with anchored rubrics, calibrated against human labels. Holdout sets come from Getnet's own FAQ and run once (`evals/EXPOSURE.md`). All raw results are committed.
**Alternatives.** Author-written rubric scores (v1). Judge-only scoring (no deterministic anchor).
**Consequences.** Evals cost money (budget ledger), so the full run is a deliberate step, not CI. CI runs the offline suite on every push.
