# Retrieval: `holdout_v3` (261 queries, 992 chunks)

Generated 2026-11-19 12:44 UTC. Query text removed from the index while measuring.

| Mode | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| lexical | 0.19 | 0.52 | 0.64 | 0.32 |
| dense | 0.38 | 0.73 | 0.81 | 0.52 |
| hybrid | 0.30 | 0.64 | 0.75 | 0.44 |

Production ranking in v4 is `dense` (google/embeddinggemma-300m). `hybrid` above is equal-weight
RRF with BM25, shown for comparison.

Same holdout, v3 retrieval system (MiniLM embeddings + BM25, equal-weight RRF), measured for
comparison only: R@1 0.21, R@5 0.52, R@10 0.67, MRR@10 0.34.

Target was R@5 >= 0.80; reached 0.73. Nothing was tuned on this set after this run.
