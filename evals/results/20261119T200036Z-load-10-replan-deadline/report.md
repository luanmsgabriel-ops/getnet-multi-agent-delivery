# Load test: 10 concurrent merchants, 6.0 min

2026-11-19 20:00 UTC, full docker compose stack (Postgres, Redis, OIDC), real model. Each user runs conversations from the 10 challenge scenarios and the 40 dev cases over `/chat/stream`, with 5 s between turns, spread over 3 merchants.

| SLO (docs/SLO.md) | Measured | Target | Met |
|---|---|---|---|
| Availability (turns without error) | 100.0% | ≥ 99.5% | yes |
| Turn p95 | 27.3 s | < 30 s | yes |
| First specialist at work p95 | 7.92 s | < 5 s | **no** |
| Cost per turn | US$ 0.0255 | < US$ 0.05 | yes |

Turns 149 · throughput 24.8/min · p50 14.7 s · p95 27.3 s · p99 50.3 s · first event p50 0.04 s · first specialist at work p50 2.16 s / p95 7.92 s · cost US$ 3.795 · errors none

| Kind | Turns | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| support | 45 | 12.9 | 22.7 |
| kb | 43 | 17.0 | 25.2 |
| knowledge | 17 | 16.9 | 30.6 |
| multi | 17 | 24.4 | 50.3 |
| clarify | 9 | 5.2 | 12.0 |
| fx | 9 | 9.9 | 12.2 |
| weather | 5 | 14.8 | 20.9 |
| guardrail | 4 | 4.2 | 5.1 |

Outcomes: {'clarify': 9, 'answered': 136, 'blocked': 4}
