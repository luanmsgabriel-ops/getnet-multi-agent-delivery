# Dataset exposure log

Which evaluation sets were seen, and what was tuned on them. A set marked **holdout** is run
once for the reported number and never used to choose prompts, parameters or models.

| Set | Type | Source (author) | Used for tuning? | Runs |
|---|---|---|---|---|
| `original.jsonl` | answer | challenge statement (Getnet) | yes (dev) | 2026-11-17: 10x3 real run (F2) |
| `retrieval_dev.jsonl` | retrieval | help-center article titles (Getnet site) | yes: chunk size, RRF weights, embedding model | 2026-11-17 sweep |
| `retrieval_xling.jsonl` | retrieval | 10 English questions (written by us) | yes: choice of hybrid over lexical | 2026-11-17 |
| `retrieval_holdout.jsonl` | retrieval | official FAQ questions, `/duvidas` page (Getnet site) | **no** | 2026-11-17 17:5x UTC, once, after all retrieval choices were fixed |
| `adversarial.jsonl` | guardrail | 60 attacks + 60 benign look-alikes (written by us) | **no**: classifier prompt written before the first run, unchanged after | 2026-11-17 18:28 UTC, once |

## Retrieval decisions made on dev (before the holdout run)

- Chunk size 1000 chars, section-aware: 600 and 1500 tested, no gain.
- Embeddings `paraphrase-multilingual-MiniLM-L12-v2`: `potion-multilingual-128M` tested, worse.
- Hybrid RRF with equal weights: on Portuguese titles it ties lexical (R@5 0.63 vs 0.66).
  On English questions against the Portuguese corpus it is clearly better (R@5 0.90 vs 0.60),
  which is the challenge's setting.
