# ADR 018: Latency under load: measured levers and a replan deadline

**Context.** The v3 evaluation flagged latency (p95 85 s with 3 clients, measured on Opus) and set the path "p95 below 30 s with 10 clients". `make load` now runs 10 concurrent merchants for 5 minutes against the full compose stack with the real model (`evals/load/`).

**What the first run showed** (`20261119T191921Z-load-10`):
- p95 was 33.5 s, and 10 turns (6.4%) failed.
- The failures never reached the server, which logged 147 requests, all 200. Uvicorn closes idle connections after **5 s**, the client paused 5 s between turns, and a reused connection was reset.
- Knowledge-base search had a p95 of 12.9 s, from CPU contention: the query embedding runs on CPU, and the container had 2 CPUs.

**Decision: three levers, measured one run at a time** (10 users, 5 min each):

| Run | Change | Turns | Availability | p50 | p95 | p99 | First specialist p95 | Cost/turn |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | baseline | 157 | 93.6% | 14.4 s | 33.5 s | 47.1 s | 5.3 s | US$ 0.026 |
| 2 | + 4 CPUs, keep-alive 75 s | 134 | **100%** | 13.8 s | 44.0 s | 71.3 s | 11.0 s | US$ 0.027 |
| 3 | + replan deadline 12 s | 149 | **100%** | 14.7 s | **27.3 s** | 50.3 s | 7.9 s | US$ 0.026 |

- **Keep-alive 75 s** (longer than a load balancer's usual 60 s idle timeout): connection errors went to zero.
- **4 CPUs for the API:** knowledge-base search p95 fell from 12.9 s to 1.7 s (run 2). The turn p95 still rose in run 2, so search was not the tail.
- **Replan deadline:**
  - Server logs from run 2 split the turns. The 19 turns where the verifier asked for a second round had p50 29 s and p95 **72 s**. The other turns had p95 **27 s**.
  - So a failed check replans only while the turn is younger than 12 s (`REPLAN_DEADLINE_S`). After that, the unsupported sentences are removed with a limitation sentence, the same path as a failed replan.
  - The safety property is unchanged: no unsupported claim reaches the merchant.
- **Quality, checked at the worst case:** the dev set was run with replans disabled entirely (`20261119T195529Z-dev-no-replan`) and compared with the reference run that replans:
  - judge pass 98% vs 98%; correctness 4.85 vs 4.85; groundedness 4.73 vs 4.67;
  - unsupported claims 23 vs 19, within one run's noise.

**Result.** Availability, turn p95 and cost meet their SLOs (`docs/SLO.md`).
- The progress SLO, first specialist at work p95 < 5 s, does not (7.9 s). Under load, the first supervisor call and the input classifier both take a few seconds, and no tool may run before the classifier allows it.
- These are single 5-minute runs. Provider latency varies between runs, which is why run 2's tail moved without a model-path change. The split of turns with and without a replan is the robust evidence.

**Alternatives.**
- Claude Haiku on the Support Agent: planned, but the measurement showed the Support Agent was not the tail.
- No replan at all: the same quality on dev, but it gives up the replan on fast turns, where it costs little.
- More uvicorn workers: the turn is I/O-bound on model calls, and one process with a thread pool handled 10 users without queueing.

**Consequences.**
- About 12% of turns under load get a trimmed answer with a limitation sentence instead of a second attempt.
- The compose file sets `cpus: 4.0` for the API.
- The image CMD and compose both set `--timeout-keep-alive 75`.
