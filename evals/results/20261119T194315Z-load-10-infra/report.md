# Load test: 10 concurrent merchants, 5.4 min

2026-11-19 19:43 UTC, full docker compose stack (Postgres, Redis, OIDC), real model. Each user runs conversations from the 10 challenge scenarios and the 40 dev cases over `/chat/stream`, with 5 s between turns, spread over 3 merchants.

| SLO (docs/SLO.md) | Measured | Target | Met |
|---|---|---|---|
| Availability (turns without error) | 100.0% | ≥ 99.5% | yes |
| Turn p95 | 44.0 s | < 30 s | **no** |
| First specialist at work p95 | 10.96 s | < 5 s | **no** |
| Cost per turn | US$ 0.0273 | < US$ 0.05 | yes |

Turns 134 · throughput 24.8/min · p50 13.8 s · p95 44.0 s · p99 71.3 s · first event p50 0.04 s · first specialist at work p50 2.14 s / p95 10.96 s · cost US$ 3.658 · errors none

| Kind | Turns | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| kb | 39 | 14.2 | 48.9 |
| support | 33 | 15.4 | 39.6 |
| knowledge | 24 | 15.2 | 64.1 |
| multi | 11 | 26.1 | 35.9 |
| fx | 10 | 10.1 | 13.5 |
| weather | 8 | 12.7 | 28.2 |
| clarify | 6 | 2.2 | 4.5 |
| guardrail | 3 | 4.3 | 9.9 |

Outcomes: {'blocked': 3, 'answered': 125, 'clarify': 6}
