# ADR 013: The input classifier runs alongside the supervisor; progress streams over SSE

**Context.** The evaluator's main business-fit discount was latency (p50 of 14 s). Every turn started with the input classifier (one LLM call, about 2 s) before the supervisor could begin, and the merchant saw nothing until the whole answer was ready.

**Decision.**
- **Redaction stays first.** It is instant and deterministic, so no model ever sees a card number or CPF.
- **The LLM classifier runs in a thread alongside the supervisor's first step.** The graph waits for its verdict before any tool runs, before the verifier and before `finalize`. A blocked message can make the supervisor start planning, but it never reaches a specialist or a tool, and no agent answer leaves the graph. A regression test covers this.
- **The reply language comes from a cheap pt/en guess,** so the supervisor does not wait for the classifier.
- **`POST /chat/stream` (SSE)**, the author's choice over WebSocket because it reuses the existing event flow:
  - `status` events as the work happens: analyzing, official content, account data, escalation, verifying;
  - the verified answer as `delta` events;
  - the same JSON as `/chat` in a final `final` event.
  
  Answer tokens are not streamed before verification, because that would show the merchant claims the verifier may still remove.

**Measured.**
- Dev p50 went from 12 s in v3 to 10.7 s with the verifier off.
- Through the stream, on the 10 challenge questions: first specialist status at p50 2.1 s and p95 5.0 s; the full answer at p50 17.5 s, which includes the verifier and its replans (`evals/results/*-stream-original`).

**Alternatives.**
- Stream the supervisor's tokens: faster first text, but unverified.
- Keep the classifier first: simpler, about 2 s slower.
- WebSocket: two-way, which this flow does not need.

**Consequences.**
- A blocked message costs a wasted supervisor call. That is rare, and the turn cost cap still applies.
- The end-to-end p50 target of 9 s was not reached. The remaining levers are effort and model per agent, measured under load in phase 8.
