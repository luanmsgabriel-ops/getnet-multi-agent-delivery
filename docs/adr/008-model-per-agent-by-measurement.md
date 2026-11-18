# ADR 008: Choose the model per agent by measurement

**Context.** Claude Opus 5.5 gave the best answers in development, but at about US$ 0.10 and 30-45 s per turn. The cost and latency budget matters for a support desk.
**Decision.** One configurable model for all agents (`LLM_MODEL`) with an effort level per agent (supervisor and Knowledge `medium`, Support and guardrail `low`). The full eval runs on Claude Sonnet 5.5, plus an Opus sample on the same cases, and the cheaper model is kept only where quality holds (`docs/EVALUATION.md`).
**Alternatives.** Picking models by intuition, or the most capable model everywhere.
**Consequences.** Model choice is a measured, documented trade-off; switching is one environment variable.
