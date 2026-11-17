# ADR 005: Agents read; writes and money decisions need a human

**Context.** Refunds, disputes and suspected fraud have financial impact. A model can hallucinate a confirmation.
**Decision.** Agents only read. A ticket is a proposal until the merchant confirms it through the API (idempotent). Disputes, fraud and explicit requests go to a human: the graph pauses, the operator gets a signed webhook, and the operator's reply resumes the supervisor. No prompt or template promises deadlines or refunds; the output guardrail flags any such promise.
**Alternatives.** Letting the agent open tickets directly (an irreversible action on model judgment). Handoff by polling only (the v2 reviewer's main HITL gap).
**Consequences.** Slower resolution for sensitive cases, by design. Handoff state survives restarts (tested).
