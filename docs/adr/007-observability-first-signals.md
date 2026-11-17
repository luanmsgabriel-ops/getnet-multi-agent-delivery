# ADR 007: OpenTelemetry, Prometheus and alert tests from day one

**Context.** Agent systems fail in ways unit tests miss: slow model calls, cost drift, resource limits under concurrency.
**Decision.** OTel spans for every agent, tool and LLM call (tokens and cost as attributes), Prometheus metrics without merchant identifiers, JSON logs with `trace_id`, a provisioned Grafana dashboard, and 8 alert rules unit-tested with promtool.
**Consequences.** The first real concurrent run exposed an OOM kill (the embedding model loaded concurrently) and CPU contention in retrieval. Both were fixed with regression tests (`docs/OBSERVABILITY.md`).
