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
| `dev.jsonl`, `multi_turn.jsonl`, `handoff.jsonl` | answer | written by us | yes: three fixes after the first full run (reply language in context, output redaction scope, honest answer at the per-turn cost cap) | 2026-11-17 21:11 UTC (before fixes) and 21:35 UTC (dev and original after fixes) |
| `holdout_answers.jsonl` | answer | 20 official FAQ questions with the official answer (Getnet site) | **no** | 2026-11-17 21:21 UTC, once. Five of six judge failures were "not found in the knowledge base"; that weakness is documented, not tuned on this set. |

## Judge packet fix (harness, not system)

The first judge pass truncated evidence to 2,500 characters and did not show that a handoff had been created, so it marked supported claims as invented. The packet now rebuilds the full retrieved passages (retrieval is deterministic), maps `[S#]` to URLs and shows the handoff action. All runs were re-judged with the same packet.
