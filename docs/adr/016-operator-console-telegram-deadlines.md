# ADR 016: Operator console, Telegram channel, deadlines and audit trail

**Context.** The v3 evaluation kept Human Oversight below 10 because there was no operator screen, and noted a competitor's human channel in use (Telegram). Our own review found a gap: the operator's text reached the graph without any check.

**Decision.**
- **Console:** a static page served by the API at `/operator`, calling the operator API with a pasted token. No framework, no build step, strict CSP.
- **Telegram (Luan's choice, DECISIONS.md):**
  - it notifies every handoff and every missed deadline;
  - the operator can answer from the chat;
  - commands call the same `resume` as the console, so there is one path to guard and audit;
  - long polling instead of a webhook, because a local or private deployment has no public URL.
- **Operator guardrail:**
  - the text is redacted and classified with an operator-specific prompt (instructions to the assistant are normal there; switching merchants, revealing the prompt, widening access or confirming actions are not);
  - it fails closed, since the operator can simply resend;
  - the reply reaches the model with explicit limits, which also hold in code.
- **Deadlines (Luan's choice):** 15 min for high priority, 60 min for normal. A breach raises the handoff to urgent once (an atomic update, safe with replicas), sends a reminder, increments a metric and fires an alert.
- **Audit trail:** one table, append-only from the code. It records creation, each notification per channel, breaches, blocked and accepted replies (redacted text, actor) and the resume result.

**Alternatives.**
- A React console: nicer, but a build chain for four screens.
- A Telegram webhook: lower latency, but it needs a public HTTPS endpoint.
- Slack: needs a workspace; Telegram is what the benchmark used.
- Trusting the operator's text because the operator is authenticated: a compromised operator account, or a pasted email with hidden instructions, would reach the graph unchecked.

**Consequences.**
- One more LLM call per operator reply (the classifier).
- Telegram is a third party: notifications are redacted, and operators should use the console for sensitive details.
- Only one replica may poll Telegram (`TELEGRAM_POLLING`).
