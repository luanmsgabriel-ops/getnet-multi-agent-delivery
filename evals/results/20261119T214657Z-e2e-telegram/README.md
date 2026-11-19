# Human handoff through Telegram (real bot, real model)

2026-11-19, full compose stack (Postgres, Redis, OIDC), Claude Sonnet 5.5, a temporary bot created for this test.

1. The merchant (cliente1988) reports a duplicated charge; the assistant opens handoff H-4373CB (charge_dispute, high).
2. The operator is notified by the signed webhook and by Telegram (`delivered: true` for both).
3. The operator answers from Telegram with `/reply H-4373CB ...`. The text goes through the operator guardrail and the same resume path as the console.
4. The assistant re-checks the sales, writes the answer, and the merchant gets it by SSE and webhook.

Audit trail (`case.json`, the operator's Telegram id masked):

- 21:42:51 `created` by `assistant`
- 21:42:54 `notified` by `system`
- 21:42:54 `notified` by `system`
- 21:45:44 `replied` by `telegram:<operator>`
- 21:46:04 `resolved` by `assistant`
- 21:46:04 `notified` by `system`

The merchant's server-sent events are in `merchant_events.txt`. The bot's poller hit a temporary DNS failure at startup and recovered with backoff, as designed.
