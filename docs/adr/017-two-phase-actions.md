# ADR 017: Two-phase actions: anticipation and terminal service

**Context.** The v3 evaluation noted that the only write was the support ticket. Real merchant flows that change state are missing, and every write is a place where a model mistake or an injection could cost money.

**Decision (actions chosen by Luan, DECISIONS.md).**
- **Two new actions**, both in two phases:
  - *anticipation of receivables*: `simulate_anticipation` (read-only), then `propose_anticipation`;
  - *terminal replacement or technician visit*: `propose_terminal_service`, accepted only for the merchant's own terminal that is offline or failing.
- **The model only proposes.**
  - A proposal stores the quote, belongs to one merchant and expires in 10 minutes.
  - Only that merchant confirms it, through `POST /actions/{id}/confirm` with the `actions:write` scope.
  - There is no confirm tool, so nothing the model writes, and no "yes" in the chat, can confirm.
- **Confirmation is safe to repeat and to race:**
  - an atomic claim (`proposed` → `executing`) means concurrent confirmations execute once;
  - repeating the call returns the first result (`replayed: true`), and an `Idempotency-Key` is recorded.
- **Data is checked again at confirmation.** Each receivable must still be pending; if one changed, the update is rolled back and the proposal fails with `quote_stale`.
- **Audit:** `actions_audit` records who proposed, who confirmed, when, the request id, and the state before and after. `GET /actions/{id}` shows it.
- **Fee:** a fixed, fictitious 1.99% a month, pro rata by the days brought forward. Every quote carries a disclaimer that it is illustrative.
- **Left out:** cancelling or refunding a sale. It moves the customer's money and stays with a human (handoff).

**Measured.**
- Tool accuracy with the real model (`evals/results/20261119T163642Z-tools`, 40 requests, 4 per tool, one run, US$ 0.27):
  - selection 100%, arguments 98%;
  - every tool at 100% except `simulate_anticipation` arguments, 3/4. The miss was ambiguous wording: "the next 60 days, starting tomorrow" read as tomorrow + 60.
  - The agent simulated before every proposal and checked the terminal before every service request, without being told to in those cases.
- Tests (`tests/integration/test_actions.py`): proposal → confirmation → receivables updated → audit; missing scope 403; another merchant 404; expiry 410; idempotent repeat; four concurrent confirmations execute once; stale quote rolled back; online or foreign terminal refused; the model trying a confirm tool gets "unknown tool" and nothing changes.

**Alternatives.**
- Let the model confirm after a "yes" in the chat: one injected or misread message would move money.
- Confirmation codes by SMS: closer to production, but outside a demo.
- No fee in the simulation: safer from misreading, but useless for deciding.

**Consequences.**
- One more scope (`actions:write`) that the identity provider must grant to merchants.
- The mock receivables change state on confirmation, and the daily reseed resets them.
