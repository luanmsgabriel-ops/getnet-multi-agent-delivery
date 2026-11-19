# Service level objectives

What a merchant should be able to count on, how it is measured, and what fires when it slips. Targets are for the chat turn (`POST /chat` and `POST /chat/stream`), over 30 days.

| SLO | Target | Measured by | Alert |
|---|---|---|---|
| Availability: turns that do not fail on our side | ≥ 99.5% (error budget 0.5%, about 3.6 h a month) | `chat_turn_errors_total` / (`chat_turns_total` + `chat_turn_errors_total`) | `ChatSLOFastBurn` (page): above 7.2% over 1 h and 5 min, 14× the budget rate. `ChatSLOSlowBurn` (ticket): above 3% over 6 h and 30 min, 6× |
| Turn latency | p95 < 30 s | `chat_turn_seconds` (fraction of turns over 30 s) | `ChatLatencySLOBreached` (ticket): more than 5% of turns over 30 s in 1 h |
| Progress shown | first specialist at work, p95 < 5 s | load test (`first_work_ms`, from `/chat/stream` status events) | none (load-test check) |
| Cost | < US$ 0.05 per turn on average | `chat_turn_cost_usd` | `CostPerChatHigh` (ticket): average above US$ 0.20 for 30 min |

**What counts as a failed turn.**
- Counted: a 5xx on `/chat`, or an `error` event on `/chat/stream` (provider unavailable, budget exhausted, unexpected error).
- Not counted: client errors (401, 403, 422, 429).
- Not counted: a blocked or out-of-scope message. That is a correct answer.
- Not counted: a handoff. That is a correct outcome.

**Why these numbers.**
- *30 s p95:* a turn is several model calls in sequence (supervisor, specialist, verifier), and the merchant sees progress events within seconds, so the wait is visible, not silent.
- *99.5%:* leaves room for provider incidents, which the model fallbacks only partly absorb.
- *Burn-rate thresholds:* the standard multi-window pair (Google SRE workbook), so a short spike pages and a slow leak opens a ticket.

**Measured under load.** `make load` runs 10 concurrent merchants for 5 minutes against the full compose stack with the real model. Results are in [EVALUATION.md](EVALUATION.md#load-and-latency-v4), and the screenshots are in `docs/observability/`.

The alert rules are tested with `promtool test rules ops/prometheus/alerts_test.yml` in CI, and each one has a runbook entry.
