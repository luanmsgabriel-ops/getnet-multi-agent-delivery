# Load test: 10 concurrent merchants, 5.6 min

2026-11-19 19:19 UTC, full docker compose stack (Postgres, Redis, OIDC), real model. Each user runs conversations from the 10 challenge scenarios and the 40 dev cases over `/chat/stream`, with 5 s between turns, spread over 3 merchants.

| SLO (docs/SLO.md) | Measured | Target | Met |
|---|---|---|---|
| Availability (turns without error) | 93.6% | ≥ 99.5% | **no** |
| Turn p95 | 33.5 s | < 30 s | **no** |
| First specialist at work p95 | 5.29 s | < 5 s | **no** |
| Cost per turn | US$ 0.0256 | < US$ 0.05 | yes |

Turns 157 · throughput 28.0/min · p50 14.4 s · p95 33.5 s · p99 47.1 s · first event p50 0.04 s · first specialist at work p50 2.12 s / p95 5.29 s · cost US$ 4.017 · errors {'http 0': 10}

| Kind | Turns | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| support | 40 | 17.2 | 43.2 |
| kb | 37 | 16.8 | 33.5 |
| knowledge | 21 | 14.0 | 30.8 |
| multi | 14 | 16.9 | 45.9 |
| clarify | 12 | 2.7 | 13.0 |
| fx | 9 | 8.2 | 11.5 |
| guardrail | 8 | 3.5 | 5.8 |
| weather | 6 | 12.3 | 15.0 |

Outcomes: {'blocked': 8, 'answered': 128, 'clarify': 11, 'None': 10}
