# Decision log

Who decided what, and why. The full reasoning for each technical choice is in `docs/adr/`. This log records only decisions the author actually made, with his reasons in his own words (translated). Claude Code proposed the options and implemented the chosen one.

| Date | Phase | Decision | Alternatives considered | Decided by | Reason |
|---|---|---|---|---|---|
| 2026-11-16 | v3 | Rebuild the system on a new branch instead of patching v2 | patch v2 | Luan | v2 had too much coupling and legacy paths the evaluator had penalized |
| 2026-11-17 | v3 | Claude for the agents, a judge from another model family (OpenRouter) | one provider for both | Luan | independent judge |
| 2026-11-17 | v3 | Full eval on Sonnet plus an Opus sample on the same cases | Opus everywhere; Sonnet only | Luan | measure before paying for the larger model |
| 2026-11-17 | v3 | Label the 30 calibration items himself; discard AI-assisted labels | count the AI-assisted sheet | Luan | only human labels can calibrate the judge |
| 2026-11-18 | v3 | Stop at v3's scope and focus on the video and the interview | chase a 10 | Luan | small gain for the risk and the time left |
| 2026-11-19 | v4 · 1 | Reranker `BAAI/bge-reranker-v2-m3` int8 | `jina-reranker-v2-base-multilingual` | Luan | "light and fits in Docker's memory" |
| 2026-11-19 | v4 · 1 | Query rewriting only as an ablation | always on; not tested | Luan | "to check whether the number improves" |
| 2026-11-19 | v4 · 1 | Answer holdout v3 with 60 questions | larger | Luan | "60, and we increase it if needed" |
| 2026-11-19 | v4 · 1 | Replace the planned reranker with the `google/embeddinggemma-300m` embedding model | `intfloat/multilingual-e5-large` (MIT); keep MiniLM | Luan | "best overall recall@5 on the dev sets and 48 ms per query on the tested CPU, against 159 ms for e5-large" (both rerankers took 15–50 s per query on CPU) |
| 2026-11-19 | v4 · 2 | Final-answer verifier on Claude Haiku 5.5, only for higher-risk claims (figures, amounts, dates, merchant data), checked against the same evidence the agent used, without a new search | a model from another family via OpenRouter; verify every answer | Luan | "Haiku to check higher-risk claims against the same evidence as the agent, without redoing the search" |
| 2026-11-19 | v4 · 2 | Streaming over SSE | WebSocket | Luan | "reuse the existing event flow with less complexity" |
